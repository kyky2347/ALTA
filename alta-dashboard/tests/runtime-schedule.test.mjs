import assert from "node:assert/strict";
import test from "node:test";
import { runtimeSchedule } from "../src/lib/runtime-schedule.ts";

test("intentional scheduling disablement is not reported as unavailable", () => {
  assert.equal(
    runtimeSchedule(true, true, {
      config: { autonomousStatus: "disabled", nextCycleAt: "stale" },
    }).key,
    "scheduleDisabled",
  );
});

test("offline snapshots take precedence over their recorded scheduler state", () => {
  assert.equal(
    runtimeSchedule(false, true, {
      config: { autonomousStatus: "running" },
    }).key,
    "savedSnapshot",
  );
});

test("running, scheduled and unavailable remain distinct", () => {
  assert.equal(
    runtimeSchedule(true, true, {
      config: { autonomousStatus: "running" },
    }).key,
    "cycleInProgress",
  );
  const at = "2026-09-12T20:00:00Z";
  assert.deepEqual(
    runtimeSchedule(true, true, { config: { nextCycleAt: at } }),
    { key: "nextCycle", at },
  );
  assert.equal(runtimeSchedule(true, true, null).key, "scheduleUnavailable");
});
