import http from "node:http";
import os from "node:os";
import process from "node:process";
import { randomUUID } from "node:crypto";
import {
  kimiToResponse,
  normalizeNativeResponse,
  responseEvents,
  responsesToKimi,
} from "./translate.mjs";
import {
  providerModelCapabilities,
  redact,
  runtimeProvider,
} from "./providers.mjs";
import { validateMultimodalRequest } from "./multimodal.mjs";
import { isRetryableStatus, resilientJson } from "./provider-request.mjs";
import {
  annotateDeepSeekCalls,
  flattenNativeNamespaces,
  nativeBody,
  providerForModel,
  restoreNativeNamespaceCalls,
} from "./gateway-native-request.mjs";
import {
  HeartbeatHub,
  writeSseChunk,
  writeSseComment,
} from "./sse-channel.mjs";
import {
  ByteBudget,
  CapacityLimiter,
  LatencyMetrics,
  ProviderConcurrencyController,
  RetryCoordinator,
  acquireCapacityLease,
  boundedNumber,
  numberSetting,
} from "./resource-control.mjs";
import { InternetService } from "./internet/service.mjs";
import { handleMcpMessage } from "./internet/mcp.mjs";

const MEDIA_MEMORY_RESERVATION_MULTIPLIER = 5;

function gatewaySettings(overrides = {}) {
  const cpuDefault = Math.min(
    16,
    Math.max(4, (os.availableParallelism?.() ?? os.cpus().length) * 2),
  );
  return {
    maxRetries: numberSetting("ALTA_MAX_RETRIES", 12, 0, 1000),
    retryBudgetMs: numberSetting(
      "ALTA_RETRY_BUDGET_MS",
      5 * 60 * 1000,
      1000,
      60 * 60 * 1000,
    ),
    requestTimeoutMs: numberSetting(
      "ALTA_REQUEST_TIMEOUT_MS",
      600_000,
      10_000,
      3_600_000,
    ),
    heartbeatMs: numberSetting("ALTA_HEARTBEAT_MS", 10_000, 1000, 60_000),
    maxRequestBytes:
      numberSetting("ALTA_MAX_REQUEST_MB", 16, 1, 256) * 1024 * 1024,
    maxResponseBytes:
      numberSetting("ALTA_MAX_RESPONSE_MB", 32, 1, 256) * 1024 * 1024,
    requestMemoryBytes:
      numberSetting("ALTA_REQUEST_MEMORY_MB", 128, 16, 4096) * 1024 * 1024,
    maxMultimodalBytes:
      numberSetting("ALTA_MAX_MULTIMODAL_MB", 8, 1, 64) * 1024 * 1024,
    maxMediaItems: numberSetting("ALTA_MAX_MEDIA_ITEMS", 16, 1, 64),
    maxMediaTokens: numberSetting("ALTA_MAX_MEDIA_TOKENS", 9_000, 1_000, 9_000),
    multimodalConcurrency: numberSetting(
      "ALTA_MULTIMODAL_CONCURRENCY",
      2,
      1,
      16,
    ),
    maxTextFilePreviewBytes: numberSetting(
      "ALTA_MAX_TEXT_FILE_PREVIEW_BYTES",
      900,
      256,
      900,
    ),
    maxRssBytes:
      numberSetting("ALTA_MAX_RSS_MB", 2048, 128, 65_536) * 1024 * 1024,
    maxConcurrentRequests: numberSetting(
      "ALTA_MAX_CONCURRENT_REQUESTS",
      cpuDefault,
      1,
      256,
    ),
    maxQueuedRequests: numberSetting(
      "ALTA_MAX_QUEUED_REQUESTS",
      256,
      0,
      10_000,
    ),
    queueTimeoutMs: numberSetting(
      "ALTA_QUEUE_TIMEOUT_MS",
      2 * 60 * 1000,
      1000,
      60 * 60 * 1000,
    ),
    providerConcurrency: {
      deepseek: numberSetting("ALTA_DEEPSEEK_CONCURRENCY", 8, 1, 128),
      xai: numberSetting("ALTA_XAI_CONCURRENCY", 8, 1, 128),
      kimi: numberSetting("ALTA_KIMI_CONCURRENCY", 8, 1, 128),
    },
    closeGraceMs: numberSetting(
      "ALTA_SHUTDOWN_GRACE_MS",
      30_000,
      1000,
      10 * 60 * 1000,
    ),
    ...overrides,
  };
}

