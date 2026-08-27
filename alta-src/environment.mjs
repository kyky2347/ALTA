import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn, spawnSync } from "node:child_process";
import { acquireLease } from "./storage.mjs";
import {
  agentSafeChildEnvironment,
  ensureRuntimeConfiguration,
  readRuntimeSettings,
  runtimeChildEnvironment,
  runtimePaths,
  ALTA_PYTHON_VERSION,
} from "./environment-config.mjs";

export {
  agentSafeChildEnvironment,
  ensureRuntimeConfiguration,
  runtimeChildEnvironment,
  runtimePaths,
  ALTA_PYTHON_VERSION,
} from "./environment-config.mjs";

function executable(name, env) {
  if (path.isAbsolute(name)) return fs.existsSync(name) ? name : null;
  const suffix = process.platform === "win32" ? ".exe" : "";
  const candidates = (env.PATH ?? "")
    .split(path.delimiter)
    .filter(Boolean)
    .map((directory) => path.join(directory, `${name}${suffix}`));
  if (process.platform === "darwin") {
    if (name === "uv")
      candidates.push(path.join(os.homedir(), ".local/bin/uv"));
    if (name === "docker")
      candidates.push(
        path.join(os.homedir(), ".orbstack/bin/docker"),
        "/Applications/OrbStack.app/Contents/MacOS/xbin/docker",
        "/Applications/Docker.app/Contents/Resources/bin/docker",
      );
  }
  return candidates.find(fs.existsSync) ?? null;
}

function defaultRunner(command, args, options = {}) {
  const capture = options.capture !== false;
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env,
    stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
    timeout: options.timeoutMs,
  });
  if (result.error) throw result.error;
  return {
    code: result.status ?? 1,
    signal: result.signal,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function defaultPassthroughRunner(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: "inherit",
    });
    let shutdownTimer;
    const stop = () => {
      if (child.exitCode !== null || child.signalCode !== null) return;
      child.kill("SIGTERM");
      shutdownTimer = setTimeout(() => child.kill("SIGKILL"), 10_000);
      shutdownTimer.unref?.();
    };
    const cleanup = () => {
      clearTimeout(shutdownTimer);
      options.signal?.removeEventListener("abort", stop);
    };
    if (options.signal?.aborted) stop();
    else options.signal?.addEventListener("abort", stop, { once: true });
    child.once("error", (error) => {
      cleanup();
      reject(error);
    });
    child.once("exit", (code, signal) => {
      cleanup();
      resolve({
        code: code ?? (signal ? 1 : 0),
        signal,
        stdout: "",
        stderr: "",
      });
    });
  });
}

function parseComposeRows(text) {
  const value = text.trim();
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    return value.split(/\r?\n/).map((line) => JSON.parse(line));
  }
}

export class RuntimeEnvironment {
  constructor({
    rootDir,
    stateDir,
    env = process.env,
    runner = defaultRunner,
    passthroughRunner = defaultPassthroughRunner,
    binaries = {},
  }) {
    this.rootDir = rootDir;
    this.stateDir = stateDir;
    this.env = env;
    this.runner = runner;
    this.passthroughRunner = passthroughRunner;
    this.files = runtimePaths(rootDir, stateDir);
    this.uv =
      "uv" in binaries
        ? binaries.uv
        : (env.ALTA_UV_BIN ?? executable("uv", env));
    this.docker =
      "docker" in binaries
        ? binaries.docker
        : (env.ALTA_DOCKER_BIN ?? executable("docker", env));
  }

  uvEnvironment() {
    return runtimeChildEnvironment(this.rootDir, this.stateDir, this.env);
  }

  async execute(command, args, options = {}) {
    if (!command) throw new Error(options.missing);
    const result = await this.runner(command, args, options);
    if (result.code !== 0) {
      const detail = result.stderr?.trim() || result.stdout?.trim();
      throw new Error(
        detail || `${path.basename(command)} exited with ${result.code}`,
      );
    }
    return result;
  }

  composeArguments(...args) {
    const settings = readRuntimeSettings(
      this.files.settingsFile,
      this.stateDir,
    );
    return [
      "compose",
      "--env-file",
      this.files.settingsFile,
      "-f",
      this.files.composeFile,
      "-p",
      settings.ALTA_COMPOSE_PROJECT,
      ...args,
    ];
  }

  async setupPython({ dev = false } = {}) {
    await this.execute(this.uv, ["python", "install", ALTA_PYTHON_VERSION], {
      cwd: this.files.pythonProject,
      env: this.uvEnvironment(),
      capture: false,
      missing:
        "uv is required (https://docs.astral.sh/uv/getting-started/installation/)",
    });
    const syncArguments = [
      "sync",
      "--project",
      this.files.pythonProject,
      "--frozen",
      dev ? "--all-groups" : "--no-dev",
      "--python",
      ALTA_PYTHON_VERSION,
    ];
    await this.execute(this.uv, syncArguments, {
      cwd: this.rootDir,
      env: this.uvEnvironment(),
      capture: false,
    });
    await this.execute(
      this.files.python,
      [
        "-c",
        "import pgvector, psycopg, pydantic, redis, alta_asterism; print('ALTA Python runtime ready')",
      ],
      { env: this.uvEnvironment(), capture: false },
    );
  }

