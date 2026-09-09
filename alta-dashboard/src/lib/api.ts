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
  const timer = globalThis.setTimeout(
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
      globalThis.clearTimeout(timer);
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
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      if (bounded.signal.aborted) throw bounded.signal.reason;
      if (response.ok)
        throw new ApiError({
          message:
            "The local service returned an invalid response. The last valid snapshot is preserved; ALTA will retry.",
          code: "invalid_response",
          status: response.status,
          retriable: true,
        });
      payload = null;
    }
    if (!response.ok) {
      const detail =
        isRecord(payload) && isRecord(payload.error) ? payload.error : {};
      const code =
        typeof detail.code === "string"
          ? detail.code
          : `http_${response.status}`;
      const message =
        typeof detail.message === "string" ? detail.message : code;
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
    if (!isRecord(payload) || !validConsolePayload(path, payload.data))
      throw new ApiError({
        message:
          "The local service returned an invalid response. The last valid snapshot is preserved; ALTA will retry.",
        code: "invalid_response",
        status: response.status,
        retriable: true,
      });
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

export function replaceCredential(
  slot: string,
  secret: string,
  csrfToken: string,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<import("@/lib/types").CredentialInventory>(
    `/control/credentials/${encodeURIComponent(slot)}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-ALTA-CSRF": csrfToken,
      },
      body: JSON.stringify({ secret }),
    },
    options,
  );
}

export function verifyCredentialHealth(
  csrfToken: string,
  force = false,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<import("@/lib/types").CredentialInventory>(
    `/control/credentials/verify${force ? "?force=1" : ""}`,
    {
      method: "POST",
      headers: { "X-ALTA-CSRF": csrfToken },
    },
    { timeoutMs: 60_000, ...options },
  );
}

export function refreshPaperCapital(
  csrfToken: string,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<import("@/lib/types").PaperCapitalStatus>(
    "/control/capital/refresh",
    {
      method: "POST",
      headers: { "X-ALTA-CSRF": csrfToken },
    },
    { timeoutMs: 60_000, ...options },
  );
}

export function setPaperCapitalAuthorization(
  enabled: boolean,
  csrfToken: string,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
) {
  return requestJson<import("@/lib/types").PaperCapitalStatus>(
    "/control/capital/authorization",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-ALTA-CSRF": csrfToken,
      },
      body: JSON.stringify({
        enabled,
        confirmation: enabled ? "ENABLE TIGER PAPER" : "DISABLE TIGER PAPER",
      }),
    },
    { timeoutMs: 60_000, ...options },
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
import { isRecord, validConsolePayload } from "./response-contract.ts";