async function acquireUpstreamAttempt(
  context,
  providerName,
  signal,
  { hasMedia = false, timing = null } = {},
) {
  const queuedAt = performance.now();
  let release;
  try {
    release = await acquireCapacityLease(
      [
        hasMedia ? context.multimodalLimiter : null,
        context.providerLimiters.get(providerName),
        context.globalLimiter,
      ],
      signal,
    );
  } finally {
    if (timing) timing.queueMs += performance.now() - queuedAt;
  }
  const startedAt = performance.now();
  let active = true;
  return () => {
    if (!active) return;
    active = false;
    if (timing) timing.upstreamMs += performance.now() - startedAt;
    release();
  };
}

async function readJsonBody(req, context) {
  const chunks = [];
  let size = 0;
  let reserved = 0;
  try {
    for await (const chunk of req) {
      size += chunk.length;
      if (size > context.settings.maxRequestBytes)
        throw Object.assign(new Error("Request exceeds the ALTA body limit"), {
          status: 413,
          code: "alta_request_too_large",
        });
      context.bodyBudget.reserve(chunk.length);
      reserved += chunk.length;
      chunks.push(chunk);
    }
    let released = false;
    return {
      value: JSON.parse(Buffer.concat(chunks).toString("utf8")),
      reserveExtra: (bytes) => {
        context.bodyBudget.reserve(bytes);
        reserved += bytes;
      },
      release: () => {
        if (released) return;
        released = true;
        context.bodyBudget.release(reserved);
      },
    };
  } catch (cause) {
    context.bodyBudget.release(reserved);
    if (cause.status) throw cause;
    throw Object.assign(
      new Error("Request body is not valid JSON", { cause }),
      { status: 400, code: "alta_invalid_json" },
    );
  }
}

function gatewayErrorCode(error) {
  if (error.code) return error.code;
  if (
    Number.isInteger(error.status) &&
    error.status >= 400 &&
    error.status < 500 &&
    !isRetryableStatus(error.status)
  )
    return "invalid_prompt";
  return "alta_gateway_error";
}

function sendJson(res, status, value) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(value));
}

async function handleInternetMcp(req, res, context) {
  if (req.headers.authorization !== `Bearer ${context.token}`) {
    sendJson(res, 401, { error: { message: "Invalid local gateway token" } });
    return;
  }
  const controller = new AbortController();
  context.controllers.add(controller);
  res.on("close", () => {
    if (!res.writableEnded)
      controller.abort(new Error("MCP internet client disconnected"));
  });
  let bodyLease;
  try {
    if (context.closing)
      throw Object.assign(new Error("ALTA gateway is draining"), {
        status: 503,
        code: "alta_draining",
      });
    bodyLease = await readJsonBody(req, context);
    const researchBudget = admitBoundedScoutToolCall(
      req,
      context,
      bodyLease.value,
    );
    const result = await handleMcpMessage(
      context.internetService,
      bodyLease.value,
      { signal: controller.signal, researchBudget },
    );
    if (result === null) {
      res.writeHead(202, { "Cache-Control": "no-store" });
      res.end();
    } else {
      sendJson(res, 200, result);
    }
  } catch (error) {
    sendJson(res, error.status ?? 500, {
      jsonrpc: "2.0",
      id: bodyLease?.value?.id ?? null,
      error: {
        code: -32000,
        message: redact(error.message, Object.values(context.credentials)),
      },
    });
  } finally {
    bodyLease?.release();
    context.controllers.delete(controller);
  }
}

