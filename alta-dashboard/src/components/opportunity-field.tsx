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
import { compactNumber, relativeTime, titleCase } from "@/lib/display";
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
        <h2 id="field-title">Live opportunity flow</h2>
        <div className="field-heading-meta">
          <StatusPill
            status={runtime?.config.autonomousStatus ?? status.status}
            live
          />
          <span>{status.currentPipelineId ?? "No active cycle"}</span>
        </div>
      </div>

      <div
        className="mobile-stage-selector"
        aria-label="Opportunity flow stage"
      >
        {(["discovery", "foundry", "committee", "action"] as const).map(
          (stage) => (
            <button
              className={mobileStage === stage ? "is-active" : ""}
              key={stage}
              onClick={() => setMobileStage(stage)}
            >
              {stage === "action" ? "Audit" : titleCase(stage)}
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
            label="Discovery"
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
                        ? titleCase(candidate.alphaArchetype)
                        : "Unclassified"}{" "}
                      · {relativeTime(candidate.knownAt)}
                    </p>
                  </div>
                </article>
              ))}
              {!status.candidates.length && (
                <EmptyStage label="No candidates yet" />
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
            label="Foundry"
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
                      ? titleCase(opportunity.foundryState)
                      : "Building"}
                  </span>
                  <span>{relativeTime(opportunity.knownAt)}</span>
                </div>
              </button>
            ))}
            {!status.opportunities.length && (
              <EmptyStage label="Foundry is waiting for candidates" />
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
          <StageLabel icon={Bot} label="Committee" count={agents.length} />
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
                    label: titleCase(agent.id),
                    summary: agent as unknown as Record<string, unknown>,
                  })
                }
              >
                <span className="agent-glyph">
                  <Bot />
                </span>
                <span className="agent-copy">
                  <strong>{titleCase(agent.id)}</strong>
                  <small>
                    {agent.modelId ?? agent.modelProvider ?? "Model pending"} ·{" "}
                    {agent.runId}
                  </small>
                </span>
                <span
                  className={cn(
                    "agent-state",
                    agent.status === "running" && "is-running",
                  )}
                  aria-label={agent.status}
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
                    label: titleCase(item.eventType),
                    summary: item as unknown as Record<string, unknown>,
                  })
                }
              >
                <span>
                  {titleCase(String(item.detail.speaker ?? "committee"))}
                </span>
                <strong>
                  {String(item.detail.summary ?? titleCase(item.eventType))}
                </strong>
                <small>
                  {item.id} · {relativeTime(item.knownAt)}
                </small>
              </button>
            ))}
          </div>
          <div className="committee-brief">
            <div>
              <span>Assessments</span>
              <strong>{assessments.length}</strong>
            </div>
            <div>
              <span>Arguments</span>
              <strong>{discussion.length}</strong>
            </div>
            <div>
              <span>Context</span>
              <strong>
                {compactNumber(
                  runtime?.minds.reduce(
                    (sum, mind) => sum + (mind.contextTokens ?? 0),
                    0,
                  ),
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
            label="Expression & audit"
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
                  label: titleCase(expression.kind),
                  summary: expression as unknown as Record<string, unknown>,
                })
              }
            >
              <span className="action-icon">
                <Waypoints />
              </span>
              <div>
                <small>Selected carrier</small>
                <strong>{titleCase(expression.kind)}</strong>
                <p>{titleCase(expression.status)}</p>
              </div>
            </button>
          ) : (
            <EmptyStage label="No expression selected" />
          )}
          <div className="audit-line">
            <ShieldCheck />
            <span>Audit boundary</span>
            <strong>
              {expression?.status ? titleCase(expression.status) : "Waiting"}
            </strong>
          </div>
          {position ? (
            <button
              className="position-line"
              onClick={() =>
                onSelect({
                  kind: "position",
                  id: position.id,
                  label: `${position.symbol} shadow position`,
                  summary: position as unknown as Record<string, unknown>,
                })
              }
            >
              <CheckCircle2 />
              <span>
                <small>Shadow observation</small>
                <strong>{position.symbol}</strong>
              </span>
              <StatusPill status={position.status} />
            </button>
          ) : (
            <div className="position-line is-empty">
              <CircleDot />
              <span>
                <small>Shadow observation</small>
                <strong>No position</strong>
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="field-footnote">
        <span>
          <span className="legend-dot is-live" /> Active or recently updated
        </span>
        <span>
          <span className="legend-dot" /> Waiting or historical
        </span>
        <span className="field-truth">
          Private chain-of-thought is not exposed; saved artifacts and handoffs
          are.
        </span>
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
  return (
    <div
      className={cn("stage-arrow", active && "is-active")}
      aria-label={`Handoff from ${source} to ${target}${knownAt ? `, ${relativeTime(knownAt)}` : ""}`}
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
