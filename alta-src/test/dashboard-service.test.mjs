import assert from "node:assert/strict";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  DashboardService,
  DASHBOARD_SERVICE_LABEL,
} from "../dashboard-service.mjs";

async function availablePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port: 0 }, resolve);
  });
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

function fixture(t, platformName = "darwin") {
  const rootDir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-dashboard-"));
  const stateDir = path.join(rootDir, ".alta");
  const staticDir = path.join(rootDir, "alta-dashboard", "dist");
  const tokenFile = path.join(stateDir, "secrets", "opportunity_api_token");
  const definitionFile = path.join(rootDir, "dashboard.service");
  fs.mkdirSync(staticDir, { recursive: true });
  fs.mkdirSync(path.dirname(tokenFile), { recursive: true });
  fs.writeFileSync(path.join(staticDir, "index.html"), "<h1>ALTA</h1>");
  fs.writeFileSync(tokenFile, `${"a".repeat(48)}\n`, { mode: 0o600 });
  t.after(() => fs.rmSync(rootDir, { recursive: true, force: true }));
  const platform = {
    platform: platformName,
    home: rootDir,
    definitionPath: () => definitionFile,
    status: () => ({ code: fs.existsSync(definitionFile) ? 0 : 1 }),
    install(definition) {
      fs.writeFileSync(definitionFile, definition, { mode: 0o600 });
      return definitionFile;
    },
    start() {},
    stop() {},
    restart() {},
    uninstall() {
      fs.rmSync(definitionFile, { force: true });
    },
  };
  const service = {
    stateDir,
    tokenFile,
    runtimeEnvironment: () => ({ environment: {} }),
    status: async () => ({
      installed: false,
      ready: false,
      endpoint: "http://127.0.0.1:8876",
      capitalMode: "disabled",
    }),
  };
  return { rootDir, stateDir, platform, service };
}

test("managed dashboard definition is restartable and contains no secret", async (t) => {
  const values = fixture(t);
  const dashboard = new DashboardService({
    ...values,
    cliFile: path.join(values.rootDir, "alta-src", "cli.mjs"),
    environmentFactory: () => ({
      status: async () => ({ docker: { ready: true } }),
    }),
    port: await availablePort(),
  });

  const definition = dashboard.definition();

  assert.match(definition, new RegExp(DASHBOARD_SERVICE_LABEL));
  assert.match(definition, /dashboard/);
  assert.match(definition, /<string>run<\/string>/);
  assert.match(definition, /SuccessfulExit<\/key>\s*<false\/>/);
  assert.equal(/opportunity_api_token|\/open\/|a{40}/.test(definition), false);
});

test("managed dashboard survives bootstrap handoff without persisting its link", async (t) => {
  const values = fixture(t);
  const port = await availablePort();
  const dashboard = new DashboardService({
    ...values,
    cliFile: path.join(values.rootDir, "alta-src", "cli.mjs"),
    environmentFactory: () => ({
      status: async () => ({ docker: { ready: true } }),
    }),
    port,
  });
  const controller = new AbortController();
  const running = dashboard.run({ signal: controller.signal });
  t.after(() => controller.abort());

  const status = await dashboard.waitForReadiness(5_000);
  assert.equal(status.ready, true);
  const openUrl = dashboard.openUrl();
  assert.match(openUrl, new RegExp(`^http://127\\.0\\.0\\.1:${port}/open/`));
  if (process.platform !== "win32")
    assert.equal(fs.statSync(dashboard.stateFile).mode & 0o777, 0o600);

  const opened = await fetch(openUrl, { redirect: "manual" });
  assert.equal(opened.status, 303);
  const claimed = JSON.parse(fs.readFileSync(dashboard.stateFile, "utf8"));
  assert.equal(claimed.bootstrapAvailable, false);
  assert.equal(claimed.openUrl, undefined);
  assert.throws(() => dashboard.openUrl(), /already used/);

  controller.abort();
  assert.equal(await running, 0);
  const stopped = JSON.parse(fs.readFileSync(dashboard.stateFile, "utf8"));
  assert.equal(stopped.state, "stopped");
  assert.equal(stopped.processId, null);
});

test("managed dashboard rejects occupied endpoints before installation", async (t) => {
  const values = fixture(t);
  const port = await availablePort();
  const occupied = net.createServer();
  await new Promise((resolve) =>
    occupied.listen({ host: "127.0.0.1", port }, resolve),
  );
  t.after(() => occupied.close());
  const dashboard = new DashboardService({
    ...values,
    cliFile: path.join(values.rootDir, "alta-src", "cli.mjs"),
    environmentFactory: () => ({}),
    port,
  });

  await assert.rejects(dashboard.assertEndpointAvailable(), /already in use/);
});
