import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { randomUUID } from "node:crypto";
import { unlinkFiles, walkFiles } from "./file-inventory.mjs";
import { boundedNumber } from "./resource-control.mjs";

const GIB = 1024 ** 3;
const DAY_MS = 24 * 60 * 60 * 1000;

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

export function acquireLease(
  file,
  { staleMs = 30 * 60 * 1000, busy = "throw" } = {},
) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const descriptor = fs.openSync(file, "wx", 0o600);
      fs.writeFileSync(
        descriptor,
        `${JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() })}\n`,
      );
      fs.closeSync(descriptor);
      let released = false;
      return {
        release() {
          if (released) return;
          released = true;
          try {
            fs.unlinkSync(file);
          } catch (error) {
            if (error.code !== "ENOENT") throw error;
          }
        },
      };
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      let stale = false;
      try {
        const value = JSON.parse(fs.readFileSync(file, "utf8"));
        stale = !processIsAlive(value.pid);
      } catch {
        try {
          stale = Date.now() - fs.statSync(file).mtimeMs > staleMs;
        } catch (statError) {
          if (statError.code !== "ENOENT") throw statError;
          continue;
        }
      }
      if (stale) {
        try {
          fs.unlinkSync(file);
        } catch (unlinkError) {
          if (unlinkError.code !== "ENOENT") throw unlinkError;
        }
        continue;
      }
      if (busy === "skip") return null;
      throw new Error(`ALTA operation is already running (${file})`);
    }
  }
  if (busy === "skip") return null;
  throw new Error(`Unable to acquire ALTA operation lease (${file})`);
}

