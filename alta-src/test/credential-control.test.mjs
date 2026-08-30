import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  credentialInventory,
  replaceCredential,
} from "../credential-control.mjs";
import { credentialCommand } from "../credential-command.mjs";

function fixture(t) {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-credential-control-"),
  );
  for (const directory of ["llm", "resources"])
    fs.mkdirSync(path.join(root, directory), { mode: 0o700 });
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return {
    root,
    env: { ALTA_CREDENTIALS_DIR: root },
    write(directory, name, value) {
      const file = path.join(root, directory, name);
      fs.writeFileSync(file, `${value}\n`, { mode: 0o600 });
      return file;
    },
  };
}

test("credential inventory reports sources and revision without values", (t) => {
  const value = "sk-" + "deepseek_fixture_12345678901234567890"; // gitleaks:allow -- synthetic split test credential
  const { env, write } = fixture(t);
  write("llm", "deepseek.key", value);
  write("resources", "massive.key", "massive_fixture_12345678901234567890"); // gitleaks:allow -- synthetic Massive test credential

  const inventory = credentialInventory(env);

  assert.deepEqual(inventory.configuredSlots, ["deepseek", "massive"]);
  assert.match(inventory.revision, /^[a-f0-9]{16}$/);
  assert.match(
    inventory.slots.find((item) => item.slot === "deepseek").source,
    /external credential file/,
  );
  assert.equal(JSON.stringify(inventory).includes(value), false);
  assert.equal(
    inventory.slots.find((item) => item.slot === "jina").operational,
    true,
  );
  assert.equal(
    inventory.slots.find((item) => item.slot === "brave").credentialRequirement,
    "optional",
  );
});

test("Tiger Paper inventory exposes only safe external configuration metadata", (t) => {
  const { env, root } = fixture(t);
  const broker = path.join(root, "broker");
  fs.mkdirSync(broker, { mode: 0o700 });
  const privateMaterial = "fixture-private-material";
  fs.writeFileSync(
    path.join(broker, "tiger-paper.properties"),
    `account=fixture-account\ntiger_id=fixture-id\nprivate_key_pk8=${privateMaterial}\n`,
    { mode: 0o600 },
  );

  const inventory = credentialInventory(env);

  assert.equal(inventory.trading.configured, true);
  assert.equal(inventory.trading.mode, "paper_only");
  assert.equal(
    inventory.trading.status,
    "configured_external_capital_disabled",
  );
  assert.equal(JSON.stringify(inventory).includes(privateMaterial), false);
});

test("credential replacement is atomic, owner-only, and immediately readable", (t) => {
  const { env, write } = fixture(t);
  const file = write(
    "llm",
    "DeepSeek API.rtf",
    "sk-" + "deepseek_old_fixture_12345678901234567890",
  );
  const before = credentialInventory(env).revision;
  const replacement = replaceCredential(
    "deepseek",
    "sk-" + "deepseek_new_fixture_12345678901234567890",
    env,
  );

  assert.equal(replacement.fileName, "DeepSeek API.rtf");
  assert.notEqual(replacement.revision, before);
  assert.match(fs.readFileSync(file, "utf8"), /new_fixture/);
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.deepEqual(
    fs.readdirSync(path.dirname(file)).filter((name) => name.startsWith(".")),
    [],
  );
});

test("credential loading rejects ambiguous files instead of picking one", (t) => {
  const { env, write } = fixture(t);
  write(
    "llm",
    "deepseek-a.key",
    "sk-" + "deepseek_a_fixture_12345678901234567890",
  );
  write(
    "llm",
    "deepseek-b.key",
    "sk-" + "deepseek_b_fixture_12345678901234567890",
  );

  assert.throws(() => credentialInventory(env), /Multiple ALTA llm credential/);
});

test("credential validation rejects a matching file with no valid secret", (t) => {
  const { env, write } = fixture(t);
  write("llm", "deepseek.key", "not-a-provider-key");

  assert.throws(
    () => credentialInventory(env),
    /DeepSeek credential file .* has no valid credential/,
  );
});

test("external replacement refuses to shadow an environment credential", (t) => {
  const { env } = fixture(t);
  assert.throws(
    () =>
      replaceCredential("grok", "xai-fixture_123456789012345678901234", {
        ...env,
        XAI_API_KEY: "environment-fixture",
      }),
    /unset that environment variable/,
  );
});

test("credential command restores the old file when service reload fails", async (t) => {
  const { env, write } = fixture(t);
  const original = "sk-" + "kimi_old_fixture_1234567890123456789012";
  const file = write("llm", "kimi.key", original);
  let readinessCalls = 0;
  const service = {
    status: async () => ({ installed: true, platformActive: true }),
    platform: { restart() {} },
    waitForReadiness: async () => {
      readinessCalls += 1;
      if (readinessCalls === 1) throw new Error("fixture reload failure");
    },
  };

  await assert.rejects(
    credentialCommand(["set", "kimi"], {
      service,
      env,
      readSecret: async () => "sk-" + "kimi_new_fixture_1234567890123456789012",
      output() {},
    }),
    /previous file was restored/,
  );
  assert.equal(fs.readFileSync(file, "utf8").trim(), original);
  assert.equal(readinessCalls, 2);
});