function admitBoundedScoutToolCall(req, context, message) {
  if (message?.method !== "tools/call") return null;
  const runId = req.headers["x-alta-run-id"];
  const rawLimit = req.headers["x-alta-max-tool-calls"];
  if (runId === undefined && rawLimit === undefined) return null;
  if (
    typeof runId !== "string" ||
    !/^run_[a-f0-9]{32}$/.test(runId) ||
    typeof rawLimit !== "string" ||
    !/^([0-9]|1[0-2])$/.test(rawLimit)
  )
    throw Object.assign(new Error("Invalid ALTA Scout tool budget headers"), {
      status: 400,
      code: "alta_scout_budget_invalid",
    });
  const limit = Number(rawLimit);
  context.scoutToolCalls ??= new Map();
  const previous = context.scoutToolCalls.get(runId) ?? 0;
  if (previous >= limit)
    throw Object.assign(new Error("ALTA Scout tool call budget exhausted"), {
      status: 429,
      code: "alta_scout_tool_budget_exhausted",
    });
  context.scoutToolCalls.set(runId, previous + 1);
  if (context.scoutToolCalls.size > 1_000) {
    const oldest = context.scoutToolCalls.keys().next().value;
    context.scoutToolCalls.delete(oldest);
  }
  return { limit, used: previous + 1, remaining: limit - previous - 1 };
}

function assertGatewayReady(context) {
  if (context.closing)
    throw Object.assign(new Error("ALTA gateway is draining"), {
      status: 503,
      code: "alta_draining",
    });
  if (context.storage && !context.storage.canAcceptWork())
    throw Object.assign(
      new Error(
        "ALTA disk reserve is active; storage maintenance must free space before new work starts",
      ),
      { status: 507, code: "alta_storage_reserve" },
    );
  if (process.memoryUsage().rss > context.settings.maxRssBytes)
    throw Object.assign(
      new Error("ALTA gateway memory pressure is above its safety limit"),
      { status: 503, code: "alta_memory_pressure" },
    );
}

function prepareResponseRequest(bodyLease, context) {
  const body = bodyLease.value;
  const providerName = providerForModel(
    body.model,
    context.routes,
    context.forcedProvider,
  );
  const credential = context.credentials[providerName];
  if (!credential)
    throw Object.assign(
      new Error(
        `No ${runtimeProvider(providerName).label} credential is configured`,
      ),
      { status: 401, code: "alta_credential_missing" },
    );
  let mediaProfile;
  try {
    const capabilities =
      context.modelCapabilities.get(body.model) ??
      providerModelCapabilities(providerName, body.model);
    mediaProfile = validateMultimodalRequest(
      body,
      providerName,
      capabilities,
      context.settings,
    );
    bodyLease.reserveExtra(
      mediaProfile.inlineEncodedBytes * MEDIA_MEMORY_RESERVATION_MULTIPLIER,
    );
  } catch (error) {
    context.multimodalMetrics.rejected += 1;
    throw error;
  }
  context.multimodalMetrics.requests += mediaProfile.hasMedia ? 1 : 0;
  context.multimodalMetrics.imageItems += mediaProfile.imageItems;
  context.multimodalMetrics.audioItems += mediaProfile.audioItems;
  context.multimodalMetrics.fileItems += mediaProfile.fileItems;
  context.multimodalMetrics.inlineBytes += mediaProfile.inlineDecodedBytes;
  return { body, credential, mediaProfile, providerName };
}

