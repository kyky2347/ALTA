import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createOperatorConsole } from "../operator-console.mjs";

test("operator console keeps the API token server-side and protects mutations", async (context) => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "alta-console-"));
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  fs.writeFileSync(path.join(staticDir, "app.js"), "console.log('ALTA')");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "super-secret-token\n", { mode: 0o600 });
  const actions = [];
  let bootstrapUses = 0;
  const service = {
    tokenFile,
    platform: {
      start() {
        actions.push("start");
      },
      restart() {
        actions.push("restart");
      },
    },
    installed: () => true,
    ensureConfiguration() {},
    runtimeEnvironment: () => ({ environment: {} }),
    waitForReadiness: async () => {},
    stop: async () => actions.push("stop"),
    status: async () => ({
      installed: true,
      ready: true,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: "disabled",
    }),
  };
  const environmentFactory = () => ({
    status: async () => ({ docker: { ready: true } }),
    down: async () => actions.push("down"),
  });
  const fetchImpl = async (_target, options) => {
    assert.equal(options.headers.Authorization, "Bearer super-secret-token");
    return new Response(JSON.stringify({ data: { status: "ok" } }), {
      headers: { "Content-Type": "application/json" },
    });
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory,
    fetchImpl,
    onBootstrapUsed: () => {
      bootstrapUses += 1;
    },
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();

  const unauthorized = await fetch(`${location.origin}/control/state`);
  assert.equal(unauthorized.status, 401);

  const open = await fetch(location.openUrl, { redirect: "manual" });
  const issuedCookie = open.headers.get("set-cookie");
  const cookie = issuedCookie.split(";", 1)[0];
  assert.equal(open.status, 303);
  assert.equal(open.headers.get("location"), "/");
  assert(!cookie.includes("super-secret-token"));
  assert.match(issuedCookie, /Max-Age=2592000/);
  const reused = await fetch(location.openUrl, { redirect: "manual" });
  assert.equal(reused.headers.get("set-cookie"), null);
  assert.equal(bootstrapUses, 1);

  const bootstrap = await fetch(`${location.origin}/control/bootstrap`, {
    headers: { Cookie: cookie },
  });
  const bootstrapPayload = await bootstrap.json();
  assert.match(bootstrap.headers.get("set-cookie"), /Max-Age=2592000/);
  assert.equal(bootstrapPayload.data.safety.capitalMode, "disabled");
  assert(bootstrapPayload.data.csrfToken);
  assert.equal(bootstrapPayload.data.console.protocolVersion, 4);

  const ready = await fetch(`${location.origin}/health/ready`);
  assert.deepEqual(await ready.json(), {
    data: { ready: true, protocolVersion: 4 },
  });

  const asset = await fetch(`${location.origin}/app.js`);
  const etag = asset.headers.get("etag");
  assert.equal(await asset.text(), "console.log('ALTA')");
  assert(etag);
  const unchangedAsset = await fetch(`${location.origin}/app.js`, {
    headers: { "If-None-Match": etag },
  });
  assert.equal(unchangedAsset.status, 304);

  const initialIndex = await fetch(location.origin);
  assert.equal(await initialIndex.text(), "<h1>ALTA</h1>");
  assert.equal(initialIndex.headers.get("cache-control"), "no-store");
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA 2</h1>");
  const rebuiltIndex = await fetch(location.origin);
  assert.equal(await rebuiltIndex.text(), "<h1>ALTA 2</h1>");
  const retiredAsset = await fetch(`${location.origin}/assets/retired.js`);
  assert.equal(retiredAsset.status, 404);
  assert.deepEqual(await retiredAsset.json(), {
    error: { code: "asset_not_found" },
  });

  const proxy = await fetch(`${location.origin}/proxy/api/v1/mvp/status`, {
    headers: { Cookie: cookie },
  });
  assert.deepEqual(await proxy.json(), { data: { status: "ok" } });

  const forbidden = await fetch(`${location.origin}/control/runtime/stop`, {
    method: "POST",
    headers: { Cookie: cookie },
  });
  assert.equal(forbidden.status, 403);

  const accepted = await fetch(`${location.origin}/control/runtime/stop`, {
    method: "POST",
    headers: {
      "Cookie": cookie,
      "Origin": location.origin,
      "X-ALTA-CSRF": bootstrapPayload.data.csrfToken,
    },
  });
  assert.equal(accepted.status, 202);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.deepEqual(actions, ["stop", "down"]);

  await operator.close();
});

