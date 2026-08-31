import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  CredentialHealthMonitor,
  mergeCredentialHealth,
} from "../credential-health.mjs";

function fixture(t) {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-health-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  return stateDir;
}

test("credential health classifies provider responses without persisting secrets", async (t) => {
  const stateDir = fixture(t);
  const secrets = {
    deepseek: "sk-" + "deepseek_health_fixture_12345678901234567890",
    finnhub: "finnhub_health_fixture_1234567890",
    brave: "BSA" + "health_fixture_12345678901234567890",
  };
  const fetchImpl = async (target, options) => {
    const url = String(target);
    if (url.includes("deepseek")) {
      assert.equal(options.headers.Authorization, `Bearer ${secrets.deepseek}`);
      return new Response(null, { status: 200 });
    }
    if (url.includes("finnhub")) {
      assert(url.includes(encodeURIComponent(secrets.finnhub)));
      return new Response(null, { status: 401 });
    }
    assert.equal(options.headers["X-Subscription-Token"], secrets.brave);
    return new Response(null, { status: 429 });
  };
  const monitor = new CredentialHealthMonitor({
    stateDir,
    fetchImpl,
    now: () => Date.parse("2026-08-30T12:00:00.000Z"),
  });

  const health = await monitor.verify({
    revision: "0123456789abcdef",
    values: secrets,
    env: {},
    force: true,
  });

  assert.equal(health.slots.deepseek.status, "healthy");
  assert.equal(health.slots.finnhub.status, "auth_rejected");
  assert.equal(health.slots.brave.status, "rate_limited");
  const persisted = fs.readFileSync(monitor.file, "utf8");
  for (const secret of Object.values(secrets))
    assert.equal(persisted.includes(secret), false);
  assert.equal(fs.statSync(monitor.file).mode & 0o777, 0o600);
});

test("credential health is revision-bound, cached, and degrades network errors safely", async (t) => {
  const stateDir = fixture(t);
  let calls = 0;
  let current = Date.parse("2026-08-30T12:00:00.000Z");
  const monitor = new CredentialHealthMonitor({
    stateDir,
    fetchImpl: async () => {
      calls += 1;
      throw new Error("fixture transport detail that must not escape");
    },
    now: () => current,
    ttlMs: 60_000,
  });
  const values = { kimi: "sk-" + "kimi_health_fixture_12345678901234567890" };

  const first = await monitor.verify({
    revision: "aaaaaaaaaaaaaaaa",
    values,
    env: {},
  });
  const cached = await monitor.verify({
    revision: "aaaaaaaaaaaaaaaa",
    values,
    env: {},
  });

  assert.equal(calls, 1);
  assert.equal(first.slots.kimi.status, "unavailable");
  assert.equal(first.slots.kimi.reason, "network_error");
  assert.deepEqual(cached, first);
  assert.equal(
    JSON.stringify(first).includes("fixture transport detail"),
    false,
  );
  assert.equal(monitor.publicState("bbbbbbbbbbbbbbbb").checkedAt, null);
  current += 61_000;
  assert.equal(monitor.publicState("aaaaaaaaaaaaaaaa").stale, true);
});

test("credential inventory merge distinguishes unverified, missing, and no-key providers", () => {
  const inventory = {
    revision: "aaaaaaaaaaaaaaaa",
    slots: [
      { slot: "deepseek", configured: true },
      { slot: "brave", configured: false },
      { slot: "jina", configured: false, availableWithoutCredential: true },
    ],
  };
  const merged = mergeCredentialHealth(inventory, {
    checkedAt: null,
    expiresAt: null,
    stale: true,
    slots: {},
  });

  assert.equal(merged.slots[0].verification.status, "unverified");
  assert.equal(merged.slots[1].verification.status, "not_configured");
  assert.equal(merged.slots[2].verification.status, "not_required");
});

test("credential health cache is schema-filtered before crossing the browser boundary", (t) => {
  const stateDir = fixture(t);
  const monitor = new CredentialHealthMonitor({ stateDir });
  const injected = "must-not-cross-the-health-cache-boundary";
  fs.mkdirSync(path.dirname(monitor.file), { recursive: true, mode: 0o700 });
  fs.writeFileSync(
    monitor.file,
    JSON.stringify({
      version: 1,
      revision: "aaaaaaaaaaaaaaaa",
      checkedAt: "2026-08-30T12:00:00.000Z",
      slots: {
        deepseek: {
          status: "healthy",
          reason: null,
          checkedAt: "2026-08-30T12:00:00.000Z",
          latencyMs: 12,
          httpStatus: 200,
          providerBody: injected,
        },
        injected: { status: "healthy", secret: injected },
      },
      secret: injected,
    }),
    { mode: 0o600 },
  );

  const publicState = monitor.publicState("aaaaaaaaaaaaaaaa");

  assert.equal(publicState.slots.deepseek.status, "healthy");
  assert.equal(publicState.slots.injected, undefined);
  assert.equal(JSON.stringify(publicState).includes(injected), false);
});
