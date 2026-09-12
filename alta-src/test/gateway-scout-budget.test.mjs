import assert from "node:assert/strict";
import test from "node:test";
import { admitBoundedScoutToolCall as admit } from "../gateway-scout-budget.mjs";

const call = { method: "tools/call" };
function request(attempt, limit = "2", run = "a".repeat(32)) {
  return {
    headers: {
      "x-alta-run-id": `run_${run}`,
      "x-alta-max-tool-calls": limit,
      ...(attempt === undefined
        ? {}
        : { "x-alta-attempt-id": attempt.repeat(64) }),
    },
  };
}

test("research retries get bounded fresh capacity; reconnects do not reset it", () => {
  const context = {};
  for (const attempt of ["a", "b", "c"]) {
    assert.equal(admit(request(attempt), context, call).remaining, 1);
    assert.equal(admit(request(attempt), context, call).remaining, 0);
    assert.throws(
      () => admit(request(attempt), context, call),
      /tool call budget exhausted/,
    );
  }
  assert.throws(
    () => admit(request("d"), context, call),
    /retry budget exhausted/,
  );
  assert.throws(
    () => admit(request("a"), context, call),
    /tool call budget exhausted/,
  );
  assert.equal(context.scoutToolCalls.size, 1);
});

test("budget scopes reject malformed headers and mid-run cap increases", () => {
  const context = {};
  for (const invalid of [
    request("x"),
    request("a", "13"),
    request("a", "2", "oops"),
  ]) {
    assert.throws(() => admit(invalid, context, call), /Invalid.*headers/);
  }
  assert.equal(context.scoutToolCalls, undefined);
  admit(request("a"), context, call);
  assert.throws(() => admit(request("b", "3"), context, call), /cannot change/);
  assert.equal(admit(request("b"), context, call).remaining, 1);
});

test("legacy budgets remain bounded and non-call messages consume nothing", () => {
  const context = {};
  assert.equal(admit({ headers: {} }, context, call), null);
  assert.equal(admit(request("a"), context, { method: "tools/list" }), null);
  assert.equal(context.scoutToolCalls, undefined);
  assert.equal(admit(request(undefined, "1"), context, call).remaining, 0);
  assert.throws(
    () => admit(request(undefined, "1"), context, call),
    /exhausted/,
  );
  assert.throws(
    () => admit(request("a", "0", "b".repeat(32)), context, call),
    /exhausted/,
  );
});

test("capacity pressure cannot evict a recent run and reset its exhausted budget", () => {
  const context = {};
  for (let index = 0; index < 1_000; index += 1)
    admit(
      request("a", "1", index.toString(16).padStart(32, "0")),
      context,
      call,
    );
  assert.throws(
    () => admit(request("a", "1"), context, call),
    /registry is full/,
  );
  assert.throws(
    () => admit(request("a", "1", "0".repeat(32)), context, call),
    /exhausted/,
  );
  assert.equal(context.scoutToolCalls.size, 1_000);
});

test("day-old registry entries expire without resetting other tracked runs", () => {
  const context = {};
  admit(request("a", "1"), context, call);
  const old = context.scoutToolCalls.get(`run_${"a".repeat(32)}`);
  old.createdAt -= 24 * 60 * 60 * 1_000;
  admit(request("a", "1", "b".repeat(32)), context, call);
  assert.equal(context.scoutToolCalls.has(`run_${"a".repeat(32)}`), false);
  assert.throws(
    () => admit(request("a", "1", "b".repeat(32)), context, call),
    /exhausted/,
  );
});
