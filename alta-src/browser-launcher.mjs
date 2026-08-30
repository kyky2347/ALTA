import process from "node:process";
import { spawn } from "node:child_process";

const LAUNCH_TIMEOUT_MS = 10_000;

function launch(command, args, { runner = spawn } = {}) {
  return new Promise((resolve, reject) => {
    const child = runner(command, args, {
      stdio: "ignore",
      windowsHide: true,
    });
    let settled = false;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (error) reject(error);
      else resolve();
    };
    const timeout = setTimeout(() => {
      child.kill?.();
      const error = new Error(`${command} did not return after 10 seconds`);
      error.code = "ETIMEDOUT";
      finish(error);
    }, LAUNCH_TIMEOUT_MS);
    timeout.unref?.();
    child.once("error", finish);
    child.once("exit", (code, signal) => {
      if (code === 0) finish();
      else {
        const error = new Error(
          `${command} could not open the browser (${signal ?? `exit ${code}`})`,
        );
        error.code = code;
        finish(error);
      }
    });
  });
}

function browserLaunchers(platform) {
  if (platform === "darwin") return [["open", []]];
  if (platform === "win32")
    return [["rundll32.exe", ["url.dll,FileProtocolHandler"]]];
  return [
    ["xdg-open", []],
    ["gio", ["open"]],
  ];
}

export async function openDefaultBrowser(
  url,
  { platform = process.platform, runner = spawn } = {},
) {
  let lastError;
  for (const [command, args] of browserLaunchers(platform)) {
    try {
      await launch(command, [...args, url], { runner });
      return { command };
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(
    `No desktop browser launcher succeeded: ${lastError?.message ?? "unknown error"}`,
    { cause: lastError },
  );
}
