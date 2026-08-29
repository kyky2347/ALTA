import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import net from "node:net";
import { randomBytes } from "node:crypto";
import { acquireLease } from "./storage.mjs";
import { atomicWrite } from "./durable-file.mjs";
import { loadResourceCredentials } from "./resource-credentials.mjs";
import { credentialInventory } from "./credential-control.mjs";
import {
  HostServicePlatform,
  launchdDefinition,
  managedServiceLayout,
  systemdDefinition,
} from "./host-service-platform.mjs";

const CAPTURED_SETTINGS = Object.freeze([
  "ALTA_CREDENTIALS_DIR",
  "ALTA_SERVICE_HOST",
  "ALTA_SERVICE_PORT",
  "ALTA_AUTONOMOUS_INTERVAL_SECONDS",
  "ALTA_AUTONOMOUS_HEARTBEAT_SECONDS",
  "ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS",
  "ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS",
  "ALTA_AUTONOMOUS_CYCLE_TIMEOUT_SECONDS",
  "ALTA_SUPERVISOR_RESTART_MAX_SECONDS",
  "ALTA_SUPERVISOR_STABLE_UPTIME_SECONDS",
  "ALTA_SUPERVISOR_PROBE_SECONDS",
  "ALTA_SUPERVISOR_UNHEALTHY_GRACE_SECONDS",
  "ALTA_SUPERVISOR_UNRESPONSIVE_GRACE_SECONDS",
  "ALTA_SUPERVISOR_SHUTDOWN_GRACE_SECONDS",
  "ALTA_SERVICE_LOG_MAX_MB",
  "ALTA_AGENT_PROVIDER",
  "ALTA_AGENT_MODEL",
  "ALTA_AGENT_REASONING_EFFORT",
  "ALTA_THESIS_PROVIDER",
  "ALTA_THESIS_MODEL",
  "ALTA_DISCONFIRMING_PROVIDER",
  "ALTA_DISCONFIRMING_MODEL",
  "ALTA_MODERATOR_PROVIDER",
  "ALTA_MODERATOR_MODEL",
  "ALTA_EXPRESSION_PROVIDER",
  "ALTA_EXPRESSION_MODEL",
  "ALTA_AUDIT_PROVIDER",
  "ALTA_AUDIT_MODEL",
  "ALTA_AGENT_DEADLINE_SECONDS",
  "ALTA_SCOUT_CONCURRENCY",
  "ALTA_UNIVERSE",
  "ALTA_MASSIVE_ENABLED",
  "ALTA_MASSIVE_DISCOVERY_ENABLED",
  "ALTA_MASSIVE_MAX_REQUESTS_PER_CYCLE",
  "ALTA_MASSIVE_BASE_URL",
  "ALTA_MASSIVE_ALLOW_INSECURE_HTTP",
  "ALTA_MASSIVE_AUTH_MODE",
  "ALTA_SHADOW_MAX_POSITION_NOTIONAL",
  "ALTA_SHADOW_REFERENCE_NAV",
  "ALTA_SHADOW_TRADE_LOSS_BUDGET_BPS",
  "ALTA_SHADOW_MAX_POSITION_NAV_BPS",
  "ALTA_SHADOW_MAX_GROSS_NAV_BPS",
  "ALTA_SHADOW_EQUITY_STRESS_FLOOR_BPS",
  "ALTA_SHADOW_MAX_EXIT_DAYS",
  "ALTA_SHADOW_ADV_PARTICIPATION_BPS",
  "ALTA_SHADOW_MIN_NET_ALPHA_BPS",
  "ALTA_WEB_XAI_MODEL",
  "ALTA_XAI_WEB_SEARCH_ENABLED",
  "ALTA_SEARXNG_URL",
  "ALTA_SEC_USER_AGENT",
  "CROSSREF_MAILTO",
]);

const PAPER_SERVICE_SETTINGS = Object.freeze([
  "ALTA_TIGER_PAPER_ENABLED",
  "ALTA_TIGER_CONFIG_PATH",
  "ALTA_TIGER_PAPER_ACCOUNT_SHA256",
  "ALTA_TIGER_ORDER_TIMEOUT_SECONDS",
]);