test("operator console installs an unconfigured runtime during the first start", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-first-start-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  const actions = [];
  let installed = false;
  let ready = false;
  const service = {
    stateDir: temporary,
    tokenFile,
    installed: () => installed,
    runtimeEnvironment: () => ({ environment: { ALTA_FIXTURE: "1" } }),
    assertEndpointAvailable: async () => actions.push("endpoint"),
    install({ start }) {
      assert.equal(start, false);
      installed = true;
      actions.push("install");
    },
    async start() {
      actions.push("start");
      ready = true;
      actions.push("ready");
    },
    status: async () => ({
      installed,
      ready,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: "disabled",
    }),
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory: (environment) => ({
      setup: async () => {
        assert.equal(environment.ALTA_FIXTURE, "1");
        actions.push("setup");
      },
      status: async () => ({}),
    }),
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
  const bootstrap = await fetch(`${location.origin}/control/bootstrap`, {
    headers: { Cookie: cookie },
  }).then((response) => response.json());
  const response = await fetch(`${location.origin}/control/runtime/start`, {
    method: "POST",
    headers: {
      "Cookie": cookie,
      "Origin": location.origin,
      "X-ALTA-CSRF": bootstrap.data.csrfToken,
    },
  });
  assert.equal(response.status, 202);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.deepEqual(actions, ["setup", "endpoint", "install", "start", "ready"]);
  const state = await fetch(`${location.origin}/control/state`, {
    headers: { Cookie: cookie },
  }).then((value) => value.json());
  assert.equal(state.data.operation.status, "completed");
  assert.equal(state.data.operation.phase, "ready");
});

