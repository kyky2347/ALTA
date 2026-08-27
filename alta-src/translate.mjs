import { randomUUID } from "node:crypto";
import { kimiContentPart } from "./multimodal.mjs";

const COMPACTION_ITEMS = new Set([
  "compaction",
  "compaction_summary",
  "context_compaction",
  "compaction_trigger",
]);

function textOf(value) {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return JSON.stringify(value ?? "");
  return value
    .map((part) => part?.text ?? part?.output_text ?? String(part ?? ""))
    .join("\n");
}

function contentToChat(content, maximumTextFileBytes) {
  const parts = [];
  for (const item of content ?? []) {
    if (["input_text", "output_text"].includes(item?.type)) {
      parts.push({ type: "text", text: item.text ?? "" });
    } else if (["input_image", "input_file"].includes(item?.type)) {
      const part = kimiContentPart(item, maximumTextFileBytes);
      if (part) parts.push(part);
    }
  }
  return parts.every((part) => part.type === "text")
    ? parts.map((part) => part.text).join("\n")
    : parts;
}

function identityKey(identity) {
  return `${identity.kind}\0${identity.namespace ?? ""}\0${identity.name}`;
}

function safeToolName(identity, byName, byIdentity) {
  const key = identityKey(identity);
  if (byIdentity.has(key)) return byIdentity.get(key);
  const base =
    identity.name.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 48) || "tool";
  const namespace = (identity.namespace ?? identity.kind).replace(
    /[^A-Za-z0-9_-]/g,
    "_",
  );
  let name = base;
  for (let suffix = 2; byName.has(name); suffix += 1) {
    name = `${namespace}__${base}_${suffix}`.slice(0, 64);
  }
  byName.set(name, identity);
  byIdentity.set(key, name);
  return name;
}

function registerTool(tool, byName, byIdentity, namespace = null) {
  if (!tool || typeof tool !== "object") return [];
  if (tool.type === "namespace") {
    return (tool.tools ?? []).flatMap((child) =>
      registerTool(child, byName, byIdentity, tool.name),
    );
  }
  if (!["function", "custom"].includes(tool.type) || !tool.name) return [];
  const identity = { kind: tool.type, namespace, name: tool.name };
  const name = safeToolName(identity, byName, byIdentity);
  const parameters =
    tool.type === "custom"
      ? {
          type: "object",
          properties: {
            input: { type: "string", description: "Raw free-form tool input" },
          },
          required: ["input"],
          additionalProperties: false,
        }
      : (tool.parameters ?? { type: "object", properties: {} });
  return [
    {
      type: "function",
      function: {
        name,
        ...(tool.description ? { description: tool.description } : {}),
        parameters,
        ...(tool.strict === true ? { strict: true } : {}),
      },
    },
  ];
}

function chatToolChoice(choice, byName, byIdentity) {
  if (typeof choice === "string") return choice;
  if (choice?.type !== "function" || !choice.name) return undefined;
  const name = safeToolName(
    {
      kind: "function",
      namespace: choice.namespace ?? null,
      name: choice.name,
    },
    byName,
    byIdentity,
  );
  return { type: "function", function: { name } };
}

function pushToolCall(messages, toolCall, reasoning) {
  const previous = messages.at(-1);
  if (previous?.role === "assistant") {
    previous.tool_calls ??= [];
    previous.tool_calls.push(toolCall);
    if (reasoning && !previous.reasoning_content)
      previous.reasoning_content = reasoning;
  } else {
    messages.push({
      role: "assistant",
      content: null,
      ...(reasoning ? { reasoning_content: reasoning } : {}),
      tool_calls: [toolCall],
    });
  }
}

function reasoningText(item) {
  const raw = (item?.content ?? [])
    .filter((part) => part?.type === "reasoning_text")
    .map((part) => part.text ?? "")
    .join("");
  return raw || (item?.summary ?? []).map((part) => part?.text ?? "").join("");
}

function configureKimiReasoning(chat, effort) {
  if (chat.model === "kimi-k3") {
    if (!effort || effort === "provider-default") return;
    chat.reasoning_effort = ["xhigh", "ultra"].includes(effort)
      ? "max"
      : effort;
  } else if (/kimi-k2\.7-code/.test(chat.model)) {
    chat.thinking =
      effort === "none"
        ? { type: "disabled" }
        : { type: "enabled", keep: "all" };
  } else if (chat.model === "kimi-k2.6") {
    chat.thinking =
      effort === "none"
        ? { type: "disabled" }
        : { type: "enabled", keep: "all" };
  }
}

