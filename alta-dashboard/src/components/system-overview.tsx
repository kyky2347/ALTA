import {
  Activity,
  Bot,
  CalendarClock,
  Database,
  FileSearch2,
  Focus,
  Network,
  Radar,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { RuntimeRecovery } from "@/components/runtime-recovery";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import {
  recordedSourceIssue,
  summarizeSourceRecords,
} from "@/lib/source-posture";
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
  const { domain, number, relative, systemMessage, t } = useI18n();
  const attention = runtime?.researchAttention;
  const continuity = runtime?.opportunityContinuity;
  const research = runtime?.researchOperations;
  const sourceSummary = summarizeSourceRecords(status.sources);
  const sourcePostures = sourceSummary.visible.map((summary) => {
    const latest = sourcePosture(summary.latest, relative, domain);
    const previousDifferent = summary.history
      .map((source) => sourcePosture(source, relative, domain))
      .find(
        (previous) =>
          previous.posture !== latest.posture ||
          previous.issue !== latest.issue,
      );
    return { ...summary, ...latest, previousDifferent };
  });
  const percent = (value?: string | null) => {
    const parsed = value === null || value === undefined ? NaN : Number(value);
    return Number.isFinite(parsed)
      ? number(parsed, { style: "percent", maximumFractionDigits: 1 })
      : t("unavailable");
  };
  return (
    <section className="overview-grid">
      <div className="overview-pulse" role="list">
        <OverviewMetric
          icon={FileSearch2}
          label={t("candidates")}
          value={status.candidates.length}
          detail={t("recentFoundryInputs")}
        />
        <OverviewMetric
          icon={Radar}
          label={t("opportunities")}
          value={status.opportunities.length}
          detail={t("deduplicatedTheses")}
        />
        <OverviewMetric
          icon={Bot}
          label={t("agentRoles")}
          value={status.agents.length}
          detail={t("persistentMinds", { count: runtime?.minds.length ?? 0 })}
        />
        <OverviewMetric
          icon={Waypoints}
          label={t("expressions")}
          value={status.expressions.length}
          detail={t("auditedCarriers")}
        />
        <OverviewMetric
          icon={ShieldCheck}
          label={t("shadowPositions")}
          value={status.shadowPositions.length}
          detail={t("capitalDisabled")}
        />
        <OverviewMetric
          icon={Database}
          label={t("eventCursor")}
          value={status.eventCursor}
          detail={t("appendOnlyLedger")}
        />
      </div>
      <RuntimeRecovery runtime={runtime} fallbackStatus={status.status} />
      <div className="overview-wide">
        <div className="overview-wide-head">
          <span>
            <Activity /> {t("sourcePosture")}
          </span>
          <StatusPill status={status.sources.length ? "observed" : "waiting"} />
        </div>
        <div className="source-list">
          {sourcePostures.map(
            ({
              identity,
              history,
              posture,
              freshness,
              issue,
              previousDifferent,
            }) => (
              <div className={issue ? "has-source-issue" : ""} key={identity}>
                <span className="source-list-heading">
                  <strong>{domain(identity)}</strong>
                  <StatusPill status={posture} />
                </span>
                <span>{t("sourceFreshness", { freshness })}</span>
                <small>
                  {issue
                    ? t("sourceIssue", {
                        issue: localizeSourceIssue(
                          issue,
                          systemMessage,
                          domain,
                        ),
                      })
                    : t("sourceNoKnownIssue")}
                </small>
                {previousDifferent ? (
                  <small className="source-previous-state">
                    {t("sourcePreviousState", {
                      posture: domain(previousDifferent.posture),
                      freshness: previousDifferent.freshness,
                    })}
                  </small>
                ) : null}
                {history.length ? (
                  <small className="source-folded-count">
                    {t("sourcePriorRecordsHidden", { count: history.length })}
                  </small>
                ) : null}
              </div>
            ),
          )}
          {!status.sources.length && <p>{t("noSourcePosture")}</p>}
        </div>
        {sourceSummary.foldedRecordCount ||
        sourceSummary.hiddenIdentityCount ? (
          <p className="source-list-boundary" role="status">
            {sourceSummary.foldedRecordCount
              ? t("sourceHistoryFolded", {
                  count: sourceSummary.foldedRecordCount,
                })
              : null}
            {sourceSummary.foldedRecordCount &&
            sourceSummary.hiddenIdentityCount
              ? " · "
              : null}
            {sourceSummary.hiddenIdentityCount
              ? t("sourceIdentitiesHidden", {
                  count: sourceSummary.hiddenIdentityCount,
                })
              : null}
          </p>
        ) : null}
      </div>
      <div className="overview-wide research-operations">
        <div className="overview-wide-head">
          <span>
            <Network /> {t("researchOperations")}
          </span>
          <StatusPill status={research?.posture ?? "waiting"} />
        </div>
        <p className="research-operations-intro">
          {research
            ? t("researchOperationsDetail")
            : t("researchOperationsWaiting")}
        </p>
        {research ? (
          <>
            <div className="research-operations-metrics">
              <div>
                <small>{t("recentResearchRuns")}</small>
                <strong>{number(research.windowRuns)}</strong>
              </div>
              <div>
                <small>{t("completedRetrievals")}</small>
                <strong>{number(research.completedToolCalls)}</strong>
              </div>
              <div>
                <small>{t("failedRetrievals")}</small>
                <strong>{number(research.failedToolCalls)}</strong>
              </div>
              <div>
                <small>{t("researchTokens")}</small>
                <strong>
                  {number(research.totalTokens, {
                    notation: "compact",
                    maximumFractionDigits: 1,
                  })}
                </strong>
              </div>
              <div>
                <small>{t("meanResearchLatency")}</small>
                <strong>
                  {research.averageLatencyMs === null ||
                  research.averageLatencyMs === undefined
                    ? t("unavailable")
                    : t("milliseconds", {
                        value: number(Math.round(research.averageLatencyMs)),
                      })}
                </strong>
              </div>
              <div>
                <small>{t("independentEvidenceOrigins")}</small>
                <strong>{number(research.independentEvidenceOrigins)}</strong>
              </div>
              <div>
                <small>{t("crossCheckedRuns")}</small>
                <strong>{number(research.crossCheckedRuns)}</strong>
              </div>
              <div>
                <small>{t("retryRecoveredRuns")}</small>
                <strong>{number(research.retryRecoveredRuns)}</strong>
              </div>
              <div>
                <small>{t("contractRejectedRuns")}</small>
                <strong>{number(research.contractRejectedRuns)}</strong>
              </div>
              <div>
                <small>{t("followUpAssignedRuns")}</small>
                <strong>{number(research.followUpAssignedRuns)}</strong>
              </div>
              <div>
                <small>{t("followUpExecutedRuns")}</small>
                <strong>{number(research.followUpExecutedRuns)}</strong>
              </div>
              <div>
                <small>{t("followUpNoOpRuns")}</small>
                <strong>{number(research.followUpNoOpRuns)}</strong>
              </div>
            </div>
            <div className="research-mind-list">
              {research.minds.map((mind) => (
                <button
                  key={mind.scoutId}
                  type="button"
                  onClick={() =>
                    onSelect({
                      kind: "event",
                      id: `research-operations:${mind.scoutId}`,
                      label: `${domain(mind.scoutId)} · ${domain(mind.posture)}`,
                      summary: mind as unknown as Record<string, unknown>,
                    })
                  }
                >
                  <span className="research-mind-heading">
                    <span>
                      <strong>{domain(mind.scoutId)}</strong>
                      <small>
                        {mind.lastRunAt
                          ? relative(mind.lastRunAt)
                          : t("notRunYet")}
                      </small>
                    </span>
                    <StatusPill status={mind.posture} />
                  </span>
                  <span className="research-mind-stats">
                    <span>
                      {number(mind.completedToolCalls)} {t("callsShort")}
                    </span>
                    <span>
                      {number(mind.uniqueSourceDomains)} {t("domainsShort")}
                    </span>
                    <span>
                      {number(mind.independentEvidenceOrigins)}{" "}
                      {t("originsShort")}
                    </span>
                    <span>
                      {number(mind.candidateRuns)} {t("candidatesShort")}
                    </span>
                    {mind.followUpAssignedRuns ? (
                      <span>
                        {number(mind.followUpExecutedRuns)}/
                        {number(mind.followUpAssignedRuns)}{" "}
                        {t("followUpsShort")}
                      </span>
                    ) : null}
                  </span>
                  <span className="evidence-role-list">
                    {mind.evidenceRoles.length ? (
                      mind.evidenceRoles.map((role) => (
                        <small key={role}>{domain(role)}</small>
                      ))
                    ) : (
                      <small>{t("evidenceRolesPending")}</small>
                    )}
                  </span>
                  {mind.latestErrorCode ? (
                    <small className="research-mind-error">
                      {domain(mind.latestErrorCode)}
                    </small>
                  ) : null}
                  {mind.retryRecoveredRuns ? (
                    <small className="research-mind-recovered">
                      {t("retryRecoveredMind", {
                        count: number(mind.retryRecoveredRuns),
                      })}
                    </small>
                  ) : null}
                  {mind.sourceRoleCollisions ? (
                    <small className="research-mind-warning">
                      {t("sourceRoleReuse", {
                        count: number(mind.sourceRoleCollisions),
                      })}
                    </small>
                  ) : null}
                </button>
              ))}
            </div>
            <small className="research-operations-boundary">
              {t("researchOperationsBoundary")}
            </small>
          </>
        ) : null}
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
              <div>
                <small>{t("uniqueArchetypes")}</small>
                <strong>{number(attention.uniqueArchetypes ?? 0)}</strong>
              </div>
              <div>
                <small>{t("archetypeBreadth")}</small>
                <strong>
                  {attention.archetypeEffectiveBreadth ?? t("unavailable")}
                </strong>
              </div>
              <div>
                <small>{t("shortHorizon")}</small>
                <strong>{number(attention.horizonMix?.short ?? 0)}</strong>
              </div>
              <div>
                <small>{t("longHorizon")}</small>
                <strong>{number(attention.horizonMix?.long ?? 0)}</strong>
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
                    <span className="attention-targets">
                      {assignment.targetArchetype ? (
                        <small>{domain(assignment.targetArchetype)}</small>
                      ) : null}
                      {assignment.targetHorizonBucket ? (
                        <small>
                          {domain(assignment.targetHorizonBucket)} ·{" "}
                          {t("horizon")}
                        </small>
                      ) : null}
                    </span>
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
      <div className="overview-wide continuity-portfolio">
        <div className="overview-wide-head">
          <span>
            <CalendarClock /> {t("opportunityContinuity")}
          </span>
          <StatusPill status={continuity?.posture ?? "waiting"} />
        </div>
        <p className="attention-intro">
          {continuity
            ? t("opportunityContinuityDetail")
            : t("opportunityContinuityWaiting")}
        </p>
        {continuity ? (
          <>
            <div className="continuity-metrics">
              <div>
                <small>{t("activeRegistry")}</small>
                <strong>{number(continuity.registryActive)}</strong>
              </div>
              <div>
                <small>{t("frozenForResearch")}</small>
                <strong>{number(continuity.frozenActive)}</strong>
              </div>
              <div>
                <small>{t("openQuestions")}</small>
                <strong>{number(continuity.pendingQuestions)}</strong>
              </div>
              <div>
                <small>{t("deferredResearch")}</small>
                <strong>{number(continuity.deferredQuestions)}</strong>
              </div>
              <div>
                <small>{t("expiringOpportunities")}</small>
                <strong>{number(continuity.expiringActive)}</strong>
              </div>
              <div>
                <small>{t("staleOpportunities")}</small>
                <strong>{number(continuity.staleActive)}</strong>
              </div>
              <div>
                <small>{t("oldestActiveAge")}</small>
                <strong>
                  {t("daysCount", {
                    count: number(continuity.oldestActiveDays),
                  })}
                </strong>
              </div>
            </div>
            <div className="continuity-detail">
              <div>
                <small>{t("earliestDecisionDeadline")}</small>
                <strong>
                  {continuity.earliestDecisionDeadlineAt
                    ? relative(continuity.earliestDecisionDeadlineAt)
                    : t("unavailable")}
                </strong>
                <p>{continuity.warning}</p>
              </div>
              <div>
                <small>{t("nextResearchWindow")}</small>
                <strong>
                  {continuity.nextResearchDueAt
                    ? relative(continuity.nextResearchDueAt)
                    : t("noDeferredResearch")}
                </strong>
                <p>{t("researchCadenceDetail")}</p>
              </div>
              <div className="continuity-priorities">
                <small>{t("priorityFollowUps")}</small>
                {continuity.priorityOpportunityIds.length ? (
                  continuity.priorityOpportunityIds.map((opportunityId) => (
                    <button
                      key={opportunityId}
                      type="button"
                      onClick={() =>
                        onSelect({
                          kind: "opportunity",
                          id: opportunityId,
                          label: opportunityId,
                          summary: continuity as unknown as Record<
                            string,
                            unknown
                          >,
                        })
                      }
                    >
                      {opportunityId}
                    </button>
                  ))
                ) : (
                  <span>{t("noPriorityFollowUps")}</span>
                )}
              </div>
            </div>
            <small className="attention-boundary">
              {t("opportunityContinuityBoundary")}
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

function sourcePosture(
  source: MvpStatus["sources"][number],
  relative: (value?: string) => string,
  domain: (value: string) => string,
) {
  const posture = String(source.posture ?? source.status ?? "recorded");
  const freshnessValue =
    typeof source.freshness === "string"
      ? domain(source.freshness)
      : relative(source.knownAt);
  return {
    source,
    posture,
    freshness: freshnessValue,
    issue: recordedSourceIssue(source),
  };
}

function localizeSourceIssue(
  issue: string,
  systemMessage: (message: string | null | undefined) => string | null,
  domain: (value: string) => string,
) {
  const localized = systemMessage(issue);
  return localized && localized !== issue ? localized : domain(issue);
}

function OverviewMetric({
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
    <article className="overview-metric" role="listitem">
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
