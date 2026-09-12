import type { AgentRun, AltaEvent, MvpStatus, RuntimeDetail } from "./types";

/** Explicit time scope, not a success-only filter. Unknown dates remain visible. */
export function recentAgentRuns(agents: AgentRun[], now: number, hours = 24) {
  const cutoff = now - hours * 60 * 60 * 1000;
  return agents.filter((agent) => {
    const timestamp = Date.parse(agent.knownAt);
    return (
      agent.status === "running" ||
      !Number.isFinite(timestamp) ||
      timestamp >= cutoff
    );
  });
}

/** Read-only projection. Counts come from the snapshot, never a display timer. */
export function agentDeskSnapshot(
  status: Pick<MvpStatus, "agents">,
  runtime: Pick<RuntimeDetail, "minds"> | null,
  events: AltaEvent[],
) {
  const minds = new Map(runtime?.minds.map((mind) => [mind.id, mind]) ?? []);
  return {
    research: status.agents.filter((agent) => minds.has(agent.id)),
    review: status.agents.filter((agent) => !minds.has(agent.id)),
    minds,
    running: status.agents.filter((agent) => agent.status === "running").length,
    completed: status.agents.filter((agent) =>
      ["completed", "succeeded"].includes(agent.status),
    ).length,
    waiting: status.agents.filter((agent) => agent.status === "waiting").length,
    recent: [...events].sort((a, b) => b.cursor - a.cursor).slice(0, 3),
  };
}

export function agentInputTokens(agent: AgentRun) {
  const value = agent.usage?.input_tokens;
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

export function committeeAgents(agents: AgentRun[]) {
  return agents.filter((agent) =>
    /thesis|disconfirm|counter|moderator|committee/i.test(agent.id),
  );
}

/** A global latest-role snapshot is not proof that a run reviewed this opportunity. */
export function opportunityCommitteeAgents(
  status: MvpStatus,
  opportunityId?: string,
) {
  if (!opportunityId) return [];
  const runIds = new Set(
    status.assessments
      .filter((item) => item.opportunityId === opportunityId && item.runId)
      .map((item) => item.runId),
  );
  for (const item of status.discussions) {
    if (item.opportunityId !== opportunityId) continue;
    const runId = item.detail.run_id ?? item.detail.runId;
    if (typeof runId === "string") runIds.add(runId);
  }
  return committeeAgents(status.agents).filter((agent) =>
    runIds.has(agent.runId),
  );
}

export function agentRoleBrief(id: string) {
  if (/disconfirm|counter/.test(id)) return "deskChallengeRole";
  if (/moderator|committee/.test(id)) return "deskModeratorRole";
  if (/thesis/.test(id)) return "deskThesisRole";
  if (/expression/.test(id)) return "deskExpressionRole";
  if (/audit/.test(id)) return "deskAuditRole";
  return "deskOtherRole";
}
