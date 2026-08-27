import test from "node:test";
import assert from "node:assert/strict";
import { resilientJson } from "../provider-request.mjs";
import { RetryCoordinator } from "../resource-control.mjs";
import { retryDelayMs } from "../retry-policy.mjs";

test("retry delay distinguishes missing headers and accepts HTTP dates", () => {
  const options = { jitterMs: 0, now: () => 1_000, random: () => 0 };
  assert.deepEqual(
    [
      retryDelayMs(0, null, options),
      retryDelayMs(1, "", options),
      retryDelayMs(3, "2", options),
      retryDelayMs(3, new Date(4_000).toUTCString(), options),
    ],
    [500, 1_000, 2_000, 3_000],
  );
});

test("provider retry budget stops an outage storm and serializes the body once", async () => {
  let calls = 0;
  let serializations = 0;
  const body = {
    toJSON() {
      serializations += 1;
      return { model: "grok-test", input: "hello" };
    },
  };
  const context = {
    settings: {
      maxRetries: 100,
      retryBudgetMs: 250,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: new RetryCoordinator(),
    metrics: { retries: 0 },
    fetchImpl: async () => {
      calls += 1;
      return new Response("temporarily unavailable", { status: 503 });
    },
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      body,
      "xai",
      new AbortController().signal,
      context,
    ),
    { code: "alta_retry_budget_exhausted", retryable: false },
  );
  assert.deepEqual(
    { calls, serializations, retries: context.metrics.retries },
    { calls: 1, serializations: 1, retries: 1 },
  );
});

test("retry attempts cannot outlive the remaining retry budget", async () => {
  let calls = 0;
  const attemptTimeouts = [];
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 500,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: {
      wait: async () => {},
      defer: () => {},
      success: () => {},
    },
    metrics: { retries: 0 },
    timeoutSignal: (timeoutMs) => {
      attemptTimeouts.push(timeoutMs);
      const controller = new AbortController();
      if (attemptTimeouts.length > 1) {
        queueMicrotask(() =>
          controller.abort(new Error("synthetic attempt timeout")),
        );
      }
      return controller.signal;
    },
    fetchImpl: async (_url, { signal }) => {
      calls += 1;
      if (calls === 1) return new Response("busy", { status: 503 });
      return new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        });
      });
    },
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      new AbortController().signal,
      context,
    ),
  );
  assert.equal(calls, 2);
  assert.equal(attemptTimeouts[0], 1_000);
  assert.ok(attemptTimeouts[1] > 0 && attemptTimeouts[1] <= 500);
});

test("retry budget is rechecked after capacity admission", async () => {
  let calls = 0;
  let acquisitions = 0;
  let releases = 0;
  let now = 0;
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 20,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: {
      wait: async () => {},
      defer: () => {},
      success: () => {},
    },
    metrics: { retries: 0 },
    now: () => now,
    fetchImpl: async () => {
      calls += 1;
      return new Response("busy", { status: 503 });
    },
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      new AbortController().signal,
      context,
      {
        acquireAttempt: async () => {
          acquisitions += 1;
          if (acquisitions === 2) now = 21;
          return () => {
            releases += 1;
          };
        },
      },
    ),
    { code: "alta_retry_budget_exhausted", retryable: false },
  );
  assert.deepEqual(
    { calls, acquisitions, releases },
    {
      calls: 1,
      acquisitions: 2,
      releases: 2,
    },
  );
});

test("retry budget cancels capacity admission at its deadline", async () => {
  let calls = 0;
  let acquisitions = 0;
  let releases = 0;
  let now = 0;
  let waits = 0;
  const admissionBudgets = [];
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 100,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: {
      wait: async () => {
        waits += 1;
        if (waits === 2) now = 80;
      },
      defer: () => {},
      success: () => {},
    },
    retryBudgetSignal: (budget) => {
      admissionBudgets.push(budget);
      const controller = new AbortController();
      queueMicrotask(() =>
        controller.abort(new Error("synthetic retry deadline")),
      );
      return controller.signal;
    },
    metrics: { retries: 0 },
    now: () => now,
    fetchImpl: async () => {
      calls += 1;
      return new Response("busy", { status: 503 });
    },
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      new AbortController().signal,
      context,
      {
        acquireAttempt: async (signal) => {
          acquisitions += 1;
          if (acquisitions > 1)
            return new Promise((_resolve, reject) =>
              signal.addEventListener("abort", () => reject(signal.reason), {
                once: true,
              }),
            );
          return () => {
            releases += 1;
          };
        },
      },
    ),
    { code: "alta_retry_budget_exhausted", retryable: false },
  );
  assert.deepEqual(
    { calls, acquisitions, releases, admissionBudgets },
    { calls: 1, acquisitions: 2, releases: 1, admissionBudgets: [20] },
  );
});

