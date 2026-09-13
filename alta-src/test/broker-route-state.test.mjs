import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { brokerRouteSummary } from "../broker-route-state.mjs";

test("display metadata reports selected LIVE broker, never credentials or an inferred Paper fallback", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-route-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "route.json");
  assert.equal(brokerRouteSummary(file).mode, "shadow");
  for (const provider of [
    "tiger",
    "alpaca",
    "ibkr",
    "futu",
    "longport",
    "schwab",
  ]) {
    fs.writeFileSync(
      file,
      JSON.stringify({
        provider,
        environment: "LIVE",
        binding: "b".repeat(64),
        profile_revision: "c".repeat(64),
        untrusted: "do not return",
      }),
      { mode: 0o600 },
    );
    assert.deepEqual(brokerRouteSummary(file), {
      mode: "broker_api",
      environment: "LIVE",
      provider,
    });
  }
  fs.writeFileSync(file, "{}");
  assert.equal(brokerRouteSummary(file).mode, "unavailable");
  const link = path.join(dir, "symlink");
  fs.symlinkSync(file, link);
  assert.equal(brokerRouteSummary(link).mode, "unavailable");
});