export function responsesToKimi(body, { maximumTextFileBytes = 900 } = {}) {
  const messages = [];
  const byName = new Map();
  const byIdentity = new Map();
  const responseTools = [...(body.tools ?? [])];
  for (const item of body.input ?? []) {
    if (item?.type === "additional_tools")
      responseTools.push(...(item.tools ?? []));
  }
  const tools = responseTools.flatMap((tool) =>
    registerTool(tool, byName, byIdentity),
  );
  if (body.instructions)
    messages.push({ role: "system", content: body.instructions });

  let pendingReasoning = "";
  for (const item of body.input ?? []) {
    if (item?.type === "message") {
      const role = item.role === "developer" ? "system" : item.role;
      messages.push({
        role: ["system", "user", "assistant"].includes(role) ? role : "user",
        content: contentToChat(item.content, maximumTextFileBytes),
        ...(role === "assistant" && pendingReasoning
          ? { reasoning_content: pendingReasoning }
          : {}),
      });
      if (role === "assistant") pendingReasoning = "";
    } else if (item?.type === "reasoning") {
      pendingReasoning += reasoningText(item);
    } else if (COMPACTION_ITEMS.has(item?.type)) {
      const summary = reasoningText(item);
      if (summary)
        messages.push({
          role: "user",
          content: `[Portable prior-context summary]\n${summary.slice(0, 10_000)}`,
        });
    } else if (["function_call", "custom_tool_call"].includes(item?.type)) {
      const kind = item.type === "custom_tool_call" ? "custom" : "function";
      const identity = {
        kind,
        namespace: item.namespace ?? null,
        name: item.name,
      };
      const name = safeToolName(identity, byName, byIdentity);
      const argumentsText =
        kind === "custom"
          ? JSON.stringify({ input: item.input ?? "" })
          : (item.arguments ?? "{}");
      pushToolCall(
        messages,
        {
          id: item.call_id ?? item.id ?? `call_${randomUUID()}`,
          type: "function",
          function: { name, arguments: argumentsText },
        },
        pendingReasoning,
      );
      pendingReasoning = "";
    } else if (
      [
        "function_call_output",
        "custom_tool_call_output",
        "tool_search_output",
      ].includes(item?.type)
    ) {
      messages.push({
        role: "tool",
        tool_call_id: item.call_id,
        content:
          item.type === "tool_search_output"
            ? JSON.stringify(item.tools ?? [])
            : textOf(item.output),
      });
    } else if (item?.type === "agent_message") {
      messages.push({
        role: "user",
        content: `[Agent message]\n${textOf(item.content)}`,
      });
    }
  }

  const chat = {
    model: body.model,
    messages,
    stream: false,
    ...(tools.length
      ? { tools, parallel_tool_calls: body.parallel_tool_calls !== false }
      : {}),
    ...(body.max_output_tokens ? { max_tokens: body.max_output_tokens } : {}),
  };
  if (tools.length) {
    const toolChoice = chatToolChoice(body.tool_choice, byName, byIdentity);
    if (toolChoice) chat.tool_choice = toolChoice;
  }
  configureKimiReasoning(chat, body.reasoning?.effort);
  if (typeof chat.tool_choice === "object") {
    if (chat.model === "kimi-k3") chat.reasoning_effort = "none";
    else chat.thinking = { type: "disabled" };
  }
  if (body.text?.format?.schema) {
    chat.response_format = {
      type: "json_schema",
      json_schema: {
        name: body.text.format.name ?? "alta_output",
        strict: body.text.format.strict === true,
        schema: body.text.format.schema,
      },
    };
  }
  return { chat, identities: byName };
}

function parseCustomInput(value) {
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed?.input === "string") return parsed.input;
  } catch {
    // A model may return raw free-form content despite the generated schema.
  }
  return value;
}

export function responseUsage(usage = {}) {
  const input = Number(usage.prompt_tokens ?? usage.input_tokens ?? 0);
  const output = Number(usage.completion_tokens ?? usage.output_tokens ?? 0);
  const reasoning = Number(
    usage.completion_tokens_details?.reasoning_tokens ??
      usage.reasoning_tokens ??
      0,
  );
  return {
    input_tokens: input,
    input_tokens_details: {
      cached_tokens: Number(
        usage.prompt_cache_hit_tokens ??
          usage.input_tokens_details?.cached_tokens ??
          0,
      ),
    },
    output_tokens: output,
    output_tokens_details: { reasoning_tokens: reasoning },
    total_tokens: Number(usage.total_tokens ?? input + output),
  };
}

export function kimiToResponse(data, identities = new Map()) {
  const message = data?.choices?.[0]?.message ?? {};
  const output = [];
  if (message.reasoning_content) {
    output.push({
      type: "reasoning",
      id: `rs_alta_${randomUUID()}`,
      summary: [
        { type: "summary_text", text: textOf(message.reasoning_content) },
      ],
      encrypted_content: null,
    });
  }
  const content = textOf(message.content);
  if (content) {
    output.push({
      type: "message",
      role: "assistant",
      id: `msg_alta_${randomUUID()}`,
      content: [{ type: "output_text", text: content }],
    });
  }
  for (const call of message.tool_calls ?? []) {
    const fn = call.function ?? {};
    const identity = identities.get(fn.name) ?? {
      kind: "function",
      name: fn.name,
    };
    output.push(
      identity.kind === "custom"
        ? {
            type: "custom_tool_call",
            call_id: call.id ?? `call_${randomUUID()}`,
            name: identity.name,
            ...(identity.namespace ? { namespace: identity.namespace } : {}),
            input: parseCustomInput(fn.arguments ?? ""),
          }
        : {
            type: "function_call",
            call_id: call.id ?? `call_${randomUUID()}`,
            name: identity.name,
            ...(identity.namespace ? { namespace: identity.namespace } : {}),
            arguments: fn.arguments ?? "{}",
          },
    );
  }
  return {
    id: `resp_alta_${randomUUID()}`,
    object: "response",
    status: "completed",
    output,
    usage: responseUsage(data.usage),
    end_turn: data?.choices?.[0]?.finish_reason !== "tool_calls",
  };
}

export function normalizeNativeResponse(value) {
  const response = value?.response ?? value;
  if (
    !response ||
    typeof response !== "object" ||
    !Array.isArray(response.output)
  ) {
    throw new Error("Provider returned an invalid Responses API payload");
  }
  response.id ??= `resp_alta_${randomUUID()}`;
  response.status ??= "completed";
  return response;
}

export function responseEvents(response) {
  const created = { ...response, status: "in_progress", output: [] };
  return [
    { type: "response.created", response: created },
    ...(response.output ?? []).map((item) => ({
      type: "response.output_item.done",
      item,
    })),
    { type: "response.completed", response },
  ];
}
