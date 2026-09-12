import test from "node:test";
import assert from "node:assert/strict";
import { boundedToolPreview } from "../internet/result-preview.mjs";
import { textWindow } from "../internet/text-window.mjs";
import { handleMcpMessage } from "../internet/mcp.mjs";
import {
  internetToolDefinitions,
  executeInternetTool,
} from "../internet/plugins/registry.mjs";
import { InternetService } from "../internet/service.mjs";
import { BackendHealth } from "../internet/backend-health.mjs";
import { executeSearch, normalizeSearch } from "../internet/search.mjs";

test("large structured results keep their trailing citation and valid JSON", () => {
  const url = "https://example.test/metric?symbol=EXM";
  const result = boundedToolPreview(
    {
      records: [{ text: "長文".repeat(50_000) }],
      provenance: { source_url: url },
    },
    8_500,
  );
  assert.equal(result.truncated, true);
  assert.equal(result.value.provenance.source_url, url);
  assert.deepEqual(JSON.parse(result.text), result.value);
  assert(Buffer.byteLength(result.text) <= 8_500);
  assert(!result.text.includes("\ufffd"));
});

test("bounded previews preserve independent page identities and numerical types", () => {
  const result = boundedToolPreview(
    {
      pages: Array.from({ length: 6 }, (_, i) => ({
        url: `https://source${i}.test/doc`,
        text: "content ".repeat(3_000),
        value: 123.45,
      })),
    },
    8_500,
  );
  assert.equal(result.value.pages.length, 6);
  assert.equal(result.value.pages[5].url, "https://source5.test/doc");
  assert.equal(result.value.pages[5].value, 123.45);
});

test("Finnhub metrics no longer stream historical series or lose provenance", async () => {
  const service = {
    finnhubKey: "fixture-key",
    recordTool() {},
    readText: async () => ({
      text: JSON.stringify({
        symbol: "EXM",
        metric: { peTTM: 23 },
        series: {
          annual: Array.from({ length: 10_000 }, () => ({
            v: 123,
            p: "2025-01-01",
          })),
        },
      }),
    }),
  };
  const { result } = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {
      name: "alta_finance_data",
      arguments: {
        source: "finnhub",
        dataset: "metrics",
        symbol: "EXM",
        max_records: 1,
      },
    },
  });
  assert.equal(result.structuredContent.records[0].metric.peTTM, 23);
  assert.equal(result.structuredContent.records[0].series, undefined);
  assert.match(result.structuredContent.provenance.source_url, /finnhub.io/);
  assert(!JSON.stringify(result).includes("fixture-key"));
});

test("long filing excerpts locate literal sections without changing source text", () => {
  const source =
    "Cover page ".repeat(4_000) +
    "Revenue increased by 12 percent. " +
    "More disclosure ".repeat(400);
  const result = textWindow(source, {
    limit: 2_000,
    focus: "Revenue increased",
  });
  assert.equal(result.focus_matched, true);
  assert(result.text_start > 40_000);
  assert.equal(result.text, source.slice(result.text_start, result.text_end));
  assert.equal(result.truncated, true);
  assert.equal(
    textWindow(source, { limit: 2_000, focus: "missing phrase" }).focus_matched,
    false,
  );
  assert.throws(
    () => textWindow(source, { limit: 2_000, offset: -1 }),
    /offset/,
  );
});

test("fetch cache isolates excerpts and returns verifiable extraction offsets", async () => {
  const body =
    "cover ".repeat(5_000) + "Revenue increased. " + "details ".repeat(1_000);
  const service = new InternetService({
    lookup: async () => [{ address: "93.184.216.34", family: 4 }],
    fetchImpl: async () =>
      new Response(body, { headers: { "Content-Type": "text/plain" } }),
  });
  try {
    const plain = await service.fetchPage({
      url: "https://example.test/filing",
      max_chars: 1_000,
    });
    const focused = await service.fetchPage({
      url: "https://example.test/filing",
      max_chars: 1_000,
      focus: "Revenue increased",
    });
    assert(!plain.text.includes("Revenue"));
    assert(focused.text.includes("Revenue"));
    assert(focused.text_start > 20_000);
    const next = await service.fetchPage({
      url: "https://example.test/filing",
      max_chars: 1_000,
      offset: focused.text_end,
    });
    assert.equal(next.text_start, focused.text_end);
  } finally {
    await service.close();
  }
});

test("tool catalog does not advertise missing search credentials or mutate global definitions", () => {
  const search = (service) =>
    internetToolDefinitions(service).find((t) => t.name === "alta_web_search")
      .inputSchema.properties.backend.enum;
  assert(!search({}).includes("brave"));
  assert(!search({}).includes("xai"));
  assert(search({ xaiSearch: () => {} }).includes("xai"));
  assert(search(undefined).includes("brave"));
});

test("successful searches with no domain-matching hits do not trip an outage circuit", async () => {
  const health = new BackendHealth({ failureThreshold: 1 });
  const context = {
    xaiSearch: async () => ({
      output: [
        {
          type: "message",
          content: [
            {
              type: "output_text",
              text: "Located https://unrelated.test/page",
            },
          ],
        },
      ],
    }),
    backendHealth: health,
  };
  const args = normalizeSearch(
    {
      query: "issuer disclosure",
      backend: "xai",
      allowed_domains: ["issuer.test"],
    },
    {},
  );
  for (let i = 0; i < 3; i++) {
    const result = await executeSearch(context, args);
    assert.deepEqual(result.results, []);
    assert.equal(result.answer, "");
  }
  assert.equal(health.snapshot().xai?.opens ?? 0, 0);
});

test("matching only a year or month cannot qualify a deep-research source", async () => {
  const fetched = [];
  const service = {
    search: async () => ({
      backend: "fixture",
      results: [
        {
          url: "https://calendar.test/2026",
          title: "September 2026 facts",
          snippets: [],
        },
        {
          url: "https://issuer.test/earnings",
          title: "IssuerX revenue update",
          snippets: [],
        },
      ],
    }),
    fetchPage: async ({ url }) => {
      fetched.push(url);
      return { url, text: "Source excerpt" };
    },
    recordTool() {},
  };
  await executeInternetTool(
    service,
    "alta_web_research",
    { queries: ["IssuerX September 2026 revenue"], max_pages: 2 },
    {},
  );
  assert.deepEqual(fetched, ["https://issuer.test/earnings"]);
});
