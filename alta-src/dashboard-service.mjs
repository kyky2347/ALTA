import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import { atomicWrite, atomicWriteJson } from "./durable-file.mjs";
import {
  HostServicePlatform,
  managedLaunchdDefinition,
  managedServiceLayout,
  managedSystemdDefinition,
} from "./host-service-platform.mjs";
import {
  createOperatorConsole,
  OPERATOR_PROTOCOL_VERSION,
} from "./operator-console.mjs";
import { acquireLease } from "./storage.mjs";

export const DASHBOARD_SERVICE_LABEL = "app.alta.asterism.dashboard";
export const DASHBOARD_SYSTEMD_UNIT = "alta-dashboard.service";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8877;
const LOG_MAXIMUM_BYTES = 16 * 1024 * 1024;

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function safeError(error) {
  return String(error?.message ?? error ?? "Unknown dashboard failure")
    .split("\n")[0]
    .slice(0, 300);
}

function secureJson(file) {
  try {
    const metadata = fs.lstatSync(file);
    if (metadata.isSymbolicLink() || !metadata.isFile())
      throw new Error("Dashboard host state must be a regular file");
    if (process.platform !== "win32") {
      if ((metadata.mode & 0o077) !== 0)
        throw new Error("Dashboard host state must be owner-only");
      if (
        typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()
      )
        throw new Error("Dashboard host state must be owned by this user");
    }
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT" || error instanceof SyntaxError) return null;
    throw error;
  }
}

function ensureLoopback(host) {
  if (!["127.0.0.1", "localhost", "::1"].includes(host))
    throw new Error("The managed operator dashboard must bind to loopback");
}

function ensurePort(port) {
  if (!Number.isInteger(port) || port < 1024 || port > 65_535)
    throw new Error("Dashboard port must be from 1024 through 65535");
}

export class DashboardService {
  constructor({
    rootDir,
    stateDir,
    cliFile,
    service,
    environmentFactory,
    node = process.execPath,
    host = DEFAULT_HOST,
    port = DEFAULT_PORT,
    platform = new HostServicePlatform({
      label: DASHBOARD_SERVICE_LABEL,
      systemdUnit: DASHBOARD_SYSTEMD_UNIT,
      fallbackCommand: "./alta dashboard run",
    }),
  }) {
    ensureLoopback(host);
    ensurePort(port);
    this.rootDir = rootDir;
    this.stateDir = stateDir;
    this.cliFile = cliFile;
    this.service = service;
    this.environmentFactory = environmentFactory;
    this.node = node;
    this.host = host;
    this.port = port;
    this.platform = platform;
    this.staticDir = path.join(rootDir, "alta-dashboard", "dist");
    const layout = managedServiceLayout({
      platform,
      stateDir,
      projectRoot: rootDir,
    });
    this.launchWorkingDirectory = layout.workingDirectory;
    this.stateFile = path.join(
      stateDir,
      "runtime",
      "operator-console-host.json",
    );
    this.lockFile = path.join(
      stateDir,
      "runtime",
      "operator-console-host.lock",
    );
    const { logDirectory } = layout;
    this.stdoutFile = path.join(logDirectory, "operator-console.log");
    this.stderrFile = path.join(logDirectory, "operator-console.error.log");
  }

  ensureBuilt() {
    if (!fs.existsSync(path.join(this.staticDir, "index.html")))
      throw new Error(
        "ALTA dashboard is not built; run pnpm dashboard:build before installation",
      );
  }

  definition() {
    const values = {
      node: this.node,
      cli: this.cliFile,
      args: ["dashboard", "run"],
      root: this.launchWorkingDirectory,
      stdout: this.stdoutFile,
      stderr: this.stderrFile,
    };
    if (this.platform.platform === "darwin")
      return managedLaunchdDefinition({
        ...values,
        label: DASHBOARD_SERVICE_LABEL,
      });
    if (this.platform.platform === "linux")
      return managedSystemdDefinition({
        ...values,
        description: "ALTA local operator dashboard (research-only)",
        after: ["network-online.target"],
        wants: ["network-online.target"],
      });
    this.platform.definitionPath();
  }

  installed() {
    return fs.existsSync(this.platform.definitionPath());
  }

  install({ start = true } = {}) {
    this.ensureBuilt();
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
    await new Promise((resolve, reject) => {
      const probe = net.createServer();
      probe.unref();
      probe.once("error", (error) => {
        if (error.code === "EADDRINUSE")
          reject(
            new Error(
              `Operator dashboard endpoint ${this.host}:${this.port} is already in use`,
            ),
          );
        else reject(error);
      });
      probe.listen({ host: this.host, port: this.port, exclusive: true }, () =>
        probe.close(resolve),
      );
    });
  }

