import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import {
  defaultModel,
  resolveProviderModels,
  writeCatalogs,
  writeConfig,
} from "./catalog.mjs";
import {
  loadCredentials,
  MODEL_PROVIDER_IDS,
  PROVIDERS,
} from "./providers.mjs";
import { startGateway } from "./gateway.mjs";
import {
  agentSafeChildEnvironment,
  RuntimeEnvironment,
  runtimeChildEnvironment,
} from "./environment.mjs";
import {
  configureOpenAiAuth,
  protectOfficialAuthCommand,
} from "./openai-auth.mjs";
import { thirdPartyOpenAiServicePolicy } from "./openai-background.mjs";
import { numberSetting } from "./resource-control.mjs";
import { StorageManager, acquireLease, formatBytes } from "./storage.mjs";
import { supervise } from "./supervisor.mjs";
import { OpportunityService } from "./opportunity-service.mjs";
import { opportunityServiceCommand } from "./opportunity-service-command.mjs";
import { credentialCommand } from "./credential-command.mjs";
import { dashboardCommand } from "./dashboard-command.mjs";
import { DashboardService } from "./dashboard-service.mjs";
import {
  loadResourceCredentials,
  TOOL_CREDENTIAL_KEYS,
} from "./resource-credentials.mjs";
import { runProcess as run } from "./process-runner.mjs";
import { createRustBuild } from "./rust-build.mjs";
import {
  internetPluginIds,
  internetToolNames,
} from "./internet/plugins/registry.mjs";

const SOURCE_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.dirname(SOURCE_DIR);
const CODEX_RS_DIR = path.join(ROOT_DIR, "vendor", "openai-codex", "codex-rs");
const STATE_DIR = path.join(ROOT_DIR, ".alta");
const HOME_DIR = path.join(STATE_DIR, "home");
const BINARY = path.join(
  STATE_DIR,
  "bin",
  process.platform === "win32" ? "codex.exe" : "codex",
);
const CODE_MODE_HOST = path.join(
  STATE_DIR,
  "bin",
  process.platform === "win32"
    ? "codex-code-mode-host.exe"
    : "codex-code-mode-host",
);

const HELP = `ALTA v3.5 — isolated multi-provider Codex

Usage:
  ./alta                         OpenAI through the local official Codex login
  ./alta openai [codex args]     OpenAI (all bundled OpenAI models)
  ./alta deepseek [model] [...]  DeepSeek (all models returned for the key)
  ./alta grok [model] [...]      xAI / Grok (all language models for the key)
  ./alta kimi [model] [...]      Kimi (all models returned for the key)
                                Any root can mix provider/model choices in nested agents
  ./alta models [--refresh]      List models and their generated sub-agent types
  ./alta doctor [--live [provider]]
                                Check isolation; optionally probe one provider
  ./alta credentials [status|check|set <slot>|reload]
                                Inspect or atomically replace external API keys
  ./alta supervise <provider> [codex args]
                                Restart a long-running Codex process with bounded backoff
  ./alta storage [status|maintain [--dry-run]]
                                Inspect or enforce disk/cache safety limits
  ./alta env [status|setup [--dev]|up|down|restart|logs|python]
                                Manage isolated Python, PostgreSQL, and Redis
  ./alta service [install|start|stop|restart|status|logs|uninstall|run]
                                Operate the unattended 24x7 Opportunity service
  ./alta dashboard [install|start|stop|restart|status|open|logs|uninstall]
                                Operate the restartable local operator console
  ./alta dashboard [--host 127.0.0.1] [--port 8877] [--no-open]
                                Prepare, run, and open the local control plane
  ./alta status                  Show storage and supervisor health
  ./alta setup                   Build the private binary and prepare local state
  ./alta build                   Rebuild the private release binary
  ./alta test                    Run ALTA's Node test suite

Every root, child, and deeper agent independently receives the complete ALTA
read-only toolkit: bounded workspace file pages plus search/research,
fetch/crawl, archives, social/news/finance, TradingView display navigation,
and scholarly discovery.

Examples:
  ./alta deepseek
  ./alta grok --model grok-4.5 "inspect this repository"
  ./alta supervise kimi app-server
  ./alta env setup
  ./alta service install
  ./alta service status
  ./alta dashboard
  ./alta credentials status
  ./alta credentials set deepseek
  ./alta env python --version
  ./alta storage status
  ALTA_HTTPS_PROXY=http://127.0.0.1:7890 ./alta kimi
`;