async function requestUpstreamResponse({
  body,
  context,
  controller,
  credential,
  mediaProfile,
  providerName,
  res,
  timing,
}) {
  const provider = runtimeProvider(providerName);
  const requestHooks = {
    acquireAttempt: (signal) =>
      acquireUpstreamAttempt(context, providerName, signal, {
        hasMedia: mediaProfile.hasMedia,
        timing,
      }),
    onRetry: (attempt) => writeSseComment(res, `upstream retry ${attempt}`),
  };
  if (provider.protocol === "chat") {
    const translated = responsesToKimi(body, {
      maximumTextFileBytes: context.settings.maxTextFilePreviewBytes,
    });
    const result = await resilientJson(
      provider.inferenceUrl,
      credential,
      translated.chat,
      providerName,
      controller.signal,
      context,
      requestHooks,
    );
    return kimiToResponse(result, translated.identities);
  }
  const upstreamBody = nativeBody(body, providerName);
  const namespaceAliases = ["deepseek", "xai"].includes(providerName)
    ? flattenNativeNamespaces(upstreamBody)
    : new Map();
  const result = await resilientJson(
    provider.inferenceUrl,
    credential,
    upstreamBody,
    providerName,
    controller.signal,
    context,
    requestHooks,
  );
  if (namespaceAliases.size)
    restoreNativeNamespaceCalls(result, namespaceAliases);
  const response = normalizeNativeResponse(result);
  if (providerName === "deepseek") annotateDeepSeekCalls(response);
  return response;
}

async function sendGatewayFailure(res, controller, context, error) {
  const message = redact(error.message, Object.values(context.credentials));
  const code = gatewayErrorCode(error);
  if (!res.headersSent) {
    sendJson(res, error.status ?? 500, {
      error: { type: "server_error", code, message },
    });
    return;
  }
  await writeSseChunk(
    res,
    `data: ${JSON.stringify({
      type: "response.failed",
      response: {
        id: `resp_alta_${randomUUID()}`,
        status: "failed",
        error: { type: "server_error", code, message },
      },
    })}\n\n`,
    controller.signal,
  );
}

async function handleResponses(req, res, context) {
  const receivedAt = performance.now();
  if (req.headers.authorization !== `Bearer ${context.token}`) {
    sendJson(res, 401, { error: { message: "Invalid local gateway token" } });
    return;
  }
  const controller = new AbortController();
  context.controllers.add(controller);
  res.on("close", () => {
    if (!res.writableEnded) controller.abort(new Error("Codex disconnected"));
  });
  let bodyLease;
  let unregisterHeartbeat;
  let providerName;
  let timing;
  let succeeded = false;

  try {
    assertGatewayReady(context);
    bodyLease = await readJsonBody(req, context);
    const request = prepareResponseRequest(bodyLease, context);
    providerName = request.providerName;

    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-store",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    });
    unregisterHeartbeat = context.heartbeats.register(res);
    await writeSseChunk(
      res,
      ": ALTA v3.5 resilient gateway\n\n",
      controller.signal,
    );

    timing = { queueMs: 0, upstreamMs: 0 };
    context.metrics.started += 1;
    const response = await requestUpstreamResponse({
      ...request,
      context,
      controller,
      res,
      timing,
    });
    for (const event of responseEvents(response))
      await writeSseChunk(
        res,
        `data: ${JSON.stringify(event)}\n\n`,
        controller.signal,
      );
    context.metrics.completed += 1;
    succeeded = true;
  } catch (error) {
    if (!controller.signal.aborted) {
      context.metrics.failed += 1;
      await sendGatewayFailure(res, controller, context, error);
    }
  } finally {
    if (providerName && timing) {
      const finishedAt = performance.now();
      context.latency.observe(providerName, {
        queueMs: timing.queueMs,
        upstreamMs: timing.upstreamMs,
        totalMs: finishedAt - receivedAt,
        succeeded,
      });
    }
    unregisterHeartbeat?.();
    bodyLease?.release();
    context.controllers.delete(controller);
    if (!res.destroyed) res.end();
  }
}

