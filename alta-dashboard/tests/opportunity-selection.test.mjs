import assert from "node:assert/strict";
import test from "node:test";

import {
  focusedOpportunity,
  latestRankBookMap,
  latestRankLeader,
  opportunityIdForEntity,
  refreshSelectedEntity,
} from "../src/lib/opportunity-selection.ts";

function status(overrides = {}) {
  return {
    status: "ready",
    environment: "SHADOW",
    eventCursor: 0,
    sources: [],
    pipeline: [],
    runs: [],
    agents: [],
    candidates: [],
    opportunities: [
      {
        id: "opp-old",
        title: "Old",
        status: "ranked",
        knownAt: "2026-01-01T10:00:00Z",
      },
      {
        id: "opp-new",
        title: "New",
        status: "ranked",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
    ranks: [],
    expressions: [],
    shadowPositions: [],
    assessments: [],
    discussions: [],
    ...overrides,
  };
}

test("latest rank map never joins rows from different ranking runs", () => {
  const snapshot = status({
    ranks: [
      {
        id: "rank-old-1",
        opportunityId: "opp-old",
        book: "opportunity_1_90d",
        rankingRunId: "run-old",
        rankingRunItemCount: 1,
        rankingRunComplete: true,
        position: 1,
        score: "0.99",
        knownAt: "2026-01-01T10:00:00Z",
      },
      {
        id: "rank-new-1",
        opportunityId: "opp-new",
        book: "opportunity_1_90d",
        rankingRunId: "run-new",
        rankingRunItemCount: 1,
        rankingRunComplete: true,
        position: 1,
        score: "0.72",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
  });

  assert.deepEqual([...latestRankBookMap(snapshot).keys()], ["opp-new"]);
  assert.equal(latestRankLeader(snapshot)?.id, "opp-new");
});

test("an incomplete newest ranking run cannot replace a complete book", () => {
  const snapshot = status({
    ranks: [
      {
        id: "rank-complete-1",
        opportunityId: "opp-old",
        book: "opportunity_1_90d",
        rankingRunId: "run-complete",
        rankingRunItemCount: 1,
        rankingRunComplete: true,
        position: 1,
        score: "0.70",
        knownAt: "2026-01-01T10:00:00Z",
      },
      {
        id: "rank-incomplete-2",
        opportunityId: "opp-new",
        book: "opportunity_1_90d",
        rankingRunId: "run-incomplete",
        rankingRunItemCount: 2,
        rankingRunComplete: true,
        position: 2,
        score: "0.99",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
  });

  assert.equal(latestRankLeader(snapshot)?.id, "opp-old");
});

test("a missing selected opportunity falls back to the ranked leader", () => {
  const snapshot = status({
    ranks: [
      {
        id: "rank-current",
        opportunityId: "opp-new",
        book: "opportunity_1_90d",
        rankingRunId: "run-current",
        rankingRunItemCount: 1,
        rankingRunComplete: true,
        position: 1,
        score: "0.7",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
  });
  assert.equal(focusedOpportunity(snapshot, "not-in-snapshot")?.id, "opp-new");
});

test("a bounded-out tail cannot make a ranking run look complete", () => {
  const snapshot = status({
    opportunities: [
      {
        id: "opp-new",
        title: "New",
        status: "ranked",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
    ranks: [
      {
        id: "rank-new-1",
        opportunityId: "opp-new",
        book: "opportunity_1_90d",
        rankingRunId: "run-new",
        rankingRunItemCount: 2,
        rankingRunComplete: true,
        position: 1,
        score: "0.72",
        knownAt: "2026-01-01T11:00:00Z",
      },
      {
        id: "rank-new-2",
        opportunityId: "opp-bounded-out",
        book: "opportunity_1_90d",
        rankingRunId: "run-new",
        rankingRunItemCount: 2,
        rankingRunComplete: true,
        position: 2,
        score: "0.61",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
  });

  assert.equal(latestRankLeader(snapshot), null);
  assert.equal(latestRankBookMap(snapshot).size, 0);
});

test("an expired opportunity cannot remain the current rank leader", () => {
  const snapshot = status({
    opportunities: [
      {
        id: "opp-old",
        title: "Expired",
        status: "ranked",
        knownAt: "2026-01-01T10:00:00Z",
        actionableNow: false,
      },
      {
        id: "opp-new",
        title: "Current",
        status: "ranked",
        knownAt: "2026-01-01T11:00:00Z",
        actionableNow: true,
      },
    ],
    ranks: [
      {
        id: "rank-current-1",
        opportunityId: "opp-old",
        book: "opportunity_1_90d",
        rankingRunId: "run-current",
        rankingRunItemCount: 2,
        rankingRunComplete: true,
        position: 1,
        score: "0.99",
        knownAt: "2026-01-01T11:00:00Z",
      },
      {
        id: "rank-current-2",
        opportunityId: "opp-new",
        book: "opportunity_1_90d",
        rankingRunId: "run-current",
        rankingRunItemCount: 2,
        rankingRunComplete: true,
        position: 2,
        score: "0.75",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
  });

  assert.equal(latestRankLeader(snapshot)?.id, "opp-new");
  assert.deepEqual([...latestRankBookMap(snapshot).keys()], ["opp-new"]);
  assert.equal(focusedOpportunity(snapshot, "opp-old")?.id, "opp-new");
});

test("mutable position selections are refreshed from current status", () => {
  const snapshot = status({
    expressions: [
      {
        id: "expr-1",
        opportunityId: "opp-new",
        kind: "stock",
        status: "active",
        knownAt: "2026-01-01T11:00:00Z",
      },
    ],
    shadowPositions: [
      {
        id: "position-1",
        expressionId: "expr-1",
        symbol: "TEST",
        status: "closed",
        quantity: 0,
        knownAt: "2026-01-01T11:01:00Z",
      },
    ],
  });
  const selected = {
    kind: "position",
    id: "position-1",
    label: "TEST",
    summary: { status: "open", quantity: 1 },
  };

  const refreshed = refreshSelectedEntity(snapshot, selected);
  assert.equal(refreshed?.snapshotOnly, false);
  assert.equal(refreshed?.summary?.status, "closed");
  assert.equal(refreshed?.summary?.quantity, 0);
  assert.equal(opportunityIdForEntity(snapshot, refreshed), "opp-new");
});

test("a selection outside the bounded status is marked as a snapshot", () => {
  const selected = {
    kind: "position",
    id: "position-missing",
    label: "OLD",
    summary: { status: "open" },
  };

  const refreshed = refreshSelectedEntity(status(), selected);
  assert.equal(refreshed?.snapshotOnly, true);
  assert.equal(refreshed?.summary?.status, "open");
});

test("a durable opportunity outside the bounded status remains inspectable", () => {
  const selected = {
    kind: "opportunity",
    id: "opp-historical",
    label: "Historical opportunity",
    summary: { status: "ranked", thesis: "Saved thesis" },
  };

  const refreshed = refreshSelectedEntity(status(), selected);
  assert.equal(refreshed?.id, "opp-historical");
  assert.equal(refreshed?.snapshotOnly, true);
  assert.equal(refreshed?.summary?.thesis, "Saved thesis");
});