async function removeEmptyDirectories(root) {
  let entries;
  try {
    entries = await fs.promises.readdir(root, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  for (const entry of entries) {
    if (entry.isDirectory())
      await removeEmptyDirectories(path.join(root, entry.name));
  }
  try {
    const remaining = await fs.promises.readdir(root);
    if (!remaining.length) await fs.promises.rmdir(root).catch(() => {});
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}

function category(relative) {
  const parts = relative.split(path.sep);
  const top = parts[0];
  if (top === "target") return "buildBytes";
  if (["cargo", "rustup", "just", "python"].includes(top))
    return "toolchainBytes";
  if (
    top === "cache" ||
    top === "tmp" ||
    top === "xdg" ||
    (top === "home" && ["cache", "tmp", "log"].includes(parts[1]))
  )
    return "cacheBytes";
  if (top === "home") return "durableBytes";
  return "runtimeBytes";
}

function isWithin(root, file) {
  const relative = path.relative(root, file);
  return (
    relative !== "" &&
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

function inventoryEntries(stateDir, entries) {
  const result = {
    totalBytes: 0,
    buildBytes: 0,
    toolchainBytes: 0,
    cacheBytes: 0,
    durableBytes: 0,
    runtimeBytes: 0,
    fileCount: 0,
  };
  for (const entry of entries) {
    result.totalBytes += entry.size;
    result[category(path.relative(stateDir, entry.file))] += entry.size;
    result.fileCount += 1;
  }
  return result;
}

function pressureFor({ totalBytes, freeBytes }, { maxBytes, reserveBytes }) {
  if (totalBytes >= maxBytes || freeBytes <= reserveBytes) return "critical";
  if (totalBytes >= maxBytes * 0.85 || freeBytes <= reserveBytes * 2)
    return "high";
  return "normal";
}

function defaultPolicy(env = process.env) {
  return {
    maxBytes: boundedNumber(env.ALTA_STORAGE_MAX_GB, 20, 2, 1024) * GIB,
    reserveBytes: boundedNumber(env.ALTA_STORAGE_RESERVE_GB, 5, 1, 256) * GIB,
    cacheMaxBytes: boundedNumber(env.ALTA_CACHE_MAX_GB, 2, 0.25, 128) * GIB,
    cacheTtlMs: boundedNumber(env.ALTA_CACHE_TTL_DAYS, 7, 1, 365) * DAY_MS,
    tempTtlMs:
      boundedNumber(env.ALTA_TEMP_TTL_HOURS, 24, 1, 720) * 60 * 60 * 1000,
    logTtlMs: boundedNumber(env.ALTA_LOG_TTL_DAYS, 14, 1, 365) * DAY_MS,
    intervalMs: boundedNumber(
      env.ALTA_MAINTENANCE_INTERVAL_MS,
      5 * 60 * 1000,
      60_000,
      24 * 60 * 60 * 1000,
    ),
    admissionCacheMs: boundedNumber(
      env.ALTA_STORAGE_ADMISSION_CACHE_MS,
      1000,
      100,
      60_000,
    ),
    ioConcurrency: boundedNumber(env.ALTA_STORAGE_IO_CONCURRENCY, 16, 1, 64),
    keepBuildCache: env.ALTA_KEEP_BUILD_CACHE === "1",
  };
}

function atomicJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, {
    mode: 0o600,
  });
  fs.renameSync(temporary, file);
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "unknown";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export class StorageManager {
  #admission = null;
  #running = false;
  #timer = null;

  constructor(stateDir, policy = {}) {
    this.stateDir = stateDir;
    this.policy = { ...defaultPolicy(), ...policy };
    this.runtimeDir = path.join(stateDir, "runtime");
    this.statusFile = path.join(this.runtimeDir, "storage-status.json");
    this.lastSnapshot = null;
  }

  async snapshot(entries) {
    const currentEntries =
      entries ?? (await walkFiles(this.stateDir, this.policy.ioConcurrency));
    const usage = inventoryEntries(this.stateDir, currentEntries);
    const disk = await fs.promises.statfs(this.stateDir);
    const freeBytes = disk.bavail * disk.bsize;
    const snapshot = {
      ...usage,
      freeBytes,
      maxBytes: this.policy.maxBytes,
      reserveBytes: this.policy.reserveBytes,
      pressure: pressureFor(
        { totalBytes: usage.totalBytes, freeBytes },
        this.policy,
      ),
      checkedAt: new Date().toISOString(),
    };
    this.lastSnapshot = snapshot;
    this.#admission = {
      value:
        freeBytes > this.policy.reserveBytes &&
        usage.totalBytes < this.policy.maxBytes,
      expiresAt: Date.now() + this.policy.admissionCacheMs,
    };
    atomicJson(this.statusFile, snapshot);
    return snapshot;
  }

  canAcceptWork() {
    if (this.#admission?.expiresAt > Date.now()) return this.#admission.value;
    try {
      const disk = fs.statfsSync(this.stateDir);
      const freeBytes = disk.bavail * disk.bsize;
      const value =
        freeBytes > this.policy.reserveBytes &&
        (!this.lastSnapshot ||
          this.lastSnapshot.totalBytes < this.policy.maxBytes);
      this.#admission = {
        value,
        expiresAt: Date.now() + this.policy.admissionCacheMs,
      };
      return value;
    } catch {
      this.#admission = {
        value: false,
        expiresAt: Date.now() + this.policy.admissionCacheMs,
      };
      return false;
    }
  }

  async maintain({ dryRun = false } = {}) {
    const lease = acquireLease(path.join(this.runtimeDir, "maintenance.lock"), {
      staleMs: this.policy.intervalMs * 2,
      busy: "skip",
    });
    if (!lease) return { skipped: true, reason: "maintenance already running" };
    let buildLease;
    try {
      const removed = [];
      const binary = path.join(
        this.stateDir,
        "bin",
        process.platform === "win32" ? "codex.exe" : "codex",
      );
      const codeModeHost = path.join(
        this.stateDir,
        "bin",
        process.platform === "win32"
          ? "codex-code-mode-host.exe"
          : "codex-code-mode-host",
      );
      const target = path.join(this.stateDir, "target");
      const buildLock = path.join(this.runtimeDir, "build.lock");
      buildLease = acquireLease(buildLock, {
        staleMs: 6 * 60 * 60 * 1000,
        busy: "skip",
      });
      if (!buildLease)
        return { skipped: true, reason: "runtime build in progress" };
      const disposableBuildPaths = [
        target,
        path.join(this.stateDir, "cargo", "registry"),
        path.join(this.stateDir, "cargo", "git"),
      ];
      if (
        fs.existsSync(binary) &&
        fs.existsSync(codeModeHost) &&
        buildLease &&
        !this.policy.keepBuildCache
      ) {
        for (const disposable of disposableBuildPaths) {
          if (!fs.existsSync(disposable)) continue;
          removed.push({ path: disposable, reason: "disposable build cache" });
          if (!dryRun)
            await fs.promises.rm(disposable, { recursive: true, force: true });
        }
      }

      const roots = [
        [path.join(this.stateDir, "cache"), this.policy.cacheTtlMs],
        [path.join(this.stateDir, "xdg", "cache"), this.policy.cacheTtlMs],
        [path.join(this.stateDir, "home", "cache"), this.policy.cacheTtlMs],
        [path.join(this.stateDir, "tmp"), this.policy.tempTtlMs],
        [path.join(this.stateDir, "home", "tmp"), this.policy.tempTtlMs],
        [path.join(this.stateDir, "home", "log"), this.policy.logTtlMs],
      ];
      const entries = await walkFiles(this.stateDir, this.policy.ioConcurrency);
      const now = Date.now();
      const retained = [];
      const plannedDeletes = [];
      for (const entry of entries) {
        const rootPolicy = roots.find(([root]) => isWithin(root, entry.file));
        if (!rootPolicy) continue;
        const [, ttlMs] = rootPolicy;
        if (now - entry.mtimeMs > ttlMs) {
          removed.push({ path: entry.file, reason: "expired cache" });
          plannedDeletes.push(entry.file);
        } else {
          retained.push(entry);
        }
      }
      let retainedBytes = retained.reduce((sum, entry) => sum + entry.size, 0);
      for (const entry of retained.sort((a, b) => a.mtimeMs - b.mtimeMs)) {
        if (retainedBytes <= this.policy.cacheMaxBytes) break;
        removed.push({ path: entry.file, reason: "cache size cap" });
        retainedBytes -= entry.size;
        plannedDeletes.push(entry.file);
      }
      let afterEntries = entries;
      let failures = [];
      if (!dryRun && plannedDeletes.length) {
        const deletion = await unlinkFiles(
          [...new Set(plannedDeletes)],
          this.policy.ioConcurrency,
        );
        failures = deletion.failures;
        const deleted = new Set(deletion.removed);
        afterEntries = entries.filter((entry) => !deleted.has(entry.file));
        for (const [root] of roots) await removeEmptyDirectories(root);
      }

      let after = await this.snapshot(afterEntries);
      if (after.pressure === "critical" && buildLease) {
        const packageCache = path.join(
          this.stateDir,
          "cargo",
          "registry",
          "cache",
        );
        if (fs.existsSync(packageCache)) {
          removed.push({ path: packageCache, reason: "critical disk reserve" });
          if (!dryRun)
            await fs.promises.rm(packageCache, {
              recursive: true,
              force: true,
            });
          if (!dryRun) {
            afterEntries = afterEntries.filter(
              (entry) => !isWithin(packageCache, entry.file),
            );
            after = await this.snapshot(afterEntries);
          }
        }
      }
      return { skipped: false, dryRun, removed, failures, snapshot: after };
    } finally {
      buildLease?.release();
      lease.release();
    }
  }

  start(onError = () => {}) {
    if (this.#timer) return () => this.stop();
    this.#timer = setInterval(async () => {
      if (this.#running) return;
      this.#running = true;
      try {
        await this.maintain();
      } catch (error) {
        onError(error);
      } finally {
        this.#running = false;
      }
    }, this.policy.intervalMs);
    this.#timer.unref?.();
    return () => this.stop();
  }

  stop() {
    if (this.#timer) clearInterval(this.#timer);
    this.#timer = null;
  }
}