const DEFAULT_SETTINGS = Object.freeze({
  ALTA_ENVIRONMENT: "shadow",
  ALTA_AUTONOMOUS_ENABLED: "1",
  ALTA_SERVICE_HOST: "127.0.0.1",
  ALTA_SERVICE_PORT: "8876",
  ALTA_SERVICE_LOG_MAX_MB: "16",
  ALTA_TIGER_PAPER_ENABLED: "0",
});

function parseSettings(file) {
  const allowed = new Set([
    ...Object.keys(DEFAULT_SETTINGS),
    ...CAPTURED_SETTINGS,
    ...PAPER_SERVICE_SETTINGS,
  ]);
  const result = {};
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator < 1) throw new Error(`Invalid service setting in ${file}`);
    const key = line.slice(0, separator);
    if (!allowed.has(key)) throw new Error(`Unknown service setting ${key}`);
    const encoded = line.slice(separator + 1);
    result[key] = encoded.startsWith('"') ? JSON.parse(encoded) : encoded;
  }
  return result;
}

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function secureRegularFile(file) {
  const metadata = fs.lstatSync(file);
  if (metadata.isSymbolicLink() || !metadata.isFile())
    throw new Error(`ALTA service state must be a regular file: ${file}`);
  if (process.platform !== "win32") {
    if ((metadata.mode & 0o077) !== 0)
      throw new Error(`ALTA service state must be owner-only: ${file}`);
    if (
      typeof process.getuid === "function" &&
      metadata.uid !== process.getuid()
    )
      throw new Error(`ALTA service state must be owned by this user: ${file}`);
  }
  fs.chmodSync(file, 0o600);
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT" || error instanceof SyntaxError) return null;
    throw error;
  }
}

export class OpportunityService {
  constructor({
    rootDir,
    stateDir,
    cliFile,
    node = process.execPath,
    sourceEnv = process.env,
    platform = new HostServicePlatform(),
    environmentFactory,
  }) {
    this.rootDir = rootDir;
    this.stateDir = stateDir;
    this.cliFile = cliFile;
    this.node = node;
    this.sourceEnv = sourceEnv;
    this.platform = platform;
    this.environmentFactory = environmentFactory;
    const layout = managedServiceLayout({
      platform,
      stateDir,
      projectRoot: rootDir,
    });
    this.launchWorkingDirectory = layout.workingDirectory;
    this.configFile = path.join(stateDir, "opportunity-service.env");
    this.tokenFile = path.join(stateDir, "secrets", "opportunity_api_token");
    this.stateFile = path.join(stateDir, "runtime", "opportunity-host.json");
    this.supervisorStateFile = path.join(
      stateDir,
      "runtime",
      "opportunity-supervisor.json",
    );
    this.lockFile = path.join(stateDir, "runtime", "opportunity-host.lock");
    this.stdoutFile = path.join(layout.logDirectory, "opportunity-service.log");
    this.stderrFile = path.join(
      layout.logDirectory,
      "opportunity-service.error.log",
    );
  }

  ensureConfiguration() {
    if (!fs.existsSync(this.configFile)) {
      const settings = {
        ...DEFAULT_SETTINGS,
        ...Object.fromEntries(
          CAPTURED_SETTINGS.filter(
            (key) => this.sourceEnv[key] !== undefined,
          ).map((key) => [key, this.sourceEnv[key]]),
        ),
      };
      atomicWrite(
        this.configFile,
        `${Object.entries(settings)
          .map(([key, value]) => `${key}=${JSON.stringify(String(value))}`)
          .join("\n")}\n`,
      );
    }
    if (!fs.existsSync(this.tokenFile))
      atomicWrite(this.tokenFile, `${randomBytes(48).toString("base64url")}\n`);
    secureRegularFile(this.configFile);
    secureRegularFile(this.tokenFile);
    if (
      !/^[A-Za-z0-9_-]{43,128}$/.test(
        fs.readFileSync(this.tokenFile, "utf8").trim(),
      )
    )
      throw new Error("Invalid Opportunity service API token");
    return parseSettings(this.configFile);
  }