test("provider response preflight cancels a declared oversized body", async () => {
  let cancelled = false;
  const body = new ReadableStream({
    cancel() {
      cancelled = true;
    },
  });
  const context = {
    settings: {
      maxRetries: 0,
      retryBudgetMs: 1_000,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 8,
    },
    retryCoordinator: new RetryCoordinator(),
    metrics: { retries: 0 },
    fetchImpl: async () =>
      new Response(body, { headers: { "Content-Length": "9" } }),
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      new AbortController().signal,
      context,
    ),
    /response limit/,
  );
  assert.equal(cancelled, true);
});

test("provider request reports 429 overload and successful recovery", async () => {
  let calls = 0;
  const events = [];
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 5_000,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: {
      wait: async () => {},
      defer: (_provider, delay) => events.push(`defer:${delay}`),
      success: () => {},
    },
    providerConcurrency: {
      overload: (provider) => events.push(`overload:${provider}`),
      success: (provider) => events.push(`success:${provider}`),
    },
    metrics: { retries: 0 },
    fetchImpl: async () => {
      calls += 1;
      return calls === 1
        ? new Response("limited", {
            status: 429,
            headers: { "Retry-After": "2" },
          })
        : Response.json({ ok: true });
    },
  };

  assert.deepEqual(
    await resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      new AbortController().signal,
      context,
    ),
    { ok: true },
  );
  assert.deepEqual(events, ["overload:xai", "defer:2000", "success:xai"]);
});

test("provider attempts release capacity before shared retry backoff", async () => {
  const events = [];
  let active = 0;
  let calls = 0;
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 1_000,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: {
      wait: async () => {
        events.push(`wait:${active}`);
        assert.equal(active, 0);
      },
      defer: () => events.push("defer"),
      success: () => events.push("success"),
    },
    metrics: { retries: 0 },
    fetchImpl: async () => {
      calls += 1;
      events.push(`fetch:${calls}`);
      return calls === 1
        ? new Response("busy", { status: 503 })
        : Response.json({ ok: true });
    },
  };

  const value = await resilientJson(
    "https://api.example.test/responses",
    "xai-test-placeholder",
    { model: "grok-test" },
    "xai",
    new AbortController().signal,
    context,
    {
      acquireAttempt: async () => {
        active += 1;
        events.push("acquire");
        let released = false;
        return () => {
          if (released) return;
          released = true;
          active -= 1;
          events.push("release");
        };
      },
      onRetry: () => events.push("retry"),
    },
  );

  assert.deepEqual(value, { ok: true });
  assert.equal(active, 0);
  assert.deepEqual(events, [
    "wait:0",
    "acquire",
    "fetch:1",
    "defer",
    "retry",
    "release",
    "wait:0",
    "acquire",
    "fetch:2",
    "success",
    "release",
  ]);
});

test("active provider cancellation releases its capacity lease exactly once", async () => {
  const controller = new AbortController();
  let active = 0;
  let releases = 0;
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 1_000,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator: new RetryCoordinator(),
    metrics: { retries: 0 },
    fetchImpl: async (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        });
        queueMicrotask(() => controller.abort(new Error("cancel provider")));
      }),
  };

  await assert.rejects(
    resilientJson(
      "https://api.example.test/responses",
      "xai-test-placeholder",
      { model: "grok-test" },
      "xai",
      controller.signal,
      context,
      {
        acquireAttempt: async () => {
          active += 1;
          let released = false;
          return () => {
            if (released) return;
            released = true;
            active -= 1;
            releases += 1;
          };
        },
      },
    ),
    /cancel provider/,
  );
  assert.deepEqual({ active, releases }, { active: 0, releases: 1 });
});

test("concurrent provider failures share one outage backoff round", async () => {
  const parallel = 8;
  const retryCoordinator = new RetryCoordinator();
  const metrics = { retries: 0 };
  let calls = 0;
  let admitFailures;
  const failureGate = new Promise((resolve) => {
    admitFailures = resolve;
  });
  const context = {
    settings: {
      maxRetries: 1,
      retryBudgetMs: 250,
      requestTimeoutMs: 1_000,
      maxResponseBytes: 1024,
    },
    retryCoordinator,
    metrics,
    fetchImpl: async () => {
      calls += 1;
      if (calls === parallel) admitFailures();
      await failureGate;
      return new Response("outage", { status: 503 });
    },
  };

  const results = await Promise.allSettled(
    Array.from({ length: parallel }, () =>
      resilientJson(
        "https://api.example.test/responses",
        "xai-test-placeholder",
        { model: "grok-test" },
        "xai",
        new AbortController().signal,
        context,
      ),
    ),
  );

  assert.deepEqual(
    {
      calls,
      retries: metrics.retries,
      failures: results.filter((result) => result.status === "rejected").length,
      outage: retryCoordinator.snapshot().xai.consecutiveFailures,
    },
    { calls: parallel, retries: parallel, failures: parallel, outage: 1 },
  );
});