test("operator console exposes only safe credential metadata and accepts write-only replacement while stopped", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-credentials-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  const secret = "sk-" + "write_only_fixture_12345678901234567890";
  let configured = false;
  let verified = false;
  const inventory = () => ({
    root: temporary,
    revision: configured ? "bbbbbbbbbbbbbbbb" : "aaaaaaaaaaaaaaaa",
    configuredSlots: configured ? ["deepseek"] : [],
    slots: [
      {
        slot: "deepseek",
        label: "DeepSeek",
        category: "models",
        purpose: "Primary agent inference and research",
        configured,
        source: configured
          ? "external credential file (deepseek.key)"
          : "missing",
        sourceKind: configured ? "external" : "missing",
        editable: true,
        fingerprint: configured ? "123456789abc" : null,
        verification: configured
          ? {
              status: verified ? "healthy" : "unverified",
              reason: verified ? null : "not_checked",
              checkedAt: verified ? "2026-08-30T12:00:00.000Z" : null,
              latencyMs: verified ? 42 : null,
              httpStatus: verified ? 200 : null,
            }
          : {
              status: "not_configured",
              reason: "credential_missing",
              checkedAt: null,
              latencyMs: null,
              httpStatus: null,
            },
      },
    ],
    verification: {
      checkedAt: verified ? "2026-08-30T12:00:00.000Z" : null,
      expiresAt: verified ? "2026-08-30T12:15:00.000Z" : null,
      stale: !verified,
    },
  });
  const service = {
    stateDir: temporary,
    tokenFile,
    credentialInventory: inventory,
    replaceCredential(slot, value) {
      assert.equal(slot, "deepseek");
      assert.equal(value, secret);
      configured = true;
    },
    async verifyCredentialHealth() {
      verified = true;
      return inventory();
    },
    runtimeEnvironment: () => ({ environment: {} }),
    status: async () => ({
      installed: false,
      ready: false,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: "disabled",
    }),
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory: () => ({ status: async () => ({}) }),
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
  const bootstrap = await fetch(`${location.origin}/control/bootstrap`, {
    headers: { Cookie: cookie },
  }).then((response) => response.json());

  const before = await fetch(`${location.origin}/control/credentials`, {
    headers: { Cookie: cookie },
  }).then((response) => response.json());
  assert.equal(before.data.slots[0].configured, false);
  assert.equal(JSON.stringify(before).includes(temporary), false);

  const forbidden = await fetch(
    `${location.origin}/control/credentials/deepseek`,
    {
      method: "PUT",
      headers: { "Cookie": cookie, "Content-Type": "application/json" },
      body: JSON.stringify({ secret }),
    },
  );
  assert.equal(forbidden.status, 403);

  const replaced = await fetch(
    `${location.origin}/control/credentials/deepseek`,
    {
      method: "PUT",
      headers: {
        "Cookie": cookie,
        "Origin": location.origin,
        "X-ALTA-CSRF": bootstrap.data.csrfToken,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ secret }),
    },
  );
  const payload = await replaced.json();
  assert.equal(replaced.status, 200);
  assert.equal(payload.data.slots[0].configured, true);
  assert.equal(JSON.stringify(payload).includes(secret), false);

  const verifiedResponse = await fetch(
    `${location.origin}/control/credentials/verify`,
    {
      method: "POST",
      headers: {
        "Cookie": cookie,
        "Origin": location.origin,
        "X-ALTA-CSRF": bootstrap.data.csrfToken,
      },
    },
  );
  const verifiedPayload = await verifiedResponse.json();
  assert.equal(verifiedResponse.status, 200);
  assert.equal(verifiedPayload.data.slots[0].verification.status, "healthy");
  assert.equal(JSON.stringify(verifiedPayload).includes(secret), false);
});

