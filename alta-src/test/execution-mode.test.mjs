import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash, generateKeyPairSync } from "node:crypto";
import test from "node:test";
import { executionMode, validateModeRequest } from "../execution-mode.mjs";
import {
  tigerCredentialText,
  replaceTigerCredentials,
} from "../tiger-credential-settings.mjs";
import { createOperatorConsole } from "../operator-console.mjs";
import { acquireLease } from "../storage.mjs";

const account = "0".repeat(17);
// Generated in memory; no reusable private key is committed to a fixture.
const privateKey = generateKeyPairSync("rsa", { modulusLength: 2048 })
  .privateKey.export({ type: "pkcs8", format: "pem" })
  .toString();
const credentials = () => ({ tigerId: "0000", account, privateKey });
const state = (extra = {}) => ({
  requestedEnabled: false,
  enabled: false,
  closeOnly: false,
  configured: false,
  authorizationGeneration: "fixture",
  configurationFingerprint: "fixture",
  posture: "disabled",
  ...extra,
});

test("requested authority, blocked authority, and close-only are not Shadow", () => {
  for (const [status, expected] of [
    [state(), "shadow"],
    [state({ authorizationError: "corrupt" }), "blocked"],
    [state({ requestedEnabled: true, enabled: true }), "broker_paper"],
    [state({ requestedEnabled: true }), "blocked"],
    [
      state({ requestedEnabled: true, enabled: true, closeOnly: true }),
      "close_only",
    ],
  ])
    assert.equal(executionMode(status).effective, expected);
  const status = state();
  const request = {
    mode: "broker_paper",
    confirmation: "ENABLE TIGER PAPER",
    revision: executionMode(status).revision,
  };
  assert.equal(validateModeRequest(request, status), "broker_paper");
  assert.throws(
    () => validateModeRequest({ ...request, revision: "stale" }, status),
    { code: "execution_mode_conflict" },
  );
  for (const invalid of [
    null,
    [],
    { ...request, mode: "live" },
    { ...request, confirmation: "yes" },
    { ...request, secret: "unexpected" },
  ])
    assert.throws(() => validateModeRequest(invalid, status), {
      code: "execution_mode_invalid",
    });
});

test("Paper credential intake rejects weak keys, malformed input and non-Paper accounts", () => {
  const text = tigerCredentialText(credentials());
  assert.equal(
    tigerCredentialText({
      ...credentials(),
      privateKey: privateKey.replaceAll("\n", ""),
    }),
    text,
  );
  assert.match(text, /^tiger_id=0000\naccount=0{17}\nprivate_key_pk8=/);
  const der = privateKey.replace(/-----(?:BEGIN|END) PRIVATE KEY-----|\s/g, "");
  assert.equal(
    tigerCredentialText({ ...credentials(), privateKey: der }),
    text,
  );
  for (const invalid of [
    null,
    [],
    { ...credentials(), account: "1234567" },
    { ...credentials(), tigerId: 1000 },
    { ...credentials(), account: 0 },
    { ...credentials(), privateKey: "invalid" },
    { ...credentials(), extra: true },
    {
      ...credentials(),
      privateKey: generateKeyPairSync("rsa", { modulusLength: 1024 })
        .privateKey.export({ type: "pkcs8", format: "pem" })
        .toString(),
    },
    {
      ...credentials(),
      privateKey: generateKeyPairSync("ed25519")
        .privateKey.export({ type: "pkcs8", format: "pem" })
        .toString(),
    },
  ])
    assert.throws(
      () => tigerCredentialText(invalid),
      (error) => {
        assert.equal(error.message.includes(privateKey), false);
        return /^tiger_/.test(error.code);
      },
    );
});

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-execution-modes-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const root = path.join(dir, "project");
  const credentialRoot = path.join(dir, "credentials");
  const file = path.join(
    credentialRoot,
    "broker",
    "tiger_openapi_config.properties",
  );
  let current = state();
  const capital = {
    operationLockFile: path.join(dir, "capital.lock"),
    status: () => current,
    environment: () => ({ ALTA_CREDENTIALS_DIR: credentialRoot }),
    configuration: () => ({
      accountSha256: createHash("sha256").update(account).digest("hex"),
    }),
  };
  return {
    dir,
    root,
    file,
    capital,
    set: (value) => {
      current = value;
    },
    body: () => ({
      credentials: credentials(),
      revision: executionMode(current).revision,
    }),
  };
}

test("credential save is external, write-only, atomic and recoverable", (t) => {
  const f = fixture(t);
  const result = replaceTigerCredentials(f.capital, f.body(), f.root);
  assert.equal(fs.statSync(f.file).mode & 0o777, 0o600);
  assert.equal(fs.statSync(path.dirname(f.file)).mode & 0o777, 0o700);
  assert.equal(JSON.stringify(result).includes(privateKey), false);
  const before = fs.readFileSync(f.file);
  f.capital.configuration = () => {
    throw new Error("configuration rejected");
  };
  assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
    code: "tiger_credentials_invalid",
  });
  assert.deepEqual(fs.readFileSync(f.file), before);
  assert.equal(fs.existsSync(f.capital.operationLockFile), false);
});

