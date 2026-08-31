import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { atomicWriteJson } from "./durable-file.mjs";
import { runtimeProvider } from "./providers.mjs";

const SNAPSHOT_VERSION = 1;
const DEFAULT_TTL_MS = 15 * 60 * 1000;
const DEFAULT_TIMEOUT_MS = 10_000;
const HEALTH_SLOTS = new Set([
  "deepseek",
  "xai",
  "kimi",
  "massive",
  "finlight",
  "finnhub",
  "brave",
  "jina",
  "openalex",
]);
const HEALTH_STATUSES = new Set([
  "healthy",
  "auth_rejected",
  "rate_limited",
  "unavailable",
]);
const HEALTH_REASONS = new Set([
  null,
  "authentication_rejected",
  "provider_rate_limited",
  "provider_unavailable",
  "request_rejected",
  "timeout",
  "network_error",
  "probe_not_supported",
]);

function boundedSetting(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? Math.min(maximum, Math.max(minimum, Math.trunc(parsed)))
    : fallback;
}

function safeBaseUrl(value, env) {
  const parsed = new URL(value);
  const loopback = ["127.0.0.1", "::1", "localhost"].includes(parsed.hostname);
  if (
    parsed.protocol !== "https:" &&
    !(loopback && env.ALTA_MASSIVE_ALLOW_INSECURE_HTTP === "1")
  )
    throw new Error("Credential probe endpoints must use HTTPS");
  if (parsed.username || parsed.password || parsed.search || parsed.hash)
    throw new Error("Credential probe endpoints cannot contain credentials");
  return parsed.href.replace(/\/+$/, "");
}

function providerProbe(slot, secret, env) {
  if (["deepseek", "xai", "kimi"].includes(slot)) {
    return runtimeProvider(slot, env).modelsUrls.map((url) => ({
      url,
      headers: { Authorization: `Bearer ${secret}` },
    }));
  }
  if (slot === "massive") {
    const base = safeBaseUrl(
      env.ALTA_MASSIVE_BASE_URL ?? "https://api.massive.com",
      env,
    );
    const authMode = env.ALTA_MASSIVE_AUTH_MODE ?? "bearer";
    const header =
      authMode === "x_api_key"
        ? "X-API-Key"
        : authMode === "x_proxy_key"
          ? "X-Proxy-Key"
          : "Authorization";
    const value = authMode === "bearer" ? `Bearer ${secret}` : secret;
    return [
      {
        url: `${base}/v3/reference/tickers/AAPL`,
        headers: { [header]: value },
      },
    ];
  }
  if (slot === "finlight")
    return [
      {
        url: "https://api.finlight.me/v2/sources",
        headers: { "X-API-KEY": secret },
      },
    ];
  if (slot === "finnhub") {
    const url = new URL("https://finnhub.io/api/v1/stock/metric");
    url.searchParams.set("symbol", "AAPL");
    url.searchParams.set("metric", "all");
    url.searchParams.set("token", secret);
    return [{ url: url.href, headers: {} }];
  }
  if (slot === "brave") {
    const url = new URL("https://api.search.brave.com/res/v1/web/search");
    url.searchParams.set("q", "public markets");
    url.searchParams.set("count", "1");
    return [{ url: url.href, headers: { "X-Subscription-Token": secret } }];
  }
  if (slot === "jina")
    return [
      {
        url: "https://r.jina.ai/http://example.com",
        headers: { Authorization: `Bearer ${secret}` },
      },
    ];
  if (slot === "openalex") {
    const url = new URL("https://api.openalex.org/works");
    url.searchParams.set("filter", "doi:10.1038/nature12373");
    url.searchParams.set("per-page", "1");
    url.searchParams.set("api_key", secret);
    return [{ url: url.href, headers: {} }];
  }
  return [];
}

function resultForStatus(status) {
  if (status >= 200 && status < 300) return { status: "healthy", reason: null };
  if (status === 401 || status === 403)
    return { status: "auth_rejected", reason: "authentication_rejected" };
  if (status === 429)
    return { status: "rate_limited", reason: "provider_rate_limited" };
  return {
    status: "unavailable",
    reason: status >= 500 ? "provider_unavailable" : "request_rejected",
  };
}

async function discardBody(response) {
  try {
    await response.body?.cancel?.();
  } catch {
    // The verification contract records status only; response bodies are ignored.
  }
}

async function probeSlot({ slot, secret, env, fetchImpl, timeoutMs, now }) {
  const started = now();
  const checkedAt = new Date(started).toISOString();
  let last = null;
  for (const target of providerProbe(slot, secret, env)) {
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(new Error("credential_probe_timeout")),
      timeoutMs,
    );
    timer.unref?.();
    try {
      const response = await fetchImpl(target.url, {
        method: "GET",
        headers: {
          Accept: "application/json, text/plain;q=0.8",
          ...target.headers,
        },
        redirect: "error",
        signal: controller.signal,
      });
      await discardBody(response);
      const mapped = resultForStatus(response.status);
      last = {
        ...mapped,
        checkedAt,
        latencyMs: Math.max(0, now() - started),
        httpStatus: response.status,
      };
      if (mapped.status !== "unavailable" || response.status !== 404)
        return last;
    } catch (error) {
      last = {
        status: "unavailable",
        reason: controller.signal.aborted ? "timeout" : "network_error",
        checkedAt,
        latencyMs: Math.max(0, now() - started),
        httpStatus: null,
      };
    } finally {
      clearTimeout(timer);
    }
  }
  return (
    last ?? {
      status: "unavailable",
      reason: "probe_not_supported",
      checkedAt,
      latencyMs: Math.max(0, now() - started),
      httpStatus: null,
    }
  );
}

