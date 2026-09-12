import test from "node:test";
import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";
import { BackendHealth } from "../internet/backend-health.mjs";
import { executeSearch, filteredQuery } from "../internet/search.mjs";
import { InternetService } from "../internet/service.mjs";
import {
  runSource,
  settleSources,
} from "../internet/plugins/source-runtime.mjs";

const publicLookup = async () => [{ address: "93.184.216.34", family: 4 }];

test("multi-domain primary-source scopes use OR semantics", () => {
  assert.equal(
    filteredQuery({
      query: "issuer earnings filing",
      allowed: ["sec.gov", "investor.example.com"],
      excluded: [],
    }),
    "issuer earnings filing (site:sec.gov OR site:investor.example.com)",
  );
  assert.equal(
    filteredQuery({
      query: "issuer earnings filing",
      allowed: [],
      excluded: ["wikipedia.org"],
    }),
    "issuer earnings filing -site:wikipedia.org",
  );
});

test("domain scopes are enforced again after an upstream search response", async () => {
  const result = await executeSearch(
    {
      xaiSearch: async () => ({
        output: [
          {
            type: "message",
            content: [
              {
                type: "output_text",
                text: [
                  "Allowed https://www.sec.gov/Archives/acme-10-q",
                  "Ignored https://investor.acme.example/results",
                ].join("\n"),
              },
            ],
          },
        ],
      }),
      backendHealth: new BackendHealth(),
    },
    {
      query: "ACME filing",
      maximum: 10,
      depth: "deep",
      allowed: ["sec.gov"],
      excluded: [],
      freshness: "",
      language: "en",
      backend: "xai",
    },
  );

  assert.deepEqual(
    result.results.map((item) => item.url),
    ["https://www.sec.gov/Archives/acme-10-q"],
  );
  assert.equal(result.answer, "");
});

function serviceSettings(overrides = {}) {
  return {
    cacheBytes: 1024 * 1024,
    cacheTtlMs: 60_000,
    staleTtlMs: 60_000,
    concurrency: 6,
    crawlConcurrency: 3,
    inflightLimit: 64,
    queueLimit: 64,
    timeoutMs: 5_000,
    maxDownloadBytes: 64 * 1024,
    maxOutputChars: 32_000,
    readerEnabled: false,
    ...overrides,
  };
}

test("concurrent cache misses share one fetch without coupling subscriber cancellation", async () => {
  let calls = 0;
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async (url, { signal } = {}) => {
      calls += 1;
      await delay(25, undefined, { signal });
      return new Response(
        `<html><title>Shared</title><main>${new URL(url).pathname}</main></html>`,
        { headers: { "Content-Type": "text/html" } },
      );
    },
    settings: serviceSettings(),
  });

  const shared = await Promise.all(
    Array.from({ length: 24 }, () =>
      service.fetchPage({ url: "https://example.test/shared" }),
    ),
  );
  assert.equal(calls, 1);
  assert.equal(
    shared.every((page) => page.text.includes("/shared")),
    true,
  );

  const first = new AbortController();
  const firstSubscriber = service.fetchPage(
    { url: "https://example.test/cancel" },
    { signal: first.signal },
  );
  const survivingSubscriber = service.fetchPage({
    url: "https://example.test/cancel",
  });
  first.abort(new Error("first subscriber cancelled"));
  await assert.rejects(firstSubscriber, /first subscriber cancelled/);
  assert.match((await survivingSubscriber).text, /\/cancel/);
  assert.equal(calls, 2);
  assert.deepEqual(service.snapshot().inflight, {
    active: 0,
    limit: 64,
    started: 2,
    joined: 24,
    overflow: 0,
    closed: false,
  });
  service.close();
});

test("expired internet entries serve stale data during transient outages", async () => {
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async () =>
      new Response("<html><main>known good content</main></html>", {
        headers: { "Content-Type": "text/html" },
      }),
    settings: serviceSettings({ cacheTtlMs: 5, staleTtlMs: 5_000 }),
  });
  const args = { url: "https://example.test/stale", reader: "direct" };
  const fresh = await service.fetchPage(args);
  await delay(10);
  service.request = async () => {
    throw Object.assign(new Error("temporary outage"), { status: 503 });
  };
  const stale = await service.fetchPage(args);

  assert.equal(fresh.stale, undefined);
  assert.deepEqual(stale, {
    ...fresh,
    cached: true,
    stale: true,
  });
  assert.equal(service.snapshot().metrics.staleHits, 1);
  service.close();
});

test("same-origin crawl fetches each breadth wave concurrently and isolates failures", async () => {
  let active = 0;
  let calls = 0;
  let maximum = 0;
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async (url, { signal } = {}) => {
      calls += 1;
      active += 1;
      maximum = Math.max(maximum, active);
      await delay(20, undefined, { signal });
      active -= 1;
      const pathname = new URL(url).pathname;
      if (pathname === "/bad") return new Response("missing", { status: 404 });
      const links =
        pathname === "/start"
          ? '<a href="/a">a</a><a href="/b">b</a><a href="/bad">bad</a>'
          : "";
      return new Response(`<html><main>${pathname}${links}</main></html>`, {
        headers: { "Content-Type": "text/html" },
      });
    },
    settings: serviceSettings(),
  });

  const result = await service.crawl({
    url: "https://example.test/start",
    max_pages: 4,
    max_depth: 1,
  });
  assert.deepEqual(
    { calls, attempts: result.attempt_count, maximum },
    { calls: 4, attempts: 4, maximum: 3 },
  );
  assert.deepEqual(
    result.pages.map((page) => page.url),
    [
      "https://example.test/start",
      "https://example.test/a",
      "https://example.test/b",
    ],
  );
  assert.deepEqual(result.failures, [
    { url: "https://example.test/bad", error: "Web HTTP 404" },
  ]);
  assert.equal(result.partial, true);
  service.close();
});

