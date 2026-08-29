import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getJson, mutateRuntime } from "@/lib/api";
import {
  previewControl,
  previewEvents,
  previewRuntime,
  previewStatus,
} from "@/lib/preview";
import type {
  AltaEvent,
  ConsoleConnection,
  ControlState,
  MvpStatus,
  RuntimeDetail,
} from "@/lib/types";

type Bootstrap = ControlState & { csrfToken: string };

const LIVE_POLL_MS = 2_500;
const MAX_RETRY_MS = 30_000;
const CONSOLE_PROTOCOL_VERSION = 1;

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
  const mounted = useRef(true);
  const hasSnapshot = useRef(preview);

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
      setControl(nextControl);

      if (!nextControl.runtime.ready) {
        failures.current = 0;
        setConnection({
          status: "online",
          message: hasSnapshot.current
            ? "Runtime stopped — showing the last synchronized research snapshot."
            : null,
          lastSuccessfulAt: new Date().toISOString(),
          consecutiveFailures: 0,
          retryAt: null,
          stale: hasSnapshot.current,
        });
        return;
      }

      const [statusResult, runtimeResult] = await Promise.allSettled([
        getJson<MvpStatus>("/proxy/api/v1/mvp/status?limit=100", {
          signal: controller.signal,
        }),
        getJson<RuntimeDetail>("/proxy/api/v1/system/runtime", {
          signal: controller.signal,
        }),
      ]);
      const partialFailures: unknown[] = [];

      if (statusResult.status === "fulfilled") {
        const nextStatus = statusResult.value;
        if (nextStatus.eventCursor < cursor.current) {
          cursor.current = 0;
          historyExpanded.current = false;
          setEvents([]);
        }
        setStatus(nextStatus);
        hasSnapshot.current = true;
        if (cursor.current === 0) {
          cursor.current = Math.max(0, nextStatus.eventCursor - 100);
          setHasOlder(cursor.current > 0);
        }
        try {
          const page = await getJson<{ events: AltaEvent[] }>(
            `/proxy/api/v1/events?cursor=${cursor.current}&limit=100`,
            { signal: controller.signal },
          );
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
        setRuntime(runtimeResult.value);
        hasSnapshot.current = true;
      } else {
        partialFailures.push(runtimeResult.reason);
      }

      if (partialFailures.length) throw partialFailures[0];
      failures.current = 0;
      setConnection({
        status: "online",
        message: null,
        lastSuccessfulAt: new Date().toISOString(),
        consecutiveFailures: 0,
        retryAt: null,
        stale: false,
      });
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }, [preview]);

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
          enqueueRefresh(LIVE_POLL_MS);
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
            lastSuccessfulAt: current.lastSuccessfulAt,
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

  const controlRuntime = useCallback(
    async (action: "start" | "stop" | "restart") => {
      if (preview)
        throw new Error("Controls are disabled in synthetic preview");
      if (!csrfToken.current)
        throw new Error("The secure console session is not ready yet");
      try {
        await mutateRuntime(action, csrfToken.current);
      } catch (error) {
        if (!(error instanceof ApiError) || error.code !== "mutation_forbidden")
          throw error;
        const bootstrap = validateControl(
          await getJson<Bootstrap>("/control/bootstrap"),
        );
        csrfToken.current = bootstrap.csrfToken;
        consoleInstance.current = bootstrap.console.instanceId;
        setControl(bootstrap);
        await mutateRuntime(action, csrfToken.current);
      }
      queueRefresh();
    },
    [preview, queueRefresh],
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
    loadOlderEvents,
    loadingOlder,
    historyError,
    hasOlder,
  };
}