  async verifyDocker(timeoutMs = 10_000) {
    return this.execute(
      this.docker,
      ["version", "--format", "{{.Server.Version}}"],
      {
        env: this.env,
        timeoutMs,
        missing:
          process.platform === "darwin"
            ? "Docker is missing; install and start OrbStack (recommended) or Docker Desktop"
            : "Docker Engine with Compose is required",
      },
    );
  }

  async verifyServices() {
    const settings = readRuntimeSettings(
      this.files.settingsFile,
      this.stateDir,
    );
    await this.execute(
      this.docker,
      this.composeArguments(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        settings.POSTGRES_USER,
        "-d",
        settings.POSTGRES_DB,
        "-c",
        "CREATE EXTENSION IF NOT EXISTS vector",
      ),
      { env: this.env },
    );
    await this.execute(
      this.docker,
      this.composeArguments(
        "exec",
        "-T",
        "redis",
        "sh",
        "-ec",
        'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli --no-auth-warning ping | grep -qx PONG',
      ),
      { env: this.env },
    );
  }

  async setup({ dev = false } = {}) {
    return this.#withLease(async () => {
      ensureRuntimeConfiguration(this.rootDir, this.stateDir, this.env);
      await this.setupPython({ dev });
      await this.verifyDocker();
      await this.execute(this.docker, this.composeArguments("pull"), {
        env: this.env,
        capture: false,
      });
      await this.#composeUp();
      await this.verifyServices();
    });
  }

  async up() {
    return this.#withLease(async () => {
      ensureRuntimeConfiguration(this.rootDir, this.stateDir, this.env);
      await this.verifyDocker();
      await this.#composeUp();
    });
  }

  async #composeUp() {
    await this.execute(
      this.docker,
      this.composeArguments(
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "180",
        "--remove-orphans",
      ),
      { env: this.env, capture: false },
    );
  }

  async down() {
    if (!fs.existsSync(this.files.settingsFile)) return;
    return this.#withLease(async () => {
      await this.verifyDocker();
      await this.execute(
        this.docker,
        this.composeArguments("down", "--remove-orphans"),
        { env: this.env, capture: false },
      );
    });
  }

  async restart() {
    return this.#withLease(async () => {
      ensureRuntimeConfiguration(this.rootDir, this.stateDir, this.env);
      await this.verifyDocker();
      await this.#composeUp();
      await this.verifyServices();
    });
  }

  async #withLease(action) {
    const lease = acquireLease(
      path.join(this.stateDir, "runtime", "environment.lock"),
    );
    try {
      return await action();
    } finally {
      lease.release();
    }
  }

  async logs(services = []) {
    if (!fs.existsSync(this.files.settingsFile))
      throw new Error("Run ./alta env setup before reading service logs");
    for (const service of services)
      if (!new Set(["postgres", "redis"]).has(service))
        throw new Error(`Unknown ALTA service ${service}`);
    await this.verifyDocker();
    await this.execute(
      this.docker,
      this.composeArguments("logs", "--tail", "200", ...services),
      { env: this.env, capture: false },
    );
  }

  async python(args, { signal } = {}) {
    if (!fs.existsSync(this.files.python))
      throw new Error("Run ./alta env setup before using the managed Python");
    const controller = new AbortController();
    const forwardAbort = () =>
      controller.abort(signal?.reason ?? new Error("Managed Python aborted"));
    const onInterrupt = () =>
      controller.abort(new Error("Managed Python interrupted"));
    if (signal?.aborted) forwardAbort();
    else signal?.addEventListener("abort", forwardAbort, { once: true });
    process.once("SIGINT", onInterrupt);
    process.once("SIGTERM", onInterrupt);
    try {
      const result = await this.passthroughRunner(this.files.python, args, {
        cwd: this.rootDir,
        env: this.uvEnvironment(),
        signal: controller.signal,
      });
      return result.code;
    } finally {
      signal?.removeEventListener("abort", forwardAbort);
      process.removeListener("SIGINT", onInterrupt);
      process.removeListener("SIGTERM", onInterrupt);
    }
  }

  async status() {
    const result = {
      python: fs.existsSync(this.files.python)
        ? { ready: true, version: ALTA_PYTHON_VERSION, path: this.files.python }
        : { ready: false, version: ALTA_PYTHON_VERSION },
      docker: { ready: false },
      services: { configured: fs.existsSync(this.files.settingsFile) },
    };
    if (!this.docker) return result;
    try {
      const version = await this.verifyDocker(3_000);
      const context = await this.execute(this.docker, ["context", "show"], {
        env: this.env,
        timeoutMs: 2_000,
      });
      result.docker = {
        ready: true,
        version: version.stdout.trim(),
        context: context.stdout.trim() || "default",
      };
      if (result.services.configured) {
        const rows = await this.execute(
          this.docker,
          this.composeArguments("ps", "--format", "json"),
          { env: this.env, timeoutMs: 3_000 },
        );
        result.services = {
          configured: true,
          states: Object.fromEntries(
            parseComposeRows(rows.stdout).map((row) => [
              row.Service,
              row.Health || row.State || "unknown",
            ]),
          ),
        };
      }
    } catch (error) {
      result.docker = { ready: false, error: error.message.split("\n")[0] };
    }
    return result;
  }
}
