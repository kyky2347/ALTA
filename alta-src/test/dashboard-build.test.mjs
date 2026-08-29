import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  dashboardBuildRequired,
  prepareDashboard,
} from "../dashboard-build.mjs";

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-dashboard-build-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "alta-dashboard", "src"), { recursive: true });
  fs.mkdirSync(path.join(root, "alta-dashboard", "public"), {
    recursive: true,
  });
  for (const file of [
    "package.json",
    "pnpm-lock.yaml",
    "alta-dashboard/package.json",
    "alta-dashboard/index.html",
    "alta-dashboard/src/App.tsx",
  ]) {
    fs.writeFileSync(path.join(root, file), "fixture\n");
  }
  return root;
}

test("dashboard preparation performs one locked install and build when dist is missing", async (t) => {
  const rootDir = fixture(t);
  const calls = [];
  const runner = async (command, args, options) => {
    calls.push({ command, args, cwd: options.cwd });
    if (args.at(-1) === "build") {
      const dist = path.join(rootDir, "alta-dashboard", "dist");
      fs.mkdirSync(dist, { recursive: true });
      fs.writeFileSync(path.join(dist, "index.html"), "built\n");
    }
  };

  assert.equal(dashboardBuildRequired(rootDir), true);
  assert.deepEqual(await prepareDashboard({ rootDir, runner }), {
    built: true,
  });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args, ["pnpm", "install", "--frozen-lockfile"]);
  assert.deepEqual(calls[1].args, ["pnpm", "--dir", "alta-dashboard", "build"]);
  assert.equal(dashboardBuildRequired(rootDir), false);
});

test("dashboard preparation is a no-op when the built UI is current", async (t) => {
  const rootDir = fixture(t);
  const dist = path.join(rootDir, "alta-dashboard", "dist");
  fs.mkdirSync(dist, { recursive: true });
  await new Promise((resolve) => setTimeout(resolve, 5));
  fs.writeFileSync(path.join(dist, "index.html"), "built\n");

  assert.deepEqual(
    await prepareDashboard({
      rootDir,
      runner: async () => assert.fail("runner must not be called"),
    }),
    { built: false },
  );
});
