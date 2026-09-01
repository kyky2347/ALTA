import { HeartPulse } from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { RuntimeDetail } from "@/lib/types";

export function RuntimeRecovery({
  runtime,
  fallbackStatus,
}: {
  runtime: RuntimeDetail | null;
  fallbackStatus: string;
}) {
  const { domain, number, relative, t } = useI18n();
  const config = runtime?.config;
  const posture = !runtime
    ? "waiting"
    : Number(config?.consecutiveFailures ?? 0) > 0
      ? "degraded"
      : (config?.autonomousStatus ?? fallbackStatus);

  return (
    <div className="overview-wide recovery-truth">
      <div className="overview-wide-head">
        <span>
          <HeartPulse /> {t("runtimeRecoveryTruth")}
        </span>
        <StatusPill status={String(posture)} />
      </div>
      <p className="research-operations-intro">
        {runtime
          ? t("runtimeRecoveryTruthDetail")
          : t("runtimeRecoveryWaiting")}
      </p>
      <div className="recovery-metrics">
        <div>
          <small>{t("autonomousStatus")}</small>
          <strong>
            {domain(String(config?.autonomousStatus ?? "waiting"))}
          </strong>
        </div>
        <div>
          <small>{t("lastCycleResult")}</small>
          <strong>
            {domain(String(config?.lastCycleResult ?? "unavailable"))}
          </strong>
        </div>
        <div>
          <small>{t("consecutiveFailures")}</small>
          <strong>{number(config?.consecutiveFailures ?? 0)}</strong>
        </div>
        <div>
          <small>{t("currentCycle")}</small>
          <strong>
            {String(config?.currentCycleId ?? t("noActiveCycle"))}
          </strong>
        </div>
        <div>
          <small>{t("lastHeartbeat")}</small>
          <strong>{relative(config?.lastHeartbeatAt)}</strong>
        </div>
        <div>
          <small>{t("nextResearchWindow")}</small>
          <strong>{relative(config?.nextCycleAt)}</strong>
        </div>
      </div>
    </div>
  );
}
