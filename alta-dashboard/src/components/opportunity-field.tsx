import {
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDot,
  FileSearch2,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

export function OpportunityField({
  status,
  runtime,
  selected,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  selected: SelectedEntity | null;
  onSelect: (entity: SelectedEntity) => void;
}) {
  const { domain, number, relative, t } = useI18n();
  const [mobileStage, setMobileStage] = useState<
    "discovery" | "foundry" | "committee" | "action"
  >("foundry");
  const leading = status.opportunities[0];
  const assessments = leading
    ? status.assessments.filter((item) => item.opportunityId === leading.id)
    : [];
  const discussion = leading
    ? status.discussions.filter((item) => item.opportunityId === leading.id)
    : [];
  const expression = leading
    ? status.expressions.find((item) => item.opportunityId === leading.id)
    : status.expressions[0];
  const position = expression
    ? status.shadowPositions.find((item) => item.expressionId === expression.id)
    : status.shadowPositions[0];
  const agents = status.agents.slice(0, 6);
  const sourceCandidate = status.candidates[0];
  const activeAgent =
    agents.find((agent) => agent.status === "running") ?? agents[0];
  const activeRuntime = runtime?.config.autonomousStatus === "running";
  const activeActionAgent = agents.find(
    (agent) =>
      agent.status === "running" && /(expression|audit)/i.test(agent.id),
  );

  return (
    <section className="field-shell" aria-labelledby="field-title">
      <div className="field-heading">
        <h2 id="field-title">{t("liveOpportunityFlow")}</h2>
        <div className="field-heading-meta">
          <StatusPill
            status={runtime?.config.autonomousStatus ?? status.status}
            live
          />
          <span>{status.currentPipelineId ?? t("noActiveCycle")}</span>
        </div>
      </div>

      <div
        className="mobile-stage-selector"
        aria-label={t("opportunityFlowStage")}
      >
        {(["discovery", "foundry", "committee", "action"] as const).map(
          (stage) => (
            <button
              className={mobileStage === stage ? "is-active" : ""}
              key={stage}
              onClick={() => setMobileStage(stage)}
            >
              {stage === "action"
                ? t("audit")
                : stage === "discovery"
                  ? t("discovery")
                  : stage === "foundry"
                    ? t("foundry")
                    : t("committee")}
            </button>
          ),
        )}
      </div>

      <div className="asterism-grid">
        <div
          className={cn(
            "stage-column discovery-column",
            mobileStage === "discovery" && "is-mobile-active",
          )}
        >
          <StageLabel
            icon={FileSearch2}
            label={t("discovery")}
            count={status.candidates.length}
          />
          <ScrollArea className="stage-scroll">
            <div className="stage-stack">
              {status.candidates.slice(0, 5).map((candidate) => (
                <article className="mini-card" key={candidate.id}>
                  <span className="mini-index">{candidate.id}</span>
                  <div>
                    <strong>{candidate.title}</strong>
                    <p>
                      {candidate.alphaArchetype
                        ? domain(candidate.alphaArchetype)
                        : t("unclassified")}{" "}
                      · {relative(candidate.knownAt)}
                    </p>
                  </div>
                </article>
              ))}
              {!status.candidates.length && (
                <EmptyStage label={t("noCandidates")} />
              )}
            </div>
          </ScrollArea>
        </div>

        <StageArrow
          source={sourceCandidate?.id ?? "candidate"}
          target={leading?.id ?? "foundry"}
          knownAt={leading?.knownAt ?? sourceCandidate?.knownAt}
          active={activeRuntime && !leading && Boolean(sourceCandidate)}
        />

        <div
          className={cn(
            "stage-column opportunity-column",
            mobileStage === "foundry" && "is-mobile-active",
          )}
        >
          <StageLabel
            icon={Sparkles}
            label={t("foundry")}
            count={status.opportunities.length}
          />
          <div className="stage-stack">
            {status.opportunities.slice(0, 3).map((opportunity, index) => (
              <button
                className={cn(
                  "opportunity-card",
                  selected?.id === opportunity.id && "is-selected",
                )}
                key={opportunity.id}
                onClick={() =>
                  onSelect({
                    kind: "opportunity",
                    id: opportunity.id,
                    label: opportunity.title,
                    summary: opportunity as unknown as Record<string, unknown>,
                  })
                }
              >
                <div className="opportunity-card-top">
                  <span>
                    {opportunity.id} · {String(index + 1).padStart(2, "0")}
                  </span>
                  <StatusPill status={opportunity.status} />
                </div>
                <h3>{opportunity.title}</h3>
                <div className="opportunity-card-bottom">
                  <span>
                    {opportunity.foundryState
                      ? domain(opportunity.foundryState)
                      : t("building")}
                  </span>
                  <span>{relative(opportunity.knownAt)}</span>
                </div>
              </button>
            ))}
            {!status.opportunities.length && (
              <EmptyStage label={t("foundryWaiting")} />
            )}
          </div>
        </div>

        <StageArrow
          source={leading?.id ?? "opportunity"}
          target={activeAgent?.runId ?? "committee"}
          knownAt={activeAgent?.knownAt ?? leading?.knownAt}
          active={
            activeRuntime && activeAgent?.status === "running" && !expression
          }
        />

        <div
          className={cn(
            "stage-column committee-column",
            mobileStage === "committee" && "is-mobile-active",
          )}
        >
          <StageLabel icon={Bot} label={t("committee")} count={agents.length} />
          <div className="agent-matrix">
            {agents.map((agent) => (
              <button
                className={cn(
                  "agent-node",
                  selected?.id === agent.runId && "is-selected",
                )}
                key={agent.id}
                onClick={() =>
                  onSelect({
                    kind: "run",
                    id: agent.runId,
                    label: domain(agent.id),
                    summary: agent as unknown as Record<string, unknown>,
                  })
                }
              >
                <span className="agent-glyph">
                  <Bot />
                </span>
                <span className="agent-copy">
                  <strong>{domain(agent.id)}</strong>
                  <small>
                    {agent.modelId ?? agent.modelProvider ?? t("modelPending")}{" "}
                    · {agent.runId}
                  </small>
                </span>
                <span
                  className={cn(
                    "agent-state",
                    agent.status === "running" && "is-running",
                  )}
                  aria-label={domain(agent.status)}
                />
              </button>
            ))}
          </div>
          <div className="handoff-stack">
            {discussion.slice(0, 2).map((item) => (
              <button
                key={item.id}
                onClick={() =>
                  onSelect({
                    kind: "event",
                    id: item.id,
                    label: domain(item.eventType),
                    summary: item as unknown as Record<string, unknown>,
                  })
                }
              >
                <span>
                  {domain(String(item.detail.speaker ?? "committee"))}
                </span>
                <strong>
                  {String(item.detail.summary ?? domain(item.eventType))}
                </strong>
                <small>
                  {item.id} · {relative(item.knownAt)}
                </small>
              </button>
            ))}
          </div>
          <div className="committee-brief">
            <div>
              <span>{t("assessments")}</span>
              <strong>{assessments.length}</strong>
            </div>
            <div>
              <span>{t("arguments")}</span>
              <strong>{discussion.length}</strong>
            </div>
            <div>
              <span>{t("context")}</span>
              <strong>
                {number(
                  runtime?.minds.reduce(
                    (sum, mind) => sum + (mind.contextTokens ?? 0),
                    0,
                  ),
                  { notation: "compact", maximumFractionDigits: 1 },
                )}
              </strong>
            </div>
          </div>
        </div>

        <StageArrow
          source={expression?.id ?? leading?.id ?? "packet"}
          target={position?.id ?? activeActionAgent?.runId ?? "audit"}
          knownAt={position?.knownAt ?? expression?.knownAt}
          active={activeRuntime && Boolean(activeActionAgent) && !position}
        />

        <div
          className={cn(
            "stage-column action-column",
            mobileStage === "action" && "is-mobile-active",
          )}
        >
          <StageLabel
            icon={ShieldCheck}
            label={t("expressionAudit")}
            count={status.expressions.length}
          />
          {expression ? (
            <button
              className={cn(
                "action-card",
                selected?.id === expression.id && "is-selected",
              )}
              onClick={() =>
                onSelect({
                  kind: "expression",
                  id: expression.id,
                  label: domain(expression.kind),
                  summary: expression as unknown as Record<string, unknown>,
                })
              }
            >
              <span className="action-icon">
                <Waypoints />
              </span>
              <div>
                <small>{t("selectedCarrier")}</small>
                <strong>{domain(expression.kind)}</strong>
                <p>{domain(expression.status)}</p>
              </div>
            </button>
          ) : (
            <EmptyStage label={t("noExpression")} />
          )}
          <div className="audit-line">
            <ShieldCheck />
            <span>{t("auditBoundary")}</span>
            <strong>
              {expression?.status ? domain(expression.status) : t("waiting")}
            </strong>
          </div>
          {position ? (
            <button
              className="position-line"
              onClick={() =>
                onSelect({
                  kind: "position",
                  id: position.id,
                  label: t("shadowPosition", { symbol: position.symbol }),
                  summary: position as unknown as Record<string, unknown>,
                })
              }
            >
              <CheckCircle2 />
              <span>
                <small>{t("shadowObservation")}</small>
                <strong>{position.symbol}</strong>
              </span>
              <StatusPill status={position.status} />
            </button>
          ) : (
            <div className="position-line is-empty">
              <CircleDot />
              <span>
                <small>{t("shadowObservation")}</small>
                <strong>{t("noPosition")}</strong>
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="field-footnote">
        <span>
          <span className="legend-dot is-live" /> {t("activeRecentlyUpdated")}
        </span>
        <span>
          <span className="legend-dot" /> {t("waitingHistorical")}
        </span>
        <span className="field-truth">{t("savedArtifactsTruth")}</span>
      </div>
    </section>
  );
}

function StageLabel({
  icon: Icon,
  label,
  count,
}: {
  icon: typeof Sparkles;
  label: string;
  count: number;
}) {
  return (
    <div className="stage-label">
      <Icon />
      <span>{label}</span>
      <em>{count}</em>
    </div>
  );
}

function StageArrow({
  source,
  target,
  knownAt,
  active,
}: {
  source: string;
  target: string;
  knownAt?: string;
  active: boolean;
}) {
  const { locale, relative, t } = useI18n();
  const time = knownAt
    ? `${locale === "zh-CN" ? "，" : ", "}${relative(knownAt)}`
    : "";
  return (
    <div
      className={cn("stage-arrow", active && "is-active")}
      aria-label={t("handoffLabel", { source, target, time })}
    >
      <span />
      <em title={`${source} → ${target}`}>
        <strong>{source}</strong>
        <small>→ {target}</small>
      </em>
      <ArrowRight />
    </div>
  );
}

function EmptyStage({ label }: { label: string }) {
  return (
    <div className="empty-stage">
      <CircleDot />
      <span>{label}</span>
    </div>
  );
}
