import {
  ArrowUpRight,
  Bot,
  CircleDot,
  History,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, RuntimeDetail } from "@/lib/types";

/** A bounded snapshot, not a claim about profitability or the whole account. */
export function OperatingBrief({
  status,
  runtime,
  ready,
  stale,
  preview,
  onNavigate,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  ready: boolean;
  stale: boolean;
  preview: boolean;
  onNavigate: (view: "agents" | "shadow" | "ledger") => void;
}) {
  const { t, relative } = useI18n();
  const activeAgents = status.agents.filter(
    (agent) => agent.status === "running",
  ).length;
  const openPositions = status.shadowPositions.filter((position) =>
    ["open", "observing"].includes(position.status),
  ).length;
  const state = runtime?.config.autonomousStatus;
  const running = ready && !stale && state === "running";
  const title = !ready
    ? t("briefStopped")
    : stale
      ? t("briefStale")
      : running
        ? t("briefRunning")
        : state === "waiting"
          ? t("briefWaiting")
          : t("briefReady");
  const detail =
    !ready || stale
      ? t("briefSnapshotDetail")
      : running
        ? t("briefRunningDetail")
        : runtime?.config.nextCycleAt
          ? t("briefScheduledDetail", {
              time: relative(runtime.config.nextCycleAt),
            })
          : t("briefReadyDetail");

  return (
    <section className="operating-brief" aria-label={t("currentStatus")}>
      <div className="operating-summary">
        <CircleDot className={running ? "is-running" : ""} aria-hidden="true" />
        <div>
          <div className="operating-title">
            <strong>{title}</strong>
            {preview && (
              <span className="sample-label">{t("syntheticPreview")}</span>
            )}
          </div>
          <p>{detail}</p>
        </div>
      </div>
      <div className="operating-links">
        <Button variant="ghost" size="sm" onClick={() => onNavigate("agents")}>
          <Bot data-icon="inline-start" />
          {t("briefAgents", { count: activeAgents })}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onNavigate("shadow")}>
          <ShieldCheck data-icon="inline-start" />
          {t("briefPositions", { count: openPositions })}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onNavigate("ledger")}>
          <History data-icon="inline-start" />
          {t("viewHistory")}
          <ArrowUpRight data-icon="inline-end" />
        </Button>
      </div>
    </section>
  );
}
