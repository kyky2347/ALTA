import type { RuntimeDetail } from "./types";

/** Disabled scheduling is a known operator state, not a failed status fetch. */
export function runtimeSchedule(
  ready: boolean,
  hasSnapshot: boolean,
  runtime: RuntimeDetail | null,
) {
  if (!ready && hasSnapshot) return { key: "savedSnapshot" } as const;
  const config = runtime?.config;
  if (config?.autonomousStatus === "disabled")
    return { key: "scheduleDisabled" } as const;
  if (config?.autonomousStatus === "running")
    return { key: "cycleInProgress" } as const;
  if (config?.nextCycleAt)
    return { key: "nextCycle", at: config.nextCycleAt } as const;
  return { key: "scheduleUnavailable" } as const;
}
