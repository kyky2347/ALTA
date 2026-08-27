const XAI_OPENAI_COMPACTION_ITEMS = new Set([
  "compaction",
  "compaction_summary",
  "context_compaction",
  "compaction_trigger",
]);

function portableContextSummary(item) {
  const summary = Array.isArray(item?.summary)
    ? item.summary.map((part) => part?.text ?? "").join("\n")
    : typeof item?.summary === "string"
      ? item.summary
      : "";
  const text = summary || (typeof item?.text === "string" ? item.text : "");
  if (!text.trim()) return null;
  return {
    type: "message",
    role: "user",
    content: [
      {
        type: "input_text",
        text: `[Portable prior-context summary]\n${text.slice(0, 10_000)}`,
      },
    ],
  };
}

export function providerForModel(model, routes, forcedProvider) {
  if (routes.has(model)) return routes.get(model);
  if (forcedProvider) return forcedProvider;
  if (/^deepseek-/i.test(model)) return "deepseek";
  if (/^(grok-|xai-)/i.test(model)) return "xai";
  if (/^(kimi-|moonshot-)/i.test(model)) return "kimi";
  throw new Error(`Cannot determine the provider for model "${model}"`);
}

function filterUnsupportedNativeTools(value, providerName) {
  if (!Array.isArray(value.tools)) return;
  value.tools = value.tools.filter(
    (tool) =>
      tool?.type !== "custom" ||
      (providerName === "deepseek" && tool.name === "apply_patch"),
  );
}

function deleteNestedField(value, field) {
  if (!value || typeof value !== "object") return;
  if (!Array.isArray(value)) delete value[field];
  for (const nested of Object.values(value)) deleteNestedField(nested, field);
}

function removeEncryptedContent(value) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (value[index]?.type === "encrypted_content") value.splice(index, 1);
      else removeEncryptedContent(value[index]);
    }
    return;
  }
  delete value.encrypted_content;
  if (
    Array.isArray(value.encrypted_function_args) &&
    value.encrypted_function_args.length === 0
  ) {
    delete value.encrypted_function_args;
  }
  for (const [key, nested] of Object.entries(value)) {
    if (nested?.type === "encrypted_content") delete value[key];
    else removeEncryptedContent(nested);
  }
}

function normalizePortableInput(value, providerName) {
  const additionalTools = [];
  value.input = (value.input ?? []).flatMap((item) => {
    if (
      providerName === "xai" &&
      (XAI_OPENAI_COMPACTION_ITEMS.has(item?.type) ||
        item?.type === "reasoning")
    ) {
      const portable = portableContextSummary(item);
      return portable ? [portable] : [];
    }
    if (item?.type === "additional_tools") {
      additionalTools.push(...(item.tools ?? []));
      return [];
    }
    if (item?.type === "agent_message") {
      return [{ type: "message", role: "user", content: item.content ?? [] }];
    }
    return [item];
  });
  if (additionalTools.length)
    value.tools = [...(value.tools ?? []), ...additionalTools];
}

export function flattenNativeNamespaces(value) {
  const aliases = new Map();
  let index = 0;
  value.tools = (value.tools ?? []).flatMap((tool) => {
    if (tool?.type !== "namespace") return [tool];
    return (tool.tools ?? []).flatMap((child) => {
      if (child?.type !== "function" || !child.name) return [];
      const suffix = child.name.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 44);
      const name = `alta_ns_${index}_${suffix}`;
      index += 1;
      aliases.set(name, { namespace: tool.name, name: child.name });
      return [
        {
          ...child,
          name,
          description: [tool.description, child.description]
            .filter(Boolean)
            .join(" "),
        },
      ];
    });
  });
  if (value.tool_choice?.type === "function" && value.tool_choice.namespace) {
    const match = [...aliases].find(
      ([, identity]) =>
        identity.namespace === value.tool_choice.namespace &&
        identity.name === value.tool_choice.name,
    );
    if (match) {
      value.tool_choice = { ...value.tool_choice, name: match[0] };
      delete value.tool_choice.namespace;
    }
  }
  return aliases;
}

export function restoreNativeNamespaceCalls(value, aliases) {
  if (!value || typeof value !== "object") return;
  if (value.type === "function_call") {
    const normalized = String(value.name ?? "").replace(/_+/g, "_");
    const alias = aliases.has(value.name)
      ? value.name
      : [...aliases.keys()].find(
          (candidate) => candidate.replace(/_+/g, "_") === normalized,
        );
    const identity = aliases.get(alias);
    if (identity) {
      value.name = identity.name;
      value.namespace = identity.namespace;
    }
  }
  for (const nested of Object.values(value))
    restoreNativeNamespaceCalls(nested, aliases);
}

function deepSeekBody(body) {
  const value = structuredClone(body);
  value.stream = false;
  delete value.stream_options;
  normalizePortableInput(value, "deepseek");
  filterUnsupportedNativeTools(value, "deepseek");
  const effort = value.reasoning?.effort;
  if (effort === "provider-default") delete value.reasoning.effort;
  if (["medium", "xhigh"].includes(effort)) value.reasoning.effort = "high";
  if (effort === "ultra") value.reasoning.effort = "max";
  removeEncryptedContent(value);
  return value;
}

export function nativeBody(body, providerName) {
  if (providerName === "deepseek") return deepSeekBody(body);
  const value = structuredClone(body);
  value.stream = false;
  delete value.stream_options;
  if (providerName === "xai") deleteNestedField(value, "external_web_access");
  if (providerName === "xai") removeEncryptedContent(value);
  deleteNestedField(value, "search_context_size");
  if (value.reasoning?.effort === "none") delete value.reasoning;
  if (value.reasoning?.effort === "provider-default")
    delete value.reasoning.effort;
  normalizePortableInput(value, providerName);
  filterUnsupportedNativeTools(value, providerName);
  return value;
}

export function annotateDeepSeekCalls(value) {
  if (!value || typeof value !== "object") return value;
  if (
    value.type === "function_call" &&
    value.namespace === "collaboration" &&
    ["spawn_agent", "send_message", "followup_task"].includes(value.name) &&
    value.encrypted_function_args === undefined
  ) {
    value.encrypted_function_args = [];
  }
  for (const nested of Object.values(value)) annotateDeepSeekCalls(nested);
  return value;
}
