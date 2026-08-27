function printStatus(status) {
  const hostState = status.host
    ? status.host.state === "stopped" || status.host.processAlive
      ? status.host.state
      : `${status.host.state} (stale)`
    : "unknown";
  const supervisorState = status.supervisor
    ? status.supervisor.state === "stopped" ||
      status.supervisor.childProcessAlive
      ? status.supervisor.state
      : `${status.supervisor.state} (stale)`
    : "unknown";
  console.log("ALTA autonomous Opportunity service");
  console.log(`  installed: ${status.installed ? "yes" : "no"}`);
  console.log(
    `  host manager: ${status.platformActive ? "active" : "inactive"}`,
  );
  console.log(`  readiness: ${status.ready ? "ready" : "not ready"}`);
  console.log(`  endpoint: ${status.endpoint}`);
  console.log(`  capital mode: ${status.capitalMode}`);
  console.log(
    `  credentials: ${status.credentials.valid ? `${status.credentials.currentRevision}${status.credentials.reloadRequired ? " (reload required)" : ""}` : `invalid (${status.credentials.error})`}`,
  );
  console.log(
    `  host process: ${hostState} (pid ${status.host?.processId ?? "none"})`,
  );
  console.log(
    `  scheduler: ${supervisorState} (pid ${status.supervisor?.childPid ?? "none"})`,
  );
}

async function prepareInstallation(service, ensureBinary) {
  await service.assertEndpointAvailable();
  const { environment, credentialSources } = service.runtimeEnvironment();
  const manager = service.environmentFactory(environment);
  const status = await manager.status();
  if (!status.python.ready || !status.services.configured)
    await manager.setup();
  else await manager.up();
  await ensureBinary();
  const migration = await manager.python([
    "-m",
    "alta_asterism",
    "migrate",
    "upgrade",
  ]);
  if (migration !== 0) throw new Error("Opportunity database migration failed");
  const doctor = await manager.python(["-m", "alta_asterism", "doctor"]);
  if (doctor !== 0) throw new Error("Opportunity service preflight failed");
  return credentialSources;
}

export async function opportunityServiceCommand(
  args,
  { service, ensureBinary, storageManager },
) {
  const [action = "status", ...options] = args;
  if (action === "run") {
    if (options.length)
      throw new Error("service run does not accept arguments");
    await ensureBinary();
    const storage = storageManager();
    const maintenance = await storage.maintain();
    if (!maintenance.skipped && maintenance.snapshot.pressure === "critical")
      throw new Error(
        "Storage guard is critical; autonomous service not started",
      );
    const stopMaintenance = storage.start((error) =>
      console.warn(`warning: storage maintenance failed (${error.message})`),
    );
    try {
      return await service.run();
    } finally {
      stopMaintenance();
    }
  }
  if (action === "install") {
    if (options.length)
      throw new Error("service install does not accept arguments");
    if (service.installed()) await service.stop();
    const sources = await prepareInstallation(service, ensureBinary);
    const file = service.install();
    const status = await service.waitForReadiness();
    console.log(`Installed autonomous service: ${file}`);
    for (const [key, source] of Object.entries(sources))
      console.log(`  ${key}: ${source}`);
    console.log(
      "  Tiger Paper: disabled unless explicitly configured externally",
    );
    printStatus(status);
    return;
  }
  if (options.length)
    throw new Error(`service ${action} does not accept arguments`);
  if (action === "start") {
    service.platform.start();
    return printStatus(await service.waitForReadiness());
  } else if (action === "stop") await service.stop();
  else if (action === "restart") {
    service.platform.restart();
    return printStatus(await service.waitForReadiness());
  } else if (action === "uninstall") {
    await service.stop();
    service.platform.uninstall();
  } else if (action === "status") return printStatus(await service.status());
  else if (action === "logs") {
    const logs = service.tailLogs();
    for (const [name, lines] of Object.entries(logs)) {
      console.log(`\n${name}:`);
      console.log(lines.filter(Boolean).join("\n") || "  (empty)");
    }
    return;
  } else throw new Error(`Unknown service action "${action}"`);
  return printStatus(await service.status());
}
