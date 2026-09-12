import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { startGateway } from "../gateway.mjs";

const wavDataUrl = () =>
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

async function mockServer(handler) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

test("gateway retries an interrupted native Responses request before emitting a stable SSE result", async () => {
  let calls = 0;
  let received;
  const upstream = await mockServer(async (req, res) => {
    calls += 1;
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (calls === 1) {
      res.destroy();
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    const input = JSON.stringify(received.input);
    res.end(
      JSON.stringify({
        id: "resp-upstream",
        status: "completed",
        output: [
          {
            type: "message",
            role: "assistant",
            id: "m1",
            content: [{ type: "output_text", text: "OK" }],
          },
        ],
        usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
      }),
    );
  });
  const previous = {
    base: process.env.ALTA_XAI_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
    retries: process.env.ALTA_MAX_RETRIES,
  };
  process.env.ALTA_XAI_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  process.env.ALTA_MAX_RETRIES = "2";
  const gateway = await startGateway({
    credentials: { xai: "xai-test-secret-that-is-long-enough" },
    routes: new Map([["grok-test", "xai"]]),
    modelCapabilities: new Map([
      ["grok-test", { inputModalities: ["text", "image", "audio"] }],
    ]),
    token: "local-token",
    settings: { maxMediaItems: 3 },
  });
  try {
    const response = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "grok-test",
        input: [
          {
            type: "message",
            role: "user",
            content: [
              {
                type: "input_image",
                image_url: "data:image/png;base64,eA==",
              },
            ],
          },
        ],
        reasoning: { effort: "none" },
        stream: true,
      }),
    });
    let retryHealth;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const health = await fetch(`${gateway.baseUrl}/health`).then((value) =>
        value.json(),
      );
      if (
        calls === 1 &&
        health.requests.retries === 1 &&
        health.capacity.global.active === 0 &&
        health.capacity.providers.xai.active === 0 &&
        health.capacity.multimodal.active === 0
      ) {
        retryHealth = health;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert(retryHealth, "retry backoff did not release every capacity lease");
    const text = await response.text();
    assert.equal(calls, 2);
    assert.deepEqual(
      {
        global: retryHealth.capacity.global.active,
        provider: retryHealth.capacity.providers.xai.active,
        multimodal: retryHealth.capacity.multimodal.active,
      },
      { global: 0, provider: 0, multimodal: 0 },
    );
    assert.equal(received.reasoning, undefined);
    assert.match(text, /upstream retry 1/);
    assert.match(text, /"type":"response\.completed"/);
    assert.match(text, /"text":"OK"/);
    assert.doesNotMatch(text, /xai-test-secret/);
    const invoke = (label, tools = []) =>
      fetch(`${gateway.baseUrl}/responses`, {
        method: "POST",
        headers: {
          "Authorization": "Bearer local-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "grok-test",
          input: [
            {
              type: "message",
              role: "user",
              content: [
                { type: "input_text", text: label },
                {
                  type: "input_image",
                  image_url: "data:image/png;base64,eA==",
                },
                ...(label === "multimodal"
                  ? [
                      {
                        type: "input_audio",
                        audio_url: wavDataUrl(),
                      },
                      {
                        type: "input_file",
                        file_url: "https://example.com/report.pdf",
                      },
                    ]
                  : []),
              ],
            },
          ],
          tools,
        }),
      }).then((value) => value.text());
    const media = await invoke("multimodal", [{ type: "image_generation" }]);
    assert.equal(calls, 3);
    assert.match(media, /"type":"response\.completed"/);
    assert.equal(received.input[0].content[1].type, "input_image");
    assert.equal(received.input[0].content[2].type, "input_audio");
    assert.equal(received.input[0].content[3].type, "input_file");
    assert.equal(received.tools[0].type, "image_generation");

    const health = await fetch(`${gateway.baseUrl}/health`).then((value) =>
      value.json(),
    );
    assert.equal(health.capacity.global.active, 0);
    assert.equal(health.capacity.providers.xai.active, 0);
    assert.equal(health.capacity.multimodal.active, 0);
    assert.equal(health.capacity.body.usedBytes, 0);
    assert.equal(health.multimodal.metrics.requests, 2);
    assert.equal(health.multimodal.metrics.imageItems, 2);
    assert.equal(health.multimodal.metrics.audioItems, 1);
    assert.equal(health.multimodal.metrics.fileItems, 1);
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_XAI_BASE_URL;
    else process.env.ALTA_XAI_BASE_URL = previous.base;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
    if (previous.retries === undefined) delete process.env.ALTA_MAX_RETRIES;
    else process.env.ALTA_MAX_RETRIES = previous.retries;
  }
});

