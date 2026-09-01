import assert from "node:assert/strict";
import test from "node:test";

import {
  sourceIdentity,
  summarizeSourceRecords,
} from "../src/lib/source-posture.ts";

test("per-cycle source posture records fold into the latest provider state", () => {
  const summary = summarizeSourceRecords([
    {
      id: "cycle-1:finlight_transport",
      source_id: "finlight_transport",
      knownAt: "2026-08-31T10:00:00Z",
      posture: "degraded",
      reason: "connector_backoff",
    },
    {
      id: "cycle-2:finlight_transport",
      source_id: "finlight_transport",
      knownAt: "2026-08-31T10:05:00Z",
      posture: "healthy",
    },
    {
      id: "cycle-2:massive_transport",
      source_id: "massive_transport",
      knownAt: "2026-08-31T10:05:00Z",
      posture: "healthy",
    },
  ]);

  assert.equal(summary.totalIdentityCount, 2);
  assert.equal(summary.foldedRecordCount, 1);
  const finlight = summary.visible.find(
    ({ identity }) => identity === "finlight_transport",
  );
  assert.equal(finlight?.latest.posture, "healthy");
  assert.equal(finlight?.history.length, 1);
  assert.equal(finlight?.history[0].posture, "degraded");
});

test("bounded source posture prioritizes current issues and reports omissions", () => {
  const summary = summarizeSourceRecords(
    [
      {
        id: "healthy",
        knownAt: "2026-08-31T10:10:00Z",
        posture: "healthy",
      },
      {
        id: "stale",
        knownAt: "2026-08-31T10:00:00Z",
        posture: "stale",
        reason: "freshness_expired",
      },
    ],
    1,
  );

  assert.equal(summary.visible[0].identity, "stale");
  assert.equal(summary.hiddenIdentityCount, 1);
  assert.equal(summary.foldedRecordCount, 0);
});

test("aggregate ids without source metadata use the stable suffix identity", () => {
  assert.equal(
    sourceIdentity({
      id: "cycle-204:massive_transport",
      knownAt: "not-a-date",
    }),
    "massive_transport",
  );
  const summary = summarizeSourceRecords([
    {
      id: "cycle-older:massive_transport",
      knownAt: "not-a-date",
      posture: "degraded",
    },
    {
      id: "cycle-current:massive_transport",
      knownAt: "2026-08-31T10:00:00Z",
      posture: "healthy",
    },
  ]);
  assert.equal(summary.visible[0].latest.posture, "healthy");
  assert.equal(summary.visible[0].history.length, 1);
});
