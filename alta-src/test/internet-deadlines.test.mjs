import test from "node:test";
import assert from "node:assert/strict";
import { getEventListeners } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { withDeadline } from "../internet/deadline.mjs";
import { InternetService } from "../internet/service.mjs";
import { runSource } from "../internet/plugins/source-runtime.mjs";
import { executeInternetTool } from "../internet/plugins/registry.mjs";

const lookup = async () => [{ address: "93.184.216.34", family: 4 }];
const never = () => new Promise(() => {});
function service(t, options = {}) {
  const value = new InternetService({
    lookup,
    env: {},
    ...options,
    settings: {
      timeoutMs: 40,
      searchBackendTimeoutMs: 15,
      readerEnabled: false,
      ...options.settings,
    },
  });
  t.after(() => value.close());
  return value;
}

test("deadlines reject non-cooperative work and ignore late settlements", async () => {
  const parent = new AbortController();
  let finish;
  let child;
  const result = withDeadline({ signal: parent.signal }, 10, ({ signal }) => {
    child = signal;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  await assert.rejects(result, { code: "alta_source_deadline" });
  assert.equal(child.aborted, true);
  assert.equal(getEventListeners(parent.signal, "abort").length, 0);
  finish("late success");
});

test("source cancellation is immediate even when an adapter ignores its signal", async (t) => {
  const value = service(t);
  const parent = new AbortController();
  const active = runSource(
    value,
    "test",
    "stuck",
    { signal: parent.signal },
    never,
    { deadlineMs: 60_000 },
  );
  const rejected = assert.rejects(active, /operator cancelled/);
  parent.abort(new Error("operator cancelled"));
  await rejected;
  assert.deepEqual(value.backendHealth.snapshot(), {});
  assert.equal(getEventListeners(parent.signal, "abort").length, 0);
});

test("synchronous self-cancellation and throws are both handled", async () => {
  const parent = new AbortController();
  await assert.rejects(
    withDeadline({ signal: parent.signal }, 100, () => {
      parent.abort(new Error("cancelled in adapter"));
      throw parent.signal.reason;
    }),
    /cancelled in adapter/,
  );
  assert.equal(getEventListeners(parent.signal, "abort").length, 0);
  await delay(0);
});

test("reader fallback remains available for ordinary HTTP refusal", async (t) => {
  const value = service(t, {
    settings: { readerEnabled: true },
    fetchImpl: async (url) =>
      url.hostname === "issuer.example.test"
        ? new Response("private diagnostic", { status: 403 })
        : new Response(
            "Title: Report\nURL Source: https://issuer.example.test/report\nMarkdown Content:\nCurrent report.",
          ),
  });
  const result = await value.fetchPage({
    url: "https://issuer.example.test/report",
  });
  assert.equal(result.reader_used, true);
  assert.match(result.text, /Current report/);
  assert(!JSON.stringify(result).includes("private diagnostic"));
});

test("repeated cancellation and recovery leave no capacity or listener accumulation", async (t) => {
  let mode = "success";
  const value = service(t, {
    fetchImpl: async () => (mode === "cancel" ? never() : new Response("ok")),
  });
  const baseline = getEventListeners(value.lifecycleSignal, "abort").length;
  for (let index = 0; index < 150; index++) {
    mode = index % 3 === 0 ? "cancel" : "success";
    const parent = new AbortController();
    const request = value.request("https://issuer.example.test/report", {
      signal: parent.signal,
    });
    if (mode === "cancel") {
      const rejected = assert.rejects(request, /cancel round/);
      await delay(0);
      parent.abort(new Error("cancel round"));
      await rejected;
    } else assert.equal((await request).body, "ok");
    await delay(0);
    assert.equal(value.limiter.snapshot().active, 0);
    assert.equal(value.limiter.snapshot().queued, 0);
    assert.equal(getEventListeners(parent.signal, "abort").length, 0);
  }
  assert.equal(
    getEventListeners(value.lifecycleSignal, "abort").length,
    baseline,
  );
});

test("a stalled search provider times out and auto search reaches the next route", async (t) => {
  let searchSignal;
  const value = service(t, {
    braveKey: "fixture-only",
    searxngUrl: "https://search.example.test",
    fetchImpl: async (url, options) => {
      if (url.hostname.includes("brave")) {
        searchSignal = options.signal;
        return never();
      }
      return new Response(
        JSON.stringify({
          results: [
            { url: "https://issuer.example.test/report", title: "report" },
          ],
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    },
  });
  const result = await value.search({ query: "issuer filing" });
  assert.equal(result.backend, "searxng");
  assert.equal(searchSignal.aborted, true);
  assert.equal(value.limiter.snapshot().active, 0);
  assert.deepEqual(result.fallback_chain, ["brave"]);
});

test("federated timeout preserves peer results and reports partial status", async (t) => {
  const value = service(t, {
    xaiSearch: never,
    searxngUrl: "https://search.example.test",
    fetchImpl: async (url) => {
      if (url.hostname === "search.example.test")
        return new Response(
          JSON.stringify({
            results: [
              { url: "https://issuer.example.test/report", title: "report" },
            ],
          }),
        );
      return new Response("", { status: 403 });
    },
  });
  const result = await value.search({
    query: "issuer filing",
    backend: "federated",
  });
  assert.equal(result.partial, true);
  assert.equal(result.results[0].url, "https://issuer.example.test/report");
  assert(
    result.failures.some(
      (x) => x.backend === "xai" && x.code === "alta_search_backend_deadline",
    ),
  );
});

test("service close cancels federated search instead of returning a partial success", async (t) => {
  const value = service(t, { xaiSearch: never, fetchImpl: never });
  const active = value.search({ query: "issuer filing", backend: "federated" });
  const rejected = assert.rejects(active);
  await delay(2);
  value.close();
  await rejected;
  assert.equal(value.limiter.snapshot().active, 0);
});

test("DNS and ignored fetch aborts are bounded; capacity can be reused", async (t) => {
  const dns = service(t, { lookup: never });
  await assert.rejects(dns.request("https://issuer.example.test"), {
    code: "alta_web_request_deadline",
  });
  const value = service(t, { fetchImpl: never });
  await assert.rejects(value.request("https://issuer.example.test"), {
    code: "alta_web_request_deadline",
  });
  await delay(0);
  assert.equal(value.limiter.snapshot().active, 0);
  value.fetchImpl = async () => new Response("recovered");
  assert.equal(
    (await value.request("https://issuer.example.test")).body,
    "recovered",
  );
});

test("whole-tool deadline includes reader preflight DNS and stops future requests", async (t) => {
  let resolveDns;
  let calls = 0;
  const value = service(t, {
    settings: { readerEnabled: true, toolTimeoutMs: 15 },
    lookup: () =>
      new Promise((resolve) => {
        resolveDns = resolve;
      }),
    fetchImpl: async () => {
      calls++;
      return new Response("late");
    },
  });
  await assert.rejects(
    executeInternetTool(value, "alta_web_fetch", {
      url: "https://issuer.example.test/report",
      reader: "reader",
    }),
    { code: "alta_tool_deadline" },
  );
  resolveDns(await lookup());
  await delay(0);
  assert.equal(calls, 0);
  assert.equal(value.limiter.snapshot().active, 0);
});

test("deadline cancels a stalled response body without leaking a slot", async (t) => {
  let cancelled = false;
  const value = service(t, {
    fetchImpl: async () =>
      new Response(
        new ReadableStream({
          cancel() {
            cancelled = true;
          },
        }),
      ),
  });
  await assert.rejects(value.request("https://issuer.example.test"), {
    code: "alta_web_request_deadline",
  });
  await delay(0);
  assert.equal(cancelled, true);
  assert.equal(value.limiter.snapshot().active, 0);
});

test("redirect bodies are closed and credentials do not cross origins", async (t) => {
  const seen = [];
  let cancelled = 0;
  const value = service(t, {
    fetchImpl: async (url, options) => {
      seen.push({ url: String(url), headers: options.headers });
      if (seen.length === 1)
        return new Response(
          new ReadableStream({
            cancel() {
              cancelled++;
            },
          }),
          { status: 302, headers: { Location: "/next" } },
        );
      if (seen.length === 2)
        return new Response(
          new ReadableStream({
            cancel() {
              cancelled++;
            },
          }),
          {
            status: 302,
            headers: { Location: "https://other.example.test/end" },
          },
        );
      return new Response("ok");
    },
  });
  await value.request("https://issuer.example.test/start", {
    headers: { "Authorization": "fixture-only", "X-Proxy-Key": "fixture-only" },
  });
  assert.equal(seen[1].headers.Authorization, "fixture-only");
  assert.equal(seen[2].headers.Authorization, undefined);
  assert.equal(seen[2].headers["X-Proxy-Key"], undefined);
  assert.equal(cancelled, 2);
});

test("cross-origin body redirects are blocked before a second request", async (t) => {
  let calls = 0;
  const value = service(t, {
    fetchImpl: async () => {
      calls++;
      return new Response("", {
        status: 307,
        headers: { Location: "https://other.example.test/end" },
      });
    },
  });
  await assert.rejects(
    value.request("https://issuer.example.test/start", {
      method: "POST",
      body: "private payload",
    }),
    { code: "alta_web_unsafe_redirect" },
  );
  assert.equal(calls, 1);
});

test("HTTP errors never echo response bodies and cancellation prevents reader fallback", async (t) => {
  let calls = 0;
  const value = service(t, {
    fetchImpl: async () => {
      calls++;
      return new Response("provider-secret-canary", { status: 401 });
    },
  });
  await assert.rejects(
    value.request("https://issuer.example.test"),
    (e) => e.message === "Web HTTP 401" && !e.message.includes("canary"),
  );
  value.close();
  await assert.rejects(value.fetchPage({ url: "https://issuer.example.test" }));
  assert.equal(calls, 1);
});

test("cancelled reads cannot return a warm cached success", async (t) => {
  const value = service(t, {
    fetchImpl: async () => new Response("cached page"),
  });
  const args = { url: "https://issuer.example.test/report" };
  await value.fetchPage(args);
  const caller = new AbortController();
  caller.abort(new Error("caller stopped"));
  await assert.rejects(
    value.fetchPage(args, { signal: caller.signal }),
    /caller stopped/,
  );
  assert.equal(value.metrics.cacheHits, 0);
});

test("service close cannot turn an in-flight failure into stale-cache success", async (t) => {
  let stale = false;
  const value = service(t, {
    settings: { cacheTtlMs: 1, staleTtlMs: 60_000 },
    fetchImpl: async () => (stale ? never() : new Response("old page")),
  });
  const args = { url: "https://issuer.example.test/report" };
  await value.fetchPage(args);
  stale = true;
  await delay(2);
  const pending = value.fetchPage(args);
  const rejected = assert.rejects(pending, { code: "alta_internet_closed" });
  await delay(1);
  value.close();
  await rejected;
  assert.equal(value.metrics.staleHits, 0);
  assert.equal(value.cache.snapshot().entries, 0);
  assert.equal(value.limiter.snapshot().active, 0);
});

test("a long retry-after cannot extend the end-to-end request deadline", async (t) => {
  let calls = 0;
  const value = service(t, {
    fetchImpl: async () => {
      calls++;
      return new Response("", {
        status: 429,
        headers: { "Retry-After": "30" },
      });
    },
  });
  await assert.rejects(value.request("https://issuer.example.test"), {
    code: "alta_web_request_deadline",
  });
  assert.equal(calls, 1);
  assert.equal(value.limiter.snapshot().active, 0);
});