function ensureDirectories() {
  for (const dir of [
    HOME_DIR,
    path.join(STATE_DIR, "bin"),
    path.join(STATE_DIR, "cache"),
    path.join(STATE_DIR, "cargo"),
    path.join(STATE_DIR, "rustup"),
    path.join(STATE_DIR, "tmp"),
    path.join(STATE_DIR, "runtime"),
    path.join(STATE_DIR, "xdg", "cache"),
    path.join(STATE_DIR, "xdg", "config"),
    path.join(STATE_DIR, "xdg", "data"),
  ]) {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  }
}

async function acquireStateWriteLease() {
  const file = path.join(STATE_DIR, "runtime", "prepare.lock");
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const lease = acquireLease(file, { busy: "skip" });
    if (lease) return lease;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("Timed out waiting to prepare isolated ALTA state");
}

function isolatedEnvironment(extra = {}) {
  const env = runtimeChildEnvironment(ROOT_DIR, STATE_DIR, {
    ...process.env,
    CODEX_HOME: HOME_DIR,
    CARGO_HOME: path.join(STATE_DIR, "cargo"),
    RUSTUP_HOME: path.join(STATE_DIR, "rustup"),
    CARGO_TARGET_DIR: path.join(STATE_DIR, "target"),
    XDG_CACHE_HOME: path.join(STATE_DIR, "xdg", "cache"),
    XDG_CONFIG_HOME: path.join(STATE_DIR, "xdg", "config"),
    XDG_DATA_HOME: path.join(STATE_DIR, "xdg", "data"),
    TMPDIR: path.join(STATE_DIR, "tmp"),
    ALTA_DISTRIBUTION: "3.5",
  });
  Object.assign(env, extra);
  for (const provider of Object.values(PROVIDERS)) {
    for (const key of provider.envKeys) delete env[key];
  }
  delete env.BRAVE_SEARCH_API_KEY;
  delete env.JINA_API_KEY;
  delete env.OPENALEX_API_KEY;
  delete env.FINNHUB_API_KEY;
  delete env.CROSSREF_MAILTO;
  return process.env.ALTA_AGENT_SAFE_APP_SERVER === "1"
    ? agentSafeChildEnvironment(env)
    : env;
}

const { build, findCargo, hasBuildOutput, installRuntimeImage } =
  createRustBuild({
    codeModeHost: CODE_MODE_HOST,
    codexRsDir: CODEX_RS_DIR,
    ensureDirectories,
    isolatedEnvironment,
    runtimeBinary: BINARY,
    stateDir: STATE_DIR,
  });

async function prepare({ refresh = false } = {}) {
  ensureDirectories();
  const authRoute = configureOpenAiAuth({
    officialAuthFile: path.join(os.homedir(), ".codex", "auth.json"),
    altaAuthFile: path.join(HOME_DIR, "auth.json"),
  });
  const { credentials, sources } = loadCredentials();
  const resourceCredentials = loadResourceCredentials(
    process.env,
    TOOL_CREDENTIAL_KEYS,
  );
  const state = await resolveProviderModels(ROOT_DIR, STATE_DIR, credentials, {
    refresh,
  });
  const lease = await acquireStateWriteLease();
  let catalogs;
  try {
    catalogs = writeCatalogs(ROOT_DIR, STATE_DIR, state.models);
    writeConfig(STATE_DIR, {
      agentThreads: numberSetting("ALTA_AGENT_THREADS", 4, 1, 32),
      historyMaxBytes:
        numberSetting("ALTA_HISTORY_MAX_MB", 64, 1, 4096) * 1024 * 1024,
    });
  } finally {
    lease.release();
  }
  return {
    credentials,
    sources,
    resourceCredentials,
    authRoute,
    ...state,
    catalogs,
  };
}

