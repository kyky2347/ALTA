import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { StorageManager, acquireLease } from "../storage.mjs";

function write(file, contents) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, contents);
}

test("storage maintenance removes only disposable data and preserves durable state", async (t) => {
  const state = fs.mkdtempSync(path.join(os.tmpdir(), "alta-storage-"));
  t.after(() => fs.rmSync(state, { recursive: true, force: true }));
  const binary = path.join(state, "bin", "codex");
  const codeModeHost = path.join(state, "bin", "codex-code-mode-host");
  const target = path.join(state, "target", "release", "artifact");
  const cargoCache = path.join(state, "cargo", "registry", "src", "crate");
  const python = path.join(state, "python", "versions", "3.12.13", "python");
  const expired = path.join(state, "cache", "expired.json");
  const retained = path.join(state, "cache", "retained.json");
  const auth = path.join(state, "home", "auth.json");
  const session = path.join(state, "home", "sessions", "thread.jsonl.zst");
  for (const [file, contents] of [
    [binary, "binary"],
    [codeModeHost, "code-mode-host"],
    [target, "build-cache"],
    [cargoCache, "dependency-cache"],
    [python, "managed-python"],
    [expired, "old-cache"],
    [retained, "new-cache"],
    [auth, "credential"],
    [session, "durable-session"],
  ])
    write(file, contents);
  const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000);
  fs.utimesSync(expired, old, old);
  const manager = new StorageManager(state, {
    maxBytes: 1024 ** 3,
    reserveBytes: 1,
    cacheMaxBytes: 1024,
    cacheTtlMs: 24 * 60 * 60 * 1000,
    tempTtlMs: 60 * 60 * 1000,
    logTtlMs: 24 * 60 * 60 * 1000,
    intervalMs: 60_000,
    keepBuildCache: false,
  });

  const preview = await manager.maintain({ dryRun: true });
  assert.equal(preview.dryRun, true);
  assert.equal(fs.existsSync(target), true);
  assert.equal(fs.existsSync(expired), true);

  const result = await manager.maintain();
  assert.equal(result.snapshot.pressure, "normal");
  assert.equal(fs.existsSync(target), false);
  assert.equal(fs.existsSync(cargoCache), false);
  assert.equal(fs.readFileSync(python, "utf8"), "managed-python");
  assert.equal(fs.existsSync(expired), false);
  assert.equal(fs.existsSync(retained), true);
  assert.equal(fs.readFileSync(auth, "utf8"), "credential");
  assert.equal(fs.readFileSync(session, "utf8"), "durable-session");
});

test("operation leases reject live duplicates and recover after release", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-lease-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "runtime", "operation.lock");
  const first = acquireLease(file);
  assert.throws(() => acquireLease(file), /already running/);
  first.release();
  const second = acquireLease(file);
  second.release();
  assert.equal(fs.existsSync(file), false);
});

test("operation leases recover a cross-boot PID reuse artifact", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-lease-boot-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "runtime", "operation.lock");
  write(
    file,
    `${JSON.stringify({ pid: process.pid, createdAt: "2000-01-01T00:00:00.000Z" })}\n`,
  );

  const recovered = acquireLease(file);
  const current = JSON.parse(fs.readFileSync(file, "utf8"));

  assert.equal(current.pid, process.pid);
  assert.notEqual(current.createdAt, "2000-01-01T00:00:00.000Z");
  recovered.release();
});

test("storage maintenance skips all cleanup during a runtime build", async (t) => {
  const state = fs.mkdtempSync(path.join(os.tmpdir(), "alta-build-lock-"));
  t.after(() => fs.rmSync(state, { recursive: true, force: true }));
  const cache = path.join(state, "cache", "expired.bin");
  write(cache, "still-needed-by-build");
  const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000);
  fs.utimesSync(cache, old, old);
  const buildLease = acquireLease(path.join(state, "runtime", "build.lock"));
  t.after(() => buildLease.release());
  const manager = new StorageManager(state, {
    cacheTtlMs: 24 * 60 * 60 * 1000,
    intervalMs: 60_000,
  });

  const result = await manager.maintain();
  assert.deepEqual(result, {
    skipped: true,
    reason: "runtime build in progress",
  });
  assert.equal(fs.readFileSync(cache, "utf8"), "still-needed-by-build");
});

test("storage cache cap evicts oldest files without following symlinks", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-cache-cap-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const state = path.join(root, "state");
  const external = path.join(root, "external", "sentinel.txt");
  const oldest = path.join(state, "cache", "oldest.bin");
  const newest = path.join(state, "cache", "newest.bin");
  write(external, "do-not-delete");
  write(oldest, Buffer.alloc(80));
  write(newest, Buffer.alloc(80));
  fs.symlinkSync(path.dirname(external), path.join(state, "cache", "external"));
  const oldTime = new Date(Date.now() - 2 * 60 * 1000);
  fs.utimesSync(oldest, oldTime, oldTime);
  const manager = new StorageManager(state, {
    maxBytes: 1024 ** 3,
    reserveBytes: 1,
    cacheMaxBytes: 100,
    cacheTtlMs: 24 * 60 * 60 * 1000,
    tempTtlMs: 60 * 60 * 1000,
    logTtlMs: 24 * 60 * 60 * 1000,
    intervalMs: 60_000,
    keepBuildCache: true,
  });

  await manager.maintain();
  assert.equal(fs.existsSync(oldest), false);
  assert.equal(fs.existsSync(newest), true);
  assert.equal(fs.readFileSync(external, "utf8"), "do-not-delete");
});

test("storage admission reuses a short disk check without hiding sustained failures", async (t) => {
  const state = fs.mkdtempSync(path.join(os.tmpdir(), "alta-admission-"));
  t.after(() => fs.rmSync(state, { recursive: true, force: true }));
  const manager = new StorageManager(state, {
    maxBytes: 1024 ** 3,
    reserveBytes: 1,
    admissionCacheMs: 10,
  });

  assert.equal(manager.canAcceptWork(), true);
  fs.rmSync(state, { recursive: true, force: true });
  assert.equal(manager.canAcceptWork(), true);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(manager.canAcceptWork(), false);
});

test("storage maintenance clears a large expired tree with bounded I/O", async (t) => {
  const state = fs.mkdtempSync(path.join(os.tmpdir(), "alta-storage-io-"));
  t.after(() => fs.rmSync(state, { recursive: true, force: true }));
  const files = Array.from({ length: 240 }, (_, index) =>
    path.join(state, "cache", `shard-${index % 12}`, `entry-${index}.bin`),
  );
  const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000);
  for (const file of files) {
    write(file, "expired");
    fs.utimesSync(file, old, old);
  }
  const manager = new StorageManager(state, {
    maxBytes: 1024 ** 3,
    reserveBytes: 1,
    cacheMaxBytes: 1024 ** 2,
    cacheTtlMs: 24 * 60 * 60 * 1000,
    intervalMs: 60_000,
    ioConcurrency: 8,
  });

  const result = await manager.maintain();
  assert.equal(result.removed.length, files.length);
  assert.deepEqual(result.failures, []);
  assert.equal(result.snapshot.cacheBytes, 0);
  assert.equal(fs.existsSync(path.join(state, "cache")), false);
});