  runtimeEnvironment() {
    const configured = this.ensureConfiguration();
    const credentials = credentialInventory({
      ...this.sourceEnv,
      ...configured,
    });
    const resources = loadResourceCredentials({
      ...this.sourceEnv,
      ...configured,
    });
    const environment = {
      ...this.sourceEnv,
      ...configured,
      ...resources.values,
      ALTA_API_TOKEN: fs.readFileSync(this.tokenFile, "utf8").trim(),
      ALTA_CREDENTIAL_REVISION: credentials.revision,
      ALTA_CREDENTIAL_SLOTS: credentials.configuredSlots.join(","),
    };
    for (const key of Object.keys(environment)) {
      if (key.startsWith("TIGER_") || PAPER_SERVICE_SETTINGS.includes(key))
        delete environment[key];
    }
    environment.ALTA_TIGER_PAPER_ENABLED = "0";
    environment.PATH = [path.dirname(this.node), environment.PATH ?? ""]
      .filter(Boolean)
      .join(path.delimiter);
    if (configured.ALTA_MASSIVE_ENABLED === undefined)
      environment.ALTA_MASSIVE_ENABLED = resources.values.MASSIVE_API_KEY
        ? "1"
        : "0";
    return {
      environment,
      credentialSources: resources.sources,
      credentialRevision: credentials.revision,
      credentialSlots: credentials.configuredSlots,
    };
  }

  definition() {
    const values = {
      node: this.node,
      cli: this.cliFile,
      root: this.launchWorkingDirectory,
      stdout: this.stdoutFile,
      stderr: this.stderrFile,
    };
    if (this.platform.platform === "darwin") return launchdDefinition(values);
    if (this.platform.platform === "linux") return systemdDefinition(values);
    this.platform.definitionPath();
  }

  installed() {
    return fs.existsSync(this.platform.definitionPath());
  }

  install({ start = true } = {}) {
    this.ensureConfiguration();
    fs.mkdirSync(path.dirname(this.stdoutFile), {
      recursive: true,
      mode: 0o700,
    });
    for (const file of [this.stdoutFile, this.stderrFile]) {
      if (!fs.existsSync(file)) atomicWrite(file, "");
      else fs.chmodSync(file, 0o600);
    }
    return this.platform.install(this.definition(), { start });
  }

  async assertEndpointAvailable() {
    const configured = this.ensureConfiguration();
    const host = configured.ALTA_SERVICE_HOST;
    const port = Number(configured.ALTA_SERVICE_PORT);
    if (!Number.isInteger(port) || port < 1024 || port > 65535)
      throw new Error("ALTA_SERVICE_PORT must be from 1024 through 65535");
    await new Promise((resolve, reject) => {
      const probe = net.createServer();
      probe.unref();
      probe.once("error", (error) => {
        if (error.code === "EADDRINUSE")
          reject(
            new Error(
              `Opportunity endpoint ${host}:${port} is already in use; set ALTA_SERVICE_PORT before the first install`,
            ),
          );
        else reject(error);
      });
      probe.listen({ host, port, exclusive: true }, () => probe.close(resolve));
    });
  }

  async run() {
    const lease = acquireLease(this.lockFile, {
      staleMs: 24 * 60 * 60 * 1000,
    });
    const controller = new AbortController();
    const stop = () =>
      controller.abort(new Error("Opportunity service stopped"));
    process.once("SIGINT", stop);
    process.once("SIGTERM", stop);
    let exitCode = 1;
    let logGuard = null;
    try {
      const { environment, credentialRevision, credentialSlots } =
        this.runtimeEnvironment();
      const logMaximumBytes =
        Number(environment.ALTA_SERVICE_LOG_MAX_MB) * 1024 ** 2;
      if (!Number.isFinite(logMaximumBytes) || logMaximumBytes < 1024 ** 2)
        throw new Error("ALTA_SERVICE_LOG_MAX_MB must be at least 1");
      logGuard = setInterval(() => {
        for (const file of [this.stdoutFile, this.stderrFile]) {
          try {
            if (fs.statSync(file).size > logMaximumBytes)
              fs.truncateSync(file, 0);
          } catch (error) {
            if (error.code !== "ENOENT") throw error;
          }
        }
      }, 60_000);
      logGuard.unref?.();
      const manager = this.environmentFactory(environment);
      this.writeState("bootstrapping");
      await manager.up();
      if (controller.signal.aborted) return 0;
      const migration = await manager.python(
        ["-m", "alta_asterism", "migrate", "upgrade"],
        { signal: controller.signal, timeoutMs: 5 * 60_000 },
      );
      if (migration !== 0) {
        exitCode = migration;
        return exitCode;
      }
      this.writeState("running", {
        credentialRevision,
        credentialSlots,
      });
      exitCode = await manager.python(
        [
          "-m",
          "alta_asterism",
          "supervisor",
          "--host",
          environment.ALTA_SERVICE_HOST,
          "--port",
          environment.ALTA_SERVICE_PORT,
          "--state-file",
          this.supervisorStateFile,
        ],
        { signal: controller.signal },
      );
      return exitCode;
    } finally {
      if (logGuard) clearInterval(logGuard);
      process.removeListener("SIGINT", stop);
      process.removeListener("SIGTERM", stop);
      this.writeState(controller.signal.aborted ? "stopped" : "exited", {
        exitCode,
      });
      lease.release();
    }
  }