export async function startGateway({
  credentials,
  routes = new Map(),
  modelCapabilities = new Map(),
  forcedProvider = null,
  token,
  settings: settingOverrides,
  storage = null,
  internet = {},
}) {
  const settings = gatewaySettings(settingOverrides);
  const globalLimiter = new CapacityLimiter({
    limit: settings.maxConcurrentRequests,
    queueLimit: settings.maxQueuedRequests,
    queueTimeoutMs: settings.queueTimeoutMs,
    name: "ALTA global upstream capacity",
  });
  const providerLimiters = new Map(
    ["deepseek", "xai", "kimi"].map((provider) => [
      provider,
      new CapacityLimiter({
        limit: boundedNumber(settings.providerConcurrency[provider], 8, 1, 128),
        queueLimit: settings.maxQueuedRequests,
        queueTimeoutMs: settings.queueTimeoutMs,
        name: `${provider} upstream capacity`,
      }),
    ]),
  );
  const multimodalLimiter = new CapacityLimiter({
    limit: settings.multimodalConcurrency,
    queueLimit: Math.min(settings.maxQueuedRequests, 32),
    queueTimeoutMs: settings.queueTimeoutMs,
    name: "ALTA multimodal capacity",
  });
  const context = {
    credentials,
    routes,
    modelCapabilities,
    forcedProvider,
    token,
    settings,
    storage,
    globalLimiter,
    providerLimiters,
    multimodalLimiter,
    bodyBudget: new ByteBudget(settings.requestMemoryBytes),
    retryCoordinator: new RetryCoordinator(),
    providerConcurrency: new ProviderConcurrencyController(providerLimiters),
    latency: new LatencyMetrics(),
    heartbeats: new HeartbeatHub(settings.heartbeatMs),
    controllers: new Set(),
    closing: false,
    metrics: { started: 0, completed: 0, failed: 0, retries: 0 },
    multimodalMetrics: {
      requests: 0,
      rejected: 0,
      imageItems: 0,
      audioItems: 0,
      fileItems: 0,
      inlineBytes: 0,
    },
  };
  const xaiModels = [...routes]
    .filter(([, provider]) => provider === "xai")
    .map(([model]) => model);
  const xaiModel =
    internet.xaiModel ??
    ["grok-4.6", "grok-4.5", "grok-4"].find((model) =>
      xaiModels.includes(model),
    ) ??
    xaiModels[0];
  context.internetService =
    internet.service ??
    new InternetService({
      braveKey: internet.braveKey,
      searxngUrl: internet.searxngUrl,
      readerUrl: internet.readerUrl,
      readerKey: internet.readerKey,
      jinaKey: internet.jinaKey,
      openAlexKey: internet.openAlexKey,
      finnhubKey: internet.finnhubKey,
      crossrefMailto: internet.crossrefMailto,
      lemmyUrl: internet.lemmyUrl,
      mastodonUrl: internet.mastodonUrl,
      peertubeUrl: internet.peertubeUrl,
      discourseUrl: internet.discourseUrl,
      secUserAgent: internet.secUserAgent,
      fileRoots: internet.fileRoots,
      xaiSearch:
        internet.xaiSearchEnabled !== false && credentials.xai && xaiModel
          ? async ({ query, depth, maximum, filters, signal }) => {
              const controller = new AbortController();
              const cancel = () =>
                controller.abort(
                  signal.reason ?? new Error("internet search cancelled"),
                );
              if (signal?.aborted) cancel();
              else signal?.addEventListener("abort", cancel, { once: true });
              context.controllers.add(controller);
              try {
                context.metrics.started += 1;
                const value = await resilientJson(
                  runtimeProvider("xai").inferenceUrl,
                  credentials.xai,
                  {
                    model: xaiModel,
                    store: false,
                    instructions:
                      depth === "deep"
                        ? `Research the request thoroughly with multiple web searches when useful. Compare independent primary sources, identify uncertainty, and cite source URLs. Keep the final answer under 6000 words and use at most ${maximum} principal sources.`
                        : `Search the live web for the request. Give a concise evidence-grounded answer with source URLs and at most ${maximum} principal sources.`,
                    input: query,
                    tools: [
                      {
                        type: "web_search",
                        ...(filters ? { filters } : {}),
                      },
                    ],
                    max_output_tokens: depth === "deep" ? 8_000 : 3_000,
                  },
                  "xai",
                  controller.signal,
                  context,
                  {
                    acquireAttempt: (signal) =>
                      acquireUpstreamAttempt(context, "xai", signal),
                  },
                );
                context.metrics.completed += 1;
                return value;
              } catch (error) {
                context.metrics.failed += 1;
                throw error;
              } finally {
                context.controllers.delete(controller);
                signal?.removeEventListener("abort", cancel);
              }
            }
          : null,
    });
  const server = http.createServer(async (req, res) => {
    try {
      const requestUrl = new URL(req.url, "http://127.0.0.1");
      if (req.method === "GET" && requestUrl.pathname === "/health") {
        sendJson(res, context.closing ? 503 : 200, {
          status: context.closing ? "draining" : "ok",
          system: "ALTA v3.5",
          uptimeSeconds: Math.round(process.uptime()),
          memory: { rssBytes: process.memoryUsage().rss },
          requests: context.metrics,
          multimodal: {
            metrics: context.multimodalMetrics,
            limits: {
              inputBytes: settings.maxMultimodalBytes,
              mediaItems: settings.maxMediaItems,
              mediaTokens: settings.maxMediaTokens,
              textFilePreviewBytes: settings.maxTextFilePreviewBytes,
            },
          },
          capacity: {
            global: context.globalLimiter.snapshot(),
            multimodal: context.multimodalLimiter.snapshot(),
            providers: Object.fromEntries(
              [...context.providerLimiters].map(([name, limiter]) => [
                name,
                limiter.snapshot(),
              ]),
            ),
            body: context.bodyBudget.snapshot(),
          },
          retry: context.retryCoordinator.snapshot(),
          adaptiveConcurrency: context.providerConcurrency.snapshot(),
          latency: context.latency.snapshot(),
          output: context.heartbeats.snapshot(),
          internet: context.internetService.snapshot(),
          storage: context.storage?.lastSnapshot ?? null,
        });
      } else if (
        req.method === "POST" &&
        requestUrl.pathname === "/responses"
      ) {
        await handleResponses(req, res, context);
      } else if (req.method === "POST" && requestUrl.pathname === "/mcp") {
        await handleInternetMcp(req, res, context);
      } else {
        sendJson(res, 404, { error: { message: "Not found" } });
      }
    } catch (error) {
      if (!res.headersSent)
        sendJson(res, error.status ?? 500, {
          error: { message: redact(error.message, Object.values(credentials)) },
        });
      else if (!res.destroyed) res.end();
    }
  });
  server.requestTimeout = 0;
  server.headersTimeout = 30_000;
  server.keepAliveTimeout = 15_000;
  server.maxRequestsPerSocket = 1000;
  server.maxConnections =
    settings.maxConcurrentRequests + settings.maxQueuedRequests + 32;
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  let closing;
  const close = () => {
    if (closing) return closing;
    closing = (async () => {
      context.closing = true;
      context.globalLimiter.close();
      context.multimodalLimiter.close();
      for (const limiter of context.providerLimiters.values()) limiter.close();
      context.internetService.close();
      const closed = new Promise((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve(true))),
      );
      server.closeIdleConnections?.();
      let shutdownTimer;
      const deadline = new Promise((resolve) => {
        shutdownTimer = setTimeout(() => resolve(false), settings.closeGraceMs);
        shutdownTimer.unref?.();
      });
      try {
        const graceful = await Promise.race([closed, deadline]);
        clearTimeout(shutdownTimer);
        if (!graceful) {
          for (const controller of context.controllers)
            controller.abort(
              new Error("ALTA gateway shutdown deadline reached"),
            );
          server.closeAllConnections?.();
          await closed;
        }
      } finally {
        clearTimeout(shutdownTimer);
        context.heartbeats.close();
      }
    })();
    return closing;
  };
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close,
  };
}
