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
  const cookie = open.headers.get("set-cookie").split(";", 1)[0];
  assert.equal(open.status, 303);
  assert.equal(open.headers.get("location"), "/");
  assert(!cookie.includes("super-secret-token"));
  const reused = await fetch(location.openUrl, { redirect: "manual" });
  assert.equal(reused.headers.get("set-cookie"), null);
  assert.equal(bootstrapUses, 1);

  const bootstrap = await fetch(`${location.origin}/control/bootstrap`, {
    headers: { Cookie: cookie },
  });
  const bootstrapPayload = await bootstrap.json();
  assert.equal(bootstrapPayload.data.safety.capitalMode, "disabled");
  assert(bootstrapPayload.data.csrfToken);
  assert.equal(bootstrapPayload.data.console.protocolVersion, 1);

  const ready = await fetch(`${location.origin}/health/ready`);
  assert.deepEqual(await ready.json(), {
    data: { ready: true, protocolVersion: 1 },
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
  let upstreamCalls = 0;
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
