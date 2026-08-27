import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { stripRemoteAccessEnvironment } from "./remote-access-policy.mjs";

export const ALTA_PYTHON_VERSION = "3.12.13";

const DEFAULTS = {
  POSTGRES_DB: "alta",
  POSTGRES_USER: "alta",
  ALTA_POSTGRES_PORT: "55432",
  ALTA_REDIS_PORT: "56379",
  ALTA_POSTGRES_MEMORY: "1g",
  ALTA_POSTGRES_CPUS: "2",
  ALTA_REDIS_MAXMEMORY: "512mb",
  ALTA_REDIS_MEMORY: "768m",
  ALTA_REDIS_CPUS: "1",
};
const CONFIG_KEYS = new Set([
  "ALTA_STATE_DIR",
  "ALTA_COMPOSE_PROJECT",
  ...Object.keys(DEFAULTS),
]);
const RUNTIME_CONFIG_CACHE = new Map();
const AGENT_SAFE_ENVIRONMENT_KEYS = new Set([
  "APPDATA",
  "CARGO_HOME",
  "CARGO_TARGET_DIR",
  "CODEX_HOME",
  "COMSPEC",
  "HOME",
  "LANG",
  "LOCALAPPDATA",
  "NO_COLOR",
  "PATH",
  "PATHEXT",
  "RUSTUP_HOME",
  "SHELL",
  "ALTA_AGENT_SAFE_APP_SERVER",
  "ALTA_DISTRIBUTION",
  "ALTA_GATEWAY_TOKEN",
  "ALTA_XAI_WEB_SEARCH_ENABLED",
  "SYSTEMROOT",
  "TEMP",
  "TMP",
  "TMPDIR",
  "USER",
  "USERPROFILE",
  "XDG_CACHE_HOME",
  "XDG_CONFIG_HOME",
  "XDG_DATA_HOME",
]);

function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(temporary, value, { flag: "wx", mode: 0o600 });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
}

function parseEnvFile(file) {
  const result = {};
  for (const raw of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    if (!raw || raw.startsWith("#")) continue;
    const separator = raw.indexOf("=");
    if (separator <= 0)
      throw new Error(`Invalid ALTA service setting in ${file}`);
    const key = raw.slice(0, separator);
    if (!CONFIG_KEYS.has(key))
      throw new Error(`Unknown ALTA service setting ${key}`);
    const encoded = raw.slice(separator + 1);
    result[key] = encoded.startsWith('"') ? JSON.parse(encoded) : encoded;
  }
  return result;
}

function validPort(value, key) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error(`${key} must be a port from 1024 through 65535`);
  return String(port);
}

function validateSettings(value) {
  for (const key of ["POSTGRES_DB", "POSTGRES_USER"])
    if (!/^[a-z][a-z0-9_]{0,62}$/.test(value[key] ?? ""))
      throw new Error(`${key} must be a lowercase PostgreSQL identifier`);
  value.ALTA_POSTGRES_PORT = validPort(
    value.ALTA_POSTGRES_PORT,
    "ALTA_POSTGRES_PORT",
  );
  value.ALTA_REDIS_PORT = validPort(value.ALTA_REDIS_PORT, "ALTA_REDIS_PORT");
  if (value.ALTA_POSTGRES_PORT === value.ALTA_REDIS_PORT)
    throw new Error("PostgreSQL and Redis must use different host ports");
  if (!/^alta-v35-[a-f0-9]{12}$/.test(value.ALTA_COMPOSE_PROJECT ?? ""))
    throw new Error("Invalid ALTA Compose project identifier");
  for (const key of [
    "ALTA_POSTGRES_MEMORY",
    "ALTA_REDIS_MAXMEMORY",
    "ALTA_REDIS_MEMORY",
  ])
    if (!/^[1-9]\d*(?:[kmgt]b?)$/i.test(value[key] ?? ""))
      throw new Error(`${key} must be a positive container memory size`);
  for (const key of ["ALTA_POSTGRES_CPUS", "ALTA_REDIS_CPUS"])
    if (
      !Number.isFinite(Number(value[key])) ||
      Number(value[key]) < 0.25 ||
      Number(value[key]) > 64
    )
      throw new Error(`${key} must be from 0.25 through 64 CPUs`);
  return value;
}

function runtimeSecret(file) {
  const value = fs.readFileSync(file, "utf8").trim();
  if (!/^[A-Za-z0-9_-]{43,128}$/.test(value))
    throw new Error(`Invalid ALTA runtime secret in ${file}`);
  fs.chmodSync(file, 0o600);
  return value;
}

