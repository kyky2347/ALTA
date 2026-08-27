import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

export const OPPORTUNITY_SERVICE_LABEL = "app.alta.asterism.opportunity";

function xml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function systemd(value) {
  return `"${value.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function launchdDefinition({ node, cli, root, stdout, stderr }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${OPPORTUNITY_SERVICE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${xml(node)}</string>
    <string>${xml(cli)}</string>
    <string>service</string>
    <string>run</string>
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

export function systemdDefinition({ node, cli, root }) {
  return `[Unit]
Description=ALTA autonomous Opportunity OS (research-only)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${systemd(root)}
ExecStart=${systemd(node)} ${systemd(cli)} service run
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

function commandRunner(command, args, { allowFailure = false } = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
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

function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, value, { flag: "wx", mode: 0o600 });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
}

export class HostServicePlatform {
  constructor({
    platform = process.platform,
    home = os.homedir(),
    uid = typeof process.getuid === "function" ? process.getuid() : null,
    runner = commandRunner,
  } = {}) {
    this.platform = platform;
    this.home = home;
    this.uid = uid;
    this.runner = runner;
  }

  definitionPath() {
    if (this.platform === "darwin")
      return path.join(
        this.home,
        "Library",
        "LaunchAgents",
        `${OPPORTUNITY_SERVICE_LABEL}.plist`,
      );
    if (this.platform === "linux")
      return path.join(
        this.home,
        ".config",
        "systemd",
        "user",
        "alta-opportunity.service",
      );
    throw new Error(
      "Managed 24x7 installation supports macOS launchd and Linux systemd-user; use `./alta service run` on this platform",
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
      this.runner("launchctl", ["bootstrap", domain, file]);
      this.runner("launchctl", [
        "enable",
        `${domain}/${OPPORTUNITY_SERVICE_LABEL}`,
      ]);
      if (start)
        this.runner("launchctl", [
          "kickstart",
          "-k",
          `${domain}/${OPPORTUNITY_SERVICE_LABEL}`,
        ]);
    } else {
      this.runner("systemctl", ["--user", "daemon-reload"]);
      this.runner("systemctl", [
        "--user",
        "enable",
        ...(start ? ["--now"] : []),
        "alta-opportunity.service",
      ]);
    }
    return file;
  }

  start() {
    if (this.platform === "darwin")
      return this.runner("launchctl", [
        "kickstart",
        "-k",
        `gui/${this.uid}/${OPPORTUNITY_SERVICE_LABEL}`,
      ]);
    return this.runner("systemctl", [
      "--user",
      "start",
      "alta-opportunity.service",
    ]);
  }

  stop() {
    if (this.platform === "darwin")
      return this.runner(
        "launchctl",
        ["kill", "SIGTERM", `gui/${this.uid}/${OPPORTUNITY_SERVICE_LABEL}`],
        { allowFailure: true },
      );
    return this.runner(
      "systemctl",
      ["--user", "stop", "alta-opportunity.service"],
      { allowFailure: true },
    );
  }

  restart() {
    if (this.platform === "darwin") return this.start();
    return this.runner("systemctl", [
      "--user",
      "restart",
      "alta-opportunity.service",
    ]);
  }

  status() {
    if (this.platform === "darwin")
      return this.runner(
        "launchctl",
        ["print", `gui/${this.uid}/${OPPORTUNITY_SERVICE_LABEL}`],
        { allowFailure: true },
      );
    return this.runner(
      "systemctl",
      ["--user", "is-active", "alta-opportunity.service"],
      { allowFailure: true },
    );
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
        ["--user", "disable", "--now", "alta-opportunity.service"],
        { allowFailure: true },
      );
    }
    fs.rmSync(file, { force: true });
    if (this.platform === "linux")
      this.runner("systemctl", ["--user", "daemon-reload"]);
  }
}