function toml(value) {
  return JSON.stringify(value);
}

function extractRequestedModel(args, available, fallback) {
  const rest = [...args];
  let model = null;
  for (let index = 0; index < rest.length; index += 1) {
    if (["-m", "--model"].includes(rest[index]) && rest[index + 1]) {
      model = rest[index + 1];
      rest.splice(index, 2);
      break;
    }
    if (rest[index].startsWith("--model=")) {
      model = rest[index].slice("--model=".length);
      rest.splice(index, 1);
      break;
    }
  }
  if (!model && available.includes(rest[0])) model = rest.shift();
  return { model: model ?? fallback, rest };
}

async function ensureBinary() {
  if (fs.existsSync(BINARY) && fs.existsSync(CODE_MODE_HOST)) return;
  if (hasBuildOutput()) installRuntimeImage();
  else await build();
}

async function launchOpenAi(args, options = {}) {
  const state = await prepare();
  protectOfficialAuthCommand(state.authRoute.mode, args);
  await ensureBinary();
  const admin = ["login", "logout", "completion"].includes(args[0]);
  const prefix = ["-c", `model_provider=${toml("openai")}`];
  if (
    !admin &&
    !args.some(
      (arg) => arg === "-m" || arg === "--model" || arg.startsWith("--model="),
    )
  ) {
    prefix.push("-m", "gpt-5.6-sol");
  }
  if (admin) {
    return run(BINARY, [...prefix, ...args], {
      cwd: process.cwd(),
      env: isolatedEnvironment(),
      signal: options.signal,
      onChild: options.onChild,
    });
  }
  const gateway = await startUnifiedGateway(state, options.storage);
  try {
    return await run(
      BINARY,
      [...prefix, ...sharedModelRuntimeArgs(state, gateway.baseUrl), ...args],
      {
        cwd: process.cwd(),
        env: isolatedEnvironment({ ALTA_GATEWAY_TOKEN: gateway.token }),
        signal: options.signal,
        onChild: options.onChild,
      },
    );
  } finally {
    await gateway.close();
  }
}

async function startUnifiedGateway(state, storage) {
  const token = randomBytes(32).toString("hex");
  const routes = new Map(
    state.models.map((model) => [model.id, model.provider]),
  );
  const modelCapabilities = new Map(
    state.models.map((model) => [
      model.id,
      {
        inputModalities: model.input_modalities ?? ["text"],
        video: model.video === true,
      },
    ]),
  );
  const gateway = await startGateway({
    credentials: state.credentials,
    routes,
    modelCapabilities,
    token,
    storage,
    internet: {
      braveKey: state.resourceCredentials.values.BRAVE_SEARCH_API_KEY,
      searxngUrl: process.env.ALTA_SEARXNG_URL,
      xaiModel: process.env.ALTA_WEB_XAI_MODEL,
      xaiSearchEnabled: process.env.ALTA_XAI_WEB_SEARCH_ENABLED !== "0",
      readerUrl: process.env.ALTA_WEB_READER_URL,
      readerKey: state.resourceCredentials.values.JINA_API_KEY,
      jinaKey: state.resourceCredentials.values.JINA_API_KEY,
      openAlexKey: state.resourceCredentials.values.OPENALEX_API_KEY,
      finnhubKey: state.resourceCredentials.values.FINNHUB_API_KEY,
      crossrefMailto: process.env.CROSSREF_MAILTO,
      lemmyUrl: process.env.ALTA_LEMMY_URL,
      mastodonUrl: process.env.ALTA_MASTODON_URL,
      peertubeUrl: process.env.ALTA_PEERTUBE_URL,
      discourseUrl: process.env.ALTA_DISCOURSE_URL,
      secUserAgent: process.env.ALTA_SEC_USER_AGENT,
      fileRoots: [ROOT_DIR],
    },
  });
  return { ...gateway, token };
}

