import test from "node:test";
import assert from "node:assert/strict";
import {
  ByteBudget,
  CapacityLimiter,
  LatencyMetrics,
  ProviderConcurrencyController,
  RetryCoordinator,
  acquireCapacityLease,
} from "../resource-control.mjs";

test("capacity limiter bounds active work and rejects an overflowing queue", async () => {
  const limiter = new CapacityLimiter({
    limit: 1,
    queueLimit: 1,
    queueTimeoutMs: 1000,
    name: "test capacity",
  });
  const releaseFirst = await limiter.acquire();
  const second = limiter.acquire();
  await assert.rejects(limiter.acquire(), { code: "alta_queue_full" });
  assert.deepEqual(limiter.snapshot(), {
    name: "test capacity",
    limit: 1,
    active: 1,
    queued: 1,
    queueLimit: 1,
    closed: false,
  });
  releaseFirst();
  const releaseSecond = await second;
  releaseSecond();
  assert.equal(limiter.snapshot().active, 0);
});

test("byte budget is released without underflow", () => {
  const budget = new ByteBudget(10);
  budget.reserve(8);
  assert.throws(() => budget.reserve(3), { code: "alta_memory_budget" });
  budget.release(8);
  budget.release(8);
  assert.deepEqual(budget.snapshot(), { usedBytes: 0, limitBytes: 10 });
});

test("capacity limiter applies reduced limits without cancelling active work", async () => {
  const limiter = new CapacityLimiter({
    limit: 2,
    queueLimit: 2,
    queueTimeoutMs: 1000,
    name: "adaptive capacity",
  });
  const releaseFirst = await limiter.acquire();
  const releaseSecond = await limiter.acquire();
  const third = limiter.acquire();
  const fourth = limiter.acquire();

  limiter.setLimit(1);
  releaseFirst();
  assert.deepEqual(limiter.snapshot(), {
    name: "adaptive capacity",
    limit: 1,
    active: 1,
    queued: 2,
    queueLimit: 2,
    closed: false,
  });
  releaseSecond();
  const releaseThird = await third;
  assert.equal(limiter.snapshot().queued, 1);

  limiter.setLimit(2);
  const releaseFourth = await fourth;
  assert.equal(limiter.snapshot().active, 2);
  releaseThird();
  releaseFourth();
  assert.equal(limiter.snapshot().active, 0);
});

test("capacity lease releases earlier limiters when a later acquisition is cancelled", async () => {
  const first = new CapacityLimiter({
    limit: 1,
    queueLimit: 1,
    queueTimeoutMs: 1000,
    name: "first capacity",
  });
  const second = new CapacityLimiter({
    limit: 1,
    queueLimit: 1,
    queueTimeoutMs: 1000,
    name: "second capacity",
  });
  const releaseSecond = await second.acquire();
  const controller = new AbortController();
  const lease = acquireCapacityLease([first, second], controller.signal);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(
    {
      first: first.snapshot(),
      second: second.snapshot(),
    },
    {
      first: {
        name: "first capacity",
        limit: 1,
        active: 1,
        queued: 0,
        queueLimit: 1,
        closed: false,
      },
      second: {
        name: "second capacity",
        limit: 1,
        active: 1,
        queued: 1,
        queueLimit: 1,
        closed: false,
      },
    },
  );
  controller.abort(new Error("cancel grouped admission"));
  await assert.rejects(lease, /cancel grouped admission/);
  assert.deepEqual(
    {
      first: first.snapshot().active,
      secondQueued: second.snapshot().queued,
    },
    { first: 0, secondQueued: 0 },
  );
  releaseSecond();
});

test("retry coordinator exposes shared provider backoff and resets on success", () => {
  const retry = new RetryCoordinator();
  retry.defer("xai", 5000);
  assert.equal(retry.snapshot().xai.consecutiveFailures, 1);
  assert.ok(retry.snapshot().xai.retryInMs > 0);
  retry.success("xai");
  assert.deepEqual(retry.snapshot().xai, {
    consecutiveFailures: 0,
    retryInMs: 0,
  });
});

test("retry coordinator coalesces concurrent failures into one backoff round", () => {
  let now = 0;
  const retry = new RetryCoordinator({ now: () => now });
  retry.defer("kimi", 5_000);
  now = 100;
  retry.defer("kimi", 5_000);
  assert.deepEqual(retry.snapshot().kimi, {
    consecutiveFailures: 1,
    retryInMs: 5_000,
  });
  now = 5_101;
  retry.defer("kimi", 0);
  assert.deepEqual(retry.snapshot().kimi, {
    consecutiveFailures: 2,
    retryInMs: 2_000,
  });
});

test("retry coordinator rejects waits that exceed a request retry budget", async () => {
  const retry = new RetryCoordinator();
  retry.defer("xai", 5_000);
  await assert.rejects(retry.wait("xai", undefined, 10), {
    code: "alta_retry_budget_exhausted",
    retryable: false,
  });
});

test("provider concurrency halves on overload and recovers additively", () => {
  const limiter = new CapacityLimiter({
    limit: 8,
    queueLimit: 0,
    queueTimeoutMs: 1000,
    name: "provider capacity",
  });
  let now = 0;
  const controller = new ProviderConcurrencyController(
    new Map([["xai", limiter]]),
    {
      recoverySuccesses: 1,
      reductionCooldownMs: 100,
      now: () => now,
    },
  );

  controller.overload("xai");
  controller.overload("xai");
  assert.equal(controller.snapshot().xai.currentLimit, 4);
  now = 100;
  controller.overload("xai");
  assert.deepEqual(controller.snapshot().xai, {
    configuredLimit: 8,
    currentLimit: 2,
    recoveryProgress: 0,
    reductions: 2,
  });
  controller.success("xai");
  controller.success("xai");
  assert.deepEqual(controller.snapshot().xai, {
    configuredLimit: 8,
    currentLimit: 3,
    recoveryProgress: 0,
    reductions: 2,
  });
  assert.equal(limiter.snapshot().limit, 3);
});

test("latency metrics retain bounded per-provider moving averages", () => {
  const metrics = new LatencyMetrics();
  metrics.observe("kimi", {
    queueMs: 10,
    upstreamMs: 100,
    totalMs: 120,
    succeeded: true,
  });
  metrics.observe("kimi", {
    queueMs: 18,
    upstreamMs: 180,
    totalMs: 200,
    succeeded: false,
  });
  assert.deepEqual(metrics.snapshot(), {
    kimi: {
      samples: 2,
      failures: 1,
      queueMsEwma: 11,
      upstreamMsEwma: 110,
      totalMsEwma: 130,
    },
  });
});
