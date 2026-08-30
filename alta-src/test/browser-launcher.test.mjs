import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import { openDefaultBrowser } from "../browser-launcher.mjs";
import { parseDashboardOptions } from "../dashboard-command.mjs";

function successfulRunner(calls) {
  return (command, args, options) => {
    calls.push({ command, args, options });
    const child = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => child.emit("exit", 0, null));
    return child;
  };
}

test("default dashboard launch opens a browser unless explicitly disabled", () => {
  assert.equal(parseDashboardOptions([]).openBrowser, true);
  assert.equal(parseDashboardOptions(["--no-open"]).openBrowser, false);
  assert.equal(parseDashboardOptions(["--port", "9000"]).portExplicit, true);
});

test("browser launcher uses argument-safe native launchers", async () => {
  const calls = [];
  const url = "http://127.0.0.1:8877/open/one-time-token";
  await openDefaultBrowser(url, {
    platform: "darwin",
    runner: successfulRunner(calls),
  });
  assert.deepEqual(calls[0], {
    command: "open",
    args: [url],
    options: { stdio: "ignore", windowsHide: true },
  });
});

test("Linux browser launch falls back from xdg-open to gio", async () => {
  const calls = [];
  const runner = (command, args) => {
    calls.push({ command, args });
    const child = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => {
      if (command === "xdg-open") {
        const error = new Error("missing");
        error.code = "ENOENT";
        child.emit("error", error);
      } else child.emit("exit", 0, null);
    });
    return child;
  };
  const result = await openDefaultBrowser("http://127.0.0.1:8877", {
    platform: "linux",
    runner,
  });
  assert.equal(result.command, "gio");
  assert.deepEqual(
    calls.map(({ command }) => command),
    ["xdg-open", "gio"],
  );
});