function sharedModelRuntimeArgs(state, gatewayBaseUrl) {
  return [
    "-c",
    `model_catalog_json=${toml(state.catalogs.combinedFile)}`,
    "-c",
    `mcp_servers.alta_internet.url=${toml(`${gatewayBaseUrl}/mcp`)}`,
    ...Object.values(MODEL_PROVIDER_IDS).flatMap((provider) => [
      "-c",
      `model_providers.${provider}.base_url=${toml(gatewayBaseUrl)}`,
    ]),
  ];
}

async function launchProvider(providerName, args, options = {}) {
  const state = await prepare();
  if (!state.credentials[providerName]) {
    throw new Error(
      `${PROVIDERS[providerName].label} credential is missing. Use an environment variable or the external ALTA credentials directory.`,
    );
  }
  await ensureBinary();
  const available = state.models
    .filter((model) => model.provider === providerName)
    .map((model) => model.id);
  const selection = extractRequestedModel(
    args,
    available,
    defaultModel(providerName, state.models),
  );
  const gateway = await startUnifiedGateway(state, options.storage);
  const openAiServices = thirdPartyOpenAiServicePolicy(
    path.join(HOME_DIR, "auth.json"),
  );
  const codexArgs = [
    "-c",
    `model_provider=${toml(MODEL_PROVIDER_IDS[providerName])}`,
    ...openAiServices.args,
    ...sharedModelRuntimeArgs(state, gateway.baseUrl),
    "-m",
    selection.model,
    ...selection.rest,
  ];
  try {
    return await run(BINARY, codexArgs, {
      cwd: process.cwd(),
      env: isolatedEnvironment({ ALTA_GATEWAY_TOKEN: gateway.token }),
      signal: options.signal,
      onChild: options.onChild,
    });
  } finally {
    await gateway.close();
  }
}

async function listModels(refresh) {
  const state = await prepare({ refresh });
  for (const warning of state.warnings) console.warn(`warning: ${warning}`);
  const roles = new Map(
    state.catalogs.agentRoles.map((role) => [
      `${role.provider}\0${role.model}`,
      role.name,
    ]),
  );
  console.log("\nOpenAI:");
  for (const role of state.catalogs.agentRoles.filter(
    (value) => value.provider === "openai",
  ))
    console.log(`  ${role.model}  agent_type=${role.name}`);
  for (const name of Object.keys(PROVIDERS)) {
    const modelProvider = MODEL_PROVIDER_IDS[name];
    console.log(
      `\n${PROVIDERS[name].label} (${state.sources[name] ?? "no credential"}):`,
    );
    for (const model of state.models.filter(
      (value) => value.provider === name,
    )) {
      console.log(
        `  ${model.id}  context=${model.context_window} inputs=${(model.input_modalities ?? ["text"]).join(",")}${model.video ? ",video-file" : ""}${model.reasoning ? " reasoning" : ""}  agent_type=${roles.get(`${modelProvider}\0${model.id}`)}`,
      );
    }
  }
}

async function liveProbe(providerName, state) {
  if (!state.credentials[providerName])
    return { ok: false, message: "credential missing" };
  const model = defaultModel(providerName, state.models);
  const token = randomBytes(32).toString("hex");
  const routes = new Map([[model, providerName]]);
  const gateway = await startGateway({
    credentials: state.credentials,
    routes,
    forcedProvider: providerName,
    token,
  });
  try {
    const response = await fetch(`${gateway.baseUrl}/responses`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        instructions: "Call the supplied connectivity tool exactly once.",
        input: [
          {
            type: "message",
            role: "user",
            content: [
              { type: "input_text", text: "Run the ALTA connectivity check." },
            ],
          },
        ],
        tools: [
          {
            type: "function",
            name: "alta_connectivity_check",
            description: "Confirms model tool-calling compatibility.",
            parameters: {
              type: "object",
              properties: { status: { type: "string", enum: ["ok"] } },
              required: ["status"],
              additionalProperties: false,
            },
            strict: true,
          },
        ],
        tool_choice:
          providerName === "kimi"
            ? { type: "function", name: "alta_connectivity_check" }
            : "auto",
        stream: true,
        max_output_tokens: 64,
      }),
    });
    const text = await response.text();
    const events = text
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => {
        try {
          return JSON.parse(line.slice(6));
        } catch {
          return null;
        }
      })
      .filter(Boolean);
    const completed = events.some(
      (event) => event.type === "response.completed",
    );
    const toolCall = events.some(
      (event) => event.item?.type === "function_call",
    );
    const failure = events.find((event) => event.type === "response.failed");
    const eventTypes = [
      ...new Set(
        events.flatMap((event) =>
          [event.type, event.item?.type].filter(Boolean),
        ),
      ),
    ].slice(0, 8);
    return completed && toolCall
      ? { ok: true, message: `${model}, tool call` }
      : {
          ok: false,
          message:
            failure?.response?.error?.message ??
            `missing completed event or function call (events: ${eventTypes.join(", ") || "none"})`,
        };
  } finally {
    await gateway.close();
  }
}