test("gateway converts a Kimi Chat Completions response to Responses SSE", async () => {
  const received = [];
  let active = 0;
  let maximum = 0;
  let mediaActive = 0;
  let mediaMaximum = 0;
  let mediaStartedResolve;
  const mediaStarted = new Promise((resolve) => {
    mediaStartedResolve = resolve;
  });
  const upstream = await mockServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const request = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    received.push(request);
    const serialized = JSON.stringify(request.messages);
    const media = /image_url|video_url/.test(serialized);
    active += 1;
    maximum = Math.max(maximum, active);
    if (media) {
      mediaActive += 1;
      mediaMaximum = Math.max(mediaMaximum, mediaActive);
      mediaStartedResolve();
    }
    await new Promise((resolve) => setTimeout(resolve, media ? 40 : 5));
    active -= 1;
    if (media) mediaActive -= 1;
    if (serialized.includes("fail")) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: { message: "expected failure" } }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        choices: [{ message: { content: "OK" }, finish_reason: "stop" }],
        usage: { prompt_tokens: 2, completion_tokens: 1, total_tokens: 3 },
      }),
    );
  });
  const previous = {
    base: process.env.ALTA_KIMI_BASE_URL,
    deepseekBase: process.env.ALTA_DEEPSEEK_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
  };
  process.env.ALTA_KIMI_BASE_URL = upstream.baseUrl;
  process.env.ALTA_DEEPSEEK_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: {
      kimi: "sk-" + "test-secret-that-is-long-enough",
      deepseek: "sk-" + "deepseek-test-secret-that-is-long-enough",
    },
    routes: new Map([
      ["kimi-test", "kimi"],
      ["deepseek-text", "deepseek"],
    ]),
    modelCapabilities: new Map([
      ["kimi-test", { inputModalities: ["text", "image"], video: true }],
      ["deepseek-text", { inputModalities: ["text"], video: false }],
    ]),
    token: "local-token",
    settings: { multimodalConcurrency: 1, requestMemoryBytes: 2_048 },
  });
  try {
    const invoke = (content, signal) =>
      fetch(`${gateway.baseUrl}/responses`, {
        method: "POST",
        signal,
        headers: {
          "Authorization": "Bearer local-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "kimi-test",
          instructions: "system",
          input: [
            {
              type: "message",
              role: "user",
              content,
            },
          ],
          stream: true,
        }),
      }).then((response) => response.text());
    const imageContent = [
      { type: "input_text", text: "hi" },
      { type: "input_image", image_url: "data:image/png;base64,eA==" },
    ];
    const first = invoke(imageContent);
    await mediaStarted;
    const cancel = new AbortController();
    const cancelled = invoke(imageContent, cancel.signal);
    await new Promise((resolve) => setTimeout(resolve, 5));
    cancel.abort();
    await assert.rejects(cancelled);
    const output = await Promise.all([
      first,
      invoke([{ type: "input_text", text: "plain" }]),
    ]);
    assert.equal(mediaMaximum, 1);
    assert.equal(maximum, 2);
    assert.equal(received[0].stream, false);
    assert.deepEqual(
      received[0].messages.map((message) => message.role),
      ["system", "user"],
    );
    assert.equal(received[0].messages[1].content[1].type, "image_url");
    for (const text of output) {
      assert.match(text, /"type":"response\.completed"/);
      assert.match(text, /"text":"OK"/);
    }
    const video = await invoke([
      { type: "input_text", text: "video" },
      { type: "input_file", filename: "clip.mp4", file_id: "video-1" },
    ]);
    assert.match(video, /"type":"response\.completed"/);
    assert.equal(received.at(-1).messages[1].content[1].type, "video_url");
    const failure = await invoke([
      { type: "input_text", text: "fail" },
      { type: "input_image", image_url: "data:image/png;base64,eA==" },
    ]);
    assert.match(failure, /"type":"response\.failed"/);
    const unsupported = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "deepseek-text",
        input: [
          {
            type: "message",
            role: "user",
            content: [
              { type: "input_image", image_url: "https://example.com/x.png" },
            ],
          },
        ],
      }),
    });
    assert.equal(unsupported.status, 400);
    assert.equal(
      (await unsupported.json()).error.code,
      "alta_multimodal_image_unsupported",
    );
    assert.equal(received.length, 4);
    const memoryPressure = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "kimi-test",
        input: [
          {
            type: "message",
            role: "user",
            content: [
              {
                type: "input_image",
                image_url: `data:image/png;base64,${Buffer.alloc(400).toString("base64")}`,
              },
            ],
          },
        ],
      }),
    });
    assert.equal(memoryPressure.status, 503);
    assert.equal(
      (await memoryPressure.json()).error.code,
      "alta_memory_budget",
    );
    assert.equal(received.length, 4);
    await new Promise((resolve) => setTimeout(resolve, 10));
    const health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.equal(health.capacity.multimodal.active, 0);
    assert.equal(health.capacity.multimodal.queued, 0);
    assert.equal(health.capacity.global.active, 0);
    assert.equal(health.capacity.providers.kimi.active, 0);
    assert.equal(health.capacity.body.usedBytes, 0);
    assert.deepEqual(health.multimodal.metrics, {
      requests: 4,
      rejected: 2,
      imageItems: 3,
      audioItems: 0,
      fileItems: 1,
      inlineBytes: 3,
    });
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_KIMI_BASE_URL;
    else process.env.ALTA_KIMI_BASE_URL = previous.base;
    if (previous.deepseekBase === undefined)
      delete process.env.ALTA_DEEPSEEK_BASE_URL;
    else process.env.ALTA_DEEPSEEK_BASE_URL = previous.deepseekBase;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
  }
});

