import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  HostServicePlatform,
  OPPORTUNITY_SERVICE_LABEL,
  launchdDefinition,
  managedLaunchdDefinition,
  managedServiceLayout,
  managedSystemdDefinition,
  systemdDefinition,
} from "../host-service-platform.mjs";

const definitionInput = {
  node: "/opt/node/bin/node",
  cli: "/srv/ALTA/alta-src/cli.mjs",
  root: "/srv/ALTA",
  stdout: "/srv/ALTA/.alta/home/log/service.log",
  stderr: "/srv/ALTA/.alta/home/log/service.error.log",
};

test("launchd definition is restartable and contains no credentials", () => {
  const definition = launchdDefinition(definitionInput);

  assert.match(definition, new RegExp(OPPORTUNITY_SERVICE_LABEL));
  assert.match(
    definition,
    /<string>\/usr\/bin\/env<\/string>\s*<string>\/opt\/node\/bin\/node<\/string>/,
  );
  assert.match(definition, /<key>SuccessfulExit<\/key>\s*<false\/>/);
  assert.match(definition, /<key>RunAtLoad<\/key>\s*<true\/>/);
  assert.equal(/API_KEY|TOKEN|PASSWORD/.test(definition), false);
});

test("systemd definition uses bounded on-failure recovery", () => {
  const definition = systemdDefinition(definitionInput);

  assert.match(definition, /Restart=on-failure/);
  assert.match(definition, /RestartSec=30s/);
  assert.match(definition, /NoNewPrivileges=true/);
  assert.equal(/API_KEY|TOKEN|PASSWORD/.test(definition), false);
});

test("generic definitions isolate service identity and arguments", () => {
  const launchd = managedLaunchdDefinition({
    ...definitionInput,
    label: "app.alta.asterism.dashboard",
    args: ["dashboard", "run"],
  });
  const systemd = managedSystemdDefinition({
    ...definitionInput,
    description: "ALTA dashboard",
    args: ["dashboard", "run"],
  });

  for (const definition of [launchd, systemd]) {
    assert.match(definition, /dashboard/);
    assert.match(definition, /run/);
    assert.equal(/API_KEY|TOKEN|PASSWORD|\/open\//.test(definition), false);
  }
});

test("managed service layout avoids macOS protected project directories", () => {
  const mac = managedServiceLayout({
    platform: { platform: "darwin", home: "/Users/fixture" },
    stateDir: "/Users/fixture/Desktop/ALTA/.alta",
    projectRoot: "/Users/fixture/Desktop/ALTA",
  });
  const linux = managedServiceLayout({
    platform: { platform: "linux", home: "/home/fixture" },
    stateDir: "/srv/ALTA/.alta",
    projectRoot: "/srv/ALTA",
  });

  assert.equal(mac.workingDirectory, "/Users/fixture");
  assert.equal(mac.logDirectory, "/Users/fixture/Library/Logs/ALTA");
  assert.equal(linux.workingDirectory, "/srv/ALTA");
  assert.equal(linux.logDirectory, "/srv/ALTA/.alta/home/log");
});

test("macOS adapter installs an owner-only user LaunchAgent", (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "alta-launchd-"));
  const calls = [];
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const adapter = new HostServicePlatform({
    platform: "darwin",
    home,
    uid: 501,
    runner: (command, args) => {
      calls.push([command, ...args]);
      return { code: 0, stdout: "", stderr: "" };
    },
  });

  const file = adapter.install("fixture-definition", { start: true });

  assert.equal(fs.readFileSync(file, "utf8"), "fixture-definition");
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.equal(
    calls.some((call) => call.includes("bootstrap")),
    true,
  );
  assert.equal(
    calls.some((call) => call.includes("kickstart")),
    false,
  );
});

test("service adapter uses a custom label without touching the backend unit", (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "alta-dashboard-unit-"));
  const calls = [];
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const adapter = new HostServicePlatform({
    platform: "darwin",
    home,
    uid: 501,
    label: "app.alta.asterism.dashboard",
    systemdUnit: "alta-dashboard.service",
    runner: (command, args) => {
      calls.push([command, ...args]);
      return { code: 0, stdout: "", stderr: "" };
    },
  });

  const file = adapter.install("dashboard-definition");

  assert.match(file, /app\.alta\.asterism\.dashboard\.plist$/);
  assert.equal(calls.flat().includes(OPPORTUNITY_SERVICE_LABEL), false);
});

test("macOS install can remain unloaded until the next login", (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "alta-install-only-"));
  const calls = [];
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const adapter = new HostServicePlatform({
    platform: "darwin",
    home,
    uid: 501,
    runner: (command, args) => {
      calls.push([command, ...args]);
      return { code: 0, stdout: "", stderr: "" };
    },
  });

  adapter.install("fixture-definition", { start: false });

  assert.equal(
    calls.some((call) => call.includes("bootstrap")),
    false,
  );
  assert.equal(
    calls.some((call) => call.includes("enable")),
    true,
  );
});

test("macOS stop unloads the service so KeepAlive cannot relaunch it", (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "alta-stop-unit-"));
  const calls = [];
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const adapter = new HostServicePlatform({
    platform: "darwin",
    home,
    uid: 501,
    runner: (command, args, options) => {
      calls.push({ command, args, options });
      return { code: 0, stdout: "", stderr: "" };
    },
  });

  adapter.stop();

  assert.deepEqual(calls[0].args, [
    "bootout",
    "gui/501",
    path.join(
      home,
      "Library",
      "LaunchAgents",
      `${OPPORTUNITY_SERVICE_LABEL}.plist`,
    ),
  ]);
  assert.equal(calls[0].options.allowFailure, true);
  assert.equal(
    calls.some((call) => call.args.includes("kill")),
    false,
  );
});

test("macOS start bootstraps an unloaded service and kickstarts a loaded one", (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "alta-start-unit-"));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const calls = [];
  let loaded = false;
  const adapter = new HostServicePlatform({
    platform: "darwin",
    home,
    uid: 501,
    runner: (command, args, options) => {
      calls.push({ command, args, options });
      if (args[0] === "print")
        return { code: loaded ? 0 : 113, stdout: "", stderr: "" };
      return { code: 0, stdout: "", stderr: "" };
    },
  });

  adapter.start();
  assert.equal(
    calls.some((call) => call.args[0] === "bootstrap"),
    true,
  );
  assert.equal(
    calls.some((call) => call.args[0] === "kickstart"),
    false,
  );

  calls.length = 0;
  loaded = true;
  adapter.start();
  assert.equal(
    calls.some((call) => call.args[0] === "bootstrap"),
    false,
  );
  assert.equal(
    calls.some((call) => call.args[0] === "kickstart"),
    true,
  );
});