function storageManager() {
  ensureDirectories();
  return new StorageManager(STATE_DIR);
}

function printStorage(snapshot) {
  console.log("ALTA v3.5 storage guard");
  console.log(
    `  pressure: ${snapshot.pressure} (${formatBytes(snapshot.totalBytes)} / ${formatBytes(snapshot.maxBytes)})`,
  );
  console.log(`  free disk: ${formatBytes(snapshot.freeBytes)}`);
  console.log(`  durable state: ${formatBytes(snapshot.durableBytes)}`);
  console.log(
    `  rebuildable toolchain: ${formatBytes(snapshot.toolchainBytes)}`,
  );
  console.log(`  disposable build cache: ${formatBytes(snapshot.buildBytes)}`);
  console.log(`  bounded runtime cache: ${formatBytes(snapshot.cacheBytes)}`);
}

function environmentManager(env = process.env) {
  ensureDirectories();
  return new RuntimeEnvironment({
    rootDir: ROOT_DIR,
    stateDir: STATE_DIR,
    env,
  });
}

function opportunityService() {
  return new OpportunityService({
    rootDir: ROOT_DIR,
    stateDir: STATE_DIR,
    cliFile: path.join(SOURCE_DIR, "cli.mjs"),
    environmentFactory: environmentManager,
  });
}

function managedDashboardService(service = opportunityService()) {
  return new DashboardService({
    rootDir: ROOT_DIR,
    stateDir: STATE_DIR,
    cliFile: path.join(SOURCE_DIR, "cli.mjs"),
    service,
    environmentFactory: environmentManager,
  });
}

function printEnvironment(status) {
  console.log("ALTA v3.5 managed environment");
  console.log(
    `  Python: ${status.python.ready ? `${status.python.version} (${status.python.path})` : `${status.python.version} not installed`}`,
  );
  console.log(
    `  containers: ${status.docker.ready ? `Docker ${status.docker.version} (${status.docker.context})` : `unavailable${status.docker.error ? ` (${status.docker.error})` : ""}`}`,
  );
  const states = status.services.states ?? {};
  console.log(
    `  PostgreSQL 16 + pgvector: ${states.postgres ?? (status.services.configured ? "stopped" : "not configured")}`,
  );
  console.log(
    `  Redis: ${states.redis ?? (status.services.configured ? "stopped" : "not configured")}`,
  );
}

async function environmentCommand(args) {
  const manager = environmentManager();
  const [action = "status", ...rest] = args;
  if (action === "status") return printEnvironment(await manager.status());
  if (action === "setup") {
    if (rest.some((value) => value !== "--dev"))
      throw new Error("env setup only accepts --dev");
    await manager.setup({ dev: rest.includes("--dev") });
  } else if (action === "up") await manager.up();
  else if (action === "down") await manager.down();
  else if (action === "restart") await manager.restart();
  else if (action === "logs") return manager.logs(rest);
  else if (action === "python")
    return (process.exitCode = await manager.python(rest));
  else throw new Error(`Unknown environment action "${action}"`);
  printEnvironment(await manager.status());
}

