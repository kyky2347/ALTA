import os from "node:os";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { externalCredentialRoot } from "./credential-files.mjs";
import { executableInPath } from "./process-runner.mjs";

export function brokerRuntimeCommand(
  rootDir,
  findExecutable = findBrokerExecutable,
) {
  const uv = findExecutable("uv");
  if (!uv)
    throw Object.assign(new Error("broker_dependencies_not_installed"), {
      code: "broker_dependencies_not_installed",
      statusCode: 503,
    });
  // Locked lazy setup also works before research has ever been started. uv
  // serializes environment synchronization; no SDK or credential enters Node.
  return [
    uv,
    "run",
    "--frozen",
    "--all-extras",
    "--no-dev",
    "--project",
    path.join(rootDir, "alta-runtime", "broker-python"),
    "python",
    "-m",
    "alta_brokers",
  ];
}

function findBrokerExecutable(name) {
  const fromPath = executableInPath(name);
  if (fromPath) return fromPath;
  // launchd and desktop launchers intentionally have a small PATH. uv's
  // documented per-user install must work there too, without a shell profile.
  const local = path.join(
    os.homedir(),
    ".local",
    "bin",
    process.platform === "win32" ? `${name}.exe` : name,
  );
  return fs.existsSync(local) ? local : null;
}

/** Broker SDKs never execute in the research process or receive model secrets. */
export function brokerConnectionRequest(rootDir, sourceEnv, request) {
  return runBrokerProcess(
    brokerRuntimeCommand(rootDir),
    rootDir,
    sourceEnv,
    request,
  );
}

export function runBrokerProcess(
  python,
  rootDir,
  sourceEnv,
  request,
  launch = spawn,
) {
  if (
    ![
      "catalog",
      "save",
      "verify",
      "state",
      "route",
      "select",
      "authorize",
      "revoke",
      "reconcile",
    ].includes(request?.action)
  )
    throw Object.assign(new Error("broker_action_unavailable"), {
      code: "broker_action_unavailable",
      statusCode: 400,
    });
  return new Promise((resolve, reject) => {
    const command = Array.isArray(python)
      ? python
      : [python, "-m", "alta_brokers"];
    const child = launch(command[0], command.slice(1), {
      cwd: rootDir,
      detached: process.platform !== "win32",
      stdio: ["pipe", "pipe", "ignore"],
      env: {
        PATH: "/usr/bin:/bin",
        HOME: os.homedir(),
        ALTA_CREDENTIALS_DIR: externalCredentialRoot(sourceEnv),
        PYTHONUNBUFFERED: "1",
      },
    });
    let output = Buffer.alloc(0);
    let done = false;
    let exited = false;
    const fail = (code, statusCode = 503) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (child.pid && !exited) {
        try {
          process.kill(
            process.platform === "win32" ? child.pid : -child.pid,
            "SIGKILL",
          );
        } catch (error) {
          if (error.code !== "ESRCH") child.kill("SIGKILL");
        }
      }
      reject(Object.assign(new Error(code), { code, statusCode }));
    };
    const timer = setTimeout(() => fail("broker_connection_timed_out"), 90_000);
    child.on("error", () => fail("broker_process_unavailable"));
    child.stdin.on("error", () => fail("broker_process_unavailable"));
    child.stdout.on("data", (chunk) => {
      output = Buffer.concat([output, chunk]);
      if (output.length > 4 * 1024 * 1024) fail("broker_response_too_large");
    });
    child.on("close", (code) => {
      exited = true;
      if (done) return;
      if (code !== 0) return fail("broker_process_unavailable");
      try {
        const result = JSON.parse(output.toString());
        if (result.error) {
          const errorCode = /^[a-z_]{4,80}$/.test(result.error.code)
            ? result.error.code
            : "broker_operation_failed";
          return fail(
            errorCode,
            /conflict|in_progress|before_credential/.test(errorCode)
              ? 409
              : 422,
          );
        }
        if (!result.data || typeof result.data !== "object")
          return fail("broker_response_invalid");
        done = true;
        clearTimeout(timer);
        resolve(result.data);
      } catch {
        fail("broker_response_invalid");
      }
    });
    // Credentials travel only over a local pipe, never argv or an environment dump.
    child.stdin.end(JSON.stringify(request));
  });
}
