import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { atomicWrite } from "./durable-file.mjs";

export const OPPORTUNITY_SERVICE_LABEL = "app.alta.asterism.opportunity";
export const OPPORTUNITY_SYSTEMD_UNIT = "alta-opportunity.service";

export function managedServiceLayout({ platform, stateDir, projectRoot }) {
  if (platform.platform === "darwin") {
    const home = platform.home ?? os.homedir();
    return {
      workingDirectory: home,
      logDirectory: path.join(home, "Library", "Logs", "ALTA"),
    };
  }
  return {
    workingDirectory: projectRoot,
    logDirectory: path.join(stateDir, "home", "log"),
  };
}

function xml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function systemd(value) {
  return `"${value.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function managedLaunchdDefinition({
  label,
  node,
  cli,
  args,
  root,
  stdout,
  stderr,
}) {
  // Keep launchd's executable boundary on an Apple-owned binary while passing
  // the exact runtime path as data. This invokes neither a shell nor PATH; the
  // non-protected working/log layout is handled separately below.
  const argumentsXml = ["/usr/bin/env", node, cli, ...args]
    .map((argument) => `    <string>${xml(argument)}</string>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${xml(label)}</string>
  <key>ProgramArguments</key>
  <array>
${argumentsXml}
  </array>
  <key>WorkingDirectory</key>
  <string>${xml(root)}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>ProcessType</key>
  <string>Background</string>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>${xml(stdout)}</string>
  <key>StandardErrorPath</key>
  <string>${xml(stderr)}</string>
</dict>
</plist>
`;
}

export function launchdDefinition(values) {
  return managedLaunchdDefinition({
    ...values,
    label: OPPORTUNITY_SERVICE_LABEL,
    args: ["service", "run"],
  });
}

export function managedSystemdDefinition({
  description,
  node,
  cli,
  args,
  root,
  after = [],
  wants = [],
}) {
  const afterLine = after.length ? `After=${after.join(" ")}\n` : "";
  const wantsLine = wants.length ? `Wants=${wants.join(" ")}\n` : "";
  const command = [node, cli, ...args].map(systemd).join(" ");
  return `[Unit]
Description=${description}
${afterLine}${wantsLine}
[Service]
Type=simple
WorkingDirectory=${systemd(root)}
ExecStart=${command}
Restart=on-failure
RestartSec=30s
TimeoutStopSec=45s
KillMode=mixed
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
`;
}

export function systemdDefinition(values) {
  return managedSystemdDefinition({
    ...values,
    description: "ALTA autonomous Opportunity OS (research-only)",
    args: ["service", "run"],
    after: ["docker.service", "network-online.target"],
    wants: ["network-online.target"],
  });
}

function commandRunner(command, args, { allowFailure = false } = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 45_000,
    maxBuffer: 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    const detail = result.stderr?.trim() || result.stdout?.trim();
    throw new Error(detail || `${command} exited with ${result.status}`);
  }
  return {
    code: result.status ?? 1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

export class HostServicePlatform {
  constructor({
    platform = process.platform,
    home = os.homedir(),
    uid = typeof process.getuid === "function" ? process.getuid() : null,
    runner = commandRunner,
    label = OPPORTUNITY_SERVICE_LABEL,
    systemdUnit = OPPORTUNITY_SYSTEMD_UNIT,
    fallbackCommand = "./alta service run",
  } = {}) {
    this.platform = platform;
    this.home = home;
    this.uid = uid;
    this.runner = runner;
    this.label = label;
    this.systemdUnit = systemdUnit;
    this.fallbackCommand = fallbackCommand;
  }

  definitionPath() {
    if (this.platform === "darwin")
      return path.join(
        this.home,
        "Library",
        "LaunchAgents",
        `${this.label}.plist`,
      );
    if (this.platform === "linux")
      return path.join(
        this.home,
        ".config",
        "systemd",
        "user",
        this.systemdUnit,
      );
    throw new Error(
      `Managed user services support macOS launchd and Linux systemd-user; use \`${this.fallbackCommand}\` on this platform`,
    );
  }

  install(definition, { start = true } = {}) {
    const file = this.definitionPath();
    atomicWrite(file, definition);
    if (this.platform === "darwin") {
      const domain = `gui/${this.uid}`;
      this.runner("launchctl", ["bootout", domain, file], {
        allowFailure: true,
      });
      this.runner("launchctl", ["enable", `${domain}/${this.label}`]);
      if (start) this.runner("launchctl", ["bootstrap", domain, file]);
    } else {
      this.runner("systemctl", ["--user", "daemon-reload"]);
      this.runner("systemctl", [
        "--user",
        "enable",
        ...(start ? ["--now"] : []),
        this.systemdUnit,
      ]);
    }
    return file;
  }

  start() {
    if (this.platform === "darwin")
      return this.runner("launchctl", [
        "kickstart",
        "-k",
        `gui/${this.uid}/${this.label}`,
      ]);
    return this.runner("systemctl", ["--user", "start", this.systemdUnit]);
  }

  stop() {
    if (this.platform === "darwin")
      return this.runner(
        "launchctl",
        ["kill", "SIGTERM", `gui/${this.uid}/${this.label}`],
        { allowFailure: true },
      );
    return this.runner("systemctl", ["--user", "stop", this.systemdUnit], {
      allowFailure: true,
    });
  }

  restart() {
    if (this.platform === "darwin") return this.start();
    return this.runner("systemctl", ["--user", "restart", this.systemdUnit]);
  }

  status() {
    if (this.platform === "darwin")
      return this.runner(
        "launchctl",
        ["print", `gui/${this.uid}/${this.label}`],
        { allowFailure: true },
      );
    return this.runner("systemctl", ["--user", "is-active", this.systemdUnit], {
      allowFailure: true,
    });
  }

  uninstall() {
    const file = this.definitionPath();
    if (this.platform === "darwin")
      this.runner("launchctl", ["bootout", `gui/${this.uid}`, file], {
        allowFailure: true,
      });
    else {
      this.runner(
        "systemctl",
        ["--user", "disable", "--now", this.systemdUnit],
        { allowFailure: true },
      );
    }
    fs.rmSync(file, { force: true });
    if (this.platform === "linux")
      this.runner("systemctl", ["--user", "daemon-reload"]);
  }
}