test("federated search bounds every real HTTP request instead of only outer operations", async () => {
  let active = 0;
  let maximum = 0;
  const service = new InternetService({
    braveKey: "test-brave",
    jinaKey: "test-jina",
    searxngUrl: "https://search.test/",
    lookup: publicLookup,
    fetchImpl: async (url, { signal } = {}) => {
      active += 1;
      maximum = Math.max(maximum, active);
      await delay(15, undefined, { signal });
      active -= 1;
      const host = new URL(url).hostname;
      if (host === "api.search.brave.com")
        return Response.json({
          grounding: {
            generic: [{ url: "https://brave.test/", title: "Brave" }],
          },
        });
      if (host === "s.jina.ai")
        return new Response("[Jina](https://jina.test/)");
      if (host === "search.test")
        return Response.json({
          results: [{ url: "https://searx.test/", title: "SearXNG" }],
        });
      return new Response(
        '<a class="result__a" href="https://public.test/">Public</a><a class="result__snippet">Result</a>',
      );
    },
    settings: serviceSettings({ concurrency: 2 }),
  });

  const result = await service.search({
    query: "bounded fanout",
    backend: "federated",
  });

  assert.deepEqual(result.backends, ["brave", "jina", "searxng", "public"]);
  assert.equal(maximum, 2);
  assert.equal(service.snapshot().capacity.active, 0);
  service.close();
});

test("search backend circuit breaker suppresses outages and admits one recovery probe", async () => {
  let now = 0;
  let braveCalls = 0;
  const backendHealth = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
    maxCooldownMs: 1_000,
    now: () => now,
  });
  const context = {
    braveKey: "test-brave",
    backendHealth,
    request: async () => {
      braveCalls += 1;
      throw Object.assign(new Error("Brave unavailable"), { status: 503 });
    },
    xaiSearch: async () => ({
      output: [
        {
          type: "message",
          content: [
            {
              type: "output_text",
              text: "fallback https://example.test/source",
            },
          ],
        },
      ],
    }),
  };
  const args = {
    query: "resilient search",
    maximum: 5,
    depth: "quick",
    allowed: [],
    excluded: [],
    freshness: "",
    language: "",
    backend: "auto",
  };

  const first = await executeSearch(context, args);
  const suppressed = await executeSearch(context, args);
  now = 101;
  const probe = await executeSearch(context, args);

  assert.deepEqual(first.fallback_chain, ["brave"]);
  assert.deepEqual(suppressed.fallback_chain, ["brave:circuit-open"]);
  assert.deepEqual(probe.fallback_chain, ["brave"]);
  assert.equal(braveCalls, 2);
  assert.deepEqual(backendHealth.snapshot().brave, {
    state: "open",
    retryInMs: 200,
    opens: 2,
    suppressed: 1,
    lastError: "Brave unavailable",
  });
});

test("public source pacing admits a bounded burst without bypassing intervals", async () => {
  let calls = 0;
  const service = { backendHealth: new BackendHealth() };
  const operation = () => {
    calls += 1;
    return "ok";
  };

  assert.equal(
    await runSource(service, "news", "paced", {}, operation, {
      intervalMs: 10,
    }),
    "ok",
  );
  assert.equal(
    await runSource(service, "news", "paced", {}, operation, {
      intervalMs: 10,
    }),
    "ok",
  );
  assert.equal(calls, 2);
  assert.deepEqual(service.backendHealth.snapshot(), {});
});

test("rate-sensitive sources can disable request-layer retry bursts", async () => {
  let calls = 0;
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async () => {
      calls += 1;
      return new Response("slow down", { status: 429 });
    },
    settings: serviceSettings(),
  });

  await assert.rejects(
    service.readText({
      url: "https://rate-limited.test/data",
      attempts: 1,
    }),
    /Web HTTP 429/,
  );
  assert.equal(calls, 1);
  service.close();
});

test("federated sources enforce independent deadlines without delaying peers", async () => {
  const service = { backendHealth: new BackendHealth() };
  let slowCompleted = false;
  const settled = await settleSources(
    service,
    "deadline",
    ["fast", "slow"],
    {},
    async (source, options) => {
      if (source === "fast") return "ready";
      await delay(100, undefined, { signal: options.signal });
      slowCompleted = true;
      return "late";
    },
    { deadlines: { slow: 10 } },
  );

  assert.deepEqual(settled.values, [{ source: "fast", value: "ready" }]);
  assert.equal(settled.failures[0].source, "slow");
  assert.match(settled.failures[0].error, /deadline/);
  assert.equal(slowCompleted, false);
});

test("one-source adapters receive and enforce their own deadline signal", async () => {
  const service = { backendHealth: new BackendHealth() };
  let completed = false;
  await assert.rejects(
    runSource(
      service,
      "finance",
      "slow",
      {},
      async (options) => {
        await delay(100, undefined, { signal: options.signal });
        completed = true;
      },
      { deadlineMs: 10 },
    ),
    /deadline/,
  );
  assert.equal(completed, false);
});
