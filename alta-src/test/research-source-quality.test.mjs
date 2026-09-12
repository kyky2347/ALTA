import test from "node:test";
import assert from "node:assert/strict";
import {
  executeInternetTool,
  internetToolDefinitions,
} from "../internet/plugins/registry.mjs";
import { boundedToolPreview } from "../internet/result-preview.mjs";

const finance = (value, captured = []) => ({
  finnhubKey: "fixture-credential",
  readText: async (request) => {
    captured.push(request);
    return { text: JSON.stringify(value), cached: true, stale: true };
  },
});
const callFinance = (service, dataset, extra = {}) =>
  executeInternetTool(
    service,
    "alta_finance_data",
    { source: "finnhub", symbol: "EXM", dataset, ...extra },
    {},
  );

test("company identity yields an issuer locator without asserting retrieved proof", async () => {
  const requests = [];
  const result = await callFinance(
    finance(
      {
        name: "Example Corp",
        ticker: "EXM",
        weburl: "https://issuer.test/",
        shareOutstanding: 15.4,
        ignored: "do not copy",
      },
      requests,
    ),
    "company_profile",
  );
  assert.equal(new URL(requests[0].url).pathname, "/api/v1/stock/profile2");
  assert.equal(result.records[0].weburl, "https://issuer.test/");
  assert.equal(result.records[0].shareOutstanding, 15.4);
  assert.equal(result.records[0].ignored, undefined);
  assert.match(result.interpretation, /not retrieved issuer evidence/);
  assert.equal(result.stale, true);
  assert(!JSON.stringify(result).includes("fixture-credential"));
});

test("historical earnings preserves null estimates, fiscal dates and bounded requests", async () => {
  const requests = [];
  const records = [
    { symbol: "EXM", actual: 2, estimate: null, period: "2025-12-31" },
    { actual: 1 },
  ];
  const result = await callFinance(
    finance(records, requests),
    "earnings_surprises",
    { max_records: 1 },
  );
  assert.equal(new URL(requests[0].url).pathname, "/api/v1/stock/earnings");
  assert.equal(new URL(requests[0].url).searchParams.get("limit"), "1");
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].estimate, null);
  assert.equal(result.records[0].period, "2025-12-31");
  assert.match(result.interpretation, /not publication time/);
  assert.match(result.interpretation, /not current consensus/);
  assert.equal(result.stale, true);
});

test("Finnhub schema advertises both added datasets without adding tools", () => {
  const tool = internetToolDefinitions().find(
    (item) => item.name === "alta_finance_data",
  );
  for (const dataset of ["company_profile", "earnings_surprises"])
    assert(tool.inputSchema.properties.dataset.enum.includes(dataset));
});

test("unavailable and malformed finance responses cannot become empty success", async () => {
  for (const value of [
    { error: "fixture-credential" },
    "unexpected",
    null,
    { data: [] },
  ]) {
    await assert.rejects(
      callFinance(finance(value), "earnings_surprises"),
      (error) => {
        assert.equal(error.code, "alta_finance_invalid_response");
        assert(!error.message.includes("fixture-credential"));
        return true;
      },
    );
  }
  const empty = await callFinance(finance({}), "company_profile");
  assert.equal(empty.no_results, true);
  assert.deepEqual(empty.records, []);
});

test("invalid finance dataset cannot silently request company news", async () => {
  let calls = 0;
  await assert.rejects(
    callFinance(
      {
        finnhubKey: "fixture",
        readText() {
          calls++;
        },
      },
      "earning_typo",
    ),
    (error) => error.code === "alta_finance_invalid_dataset",
  );
  assert.equal(calls, 0);
});

test("research packs preserve stale diagnostics and spend fetch slots across origins", async () => {
  const fetched = [];
  const urls = [
    "https://a.test/issuer/1",
    "https://a.test/issuer/2",
    "https://b.test/issuer/1",
  ];
  const result = await executeInternetTool(
    {
      search: async () => ({
        cached: true,
        stale: true,
        results: urls.map((url) => ({ url, title: "Issuer revenue" })),
      }),
      fetchPage: async ({ url }) => {
        fetched.push(url);
        return {
          url,
          text: "Issuer revenue ".repeat(800),
          cached: true,
          stale: true,
          truncated: false,
          text_start: 200,
          text_end: 12200,
          total_chars: 12200,
          focus_matched: true,
        };
      },
    },
    "alta_web_research",
    { queries: ["Issuer revenue"], max_pages: 2 },
    {},
  );
  assert.deepEqual(fetched, [urls[0], urls[2]]);
  assert.equal(result.stale, true);
  assert.equal(result.searches[0].stale, true);
  assert.equal(result.pages[0].stale, true);
  assert.equal(result.pages[0].truncated, true);
  assert.equal(result.pages[0].text_end, 200 + result.pages[0].text.length);
  assert.equal(result.pages[0].focus_matched, true);
  const preview = boundedToolPreview(result, 8500);
  assert.equal(preview.value.stale, true);
  assert.equal(preview.value.pages[0].stale, true);
});

test("origin spreading keeps failure locators exact and permits same-domain-only work", async () => {
  const urls = [
    "https://a.test/issuer/1",
    "https://a.test/issuer/2",
    "https://b.test/issuer/1",
  ];
  const service = {
    search: async () => ({
      results: urls.map((url) => ({ url, title: "Issuer" })),
    }),
    fetchPage: async ({ url }) => {
      if (url.includes("b.test")) throw new Error("offline");
      return { url, text: "Source" };
    },
  };
  const result = await executeInternetTool(
    service,
    "alta_web_research",
    { queries: ["Issuer"], max_pages: 2 },
    {},
  );
  assert.equal(result.failures[0].url, urls[2]);
  service.search = async () => ({
    results: urls.slice(0, 2).map((url) => ({ url, title: "Issuer" })),
  });
  const same = await executeInternetTool(
    service,
    "alta_web_research",
    { queries: ["Issuer"], max_pages: 2 },
    {},
  );
  assert.equal(same.pages.length, 2);
});

test("oversized source records retain stale and incomplete status alongside identity", () => {
  const value = {
    pages: [
      {
        url: "https://issuer.test/filing",
        title: "Disclosure",
        text: "Large ".repeat(9000),
        metadata: {},
        source: "issuer",
        dataset: "filing",
        symbol: "EXM",
        date: "2025-01-01",
        cached: true,
        stale: true,
        truncated: true,
        partial: true,
      },
    ],
  };
  const result = boundedToolPreview(value, 1800);
  assert.equal(result.value.pages[0].stale, true);
  assert.equal(result.value.pages[0].partial, true);
  assert.equal(result.value.pages[0].url, value.pages[0].url);
  assert(Buffer.byteLength(result.text) <= 1800);
});

test("MCP shrinking of complete page text updates its local truncation flag and offsets", () => {
  const text = "Verbatim excerpt ".repeat(3000);
  const result = boundedToolPreview(
    {
      pages: [
        {
          url: "https://issuer.test/filing",
          text,
          truncated: false,
          text_start: 200,
          text_end: 200 + text.length,
          total_chars: 200 + text.length,
        },
      ],
    },
    2000,
  );
  const page = result.value.pages[0];
  assert.equal(page.truncated, true);
  assert.equal(page.text, text.slice(0, page.text.length));
  assert.equal(page.text_end, page.text_start + page.text.length);
  assert.equal(page.total_chars, 200 + text.length);
  assert(Buffer.byteLength(result.text) <= 2000);
});
