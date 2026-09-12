import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { startGateway } from "../gateway.mjs";
import {
  flattenNativeNamespaces,
  nativeBody,
} from "../gateway-native-request.mjs";
import { restoreDeclaredToolCalls } from "../gateway-tool-identities.mjs";

const fn = (name) => ({ type: "function", name, parameters: {} });
const namespace = (name, ...tools) => ({ type: "namespace", name, tools });
const call = (name, scope) => ({
  type: "function_call",
  name,
  ...(scope === undefined ? {} : { namespace: scope }),
  call_id: "call-test",
  arguments: '{"url":"https://issuer.example/filing","max_chars":4000}',
});

test("exact declared flat and namespace identities are preserved", () => {
  const output = [
    call("mcp__alta_internet__alta_web_fetch"),
    call("alta_web_search", "mcp__alta_internet"),
    call("local_function"),
  ];
  const expected = structuredClone(output);
  restoreDeclaredToolCalls({ output }, [
    fn("mcp__alta_internet__alta_web_fetch"),
    namespace("mcp__alta_internet", fn("alta_web_search")),
    fn("local_function"),
  ]);
  assert.deepEqual(output, expected);
});

test("split-qualified and unique bare MCP calls resolve only to declared flat names", () => {
  const output = [
    call("alta_web_fetch", "mcp__alta_internet"),
    call("alta_web_fetch"),
  ];
  const argumentsBefore = output.map((item) => item.arguments);
  restoreDeclaredToolCalls({ output }, [
    fn("mcp__alta_internet__alta_web_fetch"),
  ]);
  assert.deepEqual(
    output.map((item) => [item.namespace, item.name]),
    [
      [undefined, "mcp__alta_internet__alta_web_fetch"],
      [undefined, "mcp__alta_internet__alta_web_fetch"],
    ],
  );
  assert.deepEqual(
    output.map((item) => item.arguments),
    argumentsBefore,
  );
  assert.ok(output.every((item) => item.call_id === "call-test"));
});

test("qualified and bare calls can resolve to the originally declared namespace", () => {
  const output = [
    call("mcp__alta_internet__alta_web_fetch"),
    call("alta_web_fetch"),
  ];
  restoreDeclaredToolCalls({ response: { output } }, [
    namespace("mcp__alta_internet", fn("alta_web_fetch")),
  ]);
  for (const item of output) {
    assert.equal(item.name, "alta_web_fetch");
    assert.equal(item.namespace, "mcp__alta_internet");
  }
});

test("literal namespace::name calls resolve exactly, with foreign and ambiguous forms rejected", () => {
  const output = [
    call("mcp__alta_internet::alta_web_crawl"),
    call("mcp__alta_internet::alta_web_fetch"),
    call("mcp__foreign::alta_web_crawl"),
    call("mcp__alta_internet::alta_web_crawl::extra"),
    call("::alta_web_crawl"),
    call("mcp__alta_internet::"),
    call("mcp__alta_internet::ambiguous"),
  ];
  const expectedUnchanged = structuredClone(output.slice(2));
  restoreDeclaredToolCalls({ output }, [
    fn("mcp__alta_internet__alta_web_crawl"),
    namespace("mcp__alta_internet", fn("alta_web_fetch"), fn("ambiguous")),
    fn("mcp__alta_internet__ambiguous"),
  ]);
  assert.equal(output[0].name, "mcp__alta_internet__alta_web_crawl");
  assert.equal(output[0].namespace, undefined);
  assert.equal(output[1].name, "alta_web_fetch");
  assert.equal(output[1].namespace, "mcp__alta_internet");
  assert.deepEqual(output.slice(2), expectedUnchanged);
  assert.equal(output[0].arguments, call("original").arguments);
});

test("unknown, foreign, ambiguous and non-function identities are not repaired", () => {
  const output = [
    call("missing"),
    call("fetch", "mcp__foreign"),
    call("fetch"),
    call("write"),
    call("shell", "mcp__foreign"),
    call("shell", { invalid: true }),
  ];
  const expected = structuredClone(output);
  restoreDeclaredToolCalls({ output }, [
    fn("mcp__first__fetch"),
    fn("mcp__second__fetch"),
    namespace("mcp__first", { type: "custom", name: "write" }),
    fn("shell"),
  ]);
  assert.deepEqual(output, expected);
});

