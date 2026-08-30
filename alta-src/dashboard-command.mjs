import path from "node:path";
import process from "node:process";
import { createOperatorConsole } from "./operator-console.mjs";
import { prepareDashboard } from "./dashboard-build.mjs";
import { openDefaultBrowser } from "./browser-launcher.mjs";

const MANAGED_ACTIONS = new Set([
  "install",
  "start",
  "stop",
  "restart",
  "status",
  "open",
  "logs",
  "uninstall",
  "run",
]);

export function parseDashboardOptions(args) {
  const options = {
    host: "127.0.0.1",
    port: 8877,
    portExplicit: false,
    openBrowser: true,
  };
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    if (value === "--host" && args[index + 1]) options.host = args[++index];
    else if (value === "--port" && args[index + 1]) {
      options.port = Number(args[++index]);
      options.portExplicit = true;
    } else if (value === "--no-open") options.openBrowser = false;
    else throw new Error(`Unknown dashboard option ${value}`);
  }
  if (
    !Number.isInteger(options.port) ||
    options.port < 1024 ||
    options.port > 65535
  )
    throw new Error("Dashboard port must be from 1024 through 65535");
  if (!["127.0.0.1", "localhost", "::1"].includes(options.host))
    throw new Error("The operator dashboard must bind to a loopback address");
  return options;
}

function createConsole(options, dependencies) {
  return (dependencies.consoleFactory ?? createOperatorConsole)({
    host: options.host,
    port: options.port,
    staticDir: path.join(dependencies.rootDir, "alta-dashboard", "dist"),
    service: dependencies.service,
    environmentFactory: dependencies.environmentFactory,
  });
}

async function listenConsole(options, dependencies) {
  let consoleServer = createConsole(options, dependencies);
  try {
    return { consoleServer, location: await consoleServer.listen() };
  } catch (error) {
    await consoleServer.close().catch(() => {});
    if (error?.code !== "EADDRINUSE" || options.portExplicit) throw error;
    console.log(
      `Dashboard port ${options.port} is occupied; selecting a free loopback port…`,
    );
    consoleServer = createConsole({ ...options, port: 0 }, dependencies);
    return { consoleServer, location: await consoleServer.listen() };
  }
}

async function openOrExplain(url, opener = openDefaultBrowser) {
  try {
    await opener(url);
    console.log("  browser: opened automatically");
    return true;
  } catch (error) {
    console.log("  browser: automatic opening was unavailable");
    console.log(`  open manually: ${url}`);
    console.log(`  reason: ${error.message}`);
    return false;
  }
}

function printStatus(status) {
  const host = status.host
    ? status.host.state === "stopped" || status.host.processAlive
      ? status.host.state
      : `${status.host.state} (stale)`
    : "unknown";
  console.log("ALTA managed operator dashboard");
  console.log(`  installed: ${status.installed ? "yes" : "no"}`);
  console.log(
    `  host manager: ${status.platformActive ? "active" : "inactive"}`,
  );
  console.log(`  readiness: ${status.ready ? "ready" : "not ready"}`);
  console.log(`  endpoint: ${status.endpoint}`);
  console.log(
    `  host process: ${host} (pid ${status.host?.processId ?? "none"})`,
  );
}

async function managedCommand(action, options, dashboard, opener) {
  if (options.length)
    throw new Error(`dashboard ${action} does not accept arguments`);
  if (action === "run") return dashboard.run();
  if (action === "install") {
    if (dashboard.installed()) await dashboard.stop();
    await dashboard.assertEndpointAvailable();
    const file = dashboard.install();
    const status = await dashboard.waitForReadiness();
    console.log(`Installed managed dashboard: ${file}`);
    printStatus(status);
    console.log("  access: run ./alta dashboard open for the one-time URL");
    return;
  }
  if (action === "start") {
    if (!dashboard.installed())
      throw new Error("Dashboard service is not installed");
    const current = await dashboard.status();
    if (current.ready) return printStatus(current);
    await dashboard.assertEndpointAvailable();
    dashboard.platform.start();
    return printStatus(await dashboard.waitForReadiness());
  }
  if (action === "restart") {
    if (!dashboard.installed())
      throw new Error("Dashboard service is not installed");
    dashboard.platform.restart();
    return printStatus(await dashboard.waitForReadiness());
  }
  if (action === "stop") await dashboard.stop();
  else if (action === "uninstall") {
    await dashboard.stop();
    dashboard.platform.uninstall();
  } else if (action === "status") return printStatus(await dashboard.status());
  else if (action === "open") return openOrExplain(dashboard.openUrl(), opener);
  else if (action === "logs") {
    for (const [name, lines] of Object.entries(dashboard.tailLogs())) {
      console.log(`\n${name}:`);
      console.log(lines.filter(Boolean).join("\n") || "  (empty)");
    }
    return;
  }
  return printStatus(await dashboard.status());
}

export async function dashboardCommand(args, dependencies) {
  const [action, ...rest] = args;
  if (MANAGED_ACTIONS.has(action))
    return managedCommand(
      action,
      rest,
      dependencies.dashboardService,
      dependencies.openBrowser ?? openDefaultBrowser,
    );

  const options = parseDashboardOptions(args);
  await (dependencies.prepareDashboard ?? prepareDashboard)({
    rootDir: dependencies.rootDir,
  });
  const { consoleServer, location } = await listenConsole(
    options,
    dependencies,
  );
  console.log("ALTA operator dashboard");
  console.log(`  endpoint: ${location.origin}`);
  console.log("  safety: loopback-only, shadow research, capital disabled");
  if (options.openBrowser)
    await openOrExplain(
      location.openUrl,
      dependencies.openBrowser ?? openDefaultBrowser,
    );
  else console.log(`  open manually: ${location.openUrl}`);
  const stop = async () => {
    await consoleServer.close();
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  try {
    await new Promise((resolve) => consoleServer.server.once("close", resolve));
  } finally {
    process.removeListener("SIGINT", stop);
    process.removeListener("SIGTERM", stop);
  }
}