  async waitForReadiness(timeoutMilliseconds = 180_000) {
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
      const status = await this.status();
      if (status.ready) return status;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error(
      "Opportunity service did not become ready before the deadline",
    );
  }

  async stop(timeoutMilliseconds = 60_000) {
    this.platform.stop();
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
      const host = readJson(this.stateFile);
      if (!host || !processIsAlive(host.processId)) {
        if (host?.state !== "stopped")
          this.writeState("stopped", { exitCode: host?.exitCode ?? null });
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(
      "Opportunity service did not stop cleanly before the deadline",
    );
  }

  writeState(state, detail = {}) {
    atomicWrite(
      this.stateFile,
      `${JSON.stringify(
        {
          state,
          processId: state === "stopped" ? null : process.pid,
          platform: this.platform.platform,
          updatedAt: new Date().toISOString(),
          ...detail,
        },
        null,
        2,
      )}\n`,
    );
  }

  async status() {
    const host = readJson(this.stateFile);
    const supervisor = readJson(this.supervisorStateFile);
    const configured = fs.existsSync(this.configFile)
      ? parseSettings(this.configFile)
      : DEFAULT_SETTINGS;
    let credentials;
    try {
      const inventory = credentialInventory({
        ...this.sourceEnv,
        ...configured,
      });
      credentials = {
        valid: true,
        currentRevision: inventory.revision,
        loadedRevision: host?.credentialRevision ?? null,
        configuredSlots: inventory.configuredSlots,
        reloadRequired: Boolean(
          host?.processId &&
            processIsAlive(host.processId) &&
            host.credentialRevision !== inventory.revision,
        ),
      };
    } catch (error) {
      credentials = {
        valid: false,
        error: String(error.message).split("\n")[0].slice(0, 300),
      };
    }
    let ready = false;
    try {
      const response = await fetch(
        `http://${configured.ALTA_SERVICE_HOST}:${configured.ALTA_SERVICE_PORT}/health/ready`,
        { signal: AbortSignal.timeout(1_000) },
      );
      ready = response.ok && (await response.json()).ready === true;
    } catch {
      ready = false;
    }
    const platform = this.platform.status();
    return {
      installed: this.installed(),
      platformActive: platform.code === 0,
      host: host
        ? { ...host, processAlive: processIsAlive(host.processId) }
        : null,
      supervisor: supervisor
        ? {
            ...supervisor,
            childProcessAlive: processIsAlive(supervisor.childPid),
          }
        : null,
      ready,
      endpoint: `http://${configured.ALTA_SERVICE_HOST}:${configured.ALTA_SERVICE_PORT}`,
      capitalMode: "disabled",
      credentials,
    };
  }

  tailLogs(limit = 120) {
    const output = {};
    for (const [name, file] of [
      ["output", this.stdoutFile],
      ["error", this.stderrFile],
    ]) {
      if (!fs.existsSync(file)) {
        output[name] = [];
        continue;
      }
      output[name] = fs.readFileSync(file, "utf8").split(/\r?\n/).slice(-limit);
    }
    return output;
  }
}
