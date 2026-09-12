import { createHash } from "node:crypto";
import process from "node:process";
import { boundedNumber, CapacityLimiter } from "../resource-control.mjs";
import { BoundedCache } from "./cache.mjs";
import { BackendHealth } from "./backend-health.mjs";
import { assertPublicUrl, extractDocument } from "./content.mjs";
import { crawlSite } from "./crawl.mjs";
import { InflightCoalescer } from "./inflight.mjs";
import { extractReaderDocument, readerRequestUrl } from "./reader.mjs";
import { executeSearch, normalizeSearch } from "./search.mjs";
import { LocalFileReader } from "../local-files.mjs";
import { textWindow } from "./text-window.mjs";
import { requestPublicResource, TRANSIENT_STATUS } from "./http-request.mjs";

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
    toolTimeoutMs: boundedNumber(
      env.ALTA_WEB_TOOL_TIMEOUT_MS,
      90_000,
      10_000,
      180_000,
    ),
    searchBackendTimeoutMs: boundedNumber(
      env.ALTA_SEARCH_BACKEND_TIMEOUT_MS,
      20_000,
      1_000,
      60_000,
    ),
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

export class InternetService {
  #lifecycle = new AbortController();

  constructor(options = {}) {
    const runtimeEnv = options.env ?? process.env;
    this.closed = false;
    this.settings = { ...settings(runtimeEnv), ...options.settings };
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.lookup = options.lookup;
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
    return requestPublicResource(this, url, options);
  }

  async fetchPage(
    {
      url,
      max_chars: maxChars = 24_000,
      reader = "auto",
      offset = 0,
      focus = "",
    } = {},
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
    textWindow("", { limit, offset, focus });
    const key = canonicalKey("fetch", {
      url,
      limit,
      readerMode,
      offset,
      focus,
    });
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
            sharedSignal.throwIfAborted();
            if (
              readerMode !== "auto" ||
              !this.settings.readerEnabled ||
              (error.code?.startsWith("alta_web_") &&
                error.code !== "alta_web_http_error")
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
          ...textWindow(document.text, { limit, offset, focus }),
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
            searchBackendTimeoutMs: this.settings.searchBackendTimeoutMs,
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
      query = "",
    } = {},
    { signal } = {},
  ) {
    if (typeof query !== "string" || query.length > 400)
      throw Object.assign(
        new Error("crawl query must be at most 400 characters"),
        {
          status: 400,
          code: "alta_web_invalid_query",
        },
      );
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
        query: query.trim(),
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

  get lifecycleSignal() {
    return this.#lifecycle.signal;
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.#lifecycle.abort(
      Object.assign(new Error("ALTA internet service is closed"), {
        status: 503,
        code: "alta_internet_closed",
      }),
    );
    this.limiter.close();
    this.inflight.close();
    this.cache.clear();
    this.fileReader?.close();
  }

  async #cached(key, signal, operation) {
    signal?.throwIfAborted();
    this.lifecycleSignal.throwIfAborted();
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
          sharedSignal?.throwIfAborted();
          this.lifecycleSignal.throwIfAborted();
          this.cache.set(key, value);
          return value;
        } catch (error) {
          if (
            stale &&
            !this.closed &&
            !sharedSignal?.aborted &&
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