test("operator console enforces real Tiger Paper authorization boundaries", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-capital-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  let running = false;
  let enabled = false;
  let refreshGate = null;
  let refreshEntered = null;
  const actions = [];
  const capital = () => ({
    version: 1,
    provider: "Tiger Trade",
    environment: "PAPER",
    configured: true,
    requestedEnabled: enabled,
    enabled,
    posture: enabled ? "paper_enabled" : "paper_ready_disabled",
    accountFingerprint: "0123456789ab",
    configurationFingerprint: "abcdef012345",
    mutationPolicy: "risk_budgeted_limit_day_v1",
    riskPolicy: {
      maxOrderNotional: "10000",
      maxOpenPositions: "4",
      maxDispatchQuoteAgeSeconds: "10",
    },
    instrumentPolicy: "us_stock_only",
    outsideRegularHours: false,
    requiresStoppedRuntime: true,
    lastChangedAt: null,
    lastPreflightAt: null,
    configurationError: null,
    authorizationError: null,
    snapshotError: null,
    snapshot: null,
    audit: [],
  });
  const service = {
    stateDir: temporary,
    tokenFile,
    credentialInventory: () => ({
      revision: "aaaaaaaaaaaaaaaa",
      configuredSlots: [],
      slots: [],
      providerNetwork: [],
    }),
    capitalStatus: capital,
    refreshCapital: async () => {
      actions.push("refresh");
      refreshEntered?.();
      if (refreshGate) await refreshGate;
      return capital();
    },
    setCapitalAuthorization: async (value) => {
      enabled = value;
      actions.push(value ? "enable" : "disable");
      return capital();
    },
    runtimeEnvironment: () => ({ environment: {} }),
    stop: async () => {
      actions.push("stop");
      running = false;
    },
    status: async () => ({
      installed: true,
      ready: running,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: enabled ? "tiger_paper_acceptance" : "disabled",
      host: { processAlive: running },
      supervisor: { childProcessAlive: running },
    }),
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory: () => ({
      status: async () => ({}),
      down: async () => actions.push("down"),
    }),
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
  const bootstrap = await fetch(`${location.origin}/control/bootstrap`, {
    headers: { Cookie: cookie },
  }).then((response) => response.json());
  const headers = {
    "Cookie": cookie,
    "Content-Type": "application/json",
    "Origin": location.origin,
    "X-ALTA-CSRF": bootstrap.data.csrfToken,
  };

  const invalid = await fetch(
    `${location.origin}/control/capital/authorization`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({ enabled: true, confirmation: "yes" }),
    },
  );
  assert.equal(invalid.status, 400);

  const authorized = await fetch(
    `${location.origin}/control/capital/authorization`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({
        enabled: true,
        confirmation: "ENABLE TIGER PAPER",
      }),
    },
  );
  assert.equal(authorized.status, 200);
  assert.equal((await authorized.json()).data.enabled, true);

  let releaseRefresh;
  refreshGate = new Promise((resolve) => {
    releaseRefresh = resolve;
  });
  const entered = new Promise((resolve) => {
    refreshEntered = resolve;
  });
  const refresh = fetch(`${location.origin}/control/capital/refresh`, {
    method: "POST",
    headers,
  });
  await entered;
  const conflictingStart = await fetch(
    `${location.origin}/control/runtime/start`,
    { method: "POST", headers },
  );
  assert.equal(conflictingStart.status, 409);
  assert.equal(
    (await conflictingStart.json()).error.code,
    "operation_in_progress",
  );
  releaseRefresh();
  assert.equal((await refresh).status, 200);
  refreshGate = null;
  refreshEntered = null;

  running = true;
  const disable = await fetch(
    `${location.origin}/control/capital/authorization`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({
        enabled: false,
        confirmation: "DISABLE TIGER PAPER",
      }),
    },
  );
  assert.equal(disable.status, 200);
  assert.deepEqual(actions, ["enable", "refresh", "disable", "stop", "down"]);
  assert.equal(enabled, false);
});

test("operator console coalesces dependency probes and rejects proxy reads while runtime is down", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-down-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  let environmentProbes = 0;
  let runtimeProbes = 0;
  let upstreamCalls = 0;
  const service = {
    stateDir: temporary,
    tokenFile,
    runtimeEnvironment: () => ({ environment: {} }),
    status: async () => {
      runtimeProbes += 1;
      return {
        installed: true,
        ready: false,
        endpoint: "http://127.0.0.1:9999",
        capitalMode: "disabled",
      };
    },
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory: () => ({
      status: async () => {
        environmentProbes += 1;
        return { docker: { ready: true } };
      },
    }),
    fetchImpl: async () => {
      upstreamCalls += 1;
      throw new Error("must not call an unready upstream");
    },
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];

  await Promise.all(
    Array.from({ length: 6 }, () =>
      fetch(`${location.origin}/control/state`, {
        headers: { Cookie: cookie },
      }),
    ),
  );
  const proxy = await fetch(`${location.origin}/proxy/api/v1/system/runtime`, {
    headers: { Cookie: cookie },
  });

  assert.equal(environmentProbes, 1);
  assert.equal(runtimeProbes, 1);
  assert.equal(proxy.status, 503);
  assert.equal((await proxy.json()).error.code, "runtime_not_ready");
  assert.equal(upstreamCalls, 0);
  await operator.close();
});

