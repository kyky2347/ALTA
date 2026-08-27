import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

export function executableInPath(name) {
  for (const directory of (process.env.PATH ?? "").split(path.delimiter)) {
    const candidate = path.join(directory, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

export function runProcess(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const {
      signal,
      onChild,
      shutdownGraceMs = 10_000,
      ...spawnOptions
    } = options;
    if (signal?.aborted) return reject(signal.reason);
    const child = spawn(command, args, { stdio: "inherit", ...spawnOptions });
    let killTimer;
    const onAbort = () => {
      child.kill("SIGTERM");
      killTimer = setTimeout(() => child.kill("SIGKILL"), shutdownGraceMs);
      killTimer.unref?.();
    };
    const cleanup = () => {
      clearTimeout(killTimer);
      signal?.removeEventListener("abort", onAbort);
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    onChild?.(child.pid);
    child.once("error", (error) => {
      cleanup();
      reject(error);
    });
    child.once("exit", (code, exitSignal) => {
      cleanup();
      if (signal?.aborted) reject(signal.reason);
      else if (exitSignal)
        reject(new Error(`${command} stopped by ${exitSignal}`));
      else resolve(code ?? 1);
    });
  });
}

export function runCapture(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      ...options,
      stdio: ["ignore", "pipe", "inherit"],
    });
    const chunks = [];
    let length = 0;
    let settled = false;
    const fail = (error) => {
      if (settled) return;
      settled = true;
      reject(error);
    };
    child.stdout.on("data", (chunk) => {
      length += chunk.length;
      if (length > 1024 * 1024) {
        child.kill("SIGKILL");
        fail(new Error(`${command} produced too much output`));
        return;
      }
      chunks.push(chunk);
    });
    child.once("error", fail);
    child.once("exit", (code, signal) => {
      if (settled) return;
      settled = true;
      if (signal) return reject(new Error(`${command} stopped by ${signal}`));
      if (code !== 0)
        return reject(new Error(`${command} failed with exit code ${code}`));
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
  });
}
