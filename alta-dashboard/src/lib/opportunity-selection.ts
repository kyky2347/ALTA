import type { MvpStatus, Opportunity, SelectedEntity } from "@/lib/types";

type StatusRank = MvpStatus["ranks"][number];
type NormalizedRank = StatusRank & { knownAtMs: number; position: number };

function timestamp(value: string) {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizedRanks(status: MvpStatus): NormalizedRank[] {
  return status.ranks.flatMap((rank) => {
    const knownAt = timestamp(rank.knownAt);
    const position = Number(rank.position);
    const itemCount = Number(rank.rankingRunItemCount);
    return knownAt !== null &&
      Number.isFinite(position) &&
      position >= 1 &&
      Number.isInteger(itemCount) &&
      itemCount >= 1 &&
      typeof rank.rankingRunComplete === "boolean" &&
      rank.book.trim() &&
      rank.rankingRunId.trim()
      ? [
          {
            ...rank,
            knownAtMs: knownAt,
            position,
            rankingRunItemCount: itemCount,
          },
        ]
      : [];
  });
}

function completeRankRun(ranks: NormalizedRank[]) {
  if (ranks.length === 0) return false;
  const positions = [...ranks]
    .map((rank) => rank.position)
    .sort((a, b) => a - b);
  return (
    ranks.every((rank) => rank.rankingRunComplete) &&
    new Set(ranks.map((rank) => rank.rankingRunId)).size === 1 &&
    new Set(ranks.map((rank) => rank.opportunityId)).size === ranks.length &&
    new Set(ranks.map((rank) => rank.book)).size === 1 &&
    ranks.every((rank) => rank.rankingRunItemCount === ranks.length) &&
    positions.every((position, index) => position === index + 1)
  );
}

/** Return only rows from the newest durable ranking run. */
export function latestRankBookMap(status: MvpStatus) {
  const runs = new Map<string, NormalizedRank[]>();
  for (const rank of normalizedRanks(status)) {
    const runId = rank.rankingRunId.trim();
    if (!runId) continue;
    const key = `${rank.book}\u0000${runId}`;
    const ranks = runs.get(key) ?? [];
    ranks.push(rank);
    runs.set(key, ranks);
  }

  const opportunityIds = new Set(
    status.opportunities.map((opportunity) => opportunity.id),
  );

  const latestRun = [...runs.entries()]
    .filter(
      ([, ranks]) =>
        completeRankRun(ranks) &&
        ranks.every((rank) => opportunityIds.has(rank.opportunityId)),
    )
    .sort(([leftRunId, left], [rightRunId, right]) => {
      const recencyDifference =
        Math.max(...right.map((rank) => rank.knownAtMs)) -
        Math.max(...left.map((rank) => rank.knownAtMs));
      return recencyDifference || leftRunId.localeCompare(rightRunId);
    })[0]?.[1];
  const byOpportunity = new Map<string, NormalizedRank>();
  for (const rank of latestRun ?? []) {
    const current = byOpportunity.get(rank.opportunityId);
    if (
      !current ||
      rank.knownAtMs > current.knownAtMs ||
      (rank.knownAtMs === current.knownAtMs &&
        rank.position < current.position) ||
      (rank.knownAtMs === current.knownAtMs &&
        rank.position === current.position &&
        Number(rank.score) > Number(current.score))
    ) {
      byOpportunity.set(rank.opportunityId, rank);
    }
  }
  return byOpportunity;
}

/** Resolve the investment leader from the newest complete rank book. */
export function latestRankLeader(status: MvpStatus): Opportunity | null {
  const opportunities = new Map(
    status.opportunities.map((opportunity) => [opportunity.id, opportunity]),
  );
  const leader = [...latestRankBookMap(status).values()].sort((left, right) => {
    if (left.position !== right.position) return left.position - right.position;
    const scoreDifference = Number(right.score) - Number(left.score);
    if (Number.isFinite(scoreDifference) && scoreDifference !== 0)
      return scoreDifference;
    if (left.knownAtMs !== right.knownAtMs)
      return right.knownAtMs - left.knownAtMs;
    return left.opportunityId.localeCompare(right.opportunityId);
  })[0];
  return leader ? (opportunities.get(leader.opportunityId) ?? null) : null;
}

export function focusedOpportunity(
  status: MvpStatus,
  selectedOpportunityId: string | null,
) {
  if (selectedOpportunityId)
    return (
      status.opportunities.find(
        (opportunity) => opportunity.id === selectedOpportunityId,
      ) ?? latestRankLeader(status)
    );
  return latestRankLeader(status);
}

export function opportunityIdForEntity(
  status: MvpStatus | null,
  entity: SelectedEntity,
) {
  if (entity.kind === "opportunity") return entity.id;
  if (!status) return null;
  if (entity.kind === "expression")
    return (
      status.expressions.find((expression) => expression.id === entity.id)
        ?.opportunityId ?? null
    );
  if (entity.kind === "position") {
    const expressionId = status.shadowPositions.find(
      (position) => position.id === entity.id,
    )?.expressionId;
    return expressionId
      ? (status.expressions.find((expression) => expression.id === expressionId)
          ?.opportunityId ?? null)
      : null;
  }
  const summarizedOpportunityId = entity.summary?.opportunityId;
  return typeof summarizedOpportunityId === "string"
    ? summarizedOpportunityId
    : null;
}

/**
 * Refresh mutable selections from the newest bounded status snapshot. Records
 * which have left that snapshot remain inspectable, but are explicitly marked
 * as snapshots instead of masquerading as current state.
 */
export function refreshSelectedEntity(
  status: MvpStatus | null,
  entity: SelectedEntity | null,
): SelectedEntity | null {
  if (!entity || !status || entity.kind === "event") return entity;

  let current: Record<string, unknown> | undefined;
  if (entity.kind === "opportunity")
    current = status.opportunities.find((item) => item.id === entity.id) as
      | (Record<string, unknown> & { id: string })
      | undefined;
  if (entity.kind === "expression")
    current = status.expressions.find((item) => item.id === entity.id) as
      | (Record<string, unknown> & { id: string })
      | undefined;
  if (entity.kind === "position")
    current = status.shadowPositions.find((item) => item.id === entity.id) as
      | (Record<string, unknown> & { id: string })
      | undefined;
  if (entity.kind === "run")
    current = [...status.agents, ...status.runs].find(
      (item) =>
        ("runId" in item && item.runId === entity.id) || item.id === entity.id,
    ) as (Record<string, unknown> & { id: string }) | undefined;

  return current
    ? { ...entity, summary: current, snapshotOnly: false }
    : { ...entity, snapshotOnly: true };
}
