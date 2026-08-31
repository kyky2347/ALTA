import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createHash, randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
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
const MAX_AUDIT_EVENTS = 100;

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function safeError(error) {
  return String(error?.message ?? error ?? "Paper capital operation failed")
    .split("\n")[0]
    .slice(0, 300);
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
      value.version !== 1 ||
      typeof value.enabled !== "boolean" ||
      !Array.isArray(value.audit)
    )
      throw new Error("Paper capital authorization state is invalid");
    return value;
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
    else if (enabled) posture = "paper_enabled";
    else if (snapshotError) posture = "snapshot_invalid";
    else if (snapshot) posture = "paper_ready_disabled";
    return {
      version: 1,
      provider: "Tiger Trade",
      environment: "PAPER",
      configured: Boolean(configuration),
      requestedEnabled: authorization?.enabled === true,
      enabled,
      posture,
      accountFingerprint: configuration?.accountFingerprint ?? null,
      configurationFingerprint: configuration?.configurationFingerprint ?? null,
      mutationPolicy: "one_share_limit_day",
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
    };
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
        this.writeAuthorization(
          false,
          null,
          "authorization_disabled",
          "succeeded",
          { recoverInvalidPrevious: true },
        );
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
    { recoverInvalidPrevious = false } = {},
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
      version: 1,
      enabled,
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
      version: 1,
      enabled: previous.enabled === true,
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
      this.ownerLeasePath,
      "--owner-id",
      `operator-${action}`,
      "--timeout-seconds",
      String(CAPITAL_TIMEOUT_SECONDS),
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
