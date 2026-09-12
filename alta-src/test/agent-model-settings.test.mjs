import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { AgentModelSettings } from "../agent-model-settings.mjs";
import { createOperatorConsole } from "../operator-console.mjs";
import { acquireLease } from "../storage.mjs";

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-model-settings-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return { dir, store: new AgentModelSettings(dir, () => ({})) };
}
test("model assignments persist atomically, preserve defaults and fence stale writers", (t) => {
  const { dir, store } = fixture(t);
  const current = store.read();
  const settings = structuredClone(current.settings);
  settings.roles.position = { provider: "kimi", model: "kimi-k3" };
  settings.scouts.change_event_scout = { provider: "grok", model: "grok-4.6" };
  const saved = store.save({ revision: current.revision, settings });
  assert.notEqual(saved.revision, current.revision);
  assert.deepEqual(new AgentModelSettings(dir, () => ({})).read(), saved);
  assert.equal(fs.statSync(store.file).mode & 0o777, 0o600);
  assert.equal(store.runtimeEnvironment().ALTA_POSITION_MODEL, "kimi-k3");
  assert.deepEqual(
    JSON.parse(store.runtimeEnvironment().ALTA_SCOUT_MODEL_OVERRIDES),
    settings.scouts,
  );
  assert.throws(() => store.save({ revision: current.revision, settings }), {
    code: "model_settings_conflict",
  });
});
test("reject invalid roles, provider mismatches, secrets, unknown Scouts and lost independence", (t) => {
  const { store } = fixture(t);
  const before = store.read();
  for (const mutate of [
    (s) => {
      s.roles.scout.model = "grok-4.6";
    },
    (s) => {
      s.roles.scout.secret = "must-not-be-accepted";
    },
    (s) => {
      s.roles.scout.provider = "__proto__";
    },
    (s) => {
      s.scouts.unknown = s.roles.scout;
    },
    (s) => {
      delete s.roles.audit;
    },
    (s) => {
      s.roles.disconfirming = s.roles.thesis;
    },
    (s) => {
      s.roles.audit = s.roles.expression;
    },
  ]) {
    const settings = structuredClone(before.settings);
    mutate(settings);
    assert.throws(() => store.save({ revision: before.revision, settings }));
    assert.deepEqual(store.read(), before);
  }
});
test("corrupt configuration fails closed instead of reverting to defaults", (t) => {
  const { store } = fixture(t);
  const { revision, settings } = store.read();
  store.save({ revision, settings });
  fs.writeFileSync(store.file, "{bad-json", { mode: 0o600 });
  assert.throws(() => store.read(), { code: "model_settings_unreadable" });
  assert.throws(() => store.runtimeEnvironment(), {
    code: "model_settings_unreadable",
  });
});
test("model API requires session, CSRF and a stopped runtime, and fences concurrent start", async (t) => {
  const { dir, store } = fixture(t);
  fs.writeFileSync(path.join(dir, "index.html"), "<h1>Test</h1>");
  let active = false;
  let probe = null;
  const service = {
    stateDir: dir,
    tokenFile: path.join(dir, "token"),
    modelSettings: store,
    status: async () => {
      if (probe) await probe.promise;
      return { ready: active, host: { processAlive: active }, supervisor: {} };
    },
    runtimeEnvironment: () => ({ environment: {} }),
  };
  const operator = createOperatorConsole({
    port: 0,
    staticDir: dir,
    service,
    environmentFactory: () => ({ status: async () => ({}) }),
  });
  const location = await operator.listen();
  t.after(() => operator.close());
  const endpoint = location.origin + "/control/agent-models";
  assert.equal((await fetch(endpoint)).status, 401);
  const response = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = response.headers.get("set-cookie").split(";", 1)[0];
  const bootstrap = await (
    await fetch(location.origin + "/control/bootstrap", {
      headers: { Cookie: cookie },
    })
  ).json();
  const headers = {
    "Cookie": cookie,
    "Origin": location.origin,
    "Content-Type": "application/json",
    "X-ALTA-CSRF": bootstrap.data.csrfToken,
  };
  const { revision, settings } = store.read();
  const body = JSON.stringify({ revision, settings });
  assert.equal(
    (
      await fetch(endpoint, {
        method: "PUT",
        headers: { "Cookie": cookie, "Content-Type": "application/json" },
        body,
      })
    ).status,
    403,
  );
  active = true;
  assert.equal(
    (await fetch(endpoint, { method: "PUT", headers, body })).status,
    409,
  );
  active = false;
  const hostLease = acquireLease(
    path.join(dir, "runtime", "opportunity-host.lock"),
  );
  try {
    assert.equal(
      (await fetch(endpoint, { method: "PUT", headers, body })).status,
      409,
    );
  } finally {
    hostLease.release();
  }
  assert.equal(
    (await fetch(endpoint, { method: "PUT", headers, body })).status,
    200,
  );
  probe = Promise.withResolvers();
  const saving = fetch(endpoint, { method: "PUT", headers, body });
  await new Promise((resolve) => setTimeout(resolve, 30));
  const start = await fetch(location.origin + "/control/runtime/start", {
    method: "POST",
    headers,
  });
  assert.equal(start.status, 409);
  probe.resolve();
  probe = null;
  assert.equal((await saving).status, 200);
});