async function storageCommand(args) {
  const manager = storageManager();
  const [action = "status"] = args;
  if (action === "status") return printStorage(await manager.snapshot());
  if (action === "maintain") {
    const result = await manager.maintain({
      dryRun: args.includes("--dry-run"),
    });
    if (result.skipped)
      return console.log(`maintenance skipped: ${result.reason}`);
    console.log(
      `${result.dryRun ? "would remove" : "removed"}: ${result.removed.length} cache target(s)`,
    );
    return printStorage(result.snapshot);
  }
  throw new Error(`Unknown storage action "${action}"`);
}

async function withManagedRuntime(action) {
  const manager = storageManager();
  const runtimeReady = fs.existsSync(BINARY) && fs.existsSync(CODE_MODE_HOST);
  const enforceStorage = async () => {
    const maintenance = await manager.maintain();
    if (!maintenance.skipped && maintenance.snapshot.pressure === "critical")
      throw new Error(
        "ALTA storage guard is critical after maintenance; increase the project budget or free disk space",
      );
  };
  await enforceStorage();
  await ensureBinary();
  if (!runtimeReady) await enforceStorage();
  const stop = manager.start((error) =>
    console.warn(`warning: storage maintenance failed (${error.message})`),
  );
  try {
    return await action(manager);
  } finally {
    stop();
  }
}

async function supervisorCommand(args) {
  const [requestedProvider, ...codexArgs] = args;
  const provider = requestedProvider === "grok" ? "xai" : requestedProvider;
  if (!["openai", "deepseek", "xai", "kimi"].includes(provider))
    throw new Error(
      "supervise requires one provider: openai, deepseek, grok/xai, or kimi",
    );
  return withManagedRuntime((storage) =>
    supervise({
      stateDir: STATE_DIR,
      provider,
      launch: (options) =>
        provider === "openai"
          ? launchOpenAi(codexArgs, options)
          : launchProvider(provider, codexArgs, { ...options, storage }),
    }),
  );
}

async function status() {
  const manager = storageManager();
  printStorage(await manager.snapshot());
  printEnvironment(await environmentManager().status());
  const runtimeDir = path.join(STATE_DIR, "runtime");
  const files = fs
    .readdirSync(runtimeDir)
    .filter((file) => /^supervisor-.*\.json$/.test(file));
  console.log("  supervisors:");
  if (!files.length) console.log("    none");
  for (const file of files) {
    const value = JSON.parse(
      fs.readFileSync(path.join(runtimeDir, file), "utf8"),
    );
    console.log(
      `    ${value.provider}: ${value.state} (pid ${value.childPid ?? "none"})`,
    );
  }
}

