import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { thirdPartyOpenAiServicePolicy } from "../openai-background.mjs";

function jwt(exp) {
  const encode = (value) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none" })}.${encode({ exp })}.signature`;
}

test("third-party launches skip unusable OpenAI background services", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-openai-policy-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const authFile = path.join(root, "auth.json");
  const now = Date.UTC(2026, 0, 1);
  fs.writeFileSync(
    authFile,
    JSON.stringify({ tokens: { access_token: jwt(now / 1000 - 1) } }),
  );

  assert.deepEqual(thirdPartyOpenAiServicePolicy(authFile, { now }), {
    enabled: false,
    reason: "expired access token",
    args: [
      "-c",
      "features.apps=false",
      "-c",
      "features.remote_plugin=false",
      "-c",
      "analytics.enabled=false",
      "-c",
      'cli_auth_credentials_store="ephemeral"',
    ],
  });
});

test("fresh auth and explicit overrides keep policy deterministic", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-openai-policy-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const authFile = path.join(root, "auth.json");
  const now = Date.UTC(2026, 0, 1);
  fs.writeFileSync(
    authFile,
    JSON.stringify({ tokens: { access_token: jwt(now / 1000 + 3600) } }),
  );

  assert.deepEqual(thirdPartyOpenAiServicePolicy(authFile, { now }), {
    enabled: true,
    reason: "fresh access token",
    args: [
      "-c",
      "features.apps=false",
      "-c",
      "features.remote_plugin=false",
      "-c",
      "analytics.enabled=false",
    ],
  });
  assert.equal(
    thirdPartyOpenAiServicePolicy(authFile, { mode: "0", now }).enabled,
    false,
  );
  assert.equal(
    thirdPartyOpenAiServicePolicy("missing", { mode: "1", now }).enabled,
    true,
  );
});
