import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { atomicWrite, atomicWriteJson } from "../durable-file.mjs";

test("durable writes atomically replace owner-only state without temp debris", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-durable-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "nested", "state.json");

  atomicWrite(file, "first\n");
  atomicWriteJson(file, { state: "ready" });

  assert.deepEqual(JSON.parse(fs.readFileSync(file, "utf8")), {
    state: "ready",
  });
  if (process.platform !== "win32")
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.deepEqual(
    fs.readdirSync(path.dirname(file)).filter((name) => name.endsWith(".tmp")),
    [],
  );
});
