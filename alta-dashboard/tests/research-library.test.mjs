import assert from "node:assert/strict";
import test from "node:test";
import {
  researchLibrary,
  researchScouts,
} from "../src/lib/research-library.ts";
import { entityDetailPath } from "../src/lib/api.ts";

const now = Date.parse("2026-09-12T12:00:00Z");
const recent = {
  id: "recent",
  title: "Saved opportunity",
  knownAt: "2026-09-11T12:00:00Z",
  freshnessState: "current",
  actionableNow: true,
};
const old = {
  ...recent,
  id: "old",
  knownAt: "2026-08-01T00:00:00Z",
  freshnessState: "expired",
  actionableNow: false,
};
test("research activity is scoped, never a success-only or invented opportunity feed", () => {
  const agents = [
    { id: "change_event_scout", status: "running", knownAt: old.knownAt },
    { id: "expectation_gap_scout", status: "failed", knownAt: recent.knownAt },
    {
      id: "market_dislocation_scout",
      status: "succeeded",
      knownAt: old.knownAt,
    },
    { id: "thesis_assessor", status: "running", knownAt: recent.knownAt },
  ];
  assert.deepEqual(
    researchScouts(agents, now).map((a) => a.id),
    ["change_event_scout", "expectation_gap_scout"],
  );
  assert.deepEqual(researchScouts([], now), []);
});
test("research library distinguishes candidate records, freshness, future dates and snapshot scope", () => {
  const data = {
    candidates: [{ ...recent, id: "lead" }],
    opportunities: [
      recent,
      old,
      { ...recent, id: "future", knownAt: "2026-09-13T00:00:00Z" },
      { ...recent },
    ],
  };
  const rows = researchLibrary(data, now, "week", "");
  assert.deepEqual(
    rows.map((r) => r.id),
    ["recent", "lead"],
  );
  assert.equal(rows[1].kind, "candidate");
  assert.equal(rows[1].current, false);
  assert.equal(researchLibrary(data, now, "snapshot", "").length, 4);
  assert.equal(data.opportunities.length, 4);
});
test("research library searches real IDs and never invents rows", () => {
  assert.deepEqual(
    researchLibrary({ candidates: [], opportunities: [] }, now, "week", ""),
    [],
  );
  assert.deepEqual(
    researchLibrary({ candidates: [], opportunities: [old] }, now, "week", ""),
    [],
  );
  assert.equal(
    researchLibrary(
      { candidates: [], opportunities: [old] },
      now,
      "snapshot",
      "OLD",
    )[0].id,
    "old",
  );
  assert.equal(
    entityDetailPath("candidate", "candidate-1"),
    "/proxy/api/v1/candidates/candidate-1",
  );
});