test("gateway flattens xAI namespace tools and restores returned call identities", async () => {
  let received;
  const upstream = await mockServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        id: "resp-xai-namespace",
        status: "completed",
        output: [
          {
            type: "function_call",
            call_id: "call-wait",
            name: received.tools[1].name.replace(
              /^alta_ns_(\d+)_/,
              "alta_ns_$1__",
            ),
            arguments: "{}",
          },
        ],
        usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
      }),
    );
  });
  const previous = {
    base: process.env.ALTA_XAI_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
  };
  process.env.ALTA_XAI_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: { xai: "xai-test-secret-that-is-long-enough" },
    routes: new Map([["grok-namespace", "xai"]]),
    token: "local-token",
  });
  try {
    const response = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "grok-namespace",
        input: [
          { type: "context_compaction", encrypted_content: "openai-blob" },
          {
            type: "reasoning",
            encrypted_content: "provider-private-blob",
            summary: [{ type: "summary_text", text: "portable summary" }],
          },
          {
            type: "message",
            role: "user",
            content: [{ type: "input_text", text: "hello" }],
          },
        ],
        external_web_access: true,
        search_context_size: "high",
        tools: [
          { type: "web_search", external_web_access: true },
          {
            type: "namespace",
            name: "collaboration",
            description: "Agent tools",
            tools: [
              {
                type: "function",
                name: "wait_agent",
                description: "Wait",
                parameters: { type: "object", properties: {} },
              },
            ],
          },
        ],
        stream: true,
      }),
    });
    const text = await response.text();
    assert.equal(received.tools.length, 2);
    assert.deepEqual(received.input, [
      {
        type: "message",
        role: "user",
        content: [
          {
            type: "input_text",
            text: "[Portable prior-context summary]\nportable summary",
          },
        ],
      },
      {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: "hello" }],
      },
    ]);
    assert.equal(received.external_web_access, undefined);
    assert.equal(received.search_context_size, undefined);
    assert.equal(received.tools[0].external_web_access, undefined);
    assert.equal(received.tools[1].type, "function");
    assert.match(received.tools[1].name, /^alta_ns_0_/);
    assert.doesNotMatch(JSON.stringify(received.tools), /"type":"namespace"/);
    assert.match(text, /"name":"wait_agent"/);
    assert.match(text, /"namespace":"collaboration"/);
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_XAI_BASE_URL;
    else process.env.ALTA_XAI_BASE_URL = previous.base;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
  }
});

