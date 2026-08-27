import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { supervise } from "../supervisor.mjs";

test("supervisor backs off after failures and stops after a clean exit", async (t) => {
  const state = fs.mkdtempSync(path.join(os.tmpdir(), "alta-supervisor-"));
  t.after(() => fs.rmSync(state, { recursive: true, force: true }));
  const exits = [1, 1, 0];
  let launches = 0;
  const code = await supervise({
    stateDir: state,
    provider: "test",
    env: {
      ALTA_RESTART_BASE_MS: "250",
      ALTA_RESTART_MAX_MS: "1000",
      ALTA_STABLE_UPTIME_MS: "10000",
      ALTA_RESTARTS_PER_HOUR: "20",
      ALTA_RESTART_ON_SUCCESS: "0",
    },
    launch: async ({ onChild }) => {
      launches += 1;
      onChild(1000 + launches);
      return exits.shift();
    },
  });
  const status = JSON.parse(
    fs.readFileSync(
      path.join(state, "runtime", "supervisor-test.json"),
      "utf8",
    ),
  );
  assert.equal(code, 0);
  assert.equal(launches, 3);
  assert.equal(status.state, "stopped");
  assert.equal(
    fs.existsSync(path.join(state, "runtime", "supervisor-test.lock")),
    false,
  );
});
