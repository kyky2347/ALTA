import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import process from "node:process";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { acquireLease } from "./storage.mjs";
import { atomicWrite, atomicWriteJson } from "./durable-file.mjs";

const JSON_TYPE = "application/json; charset=utf-8";
const SESSION_COOKIE = "alta_console_session";
const ENVIRONMENT_CACHE_MS = 7_500;
const RUNTIME_CACHE_MS = 1_000;
const UPSTREAM_TIMEOUT_MS = 15_000;
const MAX_UPSTREAM_BODY_BYTES = 16 * 1024 * 1024;
const MAX_CREDENTIAL_BODY_BYTES = 8 * 1024;
export const OPERATOR_PROTOCOL_VERSION = 2;

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT" || error instanceof SyntaxError) return null;
    throw error;
  }
}

function constantTimeEqual(left, right) {
  const a = Buffer.from(String(left ?? ""));
  const b = Buffer.from(String(right ?? ""));
  return a.length === b.length && timingSafeEqual(a, b);
}

function cookies(request) {
  return Object.fromEntries(
    (request.headers.cookie ?? "")
      .split(";")
      .map((part) => part.trim().split("="))
      .filter(([key, value]) => key && value)
      .map(([key, ...value]) => [key, decodeURIComponent(value.join("="))]),
  );
}

function json(response, status, value) {
  const body = Buffer.from(JSON.stringify(value));
  response.writeHead(status, {
    "Content-Type": JSON_TYPE,
    "Content-Length": body.length,
    "Cache-Control": "no-store",
  });
  response.end(body);
}

function safeError(error) {
  return String(error?.message ?? error ?? "Unknown operation failure")
    .split("\n")[0]
    .slice(0, 300);
}

async function readJsonBody(request, maximumBytes = MAX_CREDENTIAL_BODY_BYTES) {
  if (
    !String(request.headers["content-type"] ?? "").startsWith(
      "application/json",
    )
  )
    throw Object.assign(new Error("A JSON request body is required"), {
      statusCode: 415,
      code: "json_required",
    });
  const declared = Number(request.headers["content-length"]);
  if (Number.isFinite(declared) && declared > maximumBytes)
    throw Object.assign(new Error("The credential request is too large"), {
      statusCode: 413,
      code: "credential_request_too_large",
    });
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    length += buffer.length;
    if (length > maximumBytes)
      throw Object.assign(new Error("The credential request is too large"), {
        statusCode: 413,
        code: "credential_request_too_large",
      });
    chunks.push(buffer);
  }
  try {
    return JSON.parse(Buffer.concat(chunks, length).toString("utf8"));
  } catch {
    throw Object.assign(new Error("The JSON request body is invalid"), {
      statusCode: 400,
      code: "invalid_json",
    });
  }
}

function contentType(file) {
  return (
    {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".json": JSON_TYPE,
      ".png": "image/png",
      ".svg": "image/svg+xml",
      ".woff2": "font/woff2",
    }[path.extname(file).toLowerCase()] ?? "application/octet-stream"
  );
}

function readOwnerOnlyToken(file) {
  const metadata = fs.lstatSync(file);
  if (metadata.isSymbolicLink() || !metadata.isFile())
    throw new Error(
      "The operator console session secret must be a regular file",
    );
  if (
    process.platform !== "win32" &&
    typeof process.getuid === "function" &&
    metadata.uid !== process.getuid()
  )
    throw new Error(
      "The operator console session secret must be owned by this user",
    );
  fs.chmodSync(file, 0o600);
  const token = fs.readFileSync(file, "utf8").trim();
  if (!/^[A-Za-z0-9_-]{43,128}$/.test(token))
    throw new Error("The operator console session secret is invalid");
  return token;
}

function persistentSessionToken(file) {
  const lease = acquireLease(`${file}.lock`);
  try {
    if (!fs.existsSync(file))
      atomicWrite(file, `${randomBytes(32).toString("base64url")}\n`);
    try {
      return readOwnerOnlyToken(file);
    } catch (error) {
      const metadata = fs.lstatSync(file);
      if (metadata.isSymbolicLink() || !metadata.isFile()) throw error;
      if (
        process.platform !== "win32" &&
        typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()
      )
        throw error;
      atomicWrite(file, `${randomBytes(32).toString("base64url")}\n`);
      return readOwnerOnlyToken(file);
    }
  } finally {
    lease.release();
  }
}