export function runtimePaths(rootDir, stateDir) {
  const pythonProject = path.join(rootDir, "alta-runtime", "python");
  const pythonRoot = path.join(stateDir, "python");
  return {
    pythonProject,
    pythonRoot,
    python:
      process.platform === "win32"
        ? path.join(pythonRoot, "venv", "Scripts", "python.exe")
        : path.join(pythonRoot, "venv", "bin", "python"),
    composeFile: path.join(rootDir, "alta-runtime", "compose.yaml"),
    settingsFile: path.join(stateDir, "services.env"),
    postgresSecret: path.join(stateDir, "secrets", "postgres_password"),
    redisSecret: path.join(stateDir, "secrets", "redis_password"),
  };
}

export function readRuntimeSettings(file, stateDir) {
  const value = validateSettings(parseEnvFile(file));
  if (path.resolve(value.ALTA_STATE_DIR) !== path.resolve(stateDir))
    throw new Error("ALTA_STATE_DIR does not match this project runtime");
  return value;
}

export function ensureRuntimeConfiguration(
  rootDir,
  stateDir,
  env = process.env,
) {
  const files = runtimePaths(rootDir, stateDir);
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  for (const file of [files.postgresSecret, files.redisSecret]) {
    if (!fs.existsSync(file))
      atomicWrite(file, `${randomBytes(48).toString("base64url")}\n`);
    else runtimeSecret(file);
  }
  if (!fs.existsSync(files.settingsFile)) {
    const hash = createHash("sha256")
      .update(fs.realpathSync(rootDir))
      .digest("hex")
      .slice(0, 12);
    const settings = {
      ALTA_STATE_DIR: stateDir,
      ALTA_COMPOSE_PROJECT: `alta-v35-${hash}`,
      ...DEFAULTS,
      ...Object.fromEntries(
        Object.keys(DEFAULTS)
          .filter((key) => key.startsWith("ALTA_") && env[key] !== undefined)
          .map((key) => [key, env[key]]),
      ),
    };
    validateSettings(settings);
    atomicWrite(
      files.settingsFile,
      `${Object.entries(settings)
        .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
        .join("\n")}\n`,
    );
  }
  fs.chmodSync(files.settingsFile, 0o600);
  return readRuntimeSettings(files.settingsFile, stateDir);
}

function connectionUrl(protocol, password, port, pathname, username = "") {
  const value = new URL(`${protocol}://127.0.0.1`);
  value.username = username;
  value.password = password;
  value.port = port;
  value.pathname = pathname;
  return value.toString();
}

export function runtimeChildEnvironment(
  rootDir,
  stateDir,
  source = process.env,
) {
  const files = runtimePaths(rootDir, stateDir);
  const env = {
    ...source,
    UV_PYTHON_INSTALL_DIR: path.join(files.pythonRoot, "versions"),
    UV_PYTHON_BIN_DIR: path.join(files.pythonRoot, "bin"),
    UV_PROJECT_ENVIRONMENT: path.join(files.pythonRoot, "venv"),
    UV_CACHE_DIR: path.join(stateDir, "cache", "uv"),
    UV_PYTHON_PREFERENCE: "only-managed",
    UV_NO_MODIFY_PATH: "1",
    UV_COMPILE_BYTECODE: "1",
  };
  stripRemoteAccessEnvironment(env);
  if (fs.existsSync(files.python)) {
    env.ALTA_PYTHON = files.python;
    env.PATH = `${path.dirname(files.python)}${path.delimiter}${env.PATH ?? ""}`;
  }
  if (!fs.existsSync(files.settingsFile)) return env;
  let runtime = RUNTIME_CONFIG_CACHE.get(files.settingsFile);
  if (!runtime) {
    runtime = {
      settings: readRuntimeSettings(files.settingsFile, stateDir),
      postgresPassword: runtimeSecret(files.postgresSecret),
      redisPassword: runtimeSecret(files.redisSecret),
    };
    RUNTIME_CONFIG_CACHE.set(files.settingsFile, runtime);
  }
  const { settings, postgresPassword, redisPassword } = runtime;
  env.DATABASE_URL = connectionUrl(
    "postgresql",
    postgresPassword,
    settings.ALTA_POSTGRES_PORT,
    settings.POSTGRES_DB,
    settings.POSTGRES_USER,
  );
  env.REDIS_URL = connectionUrl(
    "redis",
    redisPassword,
    settings.ALTA_REDIS_PORT,
    "0",
  );
  return env;
}

export function agentSafeChildEnvironment(source = process.env) {
  const env = Object.fromEntries(
    Object.entries(source).filter(
      ([key]) => AGENT_SAFE_ENVIRONMENT_KEYS.has(key) || key.startsWith("LC_"),
    ),
  );
  env.NO_PROXY = "127.0.0.1,localhost";
  return env;
}
