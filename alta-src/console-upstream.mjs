const DEFAULT_TIMEOUT_MS = 15_000;
const MAX_BODY_BYTES = 16 * 1024 * 1024;

function upstreamError(code, message, statusCode = 502) {
  return Object.assign(new Error(message), { code, statusCode });
}

async function boundedBody(response, maximumBytes) {
  const declared = Number(response.headers.get("content-length"));
  const oversized = () =>
    upstreamError(
      "upstream_response_too_large",
      "The research response exceeded the console safety limit.",
    );
  if (Number.isFinite(declared) && declared > maximumBytes) {
    await response.body?.cancel().catch(() => {});
    throw oversized();
  }
  if (!response.body) return Buffer.alloc(0);
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return Buffer.concat(chunks, length);
      const chunk = Buffer.from(value);
      length += chunk.length;
      if (length > maximumBytes) throw oversized();
      chunks.push(chunk);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
}

/** Bounded, cancellable loopback reads. Never expose fetch/driver diagnostics. */
export async function readConsoleUpstream(
  target,
  {
    headers,
    signal,
    fetchImpl = fetch,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    maximumBytes = MAX_BODY_BYTES,
  },
) {
  const controller = new AbortController();
  const abort = () =>
    controller.abort(
      upstreamError("upstream_cancelled", "The console request was cancelled."),
    );
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(
    () =>
      controller.abort(
        upstreamError(
          "upstream_timeout",
          "The research service did not respond before the timeout.",
          504,
        ),
      ),
    timeoutMs,
  );
  timer.unref?.();
  try {
    controller.signal.throwIfAborted();
    const response = await fetchImpl(target, {
      headers,
      signal: controller.signal,
    });
    const body = await boundedBody(response, maximumBytes);
    return { status: response.status, headers: response.headers, body };
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason;
    controller.abort();
    if (error?.code === "upstream_response_too_large") throw error;
    throw upstreamError(
      "upstream_unavailable",
      "The research service is temporarily unreachable.",
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
