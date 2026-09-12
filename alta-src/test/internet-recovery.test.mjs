import test from "node:test";
import assert from "node:assert/strict";
import { BackendHealth } from "../internet/backend-health.mjs";
import { executeSearch } from "../internet/search.mjs";
import { runSource } from "../internet/plugins/source-runtime.mjs";

function recoveryHealth(name) {
  let now = 0;
  const health = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
    now: () => now,
  });
  health.failed(name, Object.assign(new Error("unavailable"), { status: 503 }));
  now = 101;
  return health;
}

const searchArgs = {
  query: "issuer revenue",
  maximum: 5,
  depth: "quick",
  allowed: [],
  excluded: [],
  freshness: "",
  language: "",
  backend: "auto",
};

const sourceResponse = {
  output: [
    {
      type: "message",
      content: [
        {
          type: "output_text",
          text: "Source https://issuer.example/earnings",
        },
      ],
    },
  ],
};

test("aborting a half-open search probe permits the next recovery attempt", async () => {
  const backendHealth = recoveryHealth("xai");
  const controller = new AbortController();
  let calls = 0;
  const context = {
    backendHealth,
    xaiSearch: async () => {
      calls += 1;
      if (calls === 1) {
        controller.abort(new Error("research turn cancelled"));
        throw controller.signal.reason;
      }
      return sourceResponse;
    },
  };

  await assert.rejects(
    executeSearch(context, searchArgs, controller.signal),
    /research turn cancelled/,
  );
  assert.equal(backendHealth.snapshot().xai.state, "closed");
  assert.equal(backendHealth.snapshot().xai.opens, 1);
  const recovered = await executeSearch(context, searchArgs);
  assert.equal(recovered.backend, "xai");
  assert.equal(calls, 2);
  assert.equal(backendHealth.snapshot().xai.lastError, "");
});

test("late completion after cancellation cannot be counted as search success", async () => {
  const backendHealth = recoveryHealth("xai");
  const controller = new AbortController();
  await assert.rejects(
    executeSearch(
      {
        backendHealth,
        xaiSearch: async () => {
          controller.abort(new Error("cancelled while source completed"));
          return sourceResponse;
        },
      },
      searchArgs,
      controller.signal,
    ),
    /cancelled while source completed/,
  );
  assert.equal(backendHealth.snapshot().xai.lastError, "unavailable");
  assert.equal(backendHealth.snapshot().xai.opens, 1);
  assert.ok(backendHealth.acquire("xai"));
});

test("late stale settlements cannot release another request's recovery probe", () => {
  const health = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
  });
  const first = health.acquire("source");
  const oldConcurrent = health.acquire("source");
  health.failed("source", { status: 503, message: "outage" }, first);
  const probe = health.acquire("source", { force: true });
  assert.ok(probe);

  health.succeeded("source", oldConcurrent);
  health.failed("source", { status: 503, message: "late" }, oldConcurrent);
  health.cancelled("source", oldConcurrent);
  assert.equal(health.snapshot().source.opens, 1);
  assert.equal(health.snapshot().source.lastError, "outage");
  assert.equal(health.acquire("source", { force: true }), null);

  health.cancelled("source", probe);
  const replacement = health.acquire("source", { force: true });
  assert.ok(replacement);
  health.succeeded("source", probe);
  health.failed("source", { status: 503, message: "old probe" }, probe);
  health.cancelled("source", probe);
  assert.equal(health.acquire("source", { force: true }), null);
  health.succeeded("source", replacement);
  assert.equal(health.snapshot().source.state, "closed");
  assert.equal(health.snapshot().source.lastError, "");
});

test("parallel closed-circuit failures still reach the configured threshold", () => {
  const health = new BackendHealth({ failureThreshold: 2 });
  const first = health.acquire("source");
  const second = health.acquire("source");
  health.failed("source", { status: 503 }, first);
  assert.equal(health.snapshot().source.opens, 0);
  health.failed("source", { status: 503 }, second);
  assert.equal(health.snapshot().source.opens, 1);
  assert.equal(health.acquire("source"), null);
});

test("cancelled source probes recover without recording provider failure", async () => {
  const name = "finance:issuer";
  const backendHealth = recoveryHealth(name);
  const service = { backendHealth };
  const controller = new AbortController();
  await assert.rejects(
    runSource(
      service,
      "finance",
      "issuer",
      { signal: controller.signal },
      () => {
        controller.abort(new Error("source cancelled"));
        throw controller.signal.reason;
      },
    ),
    /source cancelled/,
  );
  assert.equal(backendHealth.snapshot()[name].opens, 1);
  assert.equal(
    await runSource(service, "finance", "issuer", {}, () => "recovered"),
    "recovered",
  );
  assert.equal(backendHealth.snapshot()[name].lastError, "");
});

test("already-cancelled work neither claims a probe nor consumes source pacing", async () => {
  const backendHealth = recoveryHealth("finance:issuer");
  const controller = new AbortController();
  controller.abort(new Error("already cancelled"));
  let calls = 0;
  const operation = () => {
    calls += 1;
    return "ready";
  };
  const service = { backendHealth };
  await assert.rejects(
    runSource(
      service,
      "finance",
      "issuer",
      { signal: controller.signal },
      operation,
      { intervalMs: 10_000 },
    ),
    /already cancelled/,
  );
  assert.equal(
    await runSource(service, "finance", "issuer", {}, operation, {
      intervalMs: 10_000,
    }),
    "ready",
  );
  assert.equal(calls, 1);
});
