import { redact } from "./providers.mjs";
import { retryDelayMs } from "./retry-policy.mjs";

const RETRYABLE = new Set([408, 409, 425, 429, 500, 502, 503, 504]);

export function isRetryableStatus(status) {
  return RETRYABLE.has(status);
}

async function boundedResponseText(response, maximum) {
  if (!response.body) return "";
  const chunks = [];
  let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > maximum) {
      await response.body.cancel().catch(() => {});
      const error = new Error(
        "Provider response exceeds the ALTA response limit",
      );
      error.retryable = false;
      throw error;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

export async function resilientJson(
  url,
  credential,
  body,
  providerName,
  signal,
  context,
  hooks = {},
) {
  const { maxRetries, retryBudgetMs, requestTimeoutMs, maxResponseBytes } =
    context.settings;
  const secrets = [credential];
  const serializedBody = JSON.stringify(body);
  const now = context.now ?? Date.now;
  const retryDeadline = now() + retryBudgetMs;
  const fetchImpl = context.fetchImpl ?? fetch;
  let lastError;
  let retryBudgetExhausted = false;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    let releaseAttempt;
    try {
      const remainingBudget = retryDeadline - now();
      if (attempt > 0 && remainingBudget <= 0) {
        retryBudgetExhausted = true;
        break;
      }
      await context.retryCoordinator.wait(
        providerName,
        signal,
        remainingBudget,
      );
      const remainingAfterBackoff = retryDeadline - now();
      if (attempt > 0 && remainingAfterBackoff <= 0) {
        retryBudgetExhausted = true;
        break;
      }
      let admissionBudgetSignal;
      if (hooks.acquireAttempt) {
        admissionBudgetSignal =
          attempt > 0
            ? (context.retryBudgetSignal?.(
                Math.max(1, remainingAfterBackoff),
              ) ?? AbortSignal.timeout(Math.max(1, remainingAfterBackoff)))
            : null;
        const admissionSignal = admissionBudgetSignal
          ? AbortSignal.any([signal, admissionBudgetSignal])
          : signal;
        try {
          releaseAttempt = await hooks.acquireAttempt(admissionSignal);
        } catch (error) {
          if (admissionBudgetSignal?.aborted && !signal.aborted) {
            retryBudgetExhausted = true;
            lastError = Object.assign(
              new Error("ALTA provider retry budget is exhausted"),
              {
                code: "alta_retry_budget_exhausted",
                retryable: false,
              },
            );
            break;
          }
          throw error;
        }
      }
      const admittedBudget = retryDeadline - now();
      if (attempt > 0 && admittedBudget <= 0) {
        retryBudgetExhausted = true;
        break;
      }
      const attemptTimeoutMs =
        attempt === 0
          ? requestTimeoutMs
          : Math.max(1, Math.min(requestTimeoutMs, admittedBudget));
      const timeoutSignal = context.timeoutSignal
        ? context.timeoutSignal(attemptTimeoutMs)
        : AbortSignal.timeout(attemptTimeoutMs);
      const attemptSignal = AbortSignal.any([signal, timeoutSignal]);
      const response = await fetchImpl(url, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${credential}`,
          "Content-Type": "application/json",
          "Accept": "application/json",
          "User-Agent": "ALTA-v3.5/1.0",
        },
        body: serializedBody,
        signal: attemptSignal,
      });
      const declaredSize = Number(response.headers.get("content-length") ?? 0);
      if (declaredSize > maxResponseBytes) {
        await response.body?.cancel().catch(() => {});
        const error = new Error(
          "Provider response exceeds the ALTA response limit",
        );
        error.retryable = false;
        throw error;
      }
      const text = await boundedResponseText(response, maxResponseBytes);
      if (!response.ok) {
        const error = new Error(
          `Provider HTTP ${response.status}: ${redact(text, secrets).slice(0, 1000)}`,
        );
        error.status = response.status;
        error.retryAfter = response.headers.get("retry-after");
        throw error;
      }
      let value;
      try {
        value = JSON.parse(text);
      } catch (cause) {
        const error = new Error("Provider response is not valid JSON", {
          cause,
        });
        error.retryable = false;
        throw error;
      }
      context.retryCoordinator.success(providerName);
      context.providerConcurrency?.success(providerName);
      return value;
    } catch (error) {
      if (signal.aborted) throw signal.reason ?? error;
      lastError = error;
      const retryable =
        error.retryable ?? (!error.status || isRetryableStatus(error.status));
      if (retryable && error.status === 429)
        context.providerConcurrency?.overload(providerName);
      if (!retryable || attempt >= maxRetries) break;
      const remainingBudget = retryDeadline - now();
      if (remainingBudget <= 0) {
        retryBudgetExhausted = true;
        break;
      }
      const delayMs = Math.min(
        retryDelayMs(attempt, error.retryAfter),
        remainingBudget,
      );
      context.retryCoordinator.defer(providerName, delayMs);
      context.metrics.retries += 1;
      hooks.onRetry?.(attempt + 1, error);
    } finally {
      releaseAttempt?.();
    }
  }
  const error = new Error(
    redact(lastError?.message ?? "Provider request failed", secrets),
  );
  error.status = lastError?.status;
  error.retryable = retryBudgetExhausted ? false : lastError?.retryable;
  error.code =
    lastError?.code ??
    (retryBudgetExhausted ? "alta_retry_budget_exhausted" : undefined);
  throw error;
}
