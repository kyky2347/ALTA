import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  loadResourceCredentials,
  TOOL_CREDENTIAL_KEYS,
} from "../resource-credentials.mjs";

function credentialFixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-resources-"));
  const resources = path.join(root, "resources");
  fs.mkdirSync(resources, { recursive: true, mode: 0o700 });
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return { root, resources };
}

test("resource credentials stay external and load without logging values", (t) => {
  const { root, resources } = credentialFixture(t);
  fs.writeFileSync(
    path.join(resources, "Massive API Key.rtf"),
    String.raw`{\rtf1 REST: https://proxy.example.test?key=Massive_fixture_12345678901234567890}`,
    { mode: 0o600 },
  );
  fs.writeFileSync(
    path.join(resources, "finlight api.rtf"),
    String.raw`{\rtf1 ${"sk-" + "finlight_fixture_12345678901234567890"}}`,
    { mode: 0o600 },
  );

  const result = loadResourceCredentials({ ALTA_CREDENTIALS_DIR: root });

  assert.deepEqual(Object.keys(result.values).sort(), [
    "FINLIGHT_API_KEY",
    "MASSIVE_API_KEY",
  ]);
  assert.match(result.values.MASSIVE_API_KEY, /^Massive_fixture_/);
  assert.match(result.values.FINLIGHT_API_KEY, /^sk-finlight_/);
  assert.match(result.sources.MASSIVE_API_KEY, /external credential file/);
  assert.equal(JSON.stringify(result.sources).includes("1234567890"), false);
});

test("environment resource credentials take precedence over files", (t) => {
  const { root, resources } = credentialFixture(t);
  fs.writeFileSync(
    path.join(resources, "Massive.rtf"),
    "file_fixture_123456789012345678901234",
    { mode: 0o600 },
  );

  const result = loadResourceCredentials({
    ALTA_CREDENTIALS_DIR: root,
    MASSIVE_API_KEY: "fixture-environment-value-1234567890",
  });

  assert.equal(
    result.values.MASSIVE_API_KEY,
    "fixture-environment-value-1234567890",
  );
  assert.equal(result.sources.MASSIVE_API_KEY, "environment (MASSIVE_API_KEY)");
});

test("optional tool credentials load from the same external root", (t) => {
  const { root } = credentialFixture(t);
  const tools = path.join(root, "tools");
  fs.mkdirSync(tools, { mode: 0o700 });
  fs.writeFileSync(
    path.join(tools, "Brave Search.key"),
    "BSAfixture123456789012345678901234",
    { mode: 0o600 },
  );

  const result = loadResourceCredentials({ ALTA_CREDENTIALS_DIR: root });

  assert.match(result.values.BRAVE_SEARCH_API_KEY, /^BSAfixture/);
  assert.match(result.sources.BRAVE_SEARCH_API_KEY, /external credential file/);
  assert.deepEqual(
    Object.keys(
      loadResourceCredentials(
        { ALTA_CREDENTIALS_DIR: root },
        TOOL_CREDENTIAL_KEYS,
      ).values,
    ),
    ["BRAVE_SEARCH_API_KEY"],
  );
});

test("Finnhub loads from the external resource store", (t) => {
  const { root, resources } = credentialFixture(t);
  fs.writeFileSync(
    path.join(resources, "Finnhub Basic.key"),
    "finnhub_fixture_1234567890", // gitleaks:allow -- synthetic split test credential
    { mode: 0o600 },
  );

  const result = loadResourceCredentials(
    { ALTA_CREDENTIALS_DIR: root },
    TOOL_CREDENTIAL_KEYS,
  );

  assert.match(result.values.FINNHUB_API_KEY, /^finnhub_fixture_/);
  assert.match(result.sources.FINNHUB_API_KEY, /external credential file/);
});