test("gateway preserves DeepSeek V4 reasoning, vision, and supported tools", async () => {
  let received;
  const upstream = await mockServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        id: "resp-deepseek",
        status: "completed",
        output: [],
        usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
      }),
    );
  });
  const previous = {
    base: process.env.ALTA_DEEPSEEK_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
  };
  process.env.ALTA_DEEPSEEK_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: { deepseek: "sk-" + "test-secret-that-is-long-enough" },
    routes: new Map([["deepseek-v4-flash-vision-exp", "deepseek"]]),
    modelCapabilities: new Map([
      [
        "deepseek-v4-flash-vision-exp",
        { inputModalities: ["text", "image"], video: false },
      ],
    ]),
    token: "local-token",
  });
  try {
    const response = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "deepseek-v4-flash-vision-exp",
        input: [
          { type: "encrypted_content", encrypted_content: "opaque-root" },
          {
            type: "message",
            role: "user",
            content: [
              { type: "input_text", text: "hello" },
              {
                type: "input_image",
                image_url:
                  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                detail: "low",
              },
              { type: "encrypted_content", encrypted_content: "opaque-part" },
            ],
          },
        ],
        tools: [
          { type: "custom", name: "exec", description: "unsupported" },
          { type: "custom", name: "apply_patch", description: "Patch" },
          { type: "function", name: "probe", parameters: {} },
          {
            type: "namespace",
            name: "mcp__alta_internet",
            tools: [
              {
                type: "function",
                name: "alta_web_search",
                parameters: { type: "object", properties: {} },
              },
            ],
          },
        ],
        tool_choice: "required",
        reasoning: { effort: "none", summary: "auto" },
        stream: true,
      }),
    });
    assert.match(await response.text(), /"type":"response\.completed"/);
    assert.equal(received.tool_choice, "required");
    assert.deepEqual(received.tools[0], {
      type: "custom",
      name: "apply_patch",
      description: "Patch",
    });
    assert.deepEqual(received.tools[1], {
      type: "function",
      name: "probe",
      parameters: {},
    });
    assert.equal(received.tools[2].type, "function");
    assert.match(received.tools[2].name, /^alta_ns_0_alta_web_search/);
    assert.doesNotMatch(JSON.stringify(received.tools), /"type":"namespace"/);
    assert.deepEqual(received.reasoning, { effort: "none", summary: "auto" });
    assert.deepEqual(received.input, [
      {
        type: "message",
        role: "user",
        content: [
          { type: "input_text", text: "hello" },
          {
            type: "input_image",
            image_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
            detail: "low",
          },
        ],
      },
    ]);
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_DEEPSEEK_BASE_URL;
    else process.env.ALTA_DEEPSEEK_BASE_URL = previous.base;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
  }
});

