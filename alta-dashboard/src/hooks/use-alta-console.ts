import { useCallback, useEffect, useRef, useState } from "react";
import { SnapshotFence } from "@/lib/snapshot-fence";
import {
  ApiError,
  getJson,
  mutateRuntime,
  refreshPaperCapital,
  replaceCredential,
  setPaperCapitalAuthorization,
  verifyCredentialHealth,
} from "@/lib/api";
import {
  previewCapital,
  previewControl,
  previewCredentials,
  previewEvents,
  previewRuntime,
  previewStatus,
} from "@/lib/preview";
import type {
  AltaEvent,
  ConsoleConnection,
  ControlState,
  CredentialInventory,
  MvpStatus,
  PaperCapitalStatus,
  RuntimeDetail,
} from "@/lib/types";

type Bootstrap = ControlState & { csrfToken: string };

const LIVE_POLL_MS = 2_500;
const OPERATION_POLL_MS = 1_000;
const BACKGROUND_POLL_MS = 15_000;
const AUXILIARY_POLL_MS = 30_000;
const AUXILIARY_TIMEOUT_MS = 5_000;
const MAX_RETRY_MS = 30_000;
const CONSOLE_PROTOCOL_VERSION = 4;

function retryDelay(failures: number) {
  const base = Math.min(
    LIVE_POLL_MS * 2 ** Math.max(0, failures - 1),
    MAX_RETRY_MS,
  );
  return Math.round(base * (0.85 + Math.random() * 0.3));
}

function messageFor(error: unknown) {
  return error instanceof Error
    ? error.message
    : "The local operator service is temporarily unreachable.";
}

function stableJson(value: unknown) {
  return JSON.stringify(value);
}

function controlSignature(control: ControlState) {
  return stableJson({
    ...control,
    console: { ...control.console, uptimeSeconds: 0 },
  });
}

function validateControl<T extends ControlState>(control: T): T {
  if (control.console?.protocolVersion !== CONSOLE_PROTOCOL_VERSION)
    throw new ApiError({
      message:
        "The dashboard build and local operator service use different protocol versions. Rebuild the dashboard and restart the console.",
      code: "console_protocol_mismatch",
      retriable: false,
    });
  return control;
}

function mergeEvents(
  current: AltaEvent[],
  incoming: AltaEvent[],
  expanded: boolean,
) {
  const byId = new Map(
    [...current, ...incoming].map((event) => [event.eventId, event]),
  );
  const ordered = [...byId.values()].sort((a, b) => b.cursor - a.cursor);
  return expanded ? ordered : ordered.slice(0, 1_000);
}

