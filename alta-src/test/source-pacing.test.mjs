import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { setTimeout as delay } from "node:timers/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { BackendHealth } from "../internet/backend-health.mjs";
import { InternetService } from "../internet/service.mjs";
import { SourcePacer } from "../internet/source-pacer.mjs";
import { runSource } from "../internet/plugins/source-runtime.mjs";

test("small source bursts dispatch FIFO at provider intervals, not completion times", async () => {
  const service = { backendHealth: new BackendHealth() };
  const starts = [];
  let active = 0;
  let maximum = 0;
  const values = await Promise.all(
    Array.from({ length: 4 }, (_, index) =>
      runSource(
        service,
        "finance",
        "issuer",
        {},
        async () => {
          starts.push({ index, at: performance.now() });
          active += 1;
          maximum = Math.max(maximum, active);
          await delay(65);
          active -= 1;
          return index;
        },
        { intervalMs: 20 },
      ),
    ),
  );
  assert.deepEqual(values, [0, 1, 2, 3]);
  assert.deepEqual(
    starts.map(({ index }) => index),
    values,
  );
  for (let index = 1; index < starts.length; index += 1)
    assert.ok(starts[index].at - starts[index - 1].at >= 19);
  assert.ok(
    maximum > 1,
    "pacing must not replace the HTTP concurrency limiter",
  );
});

test("a full source queue rejects excess work and cancellation frees capacity", async () => {
  const pacer = new SourcePacer({ maxQueue: 2 });
  let calls = 0;
  const request = (signal) =>
    pacer.schedule({
      name: "source",
      intervalMs: 100,
      signal,
      admit: () => true,
      execute: () => ++calls,
    });
  assert.equal(await request(), 1);
  const first = new AbortController();
  const second = new AbortController();
  const firstWaiting = request(first.signal);
  const secondWaiting = request(second.signal);
  await assert.rejects(request(), {
    status: 429,
    code: "alta_source_paced",
    message: "source local source queue is full",
  });
  const firstRejected = assert.rejects(firstWaiting, /first cancelled/);
  first.abort(new Error("first cancelled"));
  await firstRejected;
  const replacement = new AbortController();
  const replacementWaiting = request(replacement.signal);
  const secondRejected = assert.rejects(secondWaiting, /second cancelled/);
  const replacementRejected = assert.rejects(replacementWaiting, /replacement/);
  second.abort(new Error("second cancelled"));
  replacement.abort(new Error("replacement cancelled"));
  await Promise.all([secondRejected, replacementRejected]);
  assert.equal(calls, 1);
});

test("source admission has an independent hard wait bound", async () => {
  const pacer = new SourcePacer({ maxWaitMs: 15 });
  let admissions = 0;
  const request = () =>
    pacer.schedule({
      name: "slow-provider",
      intervalMs: 100,
      admit: () => ++admissions,
      execute: (admission) => admission,
    });
  assert.equal(await request(), 1);
  await assert.rejects(request(), {
    code: "alta_source_paced",
    message: "slow-provider exceeded its 15 ms local queue wait",
  });
  assert.equal(admissions, 1);
  assert.throws(() => new SourcePacer({ maxQueue: 9 }), RangeError);
  assert.throws(() => new SourcePacer({ maxWaitMs: 15_001 }), RangeError);
});

test("cancelled queued sources consume neither circuit admission nor dispatch slots", async () => {
  const backendHealth = new BackendHealth();
  const acquired = [];
  const acquire = backendHealth.acquire.bind(backendHealth);
  backendHealth.acquire = (name) => {
    acquired.push(name);
    return acquire(name);
  };
  const service = { backendHealth };
  const starts = [];
  const request = (index, signal) =>
    runSource(
      service,
      "finance",
      "issuer",
      { signal },
      () => {
        starts.push(index);
        return index;
      },
      { intervalMs: 20 },
    );
  await request(0);
  const controller = new AbortController();
  const cancelled = request(1, controller.signal);
  const survivor = request(2);
  const rejection = assert.rejects(cancelled, /queued cancelled/);
  controller.abort(new Error("queued cancelled"));
  await rejection;
  assert.equal(await survivor, 2);
  assert.deepEqual(starts, [0, 2]);
  assert.equal(acquired.length, 2);
  assert.deepEqual(backendHealth.snapshot(), {});
});

test("circuit suppression does not consume a provider dispatch slot", async () => {
  let now = 0;
  const name = "finance:issuer";
  const backendHealth = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
    now: () => now,
  });
  backendHealth.failed(name, { status: 503, message: "outage" });
  const service = { backendHealth };
  let calls = 0;
  const request = () =>
    runSource(service, "finance", "issuer", {}, () => ++calls, {
      intervalMs: 100,
    });
  await assert.rejects(request(), { code: "alta_source_circuit_open" });
  now = 101;
  const recovered = request();
  assert.equal(
    calls,
    1,
    "denied request must leave an immediate recovery slot",
  );
  assert.equal(await recovered, 1);
  assert.equal(backendHealth.snapshot()[name].state, "closed");
});