async function doctor(live, liveProviders = Object.keys(PROVIDERS)) {
  const state = await prepare({ refresh: live });
  console.log("ALTA v3.5 isolation check");
  console.log(`  workspace: ${ROOT_DIR}`);
  console.log(`  private state: ${STATE_DIR}`);
  console.log(
    `  official config untouched: ${path.join(os.homedir(), ".codex", "config.toml")}`,
  );
  console.log(`  Rust toolchain: ${findCargo() ?? "missing"}`);
  console.log(
    `  private binary: ${fs.existsSync(BINARY) ? BINARY : "not built yet"}`,
  );
  console.log(
    `  code-mode host: ${fs.existsSync(CODE_MODE_HOST) ? CODE_MODE_HOST : "not built yet"}`,
  );
  const environment = await environmentManager().status();
  console.log(
    `  managed Python: ${environment.python.ready ? `${environment.python.version} (${environment.python.path})` : `${environment.python.version} not installed`}`,
  );
  console.log(
    `  service runtime: ${environment.docker.ready ? `${environment.docker.context}; PostgreSQL ${environment.services.states?.postgres ?? "stopped"}; Redis ${environment.services.states?.redis ?? "stopped"}` : "container engine unavailable"}`,
  );
  console.log(
    `  OpenAI auth route: ${state.authRoute.mode === "official" ? "local official Codex session" : "isolated ALTA session"} (${state.authRoute.available ? state.authRoute.reference : "login required"})`,
  );
  const openAiServices = thirdPartyOpenAiServicePolicy(
    path.join(HOME_DIR, "auth.json"),
  );
  console.log(
    `  local OpenAI auth services: ${openAiServices.enabled ? "available" : "paused"} (${openAiServices.reason}); remote apps/plugins disabled`,
  );
  for (const name of Object.keys(PROVIDERS))
    console.log(
      `  ${PROVIDERS[name].label} key: ${state.sources[name] ?? "missing"}`,
    );
  const snapshot = await storageManager().snapshot();
  console.log(
    `  storage guard: ${snapshot.pressure} (${formatBytes(snapshot.totalBytes)}, ${formatBytes(snapshot.freeBytes)} free)`,
  );
  console.log(
    `  agent concurrency: ${numberSetting("ALTA_AGENT_THREADS", 4, 1, 32)} per session`,
  );
  console.log(
    `  provider recovery: ${numberSetting("ALTA_MAX_RETRIES", 12, 0, 1000)} retries / ${numberSetting("ALTA_RETRY_BUDGET_MS", 300_000, 1000, 3_600_000)} ms budget / ${numberSetting("ALTA_QUEUE_TIMEOUT_MS", 120_000, 1000, 3_600_000)} ms queue timeout`,
  );
  console.log("  agent backend: multi_agent_v2 recursive task tree");
  const internetBackend = state.resourceCredentials.values.BRAVE_SEARCH_API_KEY
    ? "Brave LLM Context"
    : state.credentials.xai
      ? "xAI Web Search"
      : process.env.ALTA_SEARXNG_URL
        ? "SearXNG"
        : "no-key public search fallback";
  const toolCount = internetToolNames().length;
  const pluginNames = internetPluginIds()
    .map((id) => id.replace(/^alta-/, ""))
    .join(", ");
  console.log(
    `  internet/files: ${internetBackend}; ${toolCount} portable read-only tools at every agent depth`,
  );
  console.log(
    `  tool plugins: ${pluginNames}${state.resourceCredentials.values.JINA_API_KEY ? ", Jina authenticated" : ", Jina no-key reader fallback"}`,
  );
  console.log(
    `  internet resilience: ${numberSetting("ALTA_WEB_CONCURRENCY", 6, 1, 64)} real HTTP requests / circuit after ${numberSetting("ALTA_WEB_BACKEND_FAILURES", 2, 1, 20)} failures / ${numberSetting("ALTA_WEB_BACKEND_COOLDOWN_MS", 15_000, 1000, 3_600_000)} ms initial cooldown`,
  );
  console.log(
    `  academic sources: OpenAlex${state.resourceCredentials.values.OPENALEX_API_KEY ? " authenticated" : " best-effort"}, Crossref, arXiv`,
  );
  console.log(
    `  company intelligence: Finnhub${state.resourceCredentials.values.FINNHUB_API_KEY ? " credential loaded (live validity requires a provider probe)" : " optional credential missing"}`,
  );
  console.log(
    `  public intelligence: 11 direct / 48 discoverable social platforms; 20 news / 18 finance sources; display-only TradingView navigation`,
  );
  console.log(
    "  provider admission: automatic 429 concurrency reduction with gradual recovery",
  );
  console.log(
    `  internet cache: ${numberSetting("ALTA_WEB_CACHE_MB", 32, 4, 512)} MiB / ${numberSetting("ALTA_WEB_CACHE_TTL_MINUTES", 10, 1, 1440)} minute fresh / ${numberSetting("ALTA_WEB_STALE_TTL_MINUTES", 60, 1, 10_080)} minute stale fallback`,
  );
  console.log(
    `  file reader: ${numberSetting("ALTA_FILE_MAX_MB", 16, 1, 64)} MiB/file / ${numberSetting("ALTA_FILE_EXPANDED_MB", 8, 1, 32)} MiB expanded / ${numberSetting("ALTA_FILE_CACHE_MB", 16, 4, 128)} MiB memory cache`,
  );
  console.log(
    `  generated model agent types: ${state.catalogs.agentRoles.length}`,
  );
  for (const warning of state.warnings) console.warn(`  warning: ${warning}`);
  if (!live) return;
  console.log("\nLive provider probes (small billable requests):");
  for (const name of liveProviders) {
    const result = await liveProbe(name, state);
    console.log(
      `  ${PROVIDERS[name].label}: ${result.ok ? "OK" : "FAILED"} (${result.message})`,
    );
    if (!result.ok) process.exitCode = 1;
  }
}

