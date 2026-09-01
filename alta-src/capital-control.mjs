import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { createHash, randomBytes } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { atomicWriteJson } from "./durable-file.mjs";
import {
  externalCredentialRoot,
  findCredentialFile,
  readCredentialText,
} from "./credential-files.mjs";
import { executableInPath } from "./process-runner.mjs";
import { acquireLease } from "./storage.mjs";
import { sanitizeCapitalSnapshot } from "./capital-snapshot.mjs";

const PAPER_ACCOUNT = /^\d{17}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_PROCESS_OUTPUT = 256 * 1024;
const CAPITAL_TIMEOUT_SECONDS = 20;
const CAPITAL_PROCESS_TIMEOUT_MS = 55_000;
const DEFAULT_MAX_ORDER_NOTIONAL = "10000";
const DEFAULT_MAX_OPEN_POSITIONS = "4";
const DEFAULT_MAX_DISPATCH_QUOTE_AGE_SECONDS = "10";
const MAX_AUDIT_EVENTS = 100;
export const PAPER_MUTATION_LEASE_PROTOCOL = "alta.paper-mutation-lease.v1";

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function safeError(error) {
  return String(error?.message ?? error ?? "Paper capital operation failed")
    .split("\n")[0]
    .slice(0, 300);
}

function processStartIdentity(pid) {
  const result = spawnSync("/bin/ps", ["-p", String(pid), "-o", "lstart="], {
    encoding: "utf8",
    timeout: 2_000,
    env: { PATH: "/usr/bin:/bin", LC_ALL: "C" },
  });
  const value = String(result.stdout ?? "")
    .trim()
    .replace(/\s+/g, " ");
  if (result.status !== 0 || !value)
    throw new Error("Paper process identity is unavailable");
  return `ps:${value}`;
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function paperMutationOwnerIsStale(current) {
  if (current.bootIdentity !== processStartIdentity(1)) return true;
  if (!processIsAlive(current.pid)) return true;
  try {
    return current.processStartIdentity !== processStartIdentity(current.pid);
  } catch (error) {
    if (!processIsAlive(current.pid)) return true;
    throw error;
  }
}

function validatePaperMutationLease(value, accountSha256) {
  const keys = Object.keys(value ?? {}).sort();
  const expected = [
    "accountSha256",
    "acquiredAt",
    "bootIdentity",
    "pid",
    "processStartIdentity",
    "protocol",
    "token",
  ].sort();
  if (
    JSON.stringify(keys) !== JSON.stringify(expected) ||
    value.protocol !== PAPER_MUTATION_LEASE_PROTOCOL ||
    value.accountSha256 !== accountSha256 ||
    !/^[a-f0-9]{64}$/.test(value.token) ||
    !Number.isSafeInteger(value.pid) ||
    value.pid < 1 ||
    typeof value.bootIdentity !== "string" ||
    typeof value.processStartIdentity !== "string"
  )
    throw new Error("Paper mutation lease is invalid");
  return value;
}

function syncLeaseDirectory(directory) {
  const descriptor = fs.openSync(directory, "r");
  try {
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

export function acquirePaperMutationLease(file, accountSha256) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const token = randomBytes(32).toString("hex");
  const owner = {
    protocol: PAPER_MUTATION_LEASE_PROTOCOL,
    accountSha256,
    token,
    pid: process.pid,
    bootIdentity: processStartIdentity(1),
    processStartIdentity: processStartIdentity(process.pid),
    acquiredAt: new Date().toISOString(),
  };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const temporary = path.join(
      path.dirname(file),
      `.${path.basename(file)}.${token}.tmp`,
    );
    let descriptor;
    try {
      descriptor = fs.openSync(temporary, "wx", 0o600);
      fs.writeFileSync(descriptor, `${JSON.stringify(owner)}\n`);
      fs.fsyncSync(descriptor);
      fs.closeSync(descriptor);
      descriptor = undefined;
      fs.linkSync(temporary, file);
      fs.unlinkSync(temporary);
      syncLeaseDirectory(path.dirname(file));
      let released = false;
      return {
        release() {
          if (released) return;
          const current = validatePaperMutationLease(
            JSON.parse(fs.readFileSync(file, "utf8")),
            accountSha256,
          );
          if (
            current.token !== token ||
            current.pid !== process.pid ||
            current.bootIdentity !== processStartIdentity(1) ||
            current.processStartIdentity !== processStartIdentity(process.pid)
          )
            throw new Error("Paper mutation lease ownership changed");
          fs.unlinkSync(file);
          syncLeaseDirectory(path.dirname(file));
          released = true;
        },
      };
    } catch (error) {
      if (descriptor !== undefined) fs.closeSync(descriptor);
      fs.rmSync(temporary, { force: true });
      if (error.code !== "EEXIST") throw error;
      const raw = fs.readFileSync(file);
      const current = validatePaperMutationLease(
        JSON.parse(raw.toString("utf8")),
        accountSha256,
      );
      const stale = paperMutationOwnerIsStale(current);
      if (!stale) return null;
      if (fs.readFileSync(file).equals(raw)) {
        fs.unlinkSync(file);
        syncLeaseDirectory(path.dirname(file));
        continue;
      }
      return null;
    }
  }
  return null;
}

function readJson(file) {
  try {
    const metadata = fs.lstatSync(file);
    if (metadata.isSymbolicLink() || !metadata.isFile())
      throw new Error("Paper capital state must be a regular file");
    if (process.platform !== "win32") {
      if ((metadata.mode & 0o077) !== 0)
        throw new Error("Paper capital state must be owner-only");
      if (
        typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()
      )
        throw new Error("Paper capital state must be owned by this user");
    }
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function assertOwnerOnlyFile(file) {
  const metadata = fs.lstatSync(file);
  if (metadata.isSymbolicLink() || !metadata.isFile())
    throw new Error("Tiger Paper configuration must be a regular file");
  if (process.platform !== "win32") {
    if ((metadata.mode & 0o077) !== 0)
      throw new Error("Tiger Paper configuration must be owner-only");
    if (
      typeof process.getuid === "function" &&
      metadata.uid !== process.getuid()
    )
      throw new Error("Tiger Paper configuration must be owned by this user");
  }
  if (!path.isAbsolute(file))
    throw new Error("Tiger Paper configuration path must be absolute");
}

function property(text, name) {
  const match = text.match(
    new RegExp(`(?:^|\\n)\\s*${name}\\s*=\\s*([^\\r\\n#]+)`, "i"),
  );
  return match?.[1]?.trim().replace(/^(?:"([\s\S]*)"|'([\s\S]*)')$/, "$1$2");
}

function isolatedEnvironment(rootDir) {
  const allowed = new Set([
    "HOME",
    "LANG",
    "PATH",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
  ]);
  const environment = Object.fromEntries(
    Object.entries(process.env).filter(
      ([key]) => allowed.has(key) || key.startsWith("LC_"),
    ),
  );
  environment.UV_PROJECT_ENVIRONMENT = path.join(
    rootDir,
    ".alta",
    "capital",
    "venv",
  );
  return environment;
}

export class PaperCapitalControl {
  constructor({ rootDir, stateDir, environment = () => process.env }) {
    this.rootDir = rootDir;
    this.stateDir = stateDir;
    this.environment = environment;
    this.authorizationFile = path.join(
      stateDir,
      "runtime",
      "paper-capital-authorization.json",
    );
    this.snapshotFile = path.join(
      stateDir,
      "runtime",
      "paper-capital-snapshot.json",
    );
    this.operationLockFile = path.join(
      stateDir,
      "runtime",
      "paper-capital-operation.lock",
    );
    this.ownerLeasePath = path.join(stateDir, "locks", "tiger-paper.owner");
  }

  configuration() {
    const environment = this.environment();
    const root = externalCredentialRoot(environment);
    const configuredPath = environment.ALTA_TIGER_CONFIG_PATH;
    const file = configuredPath
      ? path.resolve(configuredPath)
      : findCredentialFile(root, "broker", ["tiger"]);
    if (!file || !fs.existsSync(file))
      throw new Error("Tiger Paper credentials are not configured");
    assertOwnerOnlyFile(file);
    const text = readCredentialText(file);
    const account = property(text, "account");
    if (!account || !PAPER_ACCOUNT.test(account))
      throw new Error(
        "Tiger Paper configuration requires one 17-digit account",
      );
    if (!property(text, "tiger_id"))
      throw new Error("Tiger Paper configuration is missing tiger_id");
    if (
      !property(text, "private_key") &&
      !property(text, "private_key_pk1") &&
      !property(text, "private_key_pk8")
    )
      throw new Error("Tiger Paper configuration is missing a private key");
    return {
      file,
      accountSha256: hash(account),
      accountFingerprint: hash(account).slice(0, 12),
      configurationSha256: hash(text),
      configurationFingerprint: hash(text).slice(0, 12),
    };
  }

  authorization() {
    const value = readJson(this.authorizationFile);
    if (!value) return null;
    if (
      ![1, 2].includes(value.version) ||
      typeof value.enabled !== "boolean" ||
      !Array.isArray(value.audit)
    )
      throw new Error("Paper capital authorization state is invalid");
    const generation = value.generation ?? 1;
    if (!Number.isSafeInteger(generation) || generation < 1)
      throw new Error("Paper capital authorization generation is invalid");
    if (value.closeOnly !== undefined && typeof value.closeOnly !== "boolean")
      throw new Error("Paper capital drain state is invalid");
    return { ...value, generation, closeOnly: value.closeOnly === true };
  }

  riskPolicy() {
    const environment = this.environment();
    const maxOrderNotional = String(
      environment.ALTA_TIGER_PAPER_MAX_ORDER_NOTIONAL ??
        DEFAULT_MAX_ORDER_NOTIONAL,
    );
    const maxOpenPositions = String(
      environment.ALTA_TIGER_PAPER_MAX_OPEN_POSITIONS ??
        DEFAULT_MAX_OPEN_POSITIONS,
    );
    const maxDispatchQuoteAgeSeconds = String(
      environment.ALTA_TIGER_PAPER_MAX_DISPATCH_QUOTE_AGE_SECONDS ??
        DEFAULT_MAX_DISPATCH_QUOTE_AGE_SECONDS,
    );
    if (
      !/^\d+(?:\.\d+)?$/.test(maxOrderNotional) ||
      Number(maxOrderNotional) <= 0 ||
      Number(maxOrderNotional) > 1_000_000
    )
      throw new Error("Tiger Paper max order notional is invalid");
    if (
      !/^\d+$/.test(maxOpenPositions) ||
      Number(maxOpenPositions) < 1 ||
      Number(maxOpenPositions) > 8
    )
      throw new Error("Tiger Paper max open positions is invalid");
    if (
      !/^\d+$/.test(maxDispatchQuoteAgeSeconds) ||
      Number(maxDispatchQuoteAgeSeconds) < 1 ||
      Number(maxDispatchQuoteAgeSeconds) > 30
    )
      throw new Error("Tiger Paper dispatch quote age is invalid");
    return {
      maxOrderNotional,
      maxOpenPositions,
      maxDispatchQuoteAgeSeconds,
    };
  }

  status() {
    let configuration = null;
    let configurationError = null;
    try {
      configuration = this.configuration();
    } catch (error) {
      configurationError = safeError(error);
    }
    let authorization = null;
    let authorizationError = null;
    try {
      authorization = this.authorization();
    } catch (error) {
      authorizationError = safeError(error);
    }
    let snapshot = null;
    let snapshotError = null;
    try {
      const stored = readJson(this.snapshotFile);
      if (stored) {
        const savedAt = stored.savedAt;
        if (
          typeof savedAt !== "string" ||
          savedAt.length > 40 ||
          !Number.isFinite(Date.parse(savedAt))
        )
          throw new Error("Paper capital snapshot has an invalid save time");
        snapshot = {
          ...sanitizeCapitalSnapshot(stored),
          savedAt,
        };
      }
    } catch (error) {
      snapshotError = safeError(error);
    }
    const configurationMatches = Boolean(
      configuration &&
        authorization?.configurationSha256 ===
          configuration.configurationSha256 &&
        authorization?.accountSha256 === configuration.accountSha256,
    );
    const snapshotMatches = Boolean(
      configuration &&
        snapshot?.accountFingerprint === configuration.accountFingerprint,
    );
    if (authorization?.enabled && !snapshot && !snapshotError)
      snapshotError = "Paper capital authorization snapshot is missing";
    const enabled = Boolean(
      authorization?.enabled &&
        configurationMatches &&
        snapshotMatches &&
        !authorizationError &&
        !snapshotError,
    );
    let posture = "disabled";
    if (configurationError) posture = "not_configured";
    else if (authorizationError) posture = "authorization_invalid";
    else if (authorization?.enabled && !configurationMatches)
      posture = "configuration_changed";
    else if (authorization?.enabled && (!snapshotMatches || snapshotError))
      posture = "snapshot_invalid";
    else if (enabled && authorization?.closeOnly)
      posture = "paper_recovery_required";
    else if (enabled) posture = "paper_enabled";
    else if (snapshotError) posture = "snapshot_invalid";
    else if (snapshot) posture = "paper_ready_disabled";
    return {
      version: 1,
      provider: "Tiger Trade",
      environment: "PAPER",
      configured: Boolean(configuration),
      requestedEnabled: authorization?.enabled === true,
      authorizationGeneration: authorization?.generation ?? null,
      closeOnly: authorization?.closeOnly === true,
      drainRequired: authorization?.closeOnly === true,
      enabled,
      posture,
      accountFingerprint: configuration?.accountFingerprint ?? null,
      configurationFingerprint: configuration?.configurationFingerprint ?? null,
      mutationPolicy: "risk_budgeted_limit_day_v1",
      riskPolicy: this.riskPolicy(),
      instrumentPolicy: "us_stock_only",
      outsideRegularHours: false,
      requiresStoppedRuntime: true,
      lastChangedAt: authorization?.lastChangedAt ?? null,
      lastPreflightAt: authorization?.lastPreflightAt ?? null,
      configurationError,
      authorizationError,
      snapshotError,
      snapshot: snapshotMatches ? snapshot : null,
      audit: (authorization?.audit ?? []).slice(-MAX_AUDIT_EVENTS).reverse(),
    };
  }

  runtimeEnvironment() {
    const status = this.status();
    if (!status.enabled)
      return {
        ALTA_TIGER_PAPER_ENABLED: "0",
      };
    const configuration = this.configuration();
    return {
      ALTA_TIGER_PAPER_ENABLED: "1",
      ALTA_TIGER_CONFIG_PATH: configuration.file,
      ALTA_TIGER_PAPER_ACCOUNT_SHA256: configuration.accountSha256,
      ALTA_TIGER_ORDER_TIMEOUT_SECONDS: String(CAPITAL_TIMEOUT_SECONDS),
      ALTA_TIGER_PAPER_MAX_ORDER_NOTIONAL:
        this.riskPolicy().maxOrderNotional,
      ALTA_TIGER_PAPER_MAX_OPEN_POSITIONS:
        this.riskPolicy().maxOpenPositions,
      ALTA_TIGER_PAPER_MAX_DISPATCH_QUOTE_AGE_SECONDS:
        this.riskPolicy().maxDispatchQuoteAgeSeconds,
      ALTA_TIGER_PAPER_AUTHORIZATION_PATH: this.authorizationFile,
      ALTA_TIGER_PAPER_AUTHORIZATION_GENERATION: String(
        this.authorization().generation,
      ),
      ALTA_TIGER_PAPER_OWNER_LEASE_PATH: this.ownerLeasePathFor(configuration),
      ALTA_TIGER_PAPER_MUTATION_LEASE_PATH:
        this.mutationLeasePathFor(configuration),
    };
  }

  ownerLeasePathFor(configuration) {
    return path.join(
      os.homedir(),
      ".alta",
      "capital",
      "locks",
      `tiger-paper-${configuration.accountSha256}.owner`,
    );
  }

  mutationLeasePathFor(configuration) {
    return `${this.ownerLeasePathFor(configuration)}.mutation`;
  }

  async acquireMutationLease(configuration) {
    const file = this.mutationLeasePathFor(configuration);
    const deadline = Date.now() + 65_000;
    while (Date.now() < deadline) {
      const lease = acquirePaperMutationLease(
        file,
        configuration.accountSha256,
      );
      if (lease) return lease;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw Object.assign(
      new Error("Paper mutation did not drain before authorization revocation"),
      { code: "capital_mutation_drain_timeout", statusCode: 409 },
    );
  }

  async refresh() {
    const lease = acquireLease(this.operationLockFile, { busy: "skip" });
    if (!lease)
      throw Object.assign(
        new Error("A Paper capital operation is in progress"),
        {
          code: "capital_operation_in_progress",
          statusCode: 409,
        },
      );
    try {
      const configuration = this.configuration();
      const snapshot = await this.invoke("snapshot", configuration);
      this.writeSnapshot(snapshot, configuration);
      this.recordAudit("preflight_refreshed", "succeeded", configuration);
      return this.status();
    } catch (error) {
      this.recordAudit("preflight_refreshed", "failed", null, error);
      throw error;
    } finally {
      lease.release();
    }
  }

  async setEnabled(enabled) {
    if (typeof enabled !== "boolean")
      throw new Error("Paper capital authorization must be true or false");
    const lease = acquireLease(this.operationLockFile, { busy: "skip" });
    if (!lease)
      throw Object.assign(
        new Error("A Paper capital operation is in progress"),
        {
          code: "capital_operation_in_progress",
          statusCode: 409,
        },
      );
    try {
      if (!enabled) {
        let mutationLease = null;
        try {
          let currentAuthorization = null;
          try {
            currentAuthorization = this.authorization();
          } catch {
            // A corrupt authorization can only be recovered toward disabled.
          }
          if (currentAuthorization?.accountSha256) {
            mutationLease = await this.acquireMutationLease({
              accountSha256: currentAuthorization.accountSha256,
            });
          }
          const configuration = this.configuration();
          const snapshot = await this.invoke("snapshot", configuration);
          this.writeSnapshot(snapshot, configuration);
          const drainRequired =
            snapshot.positionCount !== 0 || snapshot.openOrderCount !== 0;
          this.writeAuthorization(
            drainRequired,
            configuration,
            drainRequired
              ? "authorization_drain_requested"
              : "authorization_disabled",
            "succeeded",
            {
              recoverInvalidPrevious: true,
              closeOnly: drainRequired,
            },
          );
        } finally {
          mutationLease?.release();
        }
        return this.status();
      }
      const current = this.status();
      if (current.enabled) return current;
      const configuration = this.configuration();
      const snapshot = await this.invoke("snapshot", configuration);
      if (snapshot.positionCount !== 0 || snapshot.openOrderCount !== 0)
        throw new Error(
          "Tiger Paper authorization requires an empty account and no open orders",
        );
      this.writeSnapshot(snapshot, configuration);
      this.writeAuthorization(
        true,
        configuration,
        "authorization_enabled",
        "succeeded",
        { closeOnly: false },
      );
      return this.status();
    } catch (error) {
      this.recordAudit(
        enabled ? "authorization_enabled" : "authorization_disabled",
        "failed",
        null,
        error,
      );
      throw error;
    } finally {
      lease.release();
    }
  }

  writeSnapshot(snapshot, configuration) {
    const validated = sanitizeCapitalSnapshot(snapshot);
    if (validated.accountFingerprint !== configuration.accountFingerprint)
      throw new Error(
        "Tiger Paper snapshot crossed the approved account binding",
      );
    atomicWriteJson(this.snapshotFile, {
      ...validated,
      savedAt: new Date().toISOString(),
    });
  }

  writeAuthorization(
    enabled,
    configuration,
    action,
    result,
    { recoverInvalidPrevious = false, closeOnly = false } = {},
  ) {
    let previous;
    try {
      previous = this.authorization() ?? { audit: [] };
    } catch (error) {
      if (!recoverInvalidPrevious || enabled) throw error;
      previous = { audit: [] };
    }
    const now = new Date().toISOString();
    const event = {
      id: randomBytes(12).toString("base64url"),
      action,
      result,
      knownAt: now,
      accountFingerprint:
        configuration?.accountFingerprint ??
        previous.accountSha256?.slice(0, 12) ??
        null,
    };
    atomicWriteJson(this.authorizationFile, {
      version: 2,
      generation: (previous.generation ?? 0) + 1,
      enabled,
      closeOnly: enabled && closeOnly,
      configurationSha256:
        configuration?.configurationSha256 ??
        previous.configurationSha256 ??
        null,
      accountSha256:
        configuration?.accountSha256 ?? previous.accountSha256 ?? null,
      lastChangedAt: now,
      lastPreflightAt:
        configuration && enabled ? now : (previous.lastPreflightAt ?? null),
      audit: [...(previous.audit ?? []), event].slice(-MAX_AUDIT_EVENTS),
    });
  }

  recordAudit(action, result, configuration, error = null) {
    const previous = this.authorization() ?? { audit: [] };
    const event = {
      id: randomBytes(12).toString("base64url"),
      action,
      result,
      knownAt: new Date().toISOString(),
      accountFingerprint:
        configuration?.accountFingerprint ??
        previous.accountSha256?.slice(0, 12) ??
        null,
      ...(error
        ? { errorFingerprint: hash(safeError(error)).slice(0, 16) }
        : {}),
    };
    atomicWriteJson(this.authorizationFile, {
      version: 2,
      generation: previous.generation ?? 1,
      enabled: previous.enabled === true,
      closeOnly: previous.closeOnly === true,
      configurationSha256: previous.configurationSha256 ?? null,
      accountSha256: previous.accountSha256 ?? null,
      lastChangedAt: previous.lastChangedAt ?? null,
      lastPreflightAt:
        result === "succeeded"
          ? event.knownAt
          : (previous.lastPreflightAt ?? null),
      audit: [...(previous.audit ?? []), event].slice(-MAX_AUDIT_EVENTS),
    });
  }

  invoke(action, configuration) {
    const uv = executableInPath("uv");
    if (!uv) throw new Error("uv is required for the isolated Paper process");
    const project = path.join(this.rootDir, "alta-runtime", "capital-python");
    const args = [
      "run",
      "--frozen",
      "--project",
      project,
      "python",
      "-m",
      "alta_capitald",
      action,
      "--config-path",
      configuration.file,
      "--account-sha256",
      configuration.accountSha256,
      "--owner-lease-path",
      this.ownerLeasePathFor(configuration),
      "--owner-id",
      `operator-${action}`,
      "--timeout-seconds",
      String(CAPITAL_TIMEOUT_SECONDS),
      "--max-limit-notional",
      this.riskPolicy().maxOrderNotional,
    ];
    return new Promise((resolve, reject) => {
      const child = spawn(uv, args, {
        cwd: this.rootDir,
        env: isolatedEnvironment(this.rootDir),
        stdio: ["ignore", "pipe", "pipe"],
      });
      const stdout = [];
      const stderr = [];
      let outputBytes = 0;
      let settled = false;
      const finish = (callback) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        callback();
      };
      const collect = (target) => (chunk) => {
        outputBytes += chunk.length;
        if (outputBytes > MAX_PROCESS_OUTPUT) {
          child.kill("SIGKILL");
          finish(() =>
            reject(new Error("Tiger Paper returned too much output")),
          );
          return;
        }
        target.push(Buffer.from(chunk));
      };
      child.stdout.on("data", collect(stdout));
      child.stderr.on("data", collect(stderr));
      child.once("error", (error) => finish(() => reject(error)));
      child.once("exit", (code, signal) =>
        finish(() => {
          if (signal)
            return reject(new Error("Tiger Paper process was interrupted"));
          const lines = Buffer.concat(stdout)
            .toString("utf8")
            .split(/\r?\n/)
            .filter(Boolean);
          let payload;
          try {
            payload = JSON.parse(lines.at(-1) ?? "");
          } catch {
            return reject(
              new Error("Tiger Paper returned an invalid response"),
            );
          }
          if (code !== 0 || payload.ok !== true) {
            const type = String(
              payload.errorType ?? "PaperExecutionFailure",
            ).slice(0, 64);
            const fingerprint = String(
              payload.errorFingerprint ?? hash(Buffer.concat(stderr)),
            ).slice(0, 64);
            const code =
              typeof payload.errorCode === "string" &&
              /^[A-Za-z0-9_.-]{1,32}$/.test(payload.errorCode)
                ? `[${payload.errorCode}]`
                : "";
            return reject(
              new Error(
                `Tiger Paper preflight failed: ${type}${code}:${fingerprint}`,
              ),
            );
          }
          try {
            resolve(sanitizeCapitalSnapshot(payload.result));
          } catch (error) {
            reject(error);
          }
        }),
      );
      const timer = setTimeout(() => {
        child.kill("SIGTERM");
        finish(() => reject(new Error("Tiger Paper preflight timed out")));
      }, CAPITAL_PROCESS_TIMEOUT_MS);
      timer.unref?.();
    });
  }
}
