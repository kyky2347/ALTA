# Bootstrap milestone record

This record summarizes the accepted B0–B8 engineering stages that produced the
current ALTA Opportunity OS. It replaces verbose working reports whose commands,
test counts, and intermediate constraints were superseded by later stages.

Historical acceptance means that a bounded engineering gate passed at that time.
It does not establish current security, performance, or Alpha. Current claims
are defined by the root README, tests, and active operations documentation.

## Timeline

| Stage | Delivered capability | Historical gate |
| --- | --- | --- |
| B0 | Publication boundary and Bootstrap policy | Passed |
| B1 | Typed PostgreSQL runtime and read API | Passed |
| B2 | Raw-first adapters and point-in-time Evidence | Passed |
| B3 | Four isolated autonomous Scouts | Passed |
| B4 | Foundry, private challenge, and deterministic rank | Passed |
| B5 | Expression, Shadow fill, ledger, and isolated Paper boundary | Passed |
| B6 | One-command deterministic lifecycle and replay | Passed |
| B7 | Autonomous scheduler, recovery, API, and SSE | Passed |
| B8 | Real-data Shadow, independent audit, and Alpha measurement | Passed |

## B0 — publication boundary

B0 established the repository safety posture:

- local runtime, credentials, keys, certificates, databases, caches, and build
  output were excluded from distributable source;
- local file tools rejected sensitive roots and symlink escape;
- provider credentials remained in the parent gateway boundary;
- Massive and Tiger defaulted to disabled;
- Paper-only and Shadow-only policy values were made explicit;
- an initial manifest and test baseline were recorded.

The original manifest described a dirty development worktree and is no longer a
current release artifact. Modern releases use fresh-source verification and
full-tree/history secret scans instead.

## B1 — typed persistence and service skeleton

B1 added:

- the installable Python Opportunity OS package;
- explicit schema migration commands;
- typed tables with `environment`, `version`, and timezone-aware `known_at`;
- loopback liveness, readiness, summary, and cursor SSE;
- bounded supervisor restart and signal handling;
- PostgreSQL as durable state and Redis as disposable support.

Acceptance covered migration up/down/up, invalid environment rejection, API and
SSE behavior, service restart, and clean test-database teardown.

## B2 — point-in-time source contracts

B2 added:

- Raw, Evidence, source, and connector contracts;
- source provenance, content hash, observation time, and known time;
- explicit healthy, degraded, unavailable, malformed, and rate-limited posture;
- deadline, pacing, and bounded payload behavior;
- point-in-time selection that rejects future-known Evidence.

No autonomous model, broker, or order capability was introduced.

## B3 — isolated Scout runtime

B3 added four distinct Scout roles and the durable run lifecycle:

- role-specific missions, source territories, and read-only tools;
- frozen inputs and strict Candidate or no-op outputs;
- model, prompt, budget, deadline, thread, turn, and Evidence provenance;
- separate App Server clients and bounded concurrency;
- invalid-output, timeout, and sibling-failure isolation;
- replay recovery for succeeded roles.

Acceptance proved that one failed Scout did not invalidate the other results and
that Candidate Evidence could be traced to the frozen wake or successful tool
calls.

## B4 — Opportunity Foundry and challenge

B4 added:

- stable exact and structural identities;
- duplicate, merge, competing, and related relationships;
- reversible merges and append-only relation events;
- Evidence-bound completion of missing fields;
- locked Thesis and Disconfirming assessments;
- bounded Moderator discussion;
- a deterministic `swing_5_20d` ranking book with explicit components.

Acceptance covered input-order invariance, opposite-direction merge prevention,
assessment privacy, no-information-gain stopping, deterministic tie-breaks, and
unchanged Evidence counts across discussion.

## B5 — expression and internal Shadow accounting

B5 added:

- Stock, ETF, and Wait expression contracts, followed later by Option support;
- quote provenance and point-in-time validation;
- spread, cost, freshness, side, quantity, and notional gates;
- version binding across Opportunity, Evidence, Expression, and position;
- post-intent Shadow fill rules using conservative sides of the spread;
- balanced append-only double-entry ledger events;
- frozen position thesis, monitor, and deterministic exit policy;
- an independently installable fake/read-only Paper boundary.

Acceptance demonstrated idempotent open, monitor, close, and ledger behavior with
no broker SDK or network dependency in the main research path.

## B6 — complete deterministic lifecycle

B6 connected source wake, Scouts, Foundry, assessment, discussion, ranking,
expression, Shadow open, monitoring, and exit under one orchestrator.

The fixture path introduced stable lifecycle IDs, stage checkpoints,
`MVP_RUNNING`, `MVP_IDLE`, replay hashing, and failure injection. Acceptance
required identical demo and replay hashes plus recovery from every checkpoint
without later Evidence entering the original decision time.

## B7 — autonomous Shadow service

B7 added:

- a recurring UTC scheduler with PostgreSQL advisory-lock ownership;
- durable source cursors and cycle checkpoints;
- bounded cycle failure and supervisor restart behavior;
- heartbeat-aware readiness;
- read API detail for runs, Opportunities, Expressions, Agents, and state;
- cursor-based lifecycle SSE for a future dashboard;
- normal handling of idle cycles and client disconnects.

Acceptance covered single-owner enforcement, restart recovery, no duplicate
cycles, authenticated loopback reads, graceful signal shutdown, and no remaining
managed child process.

## B8 — real-data Shadow and measurement

B8 added:

- bounded Massive snapshots, daily bars, exact quotes, and on-demand option chain;
- Finlight REST ingestion with cursor and cooldown;
- Stock, ETF, long Call, long Put, or Wait recommendation;
- deterministic option selection and cost validation;
- an independent Expression Auditor with the ranking score hidden;
- cross-cycle Shadow positions and a falsifier-only Position Monitor Agent;
- forward quote polling that never backfills an old price as a fill;
- cost-adjusted return and SPY-relative realized Alpha measurement;
- an explicit `Alpha is unproven` state.

The final controlled acceptance discovered a real QQQ downside-dislocation
Candidate, formed a five-day Opportunity, completed both private assessments,
discussion, ranking, expression, and independent audit, and safely resolved to
Wait. It created no position, ledger transaction, broker request, or order.

## Lessons carried forward

The Bootstrap sequence established several permanent project rules:

- an honest no-op is better than a fabricated opportunity;
- discussion is not Evidence;
- market facts and accounting belong to deterministic code;
- independent contexts are more valuable than a large shared chat;
- recovery must preserve the original point-in-time snapshot;
- refusal paths are part of the product, not error cases;
- a completed pipeline is not Alpha evidence;
- capital capability requires a separate, explicitly authorized system.

## Current verification

Do not reuse historical test counts. Run the current acceptance commands from a
freshly unpacked source archive:

```shell
corepack pnpm install --frozen-lockfile
corepack pnpm check
./alta env setup --dev
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
```

Then follow [Reproducibility](../../REPRODUCIBILITY.md) and the active
[Autonomous Shadow runbook](../operations/autonomous-shadow.md).
