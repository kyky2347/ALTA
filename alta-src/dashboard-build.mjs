import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { acquireLease } from "./storage.mjs";

function newestModifiedAt(target) {
  if (!fs.existsSync(target)) return 0;
  const metadata = fs.statSync(target);
  if (!metadata.isDirectory()) return metadata.mtimeMs;
  let newest = metadata.mtimeMs;
  for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
    if (["dist", "node_modules"].includes(entry.name)) continue;
    newest = Math.max(newest, newestModifiedAt(path.join(target, entry.name)));
  }
  return newest;
}

export function dashboardBuildRequired(rootDir) {
  const dashboard = path.join(rootDir, "alta-dashboard");
  const output = path.join(dashboard, "dist", "index.html");
  if (!fs.existsSync(output)) return true;
  const outputTime = fs.statSync(output).mtimeMs;
  return [
    path.join(rootDir, "pnpm-lock.yaml"),
    path.join(rootDir, "package.json"),
    path.join(dashboard, "package.json"),
    path.join(dashboard, "index.html"),
    path.join(dashboard, "src"),
    path.join(dashboard, "public"),
  ].some((target) => newestModifiedAt(target) > outputTime);
}

function streamingRunner(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: "inherit",
    });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else
        reject(
          new Error(
            `${command} ${args.join(" ")} failed (${signal ?? `exit ${code}`})`,
          ),
        );
    });
  });
}

export async function prepareDashboard({
  rootDir,
  runner = streamingRunner,
  env = process.env,
}) {
  if (!dashboardBuildRequired(rootDir)) return { built: false };
  const lease = acquireLease(
    path.join(rootDir, ".alta", "runtime", "dashboard-build.lock"),
  );
  try {
    if (!dashboardBuildRequired(rootDir)) return { built: false };
    console.log("Preparing the ALTA operator dashboard (first run or update)…");
    await runner("corepack", ["pnpm", "install", "--frozen-lockfile"], {
      cwd: rootDir,
      env,
    });
    await runner(
      "corepack",
      ["pnpm", "--dir", "alta-dashboard", "build"],
      { cwd: rootDir, env },
    );
    return { built: true };
  } finally {
    lease.release();
  }
}
