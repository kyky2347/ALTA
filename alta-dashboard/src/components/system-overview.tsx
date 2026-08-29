import {
  Activity,
  Bot,
  Database,
  FileSearch2,
  Radar,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";

export function SystemOverview({
  status,
  runtime,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  onSelect: (entity: SelectedEntity) => void;
}) {
  const { domain, relative, t } = useI18n();
  return (
    <section className="overview-grid">
      <OverviewBlock
        icon={FileSearch2}
        label={t("candidates")}
        value={status.candidates.length}
        detail={t("recentFoundryInputs")}
      />
      <OverviewBlock
        icon={Radar}
        label={t("opportunities")}
        value={status.opportunities.length}
        detail={t("deduplicatedTheses")}
      />
      <OverviewBlock
        icon={Bot}
        label={t("agentRoles")}
        value={status.agents.length}
        detail={t("persistentMinds", { count: runtime?.minds.length ?? 0 })}
      />
      <OverviewBlock
        icon={Waypoints}
        label={t("expressions")}
        value={status.expressions.length}
        detail={t("auditedCarriers")}
      />
      <OverviewBlock
        icon={ShieldCheck}
        label={t("shadowPositions")}
        value={status.shadowPositions.length}
        detail={t("capitalDisabled")}
      />
      <OverviewBlock
        icon={Database}
        label={t("eventCursor")}
        value={status.eventCursor}
        detail={t("appendOnlyLedger")}
      />
      <div className="overview-wide">
        <div className="overview-wide-head">
          <span>
            <Activity /> {t("sourcePosture")}
          </span>
          <StatusPill status={status.sources.length ? "observed" : "waiting"} />
        </div>
        <div className="source-list">
          {status.sources.slice(0, 5).map((source) => (
            <div key={source.id}>
              <strong>{domain(source.id)}</strong>
              <span>
                {domain(String(source.posture ?? source.status ?? "recorded"))}
              </span>
              <small>{relative(source.knownAt)}</small>
            </div>
          ))}
          {!status.sources.length && <p>{t("noSourcePosture")}</p>}
        </div>
      </div>
      <div className="overview-wide">
        <div className="overview-wide-head">
          <span>
            <Bot /> {t("traderMinds")}
          </span>
          <StatusPill
            status={t("minds", { count: runtime?.minds.length ?? 0 })}
          />
        </div>
        <div className="mind-list">
          {runtime?.minds.slice(0, 4).map((mind) => (
            <button
              key={mind.id}
              onClick={() =>
                onSelect({
                  kind: "event",
                  id: mind.id,
                  label: domain(mind.id),
                  summary: mind as unknown as Record<string, unknown>,
                })
              }
            >
              <strong>{domain(mind.id)}</strong>
              <span>{mind.rollingSummary ?? t("noRollingSummarySaved")}</span>
              <small>
                {mind.modelId ?? mind.modelProvider ?? t("modelPending")}
              </small>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function OverviewBlock({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  detail: string;
}) {
  const { number } = useI18n();
  return (
    <article className="overview-block">
      <span>
        <Icon />
      </span>
      <div>
        <small>{label}</small>
        <strong>{number(value)}</strong>
        <p>{detail}</p>
      </div>
    </article>
  );
}
