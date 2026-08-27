import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  configureOpenAiAuth,
  protectOfficialAuthCommand,
} from "../openai-auth.mjs";

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-openai-auth-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const officialAuthFile = path.join(root, "official", "auth.json");
  const altaAuthFile = path.join(root, "alta", "auth.json");
  fs.mkdirSync(path.dirname(officialAuthFile), { recursive: true });
  fs.writeFileSync(officialAuthFile, '{"token":"first"}', { mode: 0o600 });
  return { officialAuthFile, altaAuthFile };
}

test("official mode shares token rotation without sharing other state", (t) => {
  const files = fixture(t);
  const route = configureOpenAiAuth({ ...files, mode: "official" });

  assert.deepEqual(route, {
    mode: "official",
    available: true,
    reference: process.platform === "win32" ? route.reference : "symbolic link",
    source: files.officialAuthFile,
  });
  assert.equal(
    fs.readFileSync(files.altaAuthFile, "utf8"),
    '{"token":"first"}',
  );

  fs.writeFileSync(files.officialAuthFile, '{"token":"rotated"}');
  assert.equal(
    fs.readFileSync(files.altaAuthFile, "utf8"),
    '{"token":"rotated"}',
  );
  assert.equal(
    configureOpenAiAuth({ ...files, mode: "shared" }).reference,
    route.reference,
  );
});

test("official mode replaces a stale private copy", (t) => {
  const files = fixture(t);
  fs.mkdirSync(path.dirname(files.altaAuthFile), { recursive: true });
  fs.writeFileSync(files.altaAuthFile, '{"token":"stale"}');

  configureOpenAiAuth({ ...files, mode: "official" });

  assert.equal(
    fs.readFileSync(files.altaAuthFile, "utf8"),
    '{"token":"first"}',
  );
  assert.equal(
    fs.statSync(files.altaAuthFile).ino,
    fs.statSync(files.officialAuthFile).ino,
  );
});

test("isolated mode breaks the shared reference into a private copy", (t) => {
  const files = fixture(t);
  configureOpenAiAuth({ ...files, mode: "official" });

  const route = configureOpenAiAuth({ ...files, mode: "isolated" });
  fs.writeFileSync(files.officialAuthFile, '{"token":"rotated"}');

  assert.deepEqual(route, {
    mode: "isolated",
    available: true,
    reference: "private copy",
    source: files.altaAuthFile,
  });
  assert.equal(
    fs.readFileSync(files.altaAuthFile, "utf8"),
    '{"token":"first"}',
  );
  assert.notEqual(
    fs.statSync(files.altaAuthFile).ino,
    fs.statSync(files.officialAuthFile).ino,
  );
});

test("invalid auth mode is rejected", (t) => {
  const files = fixture(t);
  assert.throws(
    () => configureOpenAiAuth({ ...files, mode: "copy-sometimes" }),
    /must be official or isolated/,
  );
});

test("shared mode protects the official login from accidental admin changes", () => {
  assert.doesNotThrow(() =>
    protectOfficialAuthCommand("official", ["login", "status"]),
  );
  assert.doesNotThrow(() => protectOfficialAuthCommand("isolated", ["logout"]));
  assert.throws(
    () => protectOfficialAuthCommand("official", ["login"]),
    /Run `codex login`/,
  );
  assert.throws(
    () => protectOfficialAuthCommand("official", ["logout"]),
    /Run `codex login`/,
  );
});
