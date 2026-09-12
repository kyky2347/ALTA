import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { AgentMark } from "@/components/agent-mark";
import { StatusPill } from "@/components/status-pill";
import {
  agentDeskSnapshot,
  agentInputTokens,
  agentRoleBrief,
  recentAgentRuns,
} from "@/lib/agent-desk";
import { useI18n } from "@/lib/i18n";
import type {
  AgentRun,
  AltaEvent,
  MvpStatus,
  RuntimeDetail,
  SelectedEntity,
} from "@/lib/types";
import { readableMindSummary } from "@/lib/utils";

export function AgentDesk({
  status,
  runtime,
  events,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  events: AltaEvent[];
  onSelect: (entity: SelectedEntity) => void;
}) {
  const { domain, number, relative, clock, t } = useI18n();
  const [allHistory, setAllHistory] = useState(false);
  const [scopeAnchor, setScopeAnchor] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setScopeAnchor(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const visibleAgents = allHistory
    ? status.agents
    : recentAgentRuns(status.agents, scopeAnchor);
  const desk = agentDeskSnapshot({ agents: visibleAgents }, runtime, events);
  const selectRun = (agent: AgentRun) =>
    onSelect({
      kind: "run",
      id: agent.runId,
      label: domain(agent.id),
      summary: agent as unknown as Record<string, unknown>,
    });
  return (
    <section className="agent-desk" aria-label={t("agentDesk")}>
      <div className="desk-snapshot">
        <span>{t("deskSnapshot")}</span>
        <span>
          <strong>{number(desk.running)}</strong> {domain("running")}
        </span>
        <span>
          <strong>{number(desk.completed)}</strong> {domain("completed")}
        </span>
        <span>
          <strong>{number(desk.waiting)}</strong> {domain("waiting")}
        </span>
        <small>{t("openRecordHint")}</small>
      </div>
      <div className="desk-time-scope">
        <span>{allHistory ? t("deskAllHistory") : t("deskLastDay")}</span>
        {!allHistory && status.agents.length > visibleAgents.length && (
          <small>
            {t("deskOlderRecords", {
              count: status.agents.length - visibleAgents.length,
            })}
          </small>
        )}
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={allHistory}
          onClick={() => setAllHistory(!allHistory)}
        >
          {allHistory ? t("deskLastDay") : t("deskAllHistory")}
        </Button>
      </div>
      {desk.research.length > 0 && (
        <section aria-labelledby="desk-research-title">
          <h2 className="desk-section-title" id="desk-research-title">
            {t("deskResearch")}
          </h2>
          <div className="desk-grid" data-count={desk.research.length}>
            {desk.research.map((agent) => {
              const mind = desk.minds.get(agent.id);
              return (
                <button
                  className="desk-card"
                  data-state={agent.status}
                  key={agent.runId}
                  onClick={() => selectRun(agent)}
                >
                  <div className="desk-card-top">
                    <span>
                      <AgentMark role={agent.id} />
                    </span>
                    <StatusPill status={agent.status} />
                  </div>
                  <h3>{domain(agent.id)}</h3>
                  <p>
                    {readableMindSummary(mind?.rollingSummary) ??
                      t("noRollingSummarySaved")}
                  </p>
                  <div className="desk-facts">
                    <span>
                      {t("model")}
                      <strong>
                        {agent.modelId ?? agent.modelProvider ?? "—"}
                      </strong>
                    </span>
                    <span>
                      {t("turns")}
                      <strong>{number(mind?.turnCount)}</strong>
                    </span>
                    <span title={t("recordedTokensHelp")}>
                      {t("context")}
                      <strong>{number(mind?.contextTokens)}</strong>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}
      {desk.review.length > 0 && (
        <section aria-labelledby="desk-review-title">
          <h2 className="desk-section-title" id="desk-review-title">
            {t("deskReview")}
          </h2>
          <div className="desk-review-list">
            {desk.review.map((agent) => (
              <button
                className="desk-review-row"
                data-state={agent.status}
                key={agent.runId}
                onClick={() => selectRun(agent)}
              >
                <span className="desk-review-name">
                  <AgentMark role={agent.id} />
                  <strong>{domain(agent.id)}</strong>
                </span>
                <StatusPill status={agent.status} />
                <span className="desk-role-brief">
                  <small>{t("deskResponsibility")}</small>
                  {t(agentRoleBrief(agent.id))}
                </span>
                <span className="desk-review-model">
                  <small>{t("model")}</small>
                  <strong>{agent.modelId ?? agent.modelProvider ?? "—"}</strong>
                </span>
                <span className="desk-review-usage">
                  <small>{t("deskInputTokens")}</small>
                  <strong>{number(agentInputTokens(agent))}</strong>
                </span>
                <span className="desk-review-time">
                  <small>{t("knownAt")}</small>
                  <time dateTime={agent.knownAt}>
                    {relative(agent.knownAt)}
                  </time>
                </span>
                <ArrowUpRight className="desk-open-icon" aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      )}
      {!visibleAgents.length && <p className="desk-empty">{t("deskEmpty")}</p>}
      <section className="desk-handoffs" aria-labelledby="desk-handoffs-title">
        <h2 className="desk-section-title" id="desk-handoffs-title">
          {t("deskRecentActivity")}
        </h2>
        {desk.recent.length ? (
          <ol>
            {desk.recent.map((event) => (
              <li key={event.eventId}>
                <button
                  onClick={() =>
                    onSelect({
                      kind: "event",
                      id: event.eventId,
                      label: domain(event.eventType),
                      summary: event as unknown as Record<string, unknown>,
                    })
                  }
                >
                  <time dateTime={event.knownAt}>{clock(event.knownAt)}</time>
                  <strong>{domain(event.eventType)}</strong>
                  <span>
                    {event.aggregateId}
                    <ArrowUpRight aria-hidden="true" />
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p>{t("noRecordedEvents")}</p>
        )}
      </section>
    </section>
  );
}