test("credential replacement fences authority, process locks, revision, and account swaps", (t) => {
  const f = fixture(t);
  for (const current of [
    state({ requestedEnabled: true }),
    state({ authorizationError: "unreadable" }),
  ]) {
    f.set(current);
    assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
      code: "broker_authority_must_be_disabled",
    });
  }
  f.set(state());
  assert.throws(
    () =>
      replaceTigerCredentials(
        f.capital,
        { ...f.body(), revision: "stale" },
        f.root,
      ),
    { code: "execution_mode_conflict" },
  );
  const lease = acquireLease(f.capital.operationLockFile);
  assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
    code: "capital_operation_in_progress",
  });
  lease.release();
  f.capital.configuration = () => ({ accountSha256: "a".repeat(64) });
  for (const snapshot of [
    null,
    {
      positionCount: 1,
      openOrderCount: 0,
      observedAt: new Date().toISOString(),
    },
    {
      positionCount: 0,
      openOrderCount: 1,
      observedAt: new Date().toISOString(),
    },
    { positionCount: 0, openOrderCount: 0, observedAt: "invalid" },
    {
      positionCount: 0,
      openOrderCount: 0,
      observedAt: new Date(Date.now() + 10000).toISOString(),
    },
    {
      positionCount: 0,
      openOrderCount: 0,
      observedAt: new Date(Date.now() - 61000).toISOString(),
    },
  ]) {
    f.set(state({ configured: true, snapshot }));
    assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
      code: "broker_account_change_requires_empty_snapshot",
    });
  }
  assert.equal(fs.existsSync(f.file), false);
  f.set(
    state({
      configured: true,
      snapshot: {
        positionCount: 0,
        openOrderCount: 0,
        observedAt: new Date().toISOString(),
      },
    }),
  );
  replaceTigerCredentials(f.capital, f.body(), f.root);
  assert.equal(fs.existsSync(f.file), true);
});

test("credential replacement refuses an environment override or in-repository storage", (t) => {
  const f = fixture(t);
  f.capital.environment = () => ({
    ALTA_TIGER_CONFIG_PATH: "/operator-managed/config",
  });
  assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
    code: "broker_environment_override",
  });
  f.capital.environment = () => ({
    ALTA_CREDENTIALS_DIR: path.join(f.root, "secrets"),
  });
  assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
    code: "broker_credentials_require_external_storage",
  });
  fs.mkdirSync(f.root, { recursive: true });
  const alias = path.join(f.dir, "external-alias");
  fs.symlinkSync(f.root, alias);
  f.capital.environment = () => ({
    ALTA_CREDENTIALS_DIR: path.join(alias, "credentials"),
  });
  assert.throws(() => replaceTigerCredentials(f.capital, f.body(), f.root), {
    code: "broker_credentials_require_external_storage",
  });
});

test("mode and credential endpoints enforce session, CSRF, stopped runtime and shared lease", async (t) => {
  const f = fixture(t);
  fs.writeFileSync(path.join(f.dir, "index.html"), "<h1>Test</h1>");
  let active = false;
  let calls = 0;
  const service = {
    stateDir: f.dir,
    lockFile: path.join(f.dir, "host.lock"),
    tokenFile: path.join(f.dir, "token"),
    status: async () => ({
      ready: active,
      host: { processAlive: active },
      supervisor: {},
    }),
    runtimeEnvironment: () => ({ environment: {} }),
    capitalStatus: () => ({ ...state(), execution: executionMode(state()) }),
    setExecutionMode: () => {
      calls++;
      return service.capitalStatus();
    },
    replaceBrokerCredential: () => {
      calls++;
      return service.capitalStatus();
    },
    brokerConnection: () => {
      calls++;
      return service.capitalStatus();
    },
  };
  const operator = createOperatorConsole({
    port: 0,
    staticDir: f.dir,
    service,
    environmentFactory: () => ({ status: async () => ({}) }),
  });
  const location = await operator.listen();
  t.after(() => operator.close());
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
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
  for (const route of [
    "/control/execution-mode",
    "/control/broker-credentials/tiger",
    "/control/broker-connections",
    "/control/broker-connections/route",
  ]) {
    const endpoint = location.origin + route;
    assert.equal(
      (await fetch(endpoint, { method: "PUT", body: "{}" })).status,
      401,
    );
    assert.equal(
      (
        await fetch(endpoint, {
          method: "PUT",
          headers: { "Cookie": cookie, "Content-Type": "application/json" },
          body: "{}",
        })
      ).status,
      403,
    );
    active = true;
    assert.equal(
      (await fetch(endpoint, { method: "PUT", headers, body: "{}" })).status,
      409,
    );
    active = false;
    const lease = acquireLease(service.lockFile);
    assert.equal(
      (await fetch(endpoint, { method: "PUT", headers, body: "{}" })).status,
      409,
    );
    lease.release();
    const response = await fetch(endpoint, {
      method: "PUT",
      headers,
      body: "{}",
    });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).data.execution.effective, "shadow");
    assert.equal(fs.existsSync(service.lockFile), false);
  }
  assert.equal(calls, 4);
});