test("gateway serves one authenticated stateless MCP internet surface", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-gateway-files-"));
  fs.writeFileSync(path.join(root, "report.txt"), "file evidence");
  const gateway = await startGateway({
    credentials: {},
    token: "internet-token",
    internet: { fileRoots: [root] },
  });
  const invoke = (body, token = "internet-token", headers = {}) =>
    fetch(`${gateway.baseUrl}/mcp`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
        ...headers,
      },
      body: JSON.stringify(body),
    });
  try {
    const rejected = await invoke(
      { jsonrpc: "2.0", id: 0, method: "tools/list" },
      "wrong",
    );
    assert.equal(rejected.status, 401);

    const discovery = await invoke({
      jsonrpc: "2.0",
      id: 1,
      method: "server/discover",
    }).then((response) => response.json());
    assert.deepEqual(discovery.result.supportedVersions, ["2026-07-28"]);

    const listed = await invoke({
      jsonrpc: "2.0",
      id: 2,
      method: "tools/list",
    }).then((response) => response.json());
    assert.deepEqual(
      listed.result.tools.map((tool) => tool.name),
      [
        "alta_web_search",
        "alta_web_fetch",
        "alta_web_crawl",
        "alta_web_research",
        "alta_web_batch_fetch",
        "alta_web_sitemap",
        "alta_web_feed",
        "alta_web_archive",
        "alta_academic_search",
        "alta_social_search",
        "alta_social_read",
        "alta_news_search",
        "alta_finance_data",
        "alta_tradingview_navigate",
        "alta_file_read",
      ],
    );
    assert.deepEqual(
      listed.result.tools.find(
        (tool) => tool.name === "alta_tradingview_navigate",
      ).annotations,
      {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    );

    const navigation = await invoke({
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: {
        name: "alta_tradingview_navigate",
        arguments: {
          action: "bundle",
          symbol: "NASDAQ:AAPL",
          interval: "60",
        },
      },
    }).then((response) => response.json());
    assert.deepEqual(navigation.result.structuredContent, {
      source: "tradingview",
      mode: "display_only_navigation",
      action: "bundle",
      base_url: "https://www.tradingview.com/symbols/NASDAQ-AAPL/",
      chart_url:
        "https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL&interval=60",
      pages: {
        overview: "",
        technicals: "technicals/",
        financials: "financials-overview/",
        forecast: "forecast/",
        news: "news/",
      },
      machine_data_tools: ["alta_finance_data", "alta_news_search"],
      notice: "Open manually; do not pass TradingView URLs to ALTA readers.",
    });

    const file = await invoke({
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: { name: "alta_file_read", arguments: { path: "report.txt" } },
    }).then((response) => response.json());
    assert.equal(file.result.structuredContent.content, "file evidence");

    const budgetHeaders = {
      "X-ALTA-Run-ID": `run_${"a".repeat(32)}`,
      "X-ALTA-Max-Tool-Calls": "2",
    };
    const firstBudgeted = await invoke(
      {
        jsonrpc: "2.0",
        id: 5,
        method: "tools/call",
        params: { name: "alta_file_read", arguments: { path: "report.txt" } },
      },
      "internet-token",
      budgetHeaders,
    ).then((response) => response.json());
    assert.match(
      firstBudgeted.result.content[0].text,
      /1 of 2 tool calls remain/,
    );
    const finalBudgeted = await invoke(
      {
        jsonrpc: "2.0",
        id: 6,
        method: "tools/call",
        params: { name: "alta_file_read", arguments: { path: "report.txt" } },
      },
      "internet-token",
      budgetHeaders,
    ).then((response) => response.json());
    assert.match(finalBudgeted.result.content[0].text, /finalize now/);
    const exhausted = await invoke(
      {
        jsonrpc: "2.0",
        id: 7,
        method: "tools/call",
        params: { name: "alta_file_read", arguments: { path: "report.txt" } },
      },
      "internet-token",
      budgetHeaders,
    );
    assert.equal(exhausted.status, 429);
    assert.match(await exhausted.text(), /tool call budget exhausted/);
    const retry = await invoke(
      {
        jsonrpc: "2.0",
        id: 8,
        method: "tools/call",
        params: { name: "alta_file_read", arguments: { path: "report.txt" } },
      },
      "internet-token",
      { ...budgetHeaders, "X-ALTA-Attempt-ID": "b".repeat(64) },
    ).then((response) => response.json());
    assert.match(retry.result.content[0].text, /1 of 2 tool calls remain/);
  } finally {
    await gateway.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("gateway marks permanent provider errors as non-retryable Responses failures", async () => {
  let calls = 0;
  const upstream = await mockServer(async (req, res) => {
    calls += 1;
    for await (const _chunk of req) {
      /* consume */
    }
    await new Promise((resolve) => setTimeout(resolve, 15));
    res.writeHead(422, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "unsupported request" }));
  });
  const previous = {
    base: process.env.ALTA_XAI_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
  };
  process.env.ALTA_XAI_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: { xai: "xai-test-secret-that-is-long-enough" },
    routes: new Map([["grok-permanent-error", "xai"]]),
    token: "local-token",
    settings: { maxRetries: 5 },
  });
  try {
    const response = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer local-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "grok-permanent-error",
        input: [],
        stream: true,
      }),
    });
    const text = await response.text();
    assert.equal(calls, 1);
    assert.match(text, /"type":"response\.failed"/);
    assert.match(text, /"code":"invalid_prompt"/);
    assert.match(text, /Provider HTTP 422/);
    const health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.equal(health.latency.xai.samples, 1);
    assert.equal(health.latency.xai.failures, 1);
    assert.ok(health.latency.xai.upstreamMsEwma >= 10);
    assert.ok(
      health.latency.xai.totalMsEwma >= health.latency.xai.upstreamMsEwma,
    );
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_XAI_BASE_URL;
    else process.env.ALTA_XAI_BASE_URL = previous.base;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
  }
});