export function useAltaConsole() {
  const preview =
    new URLSearchParams(window.location.search).get("preview") === "1";
  const [control, setControl] = useState<ControlState | null>(
    preview ? previewControl : null,
  );
  const [status, setStatus] = useState<MvpStatus | null>(
    preview ? previewStatus : null,
  );
  const [runtime, setRuntime] = useState<RuntimeDetail | null>(
    preview ? previewRuntime : null,
  );
  const [events, setEvents] = useState<AltaEvent[]>(
    preview ? previewEvents : [],
  );
  const [credentials, setCredentials] = useState<CredentialInventory | null>(
    preview ? previewCredentials : null,
  );
  const [credentialsError, setCredentialsError] = useState<string | null>(null);
  const [capital, setCapital] = useState<PaperCapitalStatus | null>(
    preview ? previewCapital : null,
  );
  const [capitalError, setCapitalError] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConsoleConnection>({
    status: preview ? "online" : "connecting",
    message: null,
    lastSuccessfulAt: preview ? new Date().toISOString() : null,
    consecutiveFailures: 0,
    retryAt: null,
    stale: false,
  });
  const [loading, setLoading] = useState(!preview);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [hasOlder, setHasOlder] = useState(true);
  const cursor = useRef(0);
  const historyExpanded = useRef(false);
  const csrfToken = useRef(preview ? "preview" : "");
  const consoleInstance = useRef(
    preview ? previewControl.console.instanceId : "",
  );
  const inFlight = useRef<Promise<void> | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const schedule = useRef<number | null>(null);
  const failures = useRef(0);
  const nextPollDelay = useRef(LIVE_POLL_MS);
  const lastSuccessfulAt = useRef<string | null>(
    preview ? new Date().toISOString() : null,
  );
  const lastControlSignature = useRef(
    preview ? controlSignature(previewControl) : "",
  );
  const lastRuntimeSignature = useRef(
    preview ? stableJson(previewRuntime) : "",
  );
  const lastStatusSignature = useRef(preview ? stableJson(previewStatus) : "");
  const mounted = useRef(true);
  const hasSnapshot = useRef(preview);
  const credentialsNextPollAt = useRef(preview ? Number.POSITIVE_INFINITY : 0);
  const capitalNextPollAt = useRef(preview ? Number.POSITIVE_INFINITY : 0);
  const credentialFence = useRef(new SnapshotFence());
  const capitalFence = useRef(new SnapshotFence());

  const publishCredentials = useCallback((next: CredentialInventory) => {
    credentialFence.current.invalidate();
    if (!mounted.current) return;
    setCredentials(next);
    setCredentialsError(null);
    credentialsNextPollAt.current = Date.now() + AUXILIARY_POLL_MS;
  }, []);

  const publishCapital = useCallback((next: PaperCapitalStatus) => {
    capitalFence.current.invalidate();
    if (!mounted.current) return;
    setCapital(next);
    setCapitalError(null);
    capitalNextPollAt.current = Date.now() + AUXILIARY_POLL_MS;
  }, []);

  const markConnected = useCallback(
    (message: string | null, stale: boolean) => {
      failures.current = 0;
      lastSuccessfulAt.current = new Date().toISOString();
      setConnection((current) => {
        if (
          current.status === "online" &&
          current.message === message &&
          current.consecutiveFailures === 0 &&
          current.retryAt === null &&
          current.stale === stale
        )
          return current;
        return {
          status: "online",
          message,
          lastSuccessfulAt: lastSuccessfulAt.current,
          consecutiveFailures: 0,
          retryAt: null,
          stale,
        };
      });
    },
    [],
  );

  const performRefresh = useCallback(async () => {
    if (preview) return;
    if (!navigator.onLine)
      throw new ApiError({
        message: "This device is offline. ALTA will reconnect automatically.",
        code: "browser_offline",
        retriable: true,
      });

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const auxiliaryRequests: Promise<void>[] = [];
    try {
      let nextControl: ControlState;
      if (!csrfToken.current) {
        const bootstrap = validateControl(
          await getJson<Bootstrap>("/control/bootstrap", {
            signal: controller.signal,
          }),
        );
        csrfToken.current = bootstrap.csrfToken;
        consoleInstance.current = bootstrap.console.instanceId;
        nextControl = bootstrap;
      } else {
        nextControl = validateControl(
          await getJson<ControlState>("/control/state", {
            signal: controller.signal,
          }),
        );
        if (nextControl.console.instanceId !== consoleInstance.current) {
          const bootstrap = validateControl(
            await getJson<Bootstrap>("/control/bootstrap", {
              signal: controller.signal,
            }),
          );
          csrfToken.current = bootstrap.csrfToken;
          consoleInstance.current = bootstrap.console.instanceId;
          nextControl = bootstrap;
        }
      }
      if (!mounted.current) return;
      const nextControlSignature = controlSignature(nextControl);
      if (nextControlSignature !== lastControlSignature.current) {
        lastControlSignature.current = nextControlSignature;
        setControl(nextControl);
      }
      nextPollDelay.current =
        document.visibilityState === "hidden"
          ? BACKGROUND_POLL_MS
          : nextControl.operation?.status === "running"
            ? OPERATION_POLL_MS
            : LIVE_POLL_MS;
      const auxiliaryNow = Date.now();
      if (auxiliaryNow >= credentialsNextPollAt.current) {
        const revision = credentialFence.current.begin();
        credentialsNextPollAt.current = auxiliaryNow + AUXILIARY_POLL_MS;
        auxiliaryRequests.push(
          getJson<CredentialInventory>("/control/credentials", {
            signal: controller.signal,
            timeoutMs: AUXILIARY_TIMEOUT_MS,
          })
            .then((nextCredentials) => {
              if (
                !mounted.current ||
                !credentialFence.current.accepts(revision)
              )
                return;
              setCredentials(nextCredentials);
              setCredentialsError(null);
            })
            .catch((error: unknown) => {
              if (
                !mounted.current ||
                !credentialFence.current.accepts(revision)
              )
                return;
              setCredentialsError(messageFor(error));
            }),
        );
      }
      if (auxiliaryNow >= capitalNextPollAt.current) {
        const revision = capitalFence.current.begin();
        capitalNextPollAt.current = auxiliaryNow + AUXILIARY_POLL_MS;
        auxiliaryRequests.push(
          getJson<PaperCapitalStatus>("/control/capital", {
            signal: controller.signal,
            timeoutMs: AUXILIARY_TIMEOUT_MS,
          })
            .then((nextCapital) => {
              if (!mounted.current || !capitalFence.current.accepts(revision))
                return;
              setCapital(nextCapital);
              setCapitalError(null);
            })
            .catch((error: unknown) => {
              if (!mounted.current || !capitalFence.current.accepts(revision))
                return;
              setCapitalError(messageFor(error));
            }),
        );
      }

      if (!nextControl.runtime.ready) {
        markConnected(
          hasSnapshot.current
            ? "Runtime stopped — showing the last synchronized research snapshot."
            : null,
          hasSnapshot.current,
        );
        return;
      }

      const requestedEventCursor = cursor.current;
      const eventRequest =
        requestedEventCursor > 0
          ? getJson<{ events: AltaEvent[] }>(
              `/proxy/api/v1/events?cursor=${requestedEventCursor}&limit=100`,
              { signal: controller.signal },
            )
          : Promise.resolve(null);
      const [statusResult, runtimeResult, eventResult] =
        await Promise.allSettled([
          getJson<MvpStatus>("/proxy/api/v1/mvp/status?limit=100", {
            signal: controller.signal,
          }),
          getJson<RuntimeDetail>("/proxy/api/v1/system/runtime", {
            signal: controller.signal,
          }),
          eventRequest,
        ]);
      const partialFailures: unknown[] = [];

      if (statusResult.status === "fulfilled") {
        const nextStatus = statusResult.value;
        let reloadEvents = false;
        if (nextStatus.eventCursor < cursor.current) {
          cursor.current = 0;
          historyExpanded.current = false;
          setEvents([]);
          reloadEvents = true;
        }
        // Freshness can change with wall time without appending an event.
        const signature = stableJson(nextStatus);
        if (signature !== lastStatusSignature.current) {
          lastStatusSignature.current = signature;
          setStatus(nextStatus);
        }
        hasSnapshot.current = true;
        if (cursor.current === 0) {
          cursor.current = Math.max(0, nextStatus.eventCursor - 100);
          setHasOlder(cursor.current > 0);
          reloadEvents = true;
        }
        try {
          const page =
            reloadEvents || eventResult.status !== "fulfilled"
              ? await getJson<{ events: AltaEvent[] }>(
                  `/proxy/api/v1/events?cursor=${cursor.current}&limit=100`,
                  { signal: controller.signal },
                )
              : eventResult.value;
          if (!page)
            throw new Error("Event synchronization was not initialized");
          if (page.events.length) {
            cursor.current = page.events.at(-1)?.cursor ?? cursor.current;
            setEvents((current) =>
              mergeEvents(current, page.events, historyExpanded.current),
            );
          }
        } catch (error) {
          partialFailures.push(error);
        }
      } else {
        partialFailures.push(statusResult.reason);
      }

      if (runtimeResult.status === "fulfilled") {
        const nextRuntimeSignature = stableJson(runtimeResult.value);
        if (nextRuntimeSignature !== lastRuntimeSignature.current) {
          lastRuntimeSignature.current = nextRuntimeSignature;
          setRuntime(runtimeResult.value);
        }
        hasSnapshot.current = true;
      } else {
        partialFailures.push(runtimeResult.reason);
      }

      if (partialFailures.length) throw partialFailures[0];
      markConnected(null, false);
    } finally {
      // Render core health/research first; optional provider views must not
      // serialize or block it. Keep requests bounded and abortable on unmount.
      if (mounted.current) setLoading(false);
      await Promise.allSettled(auxiliaryRequests);
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }, [markConnected, preview]);

  const refreshData = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const request = performRefresh().finally(() => {
      if (inFlight.current === request) inFlight.current = null;
    });
    inFlight.current = request;
    return request;
  }, [performRefresh]);

  const queueRefresh = useCallback(
    function enqueueRefresh(delay = 0) {
      if (preview || !mounted.current) return;
      if (schedule.current !== null) window.clearTimeout(schedule.current);
      schedule.current = window.setTimeout(async () => {
        schedule.current = null;
        try {
          await refreshData();
          if (!mounted.current) return;
          setLoading(false);
          enqueueRefresh(nextPollDelay.current);
        } catch (error) {
          if (!mounted.current) return;
          setLoading(false);
          const apiError = error instanceof ApiError ? error : null;
          if (apiError?.code === "console_unauthorized") {
            setConnection((current) => ({
              ...current,
              status: "unauthorized",
              message: apiError.message,
              retryAt: null,
              stale: hasSnapshot.current,
            }));
            return;
          }
          if (apiError?.code === "console_protocol_mismatch") {
            setConnection((current) => ({
              ...current,
              status: "incompatible",
              message: apiError.message,
              retryAt: null,
              stale: hasSnapshot.current,
            }));
            return;
          }
          failures.current += 1;
          const delayMs = retryDelay(failures.current);
          setConnection((current) => ({
            status: hasSnapshot.current ? "degraded" : "offline",
            message: messageFor(error),
            lastSuccessfulAt:
              lastSuccessfulAt.current ?? current.lastSuccessfulAt,
            consecutiveFailures: failures.current,
            retryAt: new Date(Date.now() + delayMs).toISOString(),
            stale: hasSnapshot.current,
          }));
          enqueueRefresh(delayMs);
        }
      }, delay);
    },
    [preview, refreshData],
  );

  useEffect(() => {
    if (preview) return;
    mounted.current = true;
    queueRefresh();
    const resume = () => {
      if (document.visibilityState === "visible" && navigator.onLine)
        queueRefresh();
    };
    const offline = () => {
      activeRequest.current?.abort();
      setConnection((current) => ({
        ...current,
        status: hasSnapshot.current ? "degraded" : "offline",
        message: "This device is offline. ALTA will reconnect automatically.",
        stale: hasSnapshot.current,
      }));
    };
    window.addEventListener("online", resume);
    window.addEventListener("focus", resume);
    window.addEventListener("offline", offline);
    document.addEventListener("visibilitychange", resume);
    return () => {
      mounted.current = false;
      activeRequest.current?.abort();
      if (schedule.current !== null) window.clearTimeout(schedule.current);
      window.removeEventListener("online", resume);
      window.removeEventListener("focus", resume);
      window.removeEventListener("offline", offline);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [preview, queueRefresh]);

  const retryNow = useCallback(() => {
    failures.current = 0;
    setConnection((current) => ({
      ...current,
      status:
        current.status === "unauthorized" || current.status === "incompatible"
          ? current.status
          : "connecting",
      retryAt: null,
    }));
    if (
      connection.status !== "unauthorized" &&
      connection.status !== "incompatible"
    )
      queueRefresh();
  }, [connection.status, queueRefresh]);

  // Only a definitive pre-execution CSRF rejection may be retried. Timeouts
  // and uncertain mutation outcomes must never trigger an automatic replay.
  const runSecureMutation = useCallback(
    async <T>(request: (token: string) => Promise<T>): Promise<T> => {
      if (preview)
        throw new Error("Controls are disabled in synthetic preview");
      if (!csrfToken.current)
        throw new Error("The secure console session is not ready yet");
      try {
        return await request(csrfToken.current);
      } catch (error) {
        if (!(error instanceof ApiError) || error.code !== "mutation_forbidden")
          throw error;
        const bootstrap = validateControl(
          await getJson<Bootstrap>("/control/bootstrap"),
        );
        csrfToken.current = bootstrap.csrfToken;
        consoleInstance.current = bootstrap.console.instanceId;
        if (mounted.current) setControl(bootstrap);
        return request(csrfToken.current);
      }
    },
    [preview],
  );

  const controlRuntime = useCallback(
    async (action: "start" | "stop" | "restart") => {
      await runSecureMutation((token) => mutateRuntime(action, token));
      queueRefresh();
    },
    [runSecureMutation, queueRefresh],
  );

  const refreshCredentials = useCallback(async () => {
    if (preview) return;
    const revision = credentialFence.current.begin();
    const next = await getJson<CredentialInventory>("/control/credentials");
    if (credentialFence.current.accepts(revision)) publishCredentials(next);
  }, [preview, publishCredentials]);

  const verifyCredentials = useCallback(
    async (force = false) => {
      const next = await runSecureMutation((token) =>
        verifyCredentialHealth(token, force),
      );
      publishCredentials(next);
    },
    [runSecureMutation, publishCredentials],
  );

  const loadCapital = useCallback(async () => {
    if (preview) return;
    const revision = capitalFence.current.begin();
    const next = await getJson<PaperCapitalStatus>("/control/capital");
    if (capitalFence.current.accepts(revision)) publishCapital(next);
  }, [preview, publishCapital]);

  const refreshCapital = useCallback(async () => {
    const next = await runSecureMutation((token) => refreshPaperCapital(token));
    publishCapital(next);
  }, [runSecureMutation, publishCapital]);

  const setCapitalAuthorization = useCallback(
    async (enabled: boolean) => {
      const next = await runSecureMutation((token) =>
        setPaperCapitalAuthorization(enabled, token),
      );
      publishCapital(next);
      queueRefresh();
    },
    [runSecureMutation, publishCapital, queueRefresh],
  );

  const setProviderCredential = useCallback(
    async (slot: string, secret: string) => {
      const next = await runSecureMutation((token) =>
        replaceCredential(slot, secret, token),
      );
      publishCredentials(next);
    },
    [runSecureMutation, publishCredentials],
  );

  const loadOlderEvents = useCallback(async () => {
    if (preview || loadingOlder || !events.length) return;
    setLoadingOlder(true);
    setHistoryError(null);
    try {
      const before = Math.min(...events.map((event) => event.cursor));
      const page = await getJson<{ events: AltaEvent[] }>(
        `/proxy/api/v1/events?before=${before}&limit=100`,
      );
      setHasOlder(page.events.length === 100);
      historyExpanded.current = true;
      setEvents((current) => mergeEvents(current, page.events, true));
    } catch (error) {
      setHistoryError(messageFor(error));
    } finally {
      setLoadingOlder(false);
    }
  }, [events, loadingOlder, preview]);

  return {
    preview,
    control,
    status,
    runtime,
    credentials,
    credentialsError,
    capital,
    capitalError,
    events,
    connection,
    error:
      connection.status === "unauthorized" ||
      connection.status === "incompatible"
        ? connection.message
        : null,
    loading,
    refreshData,
    retryNow,
    controlRuntime,
    refreshCredentials,
    verifyCredentials,
    setProviderCredential,
    loadCapital,
    refreshCapital,
    setCapitalAuthorization,
    loadOlderEvents,
    loadingOlder,
    historyError,
    hasOlder,
  };
}
