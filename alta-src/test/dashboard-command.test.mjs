import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import { dashboardCommand } from "../dashboard-command.mjs";

function fakeConsole({ location, listenError } = {}) {
  const server = new EventEmitter();
  let closed = false;
  return {
    server,
    async listen() {
      if (listenError) throw listenError;
      return location;
    },
    async close() {
      if (closed) return;
      closed = true;
      server.emit("close");
    },
  };
}

function dependencies(consoleFactory, openBrowser) {
  return {
    rootDir: "/tmp/alta-dashboard-command-fixture",
    service: {},
    environmentFactory: () => ({}),
    prepareDashboard: async () => ({ built: false }),
    consoleFactory,
    openBrowser,
  };
}

test("foreground dashboard opens the one-time URL automatically", async () => {
  const location = {
    origin: "http://127.0.0.1:8877",
    openUrl: "http://127.0.0.1:8877/open/fixture",
  };
  const consoleServer = fakeConsole({ location });
  let opened;
  await dashboardCommand(
    [],
    dependencies(
      () => consoleServer,
      async (url) => {
        opened = url;
        setTimeout(() => consoleServer.close(), 0);
      },
    ),
  );
  assert.equal(opened, location.openUrl);
});

test("default port collision falls back to an ephemeral loopback port", async () => {
  const occupied = new Error("occupied");
  occupied.code = "EADDRINUSE";
  const first = fakeConsole({ listenError: occupied });
  const location = {
    origin: "http://127.0.0.1:54321",
    openUrl: "http://127.0.0.1:54321/open/fixture",
  };
  const second = fakeConsole({ location });
  const ports = [];
  await dashboardCommand(
    [],
    dependencies(
      (options) => {
        ports.push(options.port);
        return ports.length === 1 ? first : second;
      },
      async () => setTimeout(() => second.close(), 0),
    ),
  );
  assert.deepEqual(ports, [8877, 0]);
});

test("default launch reuses a ready managed dashboard instead of changing ports", async () => {
  const opened = [];
  let foregroundCreated = false;
  const managed = {
    installed: () => true,
    status: async () => ({
      ready: true,
      endpoint: "http://127.0.0.1:8877",
      host: { processAlive: true },
    }),
    openUrl: () => "http://127.0.0.1:8877/open/managed-fixture",
    platform: { restart: () => assert.fail("must not restart") },
  };
  const deps = dependencies(
    () => {
      foregroundCreated = true;
      return fakeConsole();
    },
    async (url) => opened.push(url),
  );
  deps.dashboardService = managed;

  await dashboardCommand([], deps);

  assert.equal(foregroundCreated, false);
  assert.deepEqual(opened, ["http://127.0.0.1:8877/open/managed-fixture"]);
});

test("default launch opens the stable endpoint after bootstrap was claimed", async () => {
  const opened = [];
  const deps = dependencies(
    () => assert.fail("must not create a second dashboard"),
    async (url) => opened.push(url),
  );
  deps.dashboardService = {
    installed: () => true,
    status: async () => ({
      ready: true,
      endpoint: "http://127.0.0.1:8877",
      host: { processAlive: true },
    }),
    openUrl: () => {
      throw new Error("one-time link already used");
    },
    platform: { restart: () => assert.fail("must not restart") },
  };

  await dashboardCommand([], deps);

  assert.deepEqual(opened, ["http://127.0.0.1:8877"]);
});

test("rebuilt assets restart an installed dashboard before reuse", async () => {
  let restarted = 0;
  const deps = dependencies(
    () => assert.fail("must not create a foreground dashboard"),
    async () => {},
  );
  deps.prepareDashboard = async () => ({ built: true });
  deps.dashboardService = {
    installed: () => true,
    status: async () => ({
      ready: true,
      endpoint: "http://127.0.0.1:8877",
      host: { processAlive: true },
    }),
    waitForReadiness: async () => ({
      ready: true,
      endpoint: "http://127.0.0.1:8877",
      host: { processAlive: true },
    }),
    openUrl: () => "http://127.0.0.1:8877/open/rebuilt-fixture",
    platform: { restart: () => (restarted += 1) },
  };

  await dashboardCommand([], deps);

  assert.equal(restarted, 1);
});