async function test() {
  ensureDirectories();
  const testDir = path.join(SOURCE_DIR, "test");
  const files = fs
    .readdirSync(testDir)
    .filter((file) => file.endsWith(".test.mjs"))
    .map((file) => path.join(testDir, file));
  const code = await run(process.execPath, ["--test", ...files], {
    cwd: ROOT_DIR,
    env: isolatedEnvironment(),
  });
  if (code !== 0) throw new Error(`tests failed with exit code ${code}`);
}

function assertProxyRuntime() {
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (
    process.env.ALTA_HTTPS_PROXY &&
    (major < 24 || (major === 24 && minor < 5))
  ) {
    throw new Error(
      "ALTA_HTTPS_PROXY requires Node.js 24.5 or newer; direct connections work on Node.js 22+",
    );
  }
}

async function runSetupCommand() {
  const state = await prepare({ refresh: true });
  for (const warning of state.warnings) console.warn(`warning: ${warning}`);
  await build();
  await storageManager().maintain();
  return doctor(false);
}

async function runDoctorCommand(args) {
  const requested = args
    .filter((value) => !value.startsWith("-"))
    .map((value) => (value === "grok" ? "xai" : value));
  const unknown = requested.find((value) => !PROVIDERS[value]);
  if (unknown) throw new Error(`Unknown doctor provider "${unknown}"`);
  return doctor(
    args.includes("--live"),
    requested.length ? requested : Object.keys(PROVIDERS),
  );
}

async function runServiceCommand(args) {
  process.exitCode =
    (await opportunityServiceCommand(args, {
      service: opportunityService(),
      ensureBinary,
      storageManager,
    })) ?? 0;
}

async function runOpenAiCommand(args) {
  process.exitCode = await withManagedRuntime((storage) =>
    launchOpenAi(args, { storage }),
  );
}

async function runProviderCommand(command, args) {
  const provider = command === "grok" ? "xai" : command;
  process.exitCode = await withManagedRuntime((storage) =>
    launchProvider(provider, args, { storage }),
  );
}

async function dispatchCommand(command, args) {
  if (["help", "--help", "-h"].includes(command)) return console.log(HELP);
  if (["version", "--version", "-V"].includes(command))
    return console.log("ALTA v3.5");
  const handlers = {
    build: async () => {
      await build();
      return storageManager().maintain();
    },
    setup: runSetupCommand,
    models: () => listModels(args.includes("--refresh")),
    doctor: () => runDoctorCommand(args),
    storage: () => storageCommand(args),
    env: () => environmentCommand(args),
    credentials: () =>
      credentialCommand(args, { service: opportunityService() }),
    service: () => runServiceCommand(args),
    dashboard: () => {
      const service = opportunityService();
      return dashboardCommand(args, {
        rootDir: ROOT_DIR,
        service,
        environmentFactory: environmentManager,
        dashboardService: managedDashboardService(service),
      });
    },
    status,
    supervise: async () => {
      process.exitCode = await supervisorCommand(args);
    },
    test,
    openai: () => runOpenAiCommand(args),
  };
  if (handlers[command]) return handlers[command]();
  if (["deepseek", "kimi", "grok", "xai"].includes(command))
    return runProviderCommand(command, args);
  throw new Error(`Unknown ALTA command "${command}". Run ./alta help.`);
}

async function main() {
  assertProxyRuntime();
  const [command = "openai", ...args] = process.argv.slice(2);
  return dispatchCommand(command, args);
}

main().catch((error) => {
  console.error(`ALTA v3.5: ${error.message}`);
  process.exitCode = 1;
});