  writeState(state, detail = {}) {
    atomicWriteJson(this.stateFile, {
      state,
      processId: ["stopped", "exited"].includes(state) ? null : process.pid,
      platform: this.platform.platform,
      endpoint: `http://${this.host}:${this.port}`,
      protocolVersion: OPERATOR_PROTOCOL_VERSION,
      updatedAt: new Date().toISOString(),
      ...detail,
    });
  }

  trimLogs() {
    for (const file of [this.stdoutFile, this.stderrFile]) {
      try {
        if (fs.statSync(file).size > LOG_MAXIMUM_BYTES)
          fs.truncateSync(file, 0);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
  }

  async run({ signal } = {}) {
    const lease = acquireLease(this.lockFile, {
      staleMs: 24 * 60 * 60 * 1000,
    });
    const startedAt = new Date().toISOString();
    let consoleServer = null;
    let closing = null;
    let failure = null;
    let logGuard = null;
    let stopRequested = signal?.aborted ?? false;
    const close = () => {
      if (!consoleServer || !consoleServer.server.listening)
        return Promise.resolve();
      closing ??= consoleServer.close();
      return closing;
    };
    const requestStop = () => {
      stopRequested = true;
      void close().catch(() => {});
    };
    process.once("SIGINT", requestStop);
    process.once("SIGTERM", requestStop);
    signal?.addEventListener("abort", requestStop, { once: true });
    try {
      this.ensureBuilt();
      this.trimLogs();
      logGuard = setInterval(() => this.trimLogs(), 60_000);
      logGuard.unref?.();
      this.writeState("bootstrapping", { startedAt });
      let publicState = null;
      consoleServer = createOperatorConsole({
        host: this.host,
        port: this.port,
        staticDir: this.staticDir,
        service: this.service,
        environmentFactory: this.environmentFactory,
        onBootstrapUsed: () => {
          if (!publicState) return;
          publicState = { ...publicState, bootstrapAvailable: false };
          delete publicState.openUrl;
          this.writeState("running", publicState);
        },
      });
      const closed = new Promise((resolve) =>
        consoleServer.server.once("close", resolve),
      );
      const location = await consoleServer.listen();
      publicState = {
        startedAt,
        origin: location.origin,
        openUrl: location.openUrl,
        bootstrapAvailable: true,
      };
      this.writeState("running", publicState);
      console.log("ALTA managed operator console ready");
      if (stopRequested) await close();
      await closed;
      return 0;
    } catch (error) {
      failure = error;
      throw error;
    } finally {
      if (logGuard) clearInterval(logGuard);
      process.removeListener("SIGINT", requestStop);
      process.removeListener("SIGTERM", requestStop);
      signal?.removeEventListener("abort", requestStop);
      await close().catch(() => {});
      this.writeState(failure ? "exited" : "stopped", {
        startedAt,
        ...(failure ? { error: safeError(failure), exitCode: 1 } : {}),
      });
      lease.release();
    }
  }

  async status() {
    const host = secureJson(this.stateFile);
    let ready = false;
    try {
      const response = await fetch(
        `http://${this.host}:${this.port}/health/ready`,
        { signal: AbortSignal.timeout(1_000) },
      );
      const payload = await response.json();
      ready =
        response.ok &&
        payload?.data?.ready === true &&
        payload.data.protocolVersion === OPERATOR_PROTOCOL_VERSION;
    } catch {
      ready = false;
    }
    const platform = this.platform.status();
    return {
      installed: this.installed(),
      platformActive: platform.code === 0,
      ready,
      endpoint: `http://${this.host}:${this.port}`,
      host: host
        ? { ...host, processAlive: processIsAlive(host.processId) }
        : null,
    };
  }

  async waitForReadiness(timeoutMilliseconds = 30_000) {
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
      const status = await this.status();
      if (status.ready) return status;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(
      "Operator dashboard did not become ready before the deadline; inspect ./alta dashboard logs",
    );
  }

  async stop(timeoutMilliseconds = 15_000) {
    this.platform.stop();
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
      const host = secureJson(this.stateFile);
      if (!host || !processIsAlive(host.processId)) {
        if (host?.state !== "stopped") this.writeState("stopped");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(
      "Operator dashboard did not stop cleanly before the deadline",
    );
  }

  openUrl() {
    const host = secureJson(this.stateFile);
    if (!host || host.state !== "running" || !processIsAlive(host.processId))
      throw new Error("Operator dashboard is not running");
    if (!host.bootstrapAvailable || !host.openUrl)
      throw new Error(
        "The one-time dashboard link was already used; an authorized browser can reconnect, or run ./alta dashboard restart for a fresh link",
      );
    return host.openUrl;
  }

  tailLogs(limit = 120) {
    const output = {};
    for (const [name, file] of [
      ["output", this.stdoutFile],
      ["error", this.stderrFile],
    ]) {
      output[name] = fs.existsSync(file)
        ? fs.readFileSync(file, "utf8").split(/\r?\n/).slice(-limit)
        : [];
    }
    return output;
  }
}
