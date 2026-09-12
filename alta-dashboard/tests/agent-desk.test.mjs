import assert from "node:assert/strict";
import test from "node:test";
import {
  agentDeskSnapshot,
  agentInputTokens,
  agentRoleBrief,
  committeeAgents,
  recentAgentRuns,
  opportunityCommitteeAgents,
} from "../src/lib/agent-desk.ts";
import {
  previewStatus,
  previewRuntime,
  previewEvents,
} from "../src/lib/preview.ts";

test("opportunity flow requires an explicit run binding and never borrows a global reviewer", () => {
  const agents = [
    { id: "thesis", runId: "run-old" },
    { id: "disconfirming", runId: "run-linked" },
    { id: "committee-moderator", runId: "run-moderator" },
  ];
  const status = {
    agents,
    assessments: [
      { opportunityId: "other", runId: "run-old" },
      { opportunityId: "selected", runId: "run-linked" },
    ],
    discussions: [
      { opportunityId: "selected", detail: { run_id: "run-moderator" } },
    ],
  };
  assert.deepEqual(
    opportunityCommitteeAgents(status, "selected"),
    agents.slice(1),
  );
  assert.deepEqual(opportunityCommitteeAgents(status, "unknown"), []);
  assert.deepEqual(
    opportunityCommitteeAgents(
      { ...status, assessments: [], discussions: [] },
      "selected",
    ),
    [],
  );
});

test("explicit recent scope excludes old records without suppressing current failures", () => {
  const now = Date.parse("2026-09-12T12:00:00Z");
  const base = { id: "thesis", runId: "test", status: "failed" };
  const old = { ...base, knownAt: "2026-08-01T00:00:00Z" };
  const recent = { ...base, knownAt: "2026-09-12T11:00:00Z" };
  const running = { ...old, status: "running" };
  const unknown = { ...base, knownAt: "bad-date" };
  const agents = [old, recent, running, unknown];
  assert.deepEqual(recentAgentRuns(agents, now), [recent, running, unknown]);
  assert.equal(agents.length, 4);
});

test("agent desk shows the complete preview team with exact snapshot counts", () => {
  const desk = agentDeskSnapshot(previewStatus, previewRuntime, previewEvents);
  assert.equal(desk.research.length, 3);
  assert.equal(desk.review.length, 5);
  assert.deepEqual(
    committeeAgents(previewStatus.agents).map((a) => a.id),
    ["thesis", "disconfirming", "committee-moderator"],
  );
  assert.deepEqual([desk.running, desk.completed, desk.waiting], [3, 3, 2]);
  assert.equal(
    new Set([...desk.research, ...desk.review].map((a) => a.runId)).size,
    8,
  );
  assert.equal(desk.recent.length, 3);
  assert.equal(desk.recent[0].eventId, "evt-1842");
  for (const agent of desk.research) {
    const mind = desk.minds.get(agent.id);
    assert.ok(mind.rollingSummary);
    assert.equal(mind.modelId, agent.modelId);
    assert.equal(mind.modelProvider, agent.modelProvider);
  }
  const model = (role) =>
    previewStatus.agents.find((a) => a.id === role).modelId;
  assert.equal(model("committee-moderator"), "gpt-5.6");
  assert.notEqual(model("thesis"), model("disconfirming"));
  assert.notEqual(model("expression"), model("audit"));
});

test("missing records never become fabricated work or tokens", () => {
  const empty = agentDeskSnapshot({ agents: [] }, null, []);
  assert.deepEqual([empty.running, empty.completed, empty.waiting], [0, 0, 0]);
  assert.equal(empty.recent.length, 0);
  const agent = {
    id: "unknown",
    runId: "run-1",
    status: "failed",
    knownAt: "2026-09-11T00:00:00Z",
  };
  assert.equal(agentDeskSnapshot({ agents: [agent] }, null, []).running, 0);
  assert.equal(agentInputTokens(agent), undefined);
  for (const invalid of [NaN, -1, Infinity])
    assert.equal(
      agentInputTokens({ ...agent, usage: { input_tokens: invalid } }),
      undefined,
    );
  assert.equal(agentInputTokens({ ...agent, usage: { input_tokens: 0 } }), 0);
  assert.equal(agentRoleBrief(agent.id), "deskOtherRole");
  assert.equal(agentRoleBrief("disconfirming"), "deskChallengeRole");
});

test("activity sorting is bounded and does not mutate source records", () => {
  const events = [...previewEvents].reverse();
  const original = events.map((e) => e.eventId);
  const result = agentDeskSnapshot(previewStatus, previewRuntime, events);
  assert.deepEqual(
    events.map((e) => e.eventId),
    original,
  );
  assert.ok(
    result.recent.every((e, i, all) => !i || all[i - 1].cursor > e.cursor),
  );
});

test("successful backend runs are included in completed desk counts", () => {
  const agents = ["running", "succeeded", "completed", "waiting", "failed"].map(
    (status, index) => ({ id: `role-${index}`, runId: `run-${index}`, status }),
  );
  const desk = agentDeskSnapshot({ agents }, null, []);
  assert.deepEqual([desk.running, desk.completed, desk.waiting], [1, 2, 1]);
});