test("queued work cannot use an old circuit lease after a concurrent failure opens it", async () => {
  let now = 0;
  const backendHealth = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
    now: () => now,
  });
  const service = { backendHealth };
  let calls = 0;
  let rejectFirst;
  const request = () =>
    runSource(
      service,
      "finance",
      "issuer",
      {},
      () => {
        calls += 1;
        return calls === 1
          ? new Promise((_, reject) => {
              rejectFirst = reject;
            })
          : "recovered";
      },
      { intervalMs: 20 },
    );
  const first = request();
  const waiting = request();
  const firstRejected = assert.rejects(first, /outage/);
  const queuedRejected = assert.rejects(waiting, {
    code: "alta_source_circuit_open",
  });
  rejectFirst(Object.assign(new Error("outage"), { status: 503 }));
  await Promise.all([firstRejected, queuedRejected]);
  assert.equal(calls, 1);
  now = 101;
  const recovered = request();
  assert.equal(
    calls,
    2,
    "circuit-denied queued work must not reserve another slot",
  );
  assert.equal(await recovered, "recovered");
});

test("queued cancellation does not claim or release a half-open recovery probe", async () => {
  let now = 0;
  const name = "finance:issuer";
  const backendHealth = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 100,
    now: () => now,
  });
  const service = { backendHealth };
  const request = (signal) =>
    runSource(service, "finance", "issuer", { signal }, () => "ok", {
      intervalMs: 100,
    });
  await request();
  backendHealth.failed(name, { status: 503, message: "outage" });
  now = 101;
  const controller = new AbortController();
  const waiting = request(controller.signal);
  const recovery = backendHealth.acquire(name);
  assert.ok(recovery, "queued work must not pre-claim the recovery probe");
  const rejection = assert.rejects(waiting, /cancelled/);
  controller.abort(new Error("cancelled"));
  await rejection;
  assert.equal(backendHealth.acquire(name), null);
  backendHealth.succeeded(name, recovery);
  assert.equal(backendHealth.snapshot()[name].state, "closed");
});

test("independent source lanes do not wait behind another provider's queue", async () => {
  const service = {};
  let calls = 0;
  const request = (source, signal) =>
    runSource(service, "finance", source, { signal }, () => ++calls, {
      intervalMs: 100,
    });
  await request("first");
  const controller = new AbortController();
  const waiting = request("first", controller.signal);
  assert.equal(await request("second"), 2);
  const rejection = assert.rejects(waiting, /cancelled/);
  controller.abort(new Error("cancelled"));
  await rejection;
  assert.equal(calls, 2);
});

test("service close drains unsignalled source queues and leaves no pacing timers", async () => {
  // A separate process must exit itself: leaked 10-second pacing timers would
  // make execFile time out. No network or real provider is involved.
  const serviceModule = new URL("../internet/service.mjs", import.meta.url)
    .href;
  const sourceModule = new URL(
    "../internet/plugins/source-runtime.mjs",
    import.meta.url,
  ).href;
  const script = `
    import assert from "node:assert/strict";
    import { InternetService } from ${JSON.stringify(serviceModule)};
    import { runSource } from ${JSON.stringify(sourceModule)};
    const service = new InternetService({ env: {} });
    let calls = 0;
    const request = (source) => runSource(
      service, "test", source, undefined, () => ++calls,
      { intervalMs: 10_000 },
    );
    await request("first");
    await request("second");
    const queued = [request("first"), request("first"), request("second")];
    service.close();
    service.close();
    for (const pending of queued)
      await assert.rejects(pending, { code: "alta_internet_closed" });
    await assert.rejects(request("first"), { code: "alta_internet_closed" });
    await assert.rejects(request("new-source"), { code: "alta_internet_closed" });
    await assert.rejects(
      runSource(service, "test", "unpaced", {}, () => ++calls),
      { code: "alta_internet_closed" },
    );
    assert.equal(calls, 2);
    assert.deepEqual(service.backendHealth.snapshot(), {});
    assert.equal(service.closed, true);
  `;
  const result = await promisify(execFile)(
    process.execPath,
    ["--input-type=module", "--eval", script],
    { timeout: 2_000 },
  );
  assert.equal(result.stderr, "");
});

test("source lifecycle cancellation composes with caller cancellation without circuit failures", async () => {
  const service = new InternetService({ env: {} });
  const controller = new AbortController();
  const active = runSource(
    service,
    "test",
    "active",
    { signal: controller.signal },
    ({ signal }) => delay(10_000, undefined, { signal }),
  );
  const callerRejected = assert.rejects(active, {
    message: "caller cancelled",
  });
  controller.abort(new Error("caller cancelled"));
  await callerRejected;
  assert.equal(service.lifecycleSignal.aborted, false);
  assert.equal(
    await runSource(service, "test", "active", {}, () => "still open"),
    "still open",
  );
  const pending = runSource(
    service,
    "test",
    "active",
    { signal: new AbortController().signal },
    ({ signal }) => delay(10_000, undefined, { signal }),
  );
  const serviceRejected = assert.rejects(pending, {
    code: "alta_internet_closed",
  });
  service.close();
  await serviceRejected;
  assert.deepEqual(service.backendHealth.snapshot(), {});
});
