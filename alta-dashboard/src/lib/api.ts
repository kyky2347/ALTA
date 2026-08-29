const DEFAULT_TIMEOUT_MS = 12_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly retriable: boolean;

  constructor({
    message,
    code,
    status = null,
    retriable,
  }: {
    message: string;
    code: string;
    status?: number | null;
    retriable: boolean;
  }) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retriable = retriable;
  }
}

function timeoutSignal(parent?: AbortSignal, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = window.setTimeout(
    () =>
      controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs,
  );
  const abort = () => controller.abort(parent?.reason);
  if (parent?.aborted) abort();
  else parent?.addEventListener("abort", abort, { once: true });
  return {
    signal: controller.signal,
    dispose() {
      window.clearTimeout(timer);
      parent?.removeEventListener("abort", abort);
    },
  };
}

function failure(error: unknown) {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError")
    return new ApiError({
      message: "The request was cancelled.",
      code: "request_cancelled",
      retriable: true,
    });
  if (error instanceof DOMException && error.name === "TimeoutError")
    return new ApiError({
      message: "The local service did not respond before the timeout.",
      code: "request_timeout",
      retriable: true,
    });
  return new ApiError({
    message: "The local operator service is temporarily unreachable.",
    code: "network_unavailable",
    retriable: true,
  });
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  { signal, timeoutMs }: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  const bounded = timeoutSignal(signal, timeoutMs);
  try {
    const response = await fetch(path, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json", ...init.headers },
      signal: bounded.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = payload?.error?.code ?? `http_${response.status}`;
      const message =
        payload?.error?.message ??
        payload?.error?.code ??
        `HTTP ${response.status}`;
      throw new ApiError({
        message,
        code,
        status: response.status,
        retriable:
          response.status === 408 ||
          response.status === 425 ||
          response.status === 429 ||
          response.status >= 500,
      });
    }
    return payload.data as T;
  } catch (error) {
    throw failure(error);
  } finally {
    bounded.dispose();
  }
}

export function getJson<T>(
  path: string,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<T>(path, {}, options);
}

export function mutateRuntime(
  action: "start" | "stop" | "restart",
  csrfToken: string,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<{ accepted: true; action: string }>(
    `/control/runtime/${action}`,
    {
      method: "POST",
      headers: { "X-ALTA-CSRF": csrfToken },
    },
    options,
  );
}

export function entityDetailPath(kind: string, id: string) {
  if (kind === "opportunity")
    return `/proxy/api/v1/opportunities/${encodeURIComponent(id)}`;
  if (kind === "run") return `/proxy/api/v1/runs/${encodeURIComponent(id)}`;
  if (kind === "expression")
    return `/proxy/api/v1/expressions/${encodeURIComponent(id)}`;
  return null;
}