test("operator console reconciles an interrupted durable operation after restart", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-reconcile-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  const runtimeDir = path.join(temporary, "runtime");
  fs.mkdirSync(staticDir);
  fs.mkdirSync(runtimeDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  fs.writeFileSync(
    path.join(runtimeDir, "operator-operation.json"),
    JSON.stringify({
      id: "interrupted",
      action: "start",
      status: "running",
      phase: "waiting_for_readiness",
      ownerPid: 999_999,
      startedAt: "2026-08-29T00:00:00.000Z",
    }),
    { mode: 0o600 },
  );
  const service = {
    stateDir: temporary,
    tokenFile,
    runtimeEnvironment: () => ({ environment: {} }),
    status: async () => ({
      installed: true,
      ready: true,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: "disabled",
    }),
  };
  const operator = createOperatorConsole({
    host: "127.0.0.1",
    port: 0,
    staticDir,
    service,
    environmentFactory: () => ({
      status: async () => ({ services: { states: { postgres: "healthy" } } }),
    }),
  });
  context.after(() => operator.server.listening && operator.close());
  const location = await operator.listen();
  const open = await fetch(location.openUrl, { redirect: "manual" });
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
  const response = await fetch(`${location.origin}/control/state`, {
    headers: { Cookie: cookie },
  });
  const payload = await response.json();

  assert.equal(payload.data.operation.status, "completed");
  assert.equal(payload.data.operation.ownerPid, undefined);
  assert.equal(
    payload.data.operation.phase,
    "reconciled_after_console_restart",
  );
  assert.equal(
    JSON.parse(
      fs.readFileSync(path.join(runtimeDir, "operator-operation.json"), "utf8"),
    ).status,
    "completed",
  );
  await operator.close();
});

test("operator console preserves the browser session and rotates CSRF after process restart", async (context) => {
  const temporary = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-console-session-"),
  );
  context.after(() => fs.rmSync(temporary, { recursive: true, force: true }));
  const staticDir = path.join(temporary, "dist");
  fs.mkdirSync(staticDir);
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  const tokenFile = path.join(temporary, "token");
  fs.writeFileSync(tokenFile, "server-only-token\n", { mode: 0o600 });
  const service = {
    stateDir: temporary,
    tokenFile,
    runtimeEnvironment: () => ({ environment: {} }),
    status: async () => ({
      installed: true,
      ready: false,
      endpoint: "http://127.0.0.1:9999",
      capitalMode: "disabled",
    }),
  };
  const create = () =>
    createOperatorConsole({
      host: "127.0.0.1",
      port: 0,
      staticDir,
      service,
      environmentFactory: () => ({
        status: async () => ({ docker: { ready: true } }),
      }),
    });

  const first = create();
  const firstLocation = await first.listen();
  const opened = await fetch(firstLocation.openUrl, { redirect: "manual" });
  const cookie = opened.headers.get("set-cookie").split(";", 1)[0];
  const firstBootstrap = await fetch(
    `${firstLocation.origin}/control/bootstrap`,
    { headers: { Cookie: cookie } },
  ).then((response) => response.json());
  await first.close();

  const second = create();
  context.after(() => second.server.listening && second.close());
  const secondLocation = await second.listen();
  const secondBootstrapResponse = await fetch(
    `${secondLocation.origin}/control/bootstrap`,
    { headers: { Cookie: cookie } },
  );
  const secondBootstrap = await secondBootstrapResponse.json();

  assert.equal(secondBootstrapResponse.status, 200);
  assert.match(
    secondBootstrapResponse.headers.get("set-cookie"),
    /Max-Age=2592000/,
  );
  assert.notEqual(
    secondBootstrap.data.console.instanceId,
    firstBootstrap.data.console.instanceId,
  );
  assert.notEqual(
    secondBootstrap.data.csrfToken,
    firstBootstrap.data.csrfToken,
  );
  const sessionFile = path.join(
    temporary,
    "secrets",
    "operator_console_session",
  );
  if (process.platform !== "win32")
    assert.equal(fs.statSync(sessionFile).mode & 0o777, 0o600);
  const serialized = JSON.stringify(secondBootstrap);
  assert.equal(
    serialized.includes(fs.readFileSync(sessionFile, "utf8").trim()),
    false,
  );
  await second.close();
});
