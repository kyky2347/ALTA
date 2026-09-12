import { sleep } from "../resource-control.mjs";
import { assertAutomatedSitePolicy, assertPublicUrl } from "./content.mjs";
import { withDeadline } from "./deadline.mjs";

export const TRANSIENT_STATUS = new Set([
  408, 409, 425, 429, 500, 502, 503, 504,
]);
const USER_AGENT = "ALTABot/3.5 (research-only local operator)";
const REDIRECT_STATUS = new Set([301, 302, 303, 307, 308]);

function retryDelay(attempt, value) {
  const seconds = value == null ? NaN : Number(value);
  const date = Number.isNaN(seconds) && value ? Date.parse(value) : NaN;
  if (Number.isFinite(seconds) && seconds >= 0)
    return Math.min(seconds * 1_000, 30_000);
  if (Number.isFinite(date))
    return Math.min(Math.max(0, date - Date.now()), 30_000);
  return Math.min(500 * 2 ** attempt, 10_000) + Math.floor(Math.random() * 250);
}

async function cancelBody(response) {
  await response.body?.cancel().catch(() => {});
}

async function boundedBody(response, maximum, signal) {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const cancel = () => {
    void reader.cancel(signal.reason).catch(() => {});
  };
  signal.addEventListener("abort", cancel, { once: true });
  const chunks = [];
  let bytes = 0;
  try {
    signal.throwIfAborted();
    while (true) {
      const { value, done } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      bytes += value.length;
      if (bytes > maximum) {
        await reader.cancel().catch(() => {});
        throw Object.assign(
          new Error("Web response exceeds the ALTA download limit"),
          {
            status: 413,
            code: "alta_web_download_too_large",
          },
        );
      }
      chunks.push(value);
    }
    return Buffer.concat(chunks).toString("utf8");
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}

async function resolveTarget(service, value, options) {
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
    lookup: service.lookup,
    allowProxyFakeIp: service.settings.allowProxyFakeIp,
  });
}

async function requestLoop(service, url, options) {
  const { signal } = options;
  let current = await resolveTarget(service, url, options);
  let headers = { ...options.headers };
  const method = options.method ?? "GET";
  const parsedAttempts = Number(options.attempts ?? 4);
  const attempts = Number.isFinite(parsedAttempts)
    ? Math.max(1, Math.min(4, Math.trunc(parsedAttempts)))
    : 4;
  for (let redirect = 0; redirect <= 5; redirect += 1) {
    signal.throwIfAborted();
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const release = await service.limiter.acquire(signal);
      let lastError;
      try {
        const result = await withDeadline(
          { signal },
          0,
          async ({ signal: requestSignal }) => {
            const response = await service.fetchImpl(current, {
              method,
              headers: {
                "User-Agent": USER_AGENT,
                "Accept":
                  options.accept ??
                  "text/html,application/json,text/plain;q=0.9,*/*;q=0.2",
                ...headers,
              },
              body: options.body,
              redirect: "manual",
              signal: requestSignal,
            });
            if (requestSignal.aborted) {
              await cancelBody(response);
              requestSignal.throwIfAborted();
            }
            if (REDIRECT_STATUS.has(response.status)) {
              const location = response.headers.get("location");
              await cancelBody(response);
              if (!location)
                throw Object.assign(
                  new Error("Redirect is missing a Location header"),
                  { status: 502 },
                );
              const next = await resolveTarget(
                service,
                new URL(location, current).href,
                options,
              );
              requestSignal.throwIfAborted();
              if (next.origin !== current.origin) {
                if (
                  !["GET", "HEAD"].includes(method.toUpperCase()) ||
                  options.body != null
                )
                  throw Object.assign(
                    new Error("Cross-origin request-body redirect is blocked"),
                    { status: 403, code: "alta_web_unsafe_redirect" },
                  );
                // A page or reader service cannot forward operator credentials to another origin.
                headers = {};
              }
              return { redirect: next };
            }
            if (!response.ok) {
              const retryAfter = response.headers.get("retry-after");
              await cancelBody(response);
              // Never echo provider response bodies, which can include credentials.
              throw Object.assign(new Error(`Web HTTP ${response.status}`), {
                status: response.status,
                retryAfter,
                code: "alta_web_http_error",
              });
            }
            const body = await boundedBody(
              response,
              options.maximum ?? service.settings.maxDownloadBytes,
              requestSignal,
            );
            return {
              body,
              contentType: response.headers.get("content-type") ?? "",
              url: current.href,
              status: response.status,
            };
          },
        );
        if (result.redirect) {
          current = result.redirect;
          break;
        }
        return result;
      } catch (error) {
        signal.throwIfAborted();
        lastError = error;
        if (
          attempt === attempts - 1 ||
          (error.status && !TRANSIENT_STATUS.has(error.status))
        )
          throw error;
      } finally {
        release();
      }
      await sleep(retryDelay(attempt, lastError.retryAfter), signal);
    }
  }
  throw Object.assign(new Error("Web request exceeded the redirect limit"), {
    status: 508,
    code: "alta_web_redirect_limit",
  });
}

export function requestPublicResource(service, url, options = {}) {
  const signals = [options.signal, service.lifecycleSignal].filter(Boolean);
  return withDeadline(
    {
      ...options,
      signal: signals.length ? AbortSignal.any(signals) : undefined,
    },
    service.settings.timeoutMs,
    (bounded) => requestLoop(service, url, bounded),
    { label: "web request", code: "alta_web_request_deadline" },
  );
}
