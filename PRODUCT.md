# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Inferred from the explicit brief and repository constraints: a local web
operator console compiled to static HTML, CSS, and JavaScript, backed by an
ALTA-owned loopback control process. The console may use React, TypeScript,
Tailwind CSS, and official shadcn/ui source components, but it must remain a
separate first-party boundary from the vendored Codex runtime.

## Users

Primary user: the ALTA operator on the same machine, supervising autonomous
research during live and replay sessions. The operator needs to understand
system health, current work, Agent reasoning artifacts, handoffs, historical
decisions, opportunities, expressions, Shadow positions, and failures without
reading logs or querying PostgreSQL manually.

This user model is inferred from the explicit dashboard request and the
repository's loopback-only operating model.

## Product Purpose

ALTA is a research-only virtual trading platform operated by specialized LLM
Agents. The operator console makes its evidence-to-opportunity lifecycle
observable and controllable: see what is happening now, reconstruct what
happened before, inspect what every Agent received and produced, and safely
start or stop the research runtime.

Success means an operator can answer within seconds whether ALTA is safe,
healthy, idle, researching, deliberating, expressing, observing, or stopped;
then drill into the exact durable artifacts behind that state.

## Positioning

The console is not a generic market terminal. It visualizes ALTA's distinctive
mechanism: Opportunities are researched and debated first; instruments are only
candidate carriers selected later under evidence, audit, portfolio, and Paper
boundaries.

## Operating Context

- The console runs locally on a desktop alongside ALTA's supervisor, research
  runtime, PostgreSQL, and Redis.
- The Opportunity OS exposes authenticated loopback JSON and cursor-based SSE.
- Operators need both a live operations surface and a durable historical
  investigation surface.
- Agent prompts, frozen inputs, tool-use metadata, artifacts, handoffs, and
  outcomes may be inspected, but credentials and hidden secrets must never be
  rendered.
- A stopped research runtime must remain startable from the console; therefore
  the console control process is operationally separate from the runtime it
  manages.

## Capabilities and Constraints

- Show liveness, readiness, heartbeat, current cycle, next cycle, failure
  streak, data-source posture, model routes, token/latency information, and
  safety boundaries in real time.
- Show current and historical Runs, Candidates, Opportunities, assessments,
  debates, ranks, expressions, audits, Shadow positions, events, and Alpha
  evaluation summaries using the canonical backend records.
- Make Agent-to-Agent work legible as ordered artifact handoffs without
  pretending that hidden chain-of-thought is available.
- Provide search, time range, status, role, Opportunity, and cycle filters; a
  command palette; reconnect states; empty states; and accessible detail views.
- Start, stop, and restart the research runtime from authenticated loopback
  controls with explicit confirmation and progress feedback.
- Never add a live brokerage path, expose credentials, expose an order API, or
  weaken deterministic Wait, replay, idempotency, recovery, or capital
  isolation.
- Tiger remains Paper-only and capital remains disabled by default. Control
  actions must not silently enable either.
- The dashboard may summarize structured reasoning artifacts but must label
  unavailable private model reasoning honestly.

## Brand Commitments

- Product name: ALTA — Autonomous LLM Trading Asterism.
- Research-only; never present simulated, replay, or Shadow outcomes as proven
  Alpha or investment performance.
- Design philosophy: trade the Opportunity; execute only its most suitable
  carrier.
- Requested visual character: high-end Apple-like operational clarity—clean,
  calm, precise, responsive, and human—without decorative finance clichés.

## Evidence on Hand

- Canonical JSON/SSE endpoints and durable PostgreSQL state in
  `alta-runtime/python/src/alta_asterism/`.
- Existing service lifecycle and host supervision in `alta-src/` and `./alta`.
- Current architecture and endpoint contracts in `docs/architecture/` and
  `docs/operations/`.
- Existing tests cover lifecycle, API, SSE, recovery, replay, and shutdown.
- Repository screenshots are generated only from the visibly labeled synthetic
  preview and contain no account or performance data. No production performance
  claim or live brokerage evidence is available; the interface must not
  fabricate either.

## Product Principles

1. Truth before spectacle: every visible state must come from a canonical
   record or be clearly marked as unavailable.
2. Now and then together: live supervision and historical reconstruction are
   two views of the same event ledger.
3. Opportunity before instrument: research and disagreement remain visible
   before expression and carrier selection.
4. Control without authority creep: operator convenience never creates Agent
   trading authority or bypasses Paper and safety gates.
5. Calm under failure: degraded sources, stale heartbeats, retries, and stopped
   services must be obvious and recoverable without alarm fatigue.

## Accessibility & Inclusion

Target WCAG 2.2 AA for keyboard operation, focus visibility, contrast, motion
reduction, screen-reader structure, and status announcements. Never rely on
color alone to communicate health, risk, state, or selection.