test("gateway keeps a multi-agent soak inside provider concurrency and memory bounds", async () => {
  let calls = 0;
  let active = 0;
  let maximum = 0;
  const upstream = await mockServer(async (req, res) => {
    for await (const _chunk of req) {
      /* consume */
    }
    calls += 1;
    if (calls === 1) {
      res.writeHead(429, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "slow down" }));
      return;
    }
    active += 1;
    maximum = Math.max(maximum, active);
    await new Promise((resolve) => setTimeout(resolve, 10));
    active -= 1;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        id: "resp-soak",
        status: "completed",
        output: [
          {
            type: "message",
            role: "assistant",
            id: "m-soak",
            content: [{ type: "output_text", text: "OK" }],
          },
        ],
        usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
      }),
    );
  });
  const previous = {
    base: process.env.ALTA_XAI_BASE_URL,
    insecure: process.env.ALTA_ALLOW_INSECURE_LOOPBACK,
  };
  process.env.ALTA_XAI_BASE_URL = upstream.baseUrl;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: { xai: "xai-test-secret-that-is-long-enough" },
    routes: new Map([["grok-soak", "xai"]]),
    token: "local-token",
    settings: {
      maxRetries: 1,
      maxConcurrentRequests: 6,
      maxQueuedRequests: 256,
      queueTimeoutMs: 10_000,
      providerConcurrency: { xai: 3 },
      requestMemoryBytes: 4 * 1024 * 1024,
      maxRssBytes: 1024 * 1024 * 1024,
    },
  });
  try {
    const invoke = () =>
      fetch(`${gateway.baseUrl}/responses`, {
        method: "POST",
        headers: {
          "Authorization": "Bearer local-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ model: "grok-soak", input: [], stream: true }),
      }).then((response) => response.text());
    const completed = (value) => value.includes('"type":"response.completed"');

    assert.ok(completed(await invoke()));
    let health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.deepEqual(health.adaptiveConcurrency.xai, {
      configuredLimit: 3,
      currentLimit: 2,
      recoveryProgress: 1,
      reductions: 1,
    });

    maximum = 0;
    const constrained = await Promise.all(
      Array.from({ length: 8 }, () => invoke()),
    );
    assert.equal(maximum, 2);
    assert.equal(constrained.filter(completed).length, 8);
    health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.equal(health.adaptiveConcurrency.xai.currentLimit, 2);

    for (let index = 0; index < 7; index += 1)
      assert.ok(completed(await invoke()));
    health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.equal(health.adaptiveConcurrency.xai.currentLimit, 3);

    maximum = 0;
    const responses = await Promise.all(
      Array.from({ length: 104 }, () => invoke()),
    );
    assert.equal(maximum, 3);
    assert.equal(responses.filter(completed).length, 104);
    health = await fetch(`${gateway.baseUrl}/health`).then((response) =>
      response.json(),
    );
    assert.equal(health.requests.completed, 120);
    assert.equal(health.capacity.global.active, 0);
    assert.equal(health.capacity.providers.xai.active, 0);
    assert.equal(health.capacity.body.usedBytes, 0);
    assert.deepEqual(health.adaptiveConcurrency.xai, {
      configuredLimit: 3,
      currentLimit: 3,
      recoveryProgress: 0,
      reductions: 1,
    });
    assert.deepEqual(health.adaptiveConcurrency.kimi, {
      configuredLimit: 8,
      currentLimit: 8,
      recoveryProgress: 0,
      reductions: 0,
    });
    assert.equal(health.latency.xai.samples, 120);
    assert.equal(health.latency.xai.failures, 0);
    assert.ok(health.latency.xai.queueMsEwma > 0);
    assert.ok(health.latency.xai.upstreamMsEwma > 0);
    assert.ok(
      health.latency.xai.totalMsEwma + 2 >=
        health.latency.xai.queueMsEwma + health.latency.xai.upstreamMsEwma,
    );
    assert.deepEqual(health.output, { listeners: 0, timerActive: false });
  } finally {
    await gateway.close();
    await upstream.close();
    if (previous.base === undefined) delete process.env.ALTA_XAI_BASE_URL;
    else process.env.ALTA_XAI_BASE_URL = previous.base;
    if (previous.insecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previous.insecure;
  }
});
