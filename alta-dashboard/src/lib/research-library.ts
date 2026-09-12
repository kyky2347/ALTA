import type { AgentRun, MvpStatus } from "./types";

/** Recent research work is visible even when its honest outcome is abstention. */
export function researchScouts(agents: AgentRun[], now: number) {
  return agents.filter((agent) => {
    const age = now - Date.parse(agent.knownAt);
    return (
      agent.id.endsWith("_scout") &&
      (agent.status === "running" ||
        (Number.isFinite(age) && age >= 0 && age <= 86400000))
    );
  });
}

export type ResearchRecord = {
  kind: "candidate" | "opportunity";
  id: string;
  title: string;
  knownAt: string;
  freshnessState: string;
  current: boolean;
  summary: Record<string, unknown>;
};

/** Browse records, not invented investment opportunities. The bounded API
 * snapshot and the event timeline have deliberately different scopes. */
export function researchLibrary(
  status: MvpStatus,
  now: number,
  scope: "week" | "snapshot",
  query: string,
) {
  const records: ResearchRecord[] = [
    ...status.opportunities.map((row) => ({
      kind: "opportunity" as const,
      id: row.id,
      title: row.title,
      knownAt: row.knownAt,
      freshnessState: row.freshnessState ?? "unknown",
      current:
        row.actionableNow === true &&
        ["live", "current"].includes(row.freshnessState ?? ""),
      summary: row as unknown as Record<string, unknown>,
    })),
    ...status.candidates.map((row) => ({
      kind: "candidate" as const,
      id: row.id,
      title: row.title,
      knownAt: row.knownAt,
      freshnessState: row.freshnessState ?? "unknown",
      current: false,
      summary: row as unknown as Record<string, unknown>,
    })),
  ];
  const seen = new Set<string>();
  const needle = query.trim().toLocaleLowerCase();
  return records
    .filter((row) => {
      const key = `${row.kind}:${row.id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      const age = now - Date.parse(row.knownAt);
      if (
        scope === "week" &&
        (!Number.isFinite(age) || age < 0 || age > 7 * 86400000)
      )
        return false;
      return (
        !needle ||
        `${row.title} ${row.id} ${row.freshnessState}`
          .toLocaleLowerCase()
          .includes(needle)
      );
    })
    .sort(
      (a, b) =>
        Number(b.current) - Number(a.current) ||
        (Date.parse(b.knownAt) || 0) - (Date.parse(a.knownAt) || 0) ||
        a.id.localeCompare(b.id),
    );
}
