import test from "node:test";
import assert from "node:assert/strict";
import { executeInternetTool } from "../internet/plugins/registry.mjs";

function feedService(items, extra = {}) {
  return {
    readText: async () => ({
      url: "https://issuer.example.test/feed",
      text: JSON.stringify({ items }),
      ...extra,
    }),
  };
}

test("feed date and query filters run before the output limit", async () => {
  const source = feedService(
    [
      { title: "Credit outlook", date_published: "2026-08-01" },
      { title: "Bank earnings", date_published: "2026-09-10" },
      {
        title: "Credit outlook revised",
        date_published: "2026-09-11",
        url: "/release",
      },
      { title: "Credit outlook unverified" },
      { title: "Credit outlook future", date_published: "2026-09-13" },
    ],
    { cached: true, stale: true },
  );
  const result = await executeInternetTool(source, "alta_web_feed", {
    url: "https://issuer.example.test/feed",
    query: "credit outlook",
    from_date: "2026-09-01",
    to_date: "2026-09-12",
    max_items: 1,
  });
  assert.equal(result.items[0].url, "https://issuer.example.test/release");
  assert.equal(result.items[0].published, "2026-09-11");
  assert.equal(result.matching_count, 1);
  assert.equal(result.scanned_count, 5);
  assert.equal(result.stale, true);
  assert.equal(result.cached, true);
  assert.equal(result.publication_time_unverified, true);
});

test("feed filtering reports truncation instead of implying full recall", async () => {
  const source = feedService(
    Array.from({ length: 510 }, (_, i) => ({ title: `Change ${i}` })),
  );
  const result = await executeInternetTool(source, "alta_web_feed", {
    url: "https://issuer.example.test/feed",
    max_items: 2,
  });
  assert.equal(result.items.length, 2);
  assert.equal(result.scanned_count, 500);
  assert.equal(result.truncated, true);
});

test("invalid feed inputs fail before network I/O and HTML is not an empty success", async () => {
  let calls = 0;
  const source = {
    readText: async () => {
      calls++;
      return { text: "<html>Access denied</html>" };
    },
  };
  for (const args of [
    { from_date: "2026-02-30" },
    { to_date: "yesterday" },
    { from_date: "2026-09-12", to_date: "2026-09-01" },
    { query: "a".repeat(201) },
  ])
    await assert.rejects(
      executeInternetTool(source, "alta_web_feed", {
        url: "https://issuer.example.test/feed",
        ...args,
      }),
      { status: 400 },
    );
  assert.equal(calls, 0);
  await assert.rejects(
    executeInternetTool(source, "alta_web_feed", {
      url: "https://issuer.example.test/feed",
    }),
    { code: "alta_feed_invalid_document" },
  );
  assert.equal(calls, 1);
});

test("Atom and RSS publisher timestamps are preserved rather than replaced by fetch time", async () => {
  for (const text of [
    '<feed><entry><title>Change</title><link href="/change"/><published>2026-09-10T23:30:00-04:00</published></entry></feed>',
    "<rss><channel><item><title>Change</title><link>/change</link><pubDate>Thu, 10 Sep 2026 23:30:00 -0400</pubDate></item></channel></rss>",
  ]) {
    const result = await executeInternetTool(
      feedService([], { text }),
      "alta_web_feed",
      {
        url: "https://issuer.example.test/feed",
        from_date: "2026-09-11",
        to_date: "2026-09-11",
      },
    );
    assert.equal(result.items.length, 1);
    assert.match(result.items[0].published, /10/);
  }
});

test("SEC filters recent filings before limiting and separates acceptance from reporting date", async () => {
  const recent = {
    accessionNumber: [
      "0000000001-26-000001",
      "0000000001-26-000002",
      "0000000001-26-000003",
    ],
    form: ["8-K", "8-K", "10-Q"],
    filingDate: ["2026-08-01", "2026-09-10", "2026-09-11"],
    acceptanceDateTime: [
      "2026-08-01T16:01:00.000Z",
      "2026-09-10T16:12:00.000Z",
    ],
    reportDate: ["2026-07-31", "2026-09-09"],
    primaryDocument: ["a.htm", "b.htm", "c.htm"],
  };
  const source = {
    readText: async () => ({
      text: JSON.stringify({ name: "Example", filings: { recent } }),
      cached: true,
      stale: true,
    }),
  };
  const result = await executeInternetTool(source, "alta_finance_data", {
    source: "sec",
    cik: "1",
    from_date: "2026-09-01",
    to_date: "2026-09-12",
    forms: ["8-K"],
    max_records: 1,
  });
  assert.equal(result.filings.length, 1);
  assert.equal(result.filings[0].filed_at, "2026-09-10");
  assert.equal(result.filings[0].accepted_at, "2026-09-10T16:12:00.000Z");
  assert.equal(result.filings[0].report_date, "2026-09-09");
  assert.equal(result.stale, true);
  assert.equal(result.cached, true);
});

test("invalid SEC date windows do not call the source", async () => {
  let calls = 0;
  const source = {
    readText: async () => {
      calls++;
      throw new Error("must not fetch");
    },
  };
  for (const args of [
    { from_date: "2026-02-30" },
    { from_date: "2026-09-12", to_date: "2026-09-01" },
  ]) {
    await assert.rejects(
      executeInternetTool(source, "alta_finance_data", {
        source: "sec",
        cik: "1",
        ...args,
      }),
      { status: 400 },
    );
  }
  assert.equal(calls, 0);
});