function safeSnapshot(value) {
  if (
    !value ||
    value.version !== SNAPSHOT_VERSION ||
    !/^[a-f0-9]{16}$/.test(value.revision) ||
    typeof value.checkedAt !== "string" ||
    !Number.isFinite(Date.parse(value.checkedAt)) ||
    !value.slots ||
    typeof value.slots !== "object" ||
    Array.isArray(value.slots)
  )
    return null;
  const slots = {};
  for (const [slot, result] of Object.entries(value.slots)) {
    if (
      !HEALTH_SLOTS.has(slot) ||
      !result ||
      typeof result !== "object" ||
      !HEALTH_STATUSES.has(result.status) ||
      !HEALTH_REASONS.has(result.reason ?? null) ||
      typeof result.checkedAt !== "string" ||
      !Number.isFinite(Date.parse(result.checkedAt))
    )
      continue;
    slots[slot] = {
      status: result.status,
      reason: result.reason ?? null,
      checkedAt: result.checkedAt,
      latencyMs:
        Number.isFinite(result.latencyMs) &&
        result.latencyMs >= 0 &&
        result.latencyMs <= 60_000
          ? Math.trunc(result.latencyMs)
          : null,
      httpStatus:
        Number.isInteger(result.httpStatus) &&
        result.httpStatus >= 100 &&
        result.httpStatus <= 599
          ? result.httpStatus
          : null,
    };
  }
  return {
    version: SNAPSHOT_VERSION,
    revision: value.revision,
    checkedAt: value.checkedAt,
    slots,
  };
}

function secureSnapshotFile(file) {
  const metadata = fs.lstatSync(file);
  if (metadata.isSymbolicLink() || !metadata.isFile())
    throw new Error("Credential health state must be a regular file");
  if (process.platform !== "win32") {
    if (
      typeof process.getuid === "function" &&
      metadata.uid !== process.getuid()
    )
      throw new Error("Credential health state must be owned by this user");
    fs.chmodSync(file, 0o600);
  }
}

export class CredentialHealthMonitor {
  constructor({
    stateDir,
    fetchImpl = globalThis.fetch,
    now = Date.now,
    ttlMs = DEFAULT_TTL_MS,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  }) {
    this.file = path.join(stateDir, "runtime", "credential-health.json");
    this.fetchImpl = fetchImpl;
    this.now = now;
    this.ttlMs = boundedSetting(
      ttlMs,
      DEFAULT_TTL_MS,
      30_000,
      24 * 60 * 60 * 1000,
    );
    this.timeoutMs = boundedSetting(
      timeoutMs,
      DEFAULT_TIMEOUT_MS,
      1_000,
      30_000,
    );
    this.inFlight = null;
  }

  read(revision) {
    let value;
    try {
      secureSnapshotFile(this.file);
      value = safeSnapshot(JSON.parse(fs.readFileSync(this.file, "utf8")));
    } catch (error) {
      if (error.code === "ENOENT" || error instanceof SyntaxError) return null;
      throw error;
    }
    return value?.revision === revision ? value : null;
  }

  publicState(revision) {
    const snapshot = this.read(revision);
    if (!snapshot)
      return { checkedAt: null, expiresAt: null, stale: true, slots: {} };
    const expiresAtMs = Date.parse(snapshot.checkedAt) + this.ttlMs;
    return {
      checkedAt: snapshot.checkedAt,
      expiresAt: new Date(expiresAtMs).toISOString(),
      stale: this.now() >= expiresAtMs,
      slots: snapshot.slots,
    };
  }

  async verify({ revision, values, env = process.env, force = false }) {
    const cached = this.publicState(revision);
    if (!force && cached.checkedAt && !cached.stale) return cached;
    if (this.inFlight) return this.inFlight;
    this.inFlight = this.#verify({ revision, values, env }).finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }

  async #verify({ revision, values, env }) {
    const entries = Object.entries(values);
    const verified = await Promise.all(
      entries.map(async ([slot, secret]) => [
        slot,
        await probeSlot({
          slot,
          secret,
          env,
          fetchImpl: this.fetchImpl,
          timeoutMs: this.timeoutMs,
          now: this.now,
        }),
      ]),
    );
    const checkedAt = new Date(this.now()).toISOString();
    const snapshot = {
      version: SNAPSHOT_VERSION,
      revision,
      checkedAt,
      slots: Object.fromEntries(verified),
    };
    atomicWriteJson(this.file, snapshot, { mode: 0o600 });
    return this.publicState(revision);
  }
}

export function mergeCredentialHealth(inventory, health) {
  return {
    ...inventory,
    verification: {
      checkedAt: health.checkedAt,
      expiresAt: health.expiresAt,
      stale: health.stale,
    },
    slots: inventory.slots.map((slot) => ({
      ...slot,
      verification: slot.configured
        ? (health.slots[slot.slot] ?? {
            status: "unverified",
            reason: "not_checked",
            checkedAt: null,
            latencyMs: null,
            httpStatus: null,
          })
        : slot.availableWithoutCredential
          ? {
              status: "not_required",
              reason: null,
              checkedAt: health.checkedAt,
              latencyMs: null,
              httpStatus: null,
            }
          : {
              status: "not_configured",
              reason: "credential_missing",
              checkedAt: null,
              latencyMs: null,
              httpStatus: null,
            },
    })),
  };
}
