import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  HostServicePlatform,
  OPPORTUNITY_SERVICE_LABEL,
  launchdDefinition,
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
    true,
  );
});
