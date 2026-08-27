import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  agentSafeChildEnvironment,
  ensureRuntimeConfiguration,
  RuntimeEnvironment,
  runtimeChildEnvironment,
  runtimePaths,
  ALTA_PYTHON_VERSION,
} from "../environment.mjs";

function temporaryRuntime(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-environment-"));
  const state = path.join(root, ".alta");
  fs.mkdirSync(path.join(root, "alta-runtime", "python"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "alta-runtime", "compose.yaml"),
    "services: {}\n",
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return { root, state, files: runtimePaths(root, state) };
}

test("runtime configuration is isolated, stable, and keeps secrets out of Compose settings", (t) => {
  const { root, state, files } = temporaryRuntime(t);
  const originalPath = process.env.PATH;
  const first = ensureRuntimeConfiguration(root, state);
  const postgresSecret = fs.readFileSync(files.postgresSecret, "utf8").trim();
  const redisSecret = fs.readFileSync(files.redisSecret, "utf8").trim();
  const second = ensureRuntimeConfiguration(root, state);
  fs.mkdirSync(path.dirname(files.python), { recursive: true });
  fs.writeFileSync(files.python, "managed python");

  const env = runtimeChildEnvironment(root, state, {
    PATH: originalPath,
    GITHUB_TOKEN: "fixture-remote-token",
    GH_TOKEN: "fixture-remote-token",
    GIT_ASKPASS: "/fixture/askpass",
    SSH_AUTH_SOCK: "/fixture/ssh-agent",
  });
  assert.deepEqual(second, first);
  assert.equal(
    fs.readFileSync(files.settingsFile, "utf8").includes(postgresSecret),
    false,
  );
  assert.equal(
    fs.readFileSync(files.settingsFile, "utf8").includes(redisSecret),
    false,
  );
  if (process.platform !== "win32") {
    assert.equal(fs.statSync(files.settingsFile).mode & 0o777, 0o600);
    assert.equal(fs.statSync(files.postgresSecret).mode & 0o777, 0o600);
    assert.equal(fs.statSync(files.redisSecret).mode & 0o777, 0o600);
  }
  assert.equal(env.ALTA_PYTHON, files.python);
  assert.equal(env.PATH.startsWith(path.dirname(files.python)), true);
  assert.equal(new URL(env.DATABASE_URL).password, postgresSecret);
  assert.equal(new URL(env.REDIS_URL).password, redisSecret);
  assert.equal(process.env.PATH, originalPath);
  assert.equal(env.GITHUB_TOKEN, undefined);
  assert.equal(env.GH_TOKEN, undefined);
  assert.equal(env.GIT_ASKPASS, undefined);
  assert.equal(env.SSH_AUTH_SOCK, undefined);
});

test("agent-safe child environment is an allowlist without business secrets", () => {
  const env = agentSafeChildEnvironment({
    PATH: "/fixture/bin",
    HOME: "/fixture/home",
    CODEX_HOME: "/fixture/codex",
    ALTA_GATEWAY_TOKEN: "fixture-local-token",
    ALTA_AGENT_SAFE_APP_SERVER: "1",
    ALTA_CREDENTIALS_DIR: "/fixture/credentials",
    ALTA_XAI_WEB_SEARCH_ENABLED: "0",
    DATABASE_URL: "postgresql://fixture-secret",
    REDIS_URL: "redis://fixture-secret",
    MASSIVE_API_KEY: "fixture-secret",
    FINLIGHT_API_KEY: "fixture-secret",
    TIGER_PRIVATE_KEY: "fixture-secret",
    OPENAI_API_KEY: "fixture-secret",
    HOST_UNRELATED_SECRET: "fixture-secret",
  });

  assert.deepEqual(env, {
    PATH: "/fixture/bin",
    HOME: "/fixture/home",
    CODEX_HOME: "/fixture/codex",
    ALTA_GATEWAY_TOKEN: "fixture-local-token",
    ALTA_AGENT_SAFE_APP_SERVER: "1",
    ALTA_XAI_WEB_SEARCH_ENABLED: "0",
    NO_PROXY: "127.0.0.1,localhost",
  });
  assert.equal(env.ALTA_CREDENTIALS_DIR, undefined);
});

test("environment setup pins Python and starts healthy services without exposing secrets", async (t) => {
  const { root, state, files } = temporaryRuntime(t);
  const calls = [];
  const runner = async (command, args) => {
    calls.push({ command, args: [...args] });
    if (args[0] === "sync") {
      fs.mkdirSync(path.dirname(files.python), { recursive: true });
      fs.writeFileSync(files.python, "python");
    }
    if (args[0] === "version")
      return { code: 0, stdout: "28.0.0\n", stderr: "" };
    if (args[0] === "context")
      return { code: 0, stdout: "orbstack\n", stderr: "" };
    if (args.includes("ps"))
      return {
        code: 0,
        stdout: JSON.stringify([
          { Service: "postgres", State: "running", Health: "healthy" },
          { Service: "redis", State: "running", Health: "healthy" },
        ]),
        stderr: "",
      };
    return { code: 0, stdout: "", stderr: "" };
  };
  const manager = new RuntimeEnvironment({
    rootDir: root,
    stateDir: state,
    runner,
    binaries: { uv: "uv", docker: "docker" },
  });

  await manager.setup();
  const status = await manager.status();
  await manager.down();

  assert.deepEqual(status, {
    python: { ready: true, version: ALTA_PYTHON_VERSION, path: files.python },
    docker: { ready: true, version: "28.0.0", context: "orbstack" },
    services: {
      configured: true,
      states: { postgres: "healthy", redis: "healthy" },
    },
  });
  assert.equal(
    calls.some(
      ({ args }) =>
        args[0] === "python" &&
        args[1] === "install" &&
        args[2] === ALTA_PYTHON_VERSION,
    ),
    true,
  );
  assert.equal(
    calls.some(({ args }) => args.includes("--frozen")),
    true,
  );
  assert.equal(
    calls.some(({ args }) => args.includes("--no-dev")),
    true,
  );
  assert.equal(
    calls.some(({ args }) => args.includes("--wait")),
    true,
  );
  const down = calls.find(({ args }) => args.includes("down"));
  assert.equal(
    down.args.includes("-v") || down.args.includes("--volumes"),
    false,
  );
  const callText = JSON.stringify(calls);
  assert.equal(
    callText.includes(fs.readFileSync(files.postgresSecret, "utf8").trim()),
    false,
  );
  assert.equal(
    callText.includes(fs.readFileSync(files.redisSecret, "utf8").trim()),
    false,
  );
});

test("development setup stays frozen and installs only explicit dev groups", async (t) => {
  const { root, state } = temporaryRuntime(t);
  const calls = [];
  const manager = new RuntimeEnvironment({
    rootDir: root,
    stateDir: state,
    runner: async (command, args) => {
      calls.push({ command, args: [...args] });
      return { code: 0, stdout: "", stderr: "" };
    },
    binaries: { uv: "uv", docker: null },
  });

  await manager.setupPython({ dev: true });

  const sync = calls.find(({ args }) => args[0] === "sync");
  assert.equal(sync.args.includes("--frozen"), true);
  assert.equal(sync.args.includes("--all-groups"), true);
  assert.equal(sync.args.includes("--no-dev"), false);
});

test("managed Python delegates to a signal-aware passthrough runner", async (t) => {
  const { root, state, files } = temporaryRuntime(t);
  ensureRuntimeConfiguration(root, state);
  fs.mkdirSync(path.dirname(files.python), { recursive: true });
  fs.writeFileSync(files.python, "python");
  const controller = new AbortController();
  let invocation;
  let passthroughSignal;
  const manager = new RuntimeEnvironment({
    rootDir: root,
    stateDir: state,
    passthroughRunner: async (command, args, options) => {
      invocation = {
        command,
        args: [...args],
        cwd: options.cwd,
      };
      passthroughSignal = options.signal;
      return new Promise((resolve) =>
        options.signal.addEventListener(
          "abort",
          () => resolve({ code: 0, signal: null, stdout: "", stderr: "" }),
          { once: true },
        ),
      );
    },
    binaries: { uv: "uv", docker: null },
  });

  const running = manager.python(["-m", "alta_asterism"], {
    signal: controller.signal,
  });
  await new Promise(setImmediate);
  controller.abort(new Error("test interruption"));
  const code = await running;

  assert.equal(code, 0);
  assert.equal(passthroughSignal.aborted, true);
  assert.deepEqual(invocation, {
    command: files.python,
    args: ["-m", "alta_asterism"],
    cwd: root,
  });
});

test("environment status is fast and non-fatal when no container engine is installed", async (t) => {
  const { root, state } = temporaryRuntime(t);
  const manager = new RuntimeEnvironment({
    rootDir: root,
    stateDir: state,
    env: { PATH: "" },
    binaries: { uv: "uv", docker: null },
  });

  assert.deepEqual(await manager.status(), {
    python: { ready: false, version: ALTA_PYTHON_VERSION },
    docker: { ready: false },
    services: { configured: false },
  });
});
