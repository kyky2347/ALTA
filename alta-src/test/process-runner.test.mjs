import assert from "node:assert/strict";
import test from "node:test";

import {
  executableInPath,
  runCapture,
  runProcess,
} from "../process-runner.mjs";

test("process runner resolves, captures, and executes bounded child processes", async () => {
  assert.equal(executableInPath("alta-command-that-does-not-exist"), null);
  assert.equal(
    await runCapture(process.execPath, ["-e", "process.stdout.write('ok')"]),
    "ok",
  );
  assert.equal(
    await runProcess(process.execPath, ["-e", "process.exit(0)"], {
      stdio: "ignore",
    }),
    0,
  );
});

test("process runner rejects a non-zero captured command", async () => {
  await assert.rejects(
    runCapture(process.execPath, ["-e", "process.exit(7)"]),
    /failed with exit code 7/,
  );
});
