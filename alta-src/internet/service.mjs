import { createHash } from "node:crypto";
import process from "node:process";
import { boundedNumber, CapacityLimiter, sleep } from "../resource-control.mjs";
import { BoundedCache } from "./cache.mjs";
import { BackendHealth } from "./backend-health.mjs";
import {
  assertAutomatedSitePolicy,
  assertPublicUrl,
  extractDocument,
} from "./content.mjs";
import { crawlSite } from "./crawl.mjs";
import { InflightCoalescer } from "./inflight.mjs";
import { extractReaderDocument, readerRequestUrl } from "./reader.mjs";
import { executeSearch, normalizeSearch } from "./search.mjs";
import { LocalFileReader } from "../local-files.mjs";

const TRANSIENT_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504]);
const USER_AGENT = "ALTABot/3.5 (research-only local operator)";
const DEFAULT_PIPED_URLS = ["https://api.piped.private.coffee"];

function publicEndpointUrls(value, fallback) {
  const candidates = String(value ?? fallback.join(","))
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return candidates
    .flatMap((candidate) => {
      try {
        const url = new URL(candidate);
        if (url.protocol !== "https:" || url.username || url.password)
          return [];
        return [url.href];
      } catch {
        return [];
      }
    })
    .slice(0, 3);
}

function settings(env = process.env) {
  return {
    cacheBytes: boundedNumber(env.ALTA_WEB_CACHE_MB, 32, 4, 512) * 1024 * 1024,
    cacheTtlMs:
      boundedNumber(env.ALTA_WEB_CACHE_TTL_MINUTES, 10, 1, 1440) * 60 * 1000,
    staleTtlMs:
      boundedNumber(env.ALTA_WEB_STALE_TTL_MINUTES, 60, 1, 10_080) * 60 * 1000,
    concurrency: boundedNumber(env.ALTA_WEB_CONCURRENCY, 6, 1, 64),
    crawlConcurrency: boundedNumber(env.ALTA_WEB_CRAWL_CONCURRENCY, 3, 1, 12),
    inflightLimit: boundedNumber(env.ALTA_WEB_INFLIGHT_LIMIT, 256, 1, 4096),
    queueLimit: boundedNumber(env.ALTA_WEB_QUEUE_LIMIT, 128, 0, 4096),
    timeoutMs: boundedNumber(env.ALTA_WEB_TIMEOUT_MS, 45_000, 5_000, 300_000),
    maxDownloadBytes:
      boundedNumber(env.ALTA_WEB_MAX_DOWNLOAD_MB, 4, 1, 32) * 1024 * 1024,
    maxOutputChars: boundedNumber(
      env.ALTA_WEB_MAX_OUTPUT_CHARS,
      32_000,
      4_000,
      40_000,
    ),
    allowProxyFakeIp: env.ALTA_ALLOW_PROXY_FAKE_IP !== "0",
    readerEnabled: env.ALTA_WEB_READER_ENABLED !== "0",
    readerMinimumChars: boundedNumber(
      env.ALTA_WEB_READER_MIN_CHARS,
      500,
      100,
      10_000,
    ),
    backendFailureThreshold: boundedNumber(
      env.ALTA_WEB_BACKEND_FAILURES,
      2,
      1,
      20,
    ),
    backendCooldownMs: boundedNumber(
      env.ALTA_WEB_BACKEND_COOLDOWN_MS,
      15_000,
      1_000,
      3_600_000,
    ),
  };
}

function cappedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed)
    ? Math.trunc(Math.min(Math.max(parsed, minimum), maximum))
    : fallback;
}

