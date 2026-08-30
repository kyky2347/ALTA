import {
  Activity,
  Bot,
  Database,
  FileSearch2,
  Focus,
  Radar,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";
import { readableMindSummary } from "@/lib/utils";

export function SystemOverview({
  status,
  runtime,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  onSelect: (entity: SelectedEntity) => void;
}) {
  const { domain, number, relative, t } = useI18n();
  const attention = runtime?.researchAttention;
  const percent = (value?: string | null) => {
    const parsed = value === null || value === undefined ? NaN : Number(value);
    return Number.isFinite(parsed)
      ? number(parsed, { style: "percent", maximumFractionDigits: 1 })
      : t("unavailable");
  };
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
      <div className="overview-wide attention-portfolio">
        <div className="overview-wide-head">
          <span>
            <Focus /> {t("researchAttention")}
          </span>
          <StatusPill status={attention?.posture ?? "waiting"} />
        </div>
        <p className="attention-intro">
          {attention
            ? t("researchAttentionDetail")
            : t("researchAttentionWaiting")}
        </p>
        {attention ? (
          <>
            <div className="attention-metrics">
              <div>
                <small>{t("candidateSample")}</small>
                <strong>{number(attention.sampleSize)}</strong>
              </div>
              <div>
                <small>{t("uniqueEntities")}</small>
                <strong>{number(attention.uniqueEntities)}</strong>
              </div>
              <div>
                <small>{t("topEntityShare")}</small>
                <strong>{percent(attention.topEntityShare)}</strong>
              </div>
              <div>
                <small>{t("effectiveBreadth")}</small>
                <strong>
                  {attention.effectiveBreadth ?? t("unavailable")}
                </strong>
              </div>
            </div>
            <div className="attention-seat-list">
              {(attention.assignments ?? []).map((assignment) => {
                const entity =
                  assignment.deprioritizedEntities[0] ??
                  attention.topEntity ??
                  t("noDominantEntity");
                const directive =
                  assignment.mode === "continue_lead"
                    ? t("continueLeadDetail", { entity })
                    : assignment.mode === "expand_coverage"
                      ? t("expandCoverageDetail", { entity })
                      : t("unconstrainedDetail");
                return (
                  <button
                    key={assignment.scoutId}
                    type="button"
                    onClick={() =>
                      onSelect({
                        kind: "event",
                        id: `research-attention:${assignment.scoutId}`,
                        label: `${domain(assignment.scoutId)} · ${domain(assignment.mode)}`,
                        summary: {
                          ...assignment,
                          posture: attention.posture,
                          sampleSize: attention.sampleSize,
                          topEntity: attention.topEntity,
                          topEntityShare: attention.topEntityShare,
                          effectiveBreadth: attention.effectiveBreadth,
                          knownAt: attention.knownAt,
                        },
                      })
                    }
                  >
                    <span className={`attention-mode is-${assignment.mode}`} />
                    <span>
                      <strong>{domain(assignment.scoutId)}</strong>
                      <small>{domain(assignment.mode)}</small>
                    </span>
                    <p>{directive}</p>
                  </button>
                );
              })}
            </div>
            <small className="attention-boundary">
              {t("researchAttentionBoundary")}
            </small>
          </>
        ) : null}
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
              <span>
                {readableMindSummary(mind.rollingSummary) ??
                  t("noRollingSummarySaved")}
              </span>
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