async function boundedBody(response) {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_UPSTREAM_BODY_BYTES)
    throw new Error("Upstream response exceeded the console safety limit");
  if (!response.body) return Buffer.alloc(0);
  const chunks = [];
  let length = 0;
  for await (const chunk of response.body) {
    const buffer = Buffer.from(chunk);
    length += buffer.length;
    if (length > MAX_UPSTREAM_BODY_BYTES) {
      await response.body.cancel?.().catch(() => {});
      throw new Error("Upstream response exceeded the console safety limit");
    }
    chunks.push(buffer);
  }
  return Buffer.concat(chunks, length);
}

export function createOperatorConsole({
  host = "127.0.0.1",
  port = 8877,
  staticDir,
  service,
  environmentFactory,
  fetchImpl = fetch,
  onBootstrapUsed = () => {},
}) {
  if (!fs.existsSync(path.join(staticDir, "index.html")))
    throw new Error("ALTA dashboard is not built; run pnpm dashboard:build");

  const stateDir = service.stateDir ?? path.dirname(service.tokenFile);
  const sessionFile = path.join(
    stateDir,
    "secrets",
    "operator_console_session",
  );
  const sessionToken = persistentSessionToken(sessionFile);
  const bootstrapToken = randomBytes(32).toString("base64url");
  const csrfToken = randomBytes(32).toString("base64url");
  const instanceId = randomBytes(16).toString("base64url");
  const startedAt = new Date().toISOString();
  let bootstrapUsed = false;
  const operationFile = path.join(
    stateDir,
    "runtime",
    "operator-operation.json",
  );
  const operationLockFile = path.join(
    stateDir,
    "runtime",
    "operator-operation.lock",
  );
  let operation = readJson(operationFile);
  let environmentCache = null;
  let environmentProbe = null;
  let runtimeCache = null;
  let runtimeProbe = null;

  function writeOperation(value) {
    operation = value;
    atomicWriteJson(operationFile, value);
  }

  function publicOperation() {
    if (!operation) return null;
    const { ownerPid: _ownerPid, ...visible } = operation;
    return visible;
  }

  async function environmentStatus({ fresh = false } = {}) {
    if (!fresh && environmentCache?.expiresAt > Date.now())
      return environmentCache.value;
    if (environmentProbe) return environmentProbe;
    environmentProbe = (async () => {
      try {
        const { environment: childEnvironment } = service.runtimeEnvironment();
        const value = await environmentFactory(childEnvironment).status();
        environmentCache = {
          value,
          expiresAt: Date.now() + ENVIRONMENT_CACHE_MS,
        };
        return value;
      } catch (error) {
        const value = { error: safeError(error) };
        environmentCache = {
          value,
          expiresAt: Date.now() + ENVIRONMENT_CACHE_MS,
        };
        return value;
      } finally {
        environmentProbe = null;
      }
    })();
    return environmentProbe;
  }

  async function runtimeStatus({ fresh = false } = {}) {
    if (!fresh && runtimeCache?.expiresAt > Date.now())
      return runtimeCache.value;
    if (runtimeProbe) return runtimeProbe;
    runtimeProbe = service
      .status()
      .then((value) => {
        runtimeCache = { value, expiresAt: Date.now() + RUNTIME_CACHE_MS };
        return value;
      })
      .finally(() => {
        runtimeProbe = null;
      });
    return runtimeProbe;
  }

  function reconcileOperation(runtime, environment) {
    if (operation?.status !== "running") return;
    if (
      operation.ownerPid === process.pid ||
      processIsAlive(operation.ownerPid)
    )
      return;
    const services = Object.values(environment?.services?.states ?? {});
    const environmentStopped = services.length === 0;
    const achieved =
      operation.action === "stop"
        ? !runtime.ready && environmentStopped
        : runtime.ready;
    writeOperation({
      ...operation,
      status: achieved ? "completed" : "failed",
      phase: "reconciled_after_console_restart",
      ...(achieved
        ? {}
        : {
            error:
              "The operator console restarted before the lifecycle action completed; the current runtime state is shown and the action can be retried safely.",
          }),
      completedAt: new Date().toISOString(),
    });
  }

  async function state() {
    const runtime = await runtimeStatus();
    const environment = await environmentStatus();
    reconcileOperation(runtime, environment);
    return {
      runtime,
      environment,
      console: {
        protocolVersion: OPERATOR_PROTOCOL_VERSION,
        instanceId,
        startedAt,
        uptimeSeconds: Math.max(
          0,
          Math.floor((Date.now() - Date.parse(startedAt)) / 1000),
        ),
      },
      operation: publicOperation(),
      safety: {
        environment: "shadow",
        capitalMode: "disabled",
        dashboardBinding: `${host}:${port}`,
      },
    };
  }

  function publicCredentialInventory() {
    const inventory = service.credentialInventory();
    return {
      revision: inventory.revision,
      configuredSlots: inventory.configuredSlots,
      slots: inventory.slots,
      providerNetwork: inventory.providerNetwork ?? [],
      trading: inventory.trading ?? {
        provider: "Tiger Trade",
        mode: "paper_only",
        configured: false,
        editable: false,
        source: "missing",
        sourceKind: "missing",
        fingerprint: null,
        status: "not_configured_capital_disabled",
      },
    };
  }

  async function runOperation(action, lease) {
    writeOperation({
      ...operation,
      phase: "validating",
    });
    try {
      const before = await service.status();
      if (action === "start" && before.ready) {
        writeOperation({
          ...operation,
          status: "completed",
          phase: "already_ready",
          completedAt: new Date().toISOString(),
        });
        return;
      }
      if (
        action === "start" &&
        (before.host?.processAlive || before.supervisor?.childProcessAlive)
      ) {
        writeOperation({
          ...operation,
          phase: "waiting_for_existing_startup",
        });
        await service.waitForReadiness();
        runtimeCache = null;
        writeOperation({
          ...operation,
          status: "completed",
          phase: "ready",
          completedAt: new Date().toISOString(),
        });
        return;
      }
      if (action === "stop" && before.host && !before.host.processAlive) {
        const { environment } = service.runtimeEnvironment();
        writeOperation({ ...operation, phase: "stopping_dependencies" });
        await environmentFactory(environment).down();
        environmentCache = null;
        runtimeCache = null;
        writeOperation({
          ...operation,
          status: "completed",
          phase: "stopped",
          completedAt: new Date().toISOString(),
        });
        return;
      }
      writeOperation({ ...operation, phase: `${action}_requested` });
      if (action === "start") {
        if (!service.installed()) {
          const { environment } = service.runtimeEnvironment();
          writeOperation({ ...operation, phase: "preparing_environment" });
          await environmentFactory(environment).setup();
          environmentCache = null;
          writeOperation({ ...operation, phase: "installing_service" });
          await service.assertEndpointAvailable();
          service.install({ start: false });
        }
        writeOperation({ ...operation, phase: "starting_service" });
        service.platform.start();
        writeOperation({ ...operation, phase: "waiting_for_readiness" });
        await service.waitForReadiness();
      } else if (action === "stop") {
        writeOperation({ ...operation, phase: "stopping_service" });
        await service.stop();
        const { environment } = service.runtimeEnvironment();
        writeOperation({ ...operation, phase: "stopping_dependencies" });
        await environmentFactory(environment).down();
      } else if (action === "restart") {
        if (!service.installed())
          throw new Error("Install the ALTA service before restarting it");
        service.platform.restart();
        writeOperation({ ...operation, phase: "waiting_for_readiness" });
        await service.waitForReadiness();
      } else {
        throw new Error(`Unknown runtime action ${action}`);
      }
      environmentCache = null;
      runtimeCache = null;
      writeOperation({
        ...operation,
        status: "completed",
        phase: action === "stop" ? "stopped" : "ready",
        completedAt: new Date().toISOString(),
      });
    } catch (error) {
      environmentCache = null;
      runtimeCache = null;
      writeOperation({
        ...operation,
        status: "failed",
        phase: "failed",
        error: safeError(error),
        completedAt: new Date().toISOString(),
      });
    } finally {
      lease.release();
    }
  }

  function acceptOperation(action) {
    const lease = acquireLease(operationLockFile, { busy: "skip" });
    if (!lease) return false;
    try {
      const id = randomBytes(12).toString("base64url");
      writeOperation({
        id,
        action,
        status: "running",
        phase: "accepted",
        ownerPid: process.pid,
        startedAt: new Date().toISOString(),
      });
      void runOperation(action, lease);
      return true;
    } catch (error) {
      lease.release();
      throw error;
    }
  }

  function authenticated(request) {
    return constantTimeEqual(cookies(request)[SESSION_COOKIE], sessionToken);
  }

  function permittedMutation(request) {
    const expectedOrigin = `http://${host}:${server.address()?.port ?? port}`;
    return (
      authenticated(request) &&
      constantTimeEqual(request.headers.origin, expectedOrigin) &&
      constantTimeEqual(request.headers["x-alta-csrf"], csrfToken)
    );
  }

  async function proxy(request, response, url) {
    const status = await service.status();
    if (!status.ready) {
      json(response, 503, {
        error: {
          code: "runtime_not_ready",
          message: "The research runtime is not ready; the console will retry.",
        },
      });
      return;
    }
    const targetPath = url.pathname.slice("/proxy".length);
    const target = new URL(`${targetPath}${url.search}`, status.endpoint);
    const token = fs.readFileSync(service.tokenFile, "utf8").trim();
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(new Error("Upstream request timed out")),
      UPSTREAM_TIMEOUT_MS,
    );
    timeout.unref?.();
    const abort = () => controller.abort(new Error("Browser disconnected"));
    request.once("aborted", abort);
    try {
      const upstream = await fetchImpl(target, {
        headers: {
          Accept: request.headers.accept ?? "application/json",
          Authorization: `Bearer ${token}`,
          ...(request.headers["last-event-id"]
            ? { "Last-Event-ID": request.headers["last-event-id"] }
            : {}),
        },
        signal: controller.signal,
      });
      const body = await boundedBody(upstream);
      response.writeHead(upstream.status, {
        "Content-Type": upstream.headers.get("content-type") ?? JSON_TYPE,
        "Cache-Control": "no-store",
        "Content-Length": body.length,
      });
      response.end(body);
    } finally {
      clearTimeout(timeout);
      request.removeListener("aborted", abort);
    }
  }

  function serveStatic(request, response, pathname) {
    const requested = pathname === "/" ? "/index.html" : pathname;
    const resolved = path.resolve(staticDir, `.${requested}`);
    const root = `${path.resolve(staticDir)}${path.sep}`;
    const candidate =
      resolved.startsWith(root) && fs.existsSync(resolved) ? resolved : null;
    const file =
      candidate && fs.statSync(candidate).isFile()
        ? candidate
        : path.join(staticDir, "index.html");
    if (!file.startsWith(root) && file !== path.join(staticDir, "index.html")) {
      json(response, 404, { error: { code: "not_found" } });
      return;
    }
    const body = fs.readFileSync(file);
    response.writeHead(200, {
      "Content-Type": contentType(file),
      "Content-Length": body.length,
      "Cache-Control": file.endsWith("index.html")
        ? "no-store"
        : "public, max-age=31536000, immutable",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  }

  const server = http.createServer(async (request, response) => {
    response.setHeader("X-Content-Type-Options", "nosniff");
    response.setHeader("Referrer-Policy", "no-referrer");
    response.setHeader("X-Frame-Options", "DENY");
    response.setHeader(
      "Content-Security-Policy",
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'",
    );
    try {
      const url = new URL(request.url, `http://${host}:${port}`);
      if (request.method === "GET" && url.pathname === "/health/live") {
        json(response, 200, {
          data: { live: true, protocolVersion: OPERATOR_PROTOCOL_VERSION },
        });
        return;
      }
      if (request.method === "GET" && url.pathname === "/health/ready") {
        json(response, 200, {
          data: { ready: true, protocolVersion: OPERATOR_PROTOCOL_VERSION },
        });
        return;
      }
      if (url.pathname === `/open/${bootstrapToken}` && !bootstrapUsed) {
        bootstrapUsed = true;
        response.writeHead(303, {
          "Location": "/",
          "Set-Cookie": `${SESSION_COOKIE}=${sessionToken}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`,
          "Cache-Control": "no-store",
        });
        response.end();
        try {
          onBootstrapUsed();
        } catch {
          // Session issuance must not depend on optional host-state bookkeeping.
        }
        return;
      }
      if (
        url.pathname.startsWith("/control/") ||
        url.pathname.startsWith("/proxy/")
      ) {
        if (!authenticated(request)) {
          json(response, 401, { error: { code: "console_unauthorized" } });
          return;
        }
      }
      if (request.method === "GET" && url.pathname === "/control/bootstrap") {
        json(response, 200, { data: { csrfToken, ...(await state()) } });
        return;
      }
      if (request.method === "GET" && url.pathname === "/control/state") {
        json(response, 200, { data: await state() });
        return;
      }
      if (request.method === "GET" && url.pathname === "/control/credentials") {
        json(response, 200, { data: publicCredentialInventory() });
        return;
      }
      const credentialSlot = url.pathname.match(
        /^\/control\/credentials\/([a-z0-9-]+)$/,
      )?.[1];
      if (request.method === "PUT" && credentialSlot) {
        if (!permittedMutation(request)) {
          json(response, 403, { error: { code: "mutation_forbidden" } });
          return;
        }
        if (operation?.status === "running") {
          json(response, 409, { error: { code: "operation_in_progress" } });
          return;
        }
        const runtime = await runtimeStatus({ fresh: true });
        if (
          runtime.ready ||
          runtime.host?.processAlive ||
          runtime.supervisor?.childProcessAlive
        ) {
          json(response, 409, {
            error: {
              code: "runtime_must_be_stopped",
              message:
                "Stop the research runtime before changing provider credentials.",
            },
          });
          return;
        }
        const body = await readJsonBody(request);
        if (
          !body ||
          typeof body !== "object" ||
          Array.isArray(body) ||
          typeof body.secret !== "string" ||
          Object.keys(body).some((key) => key !== "secret")
        ) {
          json(response, 400, {
            error: {
              code: "invalid_credential_request",
              message: "Provide exactly one write-only secret value.",
            },
          });
          return;
        }
        try {
          service.replaceCredential(credentialSlot, body.secret);
          runtimeCache = null;
          json(response, 200, { data: publicCredentialInventory() });
        } catch (error) {
          const environmentLocked = /supplied by .*environment variable/.test(
            String(error?.message ?? ""),
          );
          json(response, environmentLocked ? 409 : 400, {
            error: {
              code: environmentLocked
                ? "credential_environment_locked"
                : "credential_rejected",
              message: safeError(error),
            },
          });
        }
        return;
      }
      const action = url.pathname.match(
        /^\/control\/runtime\/(start|stop|restart)$/,
      )?.[1];
      if (request.method === "POST" && action) {
        if (!permittedMutation(request)) {
          json(response, 403, { error: { code: "mutation_forbidden" } });
          return;
        }
        if (operation?.status === "running" || !acceptOperation(action)) {
          json(response, 409, { error: { code: "operation_in_progress" } });
          return;
        }
        json(response, 202, { data: { accepted: true, action } });
        return;
      }
      if (request.method === "GET" && url.pathname.startsWith("/proxy/")) {
        await proxy(request, response, url);
        return;
      }
      if (request.method !== "GET" && request.method !== "HEAD") {
        json(response, 405, { error: { code: "method_not_allowed" } });
        return;
      }
      serveStatic(request, response, url.pathname);
    } catch (error) {
      if (response.destroyed || response.writableEnded) return;
      if (response.headersSent) {
        response.destroy();
        return;
      }
      json(response, error?.statusCode ?? 502, {
        error: {
          code: error?.code ?? "console_failure",
          message: safeError(error),
        },
      });
    }
  });
  server.requestTimeout = 30_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  server.maxRequestsPerSocket = 100;
  const connections = new Set();
  server.on("connection", (socket) => {
    connections.add(socket);
    socket.once("close", () => connections.delete(socket));
  });

  return {
    server,
    async listen() {
      await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen({ host, port, exclusive: true }, resolve);
      });
      const address = server.address();
      const actualPort = typeof address === "object" ? address.port : port;
      return {
        origin: `http://${host}:${actualPort}`,
        openUrl: `http://${host}:${actualPort}/open/${bootstrapToken}`,
      };
    },
    async close() {
      if (!server.listening) return;
      await new Promise((resolve, reject) => {
        const force = setTimeout(() => {
          for (const socket of connections) socket.destroy();
        }, 2_000);
        force.unref?.();
        server.close((error) => {
          clearTimeout(force);
          if (error) reject(error);
          else resolve();
        });
        server.closeIdleConnections?.();
      });
    },
  };
}