test("only top-level output function calls change, never arguments or nested user content", () => {
  const nested = call("alta_web_fetch", "mcp__alta_internet");
  const output = [
    { type: "message", role: "assistant", content: [nested] },
    {
      ...call("alta_web_fetch", "mcp__alta_internet"),
      arguments: { nested },
      metadata: { nested },
    },
  ];
  const nestedBefore = structuredClone(nested);
  restoreDeclaredToolCalls({ output, arbitrary: nested }, [
    fn("mcp__alta_internet__alta_web_fetch"),
  ]);
  assert.deepEqual(nested, nestedBefore);
  assert.equal(output[1].name, "mcp__alta_internet__alta_web_fetch");
  assert.equal(output[1].arguments.nested, nested);
  assert.equal(output[1].metadata.nested, nested);
});

test("request normalization preserves additional tools and restores only authorized aliases", () => {
  const upstream = nativeBody(
    {
      input: [
        {
          type: "additional_tools",
          tools: [namespace("mcp__alta_internet", fn("alta_web_fetch"))],
        },
      ],
      tools: [fn("mcp__alta_internet__alta_web_search")],
    },
    "deepseek",
  );
  const declared = upstream.tools;
  const aliases = flattenNativeNamespaces(upstream);
  const alias = [...aliases.keys()][0];
  const output = [
    call(alias.replace(/^(alta_ns_\d+)_/, "$1__")),
    call("alta_web_search", "mcp__alta_internet"),
    call(alias, "mcp__foreign"),
  ];
  restoreDeclaredToolCalls({ output }, declared, aliases);
  assert.equal(output[0].name, "alta_web_fetch");
  assert.equal(output[0].namespace, "mcp__alta_internet");
  assert.equal(output[1].name, "mcp__alta_internet__alta_web_search");
  assert.equal(output[1].namespace, undefined);
  assert.equal(output[2].name, alias);
  assert.equal(output[2].namespace, "mcp__foreign");
  assert.equal(declared[1].type, "namespace");
});

test("colliding aliases do not authorize an arbitrary matching function", () => {
  const output = [call("alta_ns__0_fetch")];
  restoreDeclaredToolCalls(
    { output },
    [namespace("one", fn("fetch")), namespace("two", fn("fetch"))],
    new Map([
      ["alta_ns_0_fetch", { namespace: "one", name: "fetch" }],
      ["alta_ns__0_fetch", { namespace: "two", name: "fetch" }],
    ]),
  );
  assert.equal(output[0].name, "alta_ns__0_fetch");
  assert.equal(output[0].namespace, undefined);
});

test("native gateway sends corrected flat MCP identities through Responses SSE", async (t) => {
  const previousBase = process.env.ALTA_DEEPSEEK_BASE_URL;
  const previousInsecure = process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
  t.after(() => {
    if (previousBase === undefined) delete process.env.ALTA_DEEPSEEK_BASE_URL;
    else process.env.ALTA_DEEPSEEK_BASE_URL = previousBase;
    if (previousInsecure === undefined)
      delete process.env.ALTA_ALLOW_INSECURE_LOOPBACK;
    else process.env.ALTA_ALLOW_INSECURE_LOOPBACK = previousInsecure;
  });
  let received;
  const upstream = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        id: "resp-test",
        output: [call("alta_web_fetch", "mcp__alta_internet")],
      }),
    );
  });
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => upstream.close(resolve)));
  process.env.ALTA_DEEPSEEK_BASE_URL = `http://127.0.0.1:${upstream.address().port}`;
  process.env.ALTA_ALLOW_INSECURE_LOOPBACK = "1";
  const gateway = await startGateway({
    credentials: { deepseek: "test-only-provider-fixture" },
    routes: new Map([["deepseek-test", "deepseek"]]),
    token: "test-only-local-token",
  });
  t.after(() => gateway.close());
  const response = await fetch(`${gateway.baseUrl}/responses`, {
    method: "POST",
    headers: {
      "Authorization": "Bearer test-only-local-token",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "deepseek-test",
      input: [],
      tools: [fn("mcp__alta_internet__alta_web_fetch")],
    }),
  });
  const text = await response.text();
  assert.equal(response.status, 200);
  assert.equal(received.tools[0].name, "mcp__alta_internet__alta_web_fetch");
  assert.match(text, /"name":"mcp__alta_internet__alta_web_fetch"/);
  assert.doesNotMatch(text, /"namespace":"mcp__alta_internet"/);
  assert.match(text, /"type":"response.completed"/);
});
