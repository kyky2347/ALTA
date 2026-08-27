import test from "node:test";
import assert from "node:assert/strict";
import {
  kimiToResponse,
  responseEvents,
  responsesToKimi,
} from "../translate.mjs";

test("Kimi translation preserves messages, reasoning, namespaces, and custom tools", () => {
  const input = {
    model: "kimi-k3",
    instructions: "You are ALTA v3.5.",
    reasoning: { effort: "high" },
    tools: [
      {
        type: "function",
        name: "read",
        namespace: "files",
        description: "Read",
        parameters: { type: "object" },
      },
      { type: "custom", name: "apply_patch", description: "Patch" },
    ],
    input: [
      {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: "hello" }],
      },
    ],
  };
  const { chat, identities } = responsesToKimi(input);
  assert.equal(chat.stream, false);
  assert.equal(chat.messages[0].role, "system");
  assert.equal(chat.messages[1].content, "hello");
  assert.equal(chat.reasoning_effort, "high");
  assert.equal(chat.tools.length, 2);

  const customName = [...identities.entries()].find(
    ([, identity]) => identity.kind === "custom",
  )[0];
  const response = kimiToResponse(
    {
      choices: [
        {
          message: {
            reasoning_content: "thought",
            content: "",
            tool_calls: [
              {
                id: "call-1",
                function: {
                  name: customName,
                  arguments: '{"input":"*** patch"}',
                },
              },
            ],
          },
          finish_reason: "tool_calls",
        },
      ],
      usage: { prompt_tokens: 4, completion_tokens: 3, total_tokens: 7 },
    },
    identities,
  );
  assert.equal(response.output[0].type, "reasoning");
  assert.deepEqual(response.output[1], {
    type: "custom_tool_call",
    call_id: "call-1",
    name: "apply_patch",
    input: "*** patch",
  });
  assert.equal(response.end_turn, false);
  assert.equal(responseEvents(response).at(-1).type, "response.completed");
});

test("Kimi disables thinking when a specific function is required", () => {
  const { chat } = responsesToKimi({
    model: "kimi-k3",
    reasoning: { effort: "high" },
    tools: [
      { type: "function", name: "probe", parameters: { type: "object" } },
    ],
    tool_choice: { type: "function", name: "probe" },
    input: [],
  });
  assert.deepEqual(chat.tool_choice, {
    type: "function",
    function: { name: "probe" },
  });
  assert.equal(chat.reasoning_effort, "none");
});

test("Kimi translation sends prior tool results back to the provider", () => {
  const { chat } = responsesToKimi({
    model: "kimi-k2.7-code",
    tools: [
      { type: "function", name: "lookup", parameters: { type: "object" } },
    ],
    input: [
      {
        type: "function_call",
        call_id: "c1",
        name: "lookup",
        arguments: '{"q":"x"}',
      },
      { type: "function_call_output", call_id: "c1", output: "result" },
    ],
  });
  assert.equal(chat.messages[0].tool_calls[0].id, "c1");
  assert.deepEqual(chat.messages[1], {
    role: "tool",
    tool_call_id: "c1",
    content: "result",
  });
  assert.deepEqual(chat.thinking, { type: "enabled", keep: "all" });
});

test("Kimi translation preserves portable compaction summaries", () => {
  const { chat } = responsesToKimi({
    model: "kimi-k3",
    input: [
      {
        type: "context_compaction",
        summary: [{ type: "summary_text", text: "bounded prior state" }],
        encrypted_content: "provider-private",
      },
      {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: "continue" }],
      },
    ],
  });

  assert.deepEqual(chat.messages, [
    {
      role: "user",
      content: "[Portable prior-context summary]\nbounded prior state",
    },
    { role: "user", content: "continue" },
  ]);
});

test("Kimi translation preserves image, video, and bounded file context", () => {
  const image = `data:image/png;base64,${Buffer.from("image").toString("base64")}`;
  const text = `data:text/plain;base64,${Buffer.from("abcd".repeat(100)).toString("base64")}`;
  const { chat } = responsesToKimi(
    {
      model: "kimi-k3",
      input: [
        {
          type: "message",
          role: "user",
          content: [
            { type: "input_text", text: "inspect" },
            { type: "input_image", image_url: image, detail: "high" },
            {
              type: "input_file",
              filename: "clip.mp4",
              file_url: "ms://video-id",
            },
            {
              type: "input_file",
              filename: "notes.txt",
              file_data: text,
            },
          ],
        },
      ],
    },
    { maximumTextFileBytes: 200 },
  );
  assert.deepEqual(
    chat.messages[0].content.map((part) => part.type),
    ["text", "image_url", "video_url", "text"],
  );
  assert.deepEqual(chat.messages[0].content[1], {
    type: "image_url",
    image_url: { url: image, detail: "high" },
  });
  assert.deepEqual(chat.messages[0].content[2], {
    type: "video_url",
    video_url: { url: "ms://video-id" },
  });
  assert.match(chat.messages[0].content[3].text, /abcd/);
  assert.match(chat.messages[0].content[3].text, /preview truncated/);
});