function canonicalKey(kind, value) {
  return `${kind}:${createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
}

function retryDelay(attempt, retryAfter) {
  const seconds = Number(retryAfter);
  if (Number.isFinite(seconds) && seconds >= 0)
    return Math.min(seconds * 1000, 30_000);
  return Math.min(500 * 2 ** attempt, 10_000) + Math.floor(Math.random() * 250);
}

async function boundedBody(response, maximum) {
  if (!response.body) return "";
  const chunks = [];
  let bytes = 0;
  for await (const chunk of response.body) {
    bytes += chunk.length;
    if (bytes > maximum) {
      await response.body.cancel().catch(() => {});
      throw Object.assign(
        new Error("Web response exceeds the ALTA download limit"),
        {
          status: 413,
          code: "alta_web_download_too_large",
        },
      );
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

export class InternetService {
  constructor(options = {}) {
    const runtimeEnv = options.env ?? process.env;
    this.closed = false;
    this.settings = { ...settings(runtimeEnv), ...options.settings };
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.lookup = options.lookup;
    this.timeoutSignal =
      options.timeoutSignal ??
      ((milliseconds) => AbortSignal.timeout(milliseconds));
    this.xaiSearch = options.xaiSearch ?? null;
    this.braveKey = options.braveKey ?? null;
    this.searxngUrl = options.searxngUrl ?? null;
    this.readerUrl = options.readerUrl ?? "https://r.jina.ai";
    this.readerKey = options.readerKey ?? null;
    this.jinaKey = options.jinaKey ?? this.readerKey;
    this.openAlexKey = options.openAlexKey ?? null;
    this.finnhubKey = options.finnhubKey ?? null;
    this.crossrefMailto = options.crossrefMailto ?? null;
    this.lemmyUrl = options.lemmyUrl ?? "https://lemmy.world";
    this.mastodonUrl = options.mastodonUrl ?? "https://mastodon.social";
    this.peertubeUrl = options.peertubeUrl ?? "https://peertube.tv";
    this.discourseUrl = options.discourseUrl ?? "https://meta.discourse.org";
    this.pipedUrls =
      options.pipedUrls ??
      publicEndpointUrls(runtimeEnv.ALTA_PIPED_URLS, DEFAULT_PIPED_URLS);
    this.secUserAgent =
      options.secUserAgent ??
      "Autonomous LLM Trading Asterism/3.5 (configure ALTA_SEC_USER_AGENT)";
    this.fileReader =
      options.fileReader ??
      (options.fileRoots?.length
        ? new LocalFileReader({ roots: options.fileRoots, env: runtimeEnv })
        : null);
    this.cache = new BoundedCache(
      this.settings.cacheBytes,
      this.settings.cacheTtlMs,
      this.settings.staleTtlMs,
    );
    this.inflight = new InflightCoalescer(this.settings.inflightLimit);
    this.limiter = new CapacityLimiter({
      limit: this.settings.concurrency,
      queueLimit: this.settings.queueLimit,
      queueTimeoutMs: this.settings.timeoutMs,
      name: "ALTA internet capacity",
    });
    this.backendHealth = new BackendHealth({
      failureThreshold: this.settings.backendFailureThreshold,
      baseCooldownMs: this.settings.backendCooldownMs,
      maxCooldownMs: Math.min(this.settings.backendCooldownMs * 20, 3_600_000),
    });
    this.metrics = {
      searches: 0,
      fetches: 0,
      crawls: 0,
      cacheHits: 0,
      staleHits: 0,
      failures: 0,
      readerFallbacks: 0,
      toolCalls: {},
    };
  }

  async readText(
    {
      url,
      accept = "text/plain,application/json,application/xml;q=0.9,*/*;q=0.2",
      headers,
      cache_namespace: cacheNamespace = "resource",
      max_chars: maxChars = 512_000,
      attempts = 4,
    },
    { signal } = {},
  ) {
    const limit = cappedInteger(maxChars, 512_000, 1_000, 1_000_000);
    const key = canonicalKey(cacheNamespace, { url, accept, limit });
    return this.#cached(key, signal, async (sharedSignal) => {
      const response = await this.request(url, {
        accept,
        headers,
        signal: sharedSignal,
        attempts,
      });
      return {
        url: response.url,
        content_type: response.contentType,
        text: response.body.slice(0, limit),
        truncated: response.body.length > limit,
        cached: false,
      };
    });
  }

  async fetchWithReader(url, signal) {
    await assertPublicUrl(url, {
      lookup: this.lookup,
      allowProxyFakeIp: this.settings.allowProxyFakeIp,
    });
    const response = await this.request(readerRequestUrl(this.readerUrl, url), {
      accept: "text/plain",
      headers: {
        "X-Respond-With": "frontmatter",
        "X-Engine": "auto",
        ...(this.readerKey
          ? { Authorization: `Bearer ${this.readerKey}` }
          : {}),
      },
      signal,
    });
    this.metrics.readerFallbacks += 1;
    const document = extractReaderDocument(response.body, url);
    if (document.metadata.source_url !== url)
      await assertPublicUrl(document.metadata.source_url, {
        lookup: this.lookup,
        allowProxyFakeIp: this.settings.allowProxyFakeIp,
      });
    return {
      response,
      document,
    };
  }

  async request(url, options = {}) {
    const maximum = options.maximum ?? this.settings.maxDownloadBytes;
    const resolveTarget = async (value) => {
      const parsed = new URL(value);
      if (
        options.trustedOrigin &&
        parsed.origin === options.trustedOrigin &&
        ["http:", "https:"].includes(parsed.protocol) &&
        !parsed.username &&
        !parsed.password
      ) {
        assertAutomatedSitePolicy(parsed);
        return parsed;
      }
      return assertPublicUrl(parsed.href, {
        lookup: this.lookup,
        allowProxyFakeIp: this.settings.allowProxyFakeIp,
      });
    };
    let current = await resolveTarget(url);
    for (let redirect = 0; redirect <= 5; redirect += 1) {
      let lastError;
      const attempts = cappedInteger(options.attempts, 4, 1, 4);
      for (let attempt = 0; attempt < attempts; attempt += 1) {
        const release = await this.limiter.acquire(options.signal);
        const controller = new AbortController();
        const cancel = () =>
          controller.abort(
            options.signal.reason ?? new Error("web request cancelled"),
          );
        const timer = setTimeout(
          () => controller.abort(new Error("web request timed out")),
          this.settings.timeoutMs,
        );
        if (options.signal?.aborted) cancel();
        else options.signal?.addEventListener("abort", cancel, { once: true });
        try {
          const response = await this.fetchImpl(current, {
            method: options.method ?? "GET",
            headers: {
              "User-Agent": USER_AGENT,
              "Accept":
                options.accept ??
                "text/html,application/json,text/plain;q=0.9,*/*;q=0.2",
              ...options.headers,
            },
            body: options.body,
            redirect: "manual",
            signal: controller.signal,
          });
          if ([301, 302, 303, 307, 308].includes(response.status)) {
            const location = response.headers.get("location");
            if (!location)
              throw new Error("Redirect is missing a Location header");
            current = await resolveTarget(new URL(location, current).href);
            lastError = null;
            break;
          }
          const body = await boundedBody(response, maximum);
          if (!response.ok) {
            const error = new Error(
              `Web HTTP ${response.status}: ${body.slice(0, 500)}`,
            );
            error.status = response.status;
            error.retryAfter = response.headers.get("retry-after");
            throw error;
          }
          return {
            body,
            contentType: response.headers.get("content-type") ?? "",
            url: current.href,
            status: response.status,
          };
        } catch (error) {
          lastError = error;
          if (
            attempt === attempts - 1 ||
            (error.status && !TRANSIENT_STATUS.has(error.status))
          )
            throw error;
        } finally {
          clearTimeout(timer);
          options.signal?.removeEventListener("abort", cancel);
          release();
        }
        await sleep(retryDelay(attempt, lastError.retryAfter), options.signal);
      }
      if (lastError) throw lastError;
    }
    throw Object.assign(new Error("Web request exceeded the redirect limit"), {
      status: 508,
      code: "alta_web_redirect_limit",
    });
  }

  async fetchPage(
    { url, max_chars: maxChars = 24_000, reader = "auto" } = {},
    { signal } = {},
  ) {
    const limit = cappedInteger(
      maxChars,
      24_000,
      1_000,
      this.settings.maxOutputChars,
    );
    const readerMode = ["auto", "direct", "reader"].includes(reader)
      ? reader
      : "auto";
    const key = canonicalKey("fetch", { url, limit, readerMode });
    return this.#cached(key, signal, async (sharedSignal) => {
      try {
        this.metrics.fetches += 1;
        let response;
        let document;
        let readerUsed = false;
        if (readerMode === "reader") {
          ({ response, document } = await this.fetchWithReader(
            url,
            sharedSignal,
          ));
          readerUsed = true;
        } else {
          try {
            response = await this.request(url, { signal: sharedSignal });
            document = extractDocument(
              response.body,
              response.contentType,
              response.url,
            );
            if (
              readerMode === "auto" &&
              this.settings.readerEnabled &&
              (document.kind === "binary" ||
                (document.kind === "html" &&
                  document.text.length < this.settings.readerMinimumChars))
            ) {
              ({ response, document } = await this.fetchWithReader(
                url,
                sharedSignal,
              ));
              readerUsed = true;
            }
          } catch (error) {
            if (
              readerMode !== "auto" ||
              !this.settings.readerEnabled ||
              error.code?.startsWith("alta_web_")
            )
              throw error;
            ({ response, document } = await this.fetchWithReader(
              url,
              sharedSignal,
            ));
            readerUsed = true;
          }
        }
        const result = {
          url: readerUsed ? url : response.url,
          title: document.title,
          content_type: response.contentType,
          kind: document.kind,
          text: document.text.slice(0, limit),
          truncated: document.text.length > limit,
          links: document.links.slice(0, 100),
          metadata: document.metadata ?? {},
          reader_used: readerUsed,
          cached: false,
        };
        return result;
      } catch (error) {
        this.metrics.failures += 1;
        throw error;
      }
    });
  }

  recordTool(name, succeeded) {
    const current = this.metrics.toolCalls[name] ?? { calls: 0, failures: 0 };
    current.calls += 1;
    if (!succeeded) current.failures += 1;
    this.metrics.toolCalls[name] = current;
  }

  async search(args = {}, { signal } = {}) {
    const normalized = normalizeSearch(args, {
      brave: Boolean(this.braveKey),
      xai: Boolean(this.xaiSearch),
      searxng: Boolean(this.searxngUrl),
      jina: Boolean(this.jinaKey),
    });
    const key = canonicalKey("search", normalized);
    return this.#cached(key, signal, async (sharedSignal) => {
      try {
        this.metrics.searches += 1;
        const result = await executeSearch(
          {
            braveKey: this.braveKey,
            xaiSearch: this.xaiSearch,
            jinaKey: this.jinaKey,
            searxngUrl: this.searxngUrl,
            request: this.request.bind(this),
            backendHealth: this.backendHealth,
          },
          normalized,
          sharedSignal,
        );
        const value = {
          query: normalized.query,
          ...result,
          cached: false,
        };
        return value;
      } catch (error) {
        this.metrics.failures += 1;
        throw error;
      }
    });
  }

  async crawl(
    {
      url,
      max_pages: maxPages = 6,
      max_depth: maxDepth = 1,
      max_chars: maxChars = 30_000,
    } = {},
    { signal } = {},
  ) {
    const pagesLimit = cappedInteger(maxPages, 6, 1, 12);
    const depthLimit = cappedInteger(maxDepth, 1, 0, 2);
    const charsLimit = cappedInteger(
      maxChars,
      30_000,
      2_000,
      this.settings.maxOutputChars,
    );
    const start = await assertPublicUrl(url, {
      lookup: this.lookup,
      allowProxyFakeIp: this.settings.allowProxyFakeIp,
    });
    this.metrics.crawls += 1;
    return crawlSite(
      this,
      {
        start,
        pagesLimit,
        depthLimit,
        charsLimit,
        concurrency: this.settings.crawlConcurrency,
      },
      { signal },
    );
  }

  async readLocalFile(args, options) {
    if (!this.fileReader)
      throw Object.assign(new Error("Local file reading is not configured"), {
        status: 503,
        code: "alta_file_disabled",
      });
    return this.fileReader.read(args, options);
  }

  snapshot() {
    return {
      metrics: { ...this.metrics },
      capacity: this.limiter.snapshot(),
      cache: this.cache.snapshot(),
      inflight: this.inflight.snapshot(),
      searchBackends: this.backendHealth.snapshot(),
      fileCache: this.fileReader?.snapshot() ?? null,
    };
  }

  close() {
    this.closed = true;
    this.limiter.close();
    this.inflight.close();
    this.cache.clear();
    this.fileReader?.close();
  }

  async #cached(key, signal, operation) {
    const cached = this.cache.get(key);
    if (cached) {
      this.metrics.cacheHits += 1;
      return { ...cached, cached: true };
    }
    const stale = this.cache.getStale(key);
    return this.inflight.run(
      key,
      async (sharedSignal) => {
        const current = this.cache.get(key);
        if (current) {
          this.metrics.cacheHits += 1;
          return { ...current, cached: true };
        }
        try {
          const value = await operation(sharedSignal);
          if (!this.closed) this.cache.set(key, value);
          return value;
        } catch (error) {
          if (
            stale &&
            !sharedSignal.aborted &&
            (!error.status || TRANSIENT_STATUS.has(error.status))
          ) {
            this.metrics.staleHits += 1;
            return { ...stale, cached: true, stale: true };
          }
          throw error;
        }
      },
      signal,
    );
  }
}
