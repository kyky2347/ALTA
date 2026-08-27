import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { randomUUID } from "node:crypto";
import { boundedNumber, sleep } from "./resource-control.mjs";
import { acquireLease } from "./storage.mjs";

function writeStatus(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(
    temporary,
    `${JSON.stringify({ ...value, updatedAt: new Date().toISOString() }, null, 2)}\n`,
    { mode: 0o600 },
  );
  fs.renameSync(temporary, file);
}

function settings(env = process.env) {
  return {
    baseDelayMs: boundedNumber(env.ALTA_RESTART_BASE_MS, 1000, 250, 60_000),
    maxDelayMs: boundedNumber(
      env.ALTA_RESTART_MAX_MS,
      5 * 60 * 1000,
      1000,
      30 * 60 * 1000,
    ),
    stableMs: boundedNumber(
      env.ALTA_STABLE_UPTIME_MS,
      10 * 60 * 1000,
      10_000,
      24 * 60 * 60 * 1000,
    ),
    restartsPerHour: boundedNumber(env.ALTA_RESTARTS_PER_HOUR, 20, 1, 1000),
    restartOnSuccess: env.ALTA_RESTART_ON_SUCCESS === "1",
  };
}

export async function supervise({ stateDir, provider, launch, env }) {
  const policy = settings(env);
  const runtimeDir = path.join(stateDir, "runtime");
  const lockFile = path.join(runtimeDir, `supervisor-${provider}.lock`);
  const statusFile = path.join(runtimeDir, `supervisor-${provider}.json`);
  const lease = acquireLease(lockFile, {
    staleMs: 24 * 60 * 60 * 1000,
    busy: "throw",
  });
  const controller = new AbortController();
  const stop = (signal) =>
    controller.abort(new Error(`supervisor stopped by ${signal}`));
  const onInterrupt = () => stop("SIGINT");
  const onTerminate = () => stop("SIGTERM");
  process.once("SIGINT", onInterrupt);
  process.once("SIGTERM", onTerminate);
  const restarts = [];
  let consecutiveFailures = 0;
  let childPid = null;
  let finalCode = 0;

  try {
    while (!controller.signal.aborted) {
      const startedAt = Date.now();
      writeStatus(statusFile, {
        system: "ALTA v3.5",
        provider,
        state: "running",
        supervisorPid: process.pid,
        childPid,
        consecutiveFailures,
      });
      let code;
      let lastError = null;
      try {
        code = await launch({
          signal: controller.signal,
          onChild: (pid) => {
            childPid = pid;
            writeStatus(statusFile, {
              system: "ALTA v3.5",
              provider,
              state: "running",
              supervisorPid: process.pid,
              childPid,
              consecutiveFailures,
            });
          },
        });
      } catch (error) {
        if (controller.signal.aborted) break;
        code = 1;
        lastError = String(error.message ?? error).slice(0, 1000);
      }
      childPid = null;
      finalCode = code ?? 1;
      if (controller.signal.aborted) break;
      if (finalCode === 0 && !policy.restartOnSuccess) break;

      const uptimeMs = Date.now() - startedAt;
      consecutiveFailures =
        uptimeMs >= policy.stableMs ? 1 : consecutiveFailures + 1;
      const now = Date.now();
      restarts.push(now);
      while (restarts.length && restarts[0] < now - 60 * 60 * 1000)
        restarts.shift();
      let delayMs = Math.min(
        policy.baseDelayMs * 2 ** Math.min(consecutiveFailures - 1, 12),
        policy.maxDelayMs,
      );
      if (restarts.length >= policy.restartsPerHour)
        delayMs = Math.max(delayMs, restarts[0] + 60 * 60 * 1000 - now);
      delayMs += Math.floor(Math.random() * Math.min(1000, delayMs / 4));
      writeStatus(statusFile, {
        system: "ALTA v3.5",
        provider,
        state: "backoff",
        supervisorPid: process.pid,
        childPid: null,
        consecutiveFailures,
        restartInMs: delayMs,
        lastExitCode: finalCode,
        lastError,
      });
      try {
        await sleep(delayMs, controller.signal);
      } catch {
        break;
      }
    }
    return controller.signal.aborted ? 0 : finalCode;
  } finally {
    process.removeListener("SIGINT", onInterrupt);
    process.removeListener("SIGTERM", onTerminate);
    writeStatus(statusFile, {
      system: "ALTA v3.5",
      provider,
      state: "stopped",
      supervisorPid: process.pid,
      childPid: null,
      lastExitCode: finalCode,
    });
    lease.release();
  }
}
