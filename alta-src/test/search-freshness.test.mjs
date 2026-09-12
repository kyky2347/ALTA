import test from "node:test";
import assert from "node:assert/strict";
import { executeSearch, normalizeSearch } from "../internet/search.mjs";
import { freshnessWindow } from "../internet/search-freshness.mjs";
import { InternetService } from "../internet/service.mjs";
import { boundedToolPreview } from "../internet/result-preview.mjs";

const at = new Date("2026-09-12T16:00:00Z");
function args(backend, freshness = "week") {
  return {
    ...normalizeSearch({ query: "issuer capacity", backend, freshness }, {}),
    freshness_window: freshnessWindow(freshness, at),
  };
}

test("freshness aliases and date windows normalize without silent widening", () => {
  assert.equal(
    normalizeSearch({ query: "issuer", freshness: "pw" }, {}).freshness,
    "week",
  );
  assert.deepEqual(freshnessWindow("week", at), {
    requested: "week",
    from_date: "2026-09-05",
    to_date: "2026-09-12",
  });
  assert.deepEqual(freshnessWindow("2026-09-01to2026-09-03", at), {
    requested: "2026-09-01to2026-09-03",
    from_date: "2026-09-01",
    to_date: "2026-09-03",
  });
  for (const value of [
    "recent",
    "2026-02-30to2026-03-10",
    "2026-09-12to2026-09-01",
  ])
    assert.throws(
      () => normalizeSearch({ query: "issuer", freshness: value }, {}),
      { code: "alta_web_invalid_freshness" },
    );
});

test("Brave receives documented provider codes and provenance is not event verification", async () => {
  for (const [input, expected] of [
    ["day", "pd"],
    ["week", "pw"],
    ["month", "pm"],
    ["year", "py"],
    ["2026-09-01to2026-09-03", "2026-09-01to2026-09-03"],
  ]) {
    let sent;
    const result = await executeSearch(
      {
        braveKey: "fixture",
        request: async (_url, options) => {
          sent = JSON.parse(options.body);
          return { body: JSON.stringify({ grounding: { generic: [] } }) };
        },
      },
      args("brave", input),
    );
    assert.equal(sent.freshness, expected);
    assert.equal(result.freshness.mode, "provider_filter");
    assert.equal(result.freshness.event_time_verified, false);
  }
});

test("xAI receives the time window with explicit publication and old-context constraints", async () => {
  let sent;
  const result = await executeSearch(
    {
      xaiSearch: async (value) => {
        sent = value;
        return { sources: [{ url: "https://issuer.example/change" }] };
      },
    },
    args("xai"),
  );
  assert.match(sent.query, /2026-09-05 through 2026-09-12/);
  assert.match(sent.query, /Do not substitute crawl\/retrieval time/);
  assert.equal(result.freshness.mode, "query_hint");
});

test("SearXNG supported periods filter natively; week remains an explicit hint", async () => {
  for (const input of ["day", "week"]) {
    let sent;
    const result = await executeSearch(
      {
        searxngUrl: "https://search.example",
        request: async (url) => {
          sent = new URL(url);
          return { body: '{"results":[]}' };
        },
      },
      args("searxng", input),
    );
    assert.equal(
      sent.searchParams.get("time_range"),
      input === "day" ? "day" : null,
    );
    assert.equal(
      result.freshness.mode,
      input === "day" ? "provider_filter" : "query_hint",
    );
    if (input === "week")
      assert.match(
        sent.searchParams.get("q"),
        /after:2026-09-05 before:2026-09-13/,
      );
  }
});

test("public search fallback retains recency hint and identifies actual backend", async () => {
  const urls = [];
  const result = await executeSearch(
    {
      request: async (url) => {
        urls.push(new URL(url));
        if (url.includes("duckduckgo")) throw new Error("unavailable");
        return {
          body: '<li class="b_algo"><h2><a href="https://issuer.example/change">Change</a></h2><p>Source</p></li>',
        };
      },
    },
    args("public"),
  );
  assert.equal(urls.length, 2);
  for (const url of urls)
    assert.match(url.searchParams.get("q"), /after:2026-09-05/);
  assert.equal(result.freshness.backend, "bing");
  assert.equal(result.freshness.mode, "query_hint");
});

test("federation preserves each engine's actual freshness capability in bounded output", async () => {
  const result = await executeSearch(
    {
      braveKey: "fixture",
      xaiSearch: async () => ({ sources: [] }),
      request: async (url) => {
        if (url.includes("brave"))
          return { body: '{"grounding":{"generic":[]}}' };
        throw new Error("unavailable");
      },
    },
    args("federated"),
  );
  assert.deepEqual(
    result.freshness.map((item) => item.mode),
    ["provider_filter", "query_hint"],
  );
  const preview = boundedToolPreview(
    { ...result, answer: "large ".repeat(5_000) },
    3_000,
  );
  assert.deepEqual(preview.value.freshness, result.freshness);
});

test("invalid freshness fails before any network I/O", async () => {
  let calls = 0;
  const service = new InternetService({
    fetchImpl: async () => {
      calls++;
      throw new Error("unexpected");
    },
  });
  try {
    await assert.rejects(
      service.search({ query: "issuer", freshness: "latest-ish" }),
      { code: "alta_web_invalid_freshness" },
    );
    assert.equal(calls, 0);
  } finally {
    await service.close();
  }
});
