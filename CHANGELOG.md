# Changelog

Notable ALTA changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
semantic versioning while the project remains experimental.

## [Unreleased]

## [0.25.0] - 2026-08-27

### Added

- A delayed, symmetric, and revocable research incentive derived only from
  closed, cost-adjusted, benchmark-relative Shadow outcomes after a 30-position
  maturity gate.
- Prospective incentive contracts in every Trader Mind wake and read-only API
  projection of the same zero-capital boundary.

### Safety

- Candidate count, turnover, self-reported confidence, and raw profit earn
  nothing. Incentives may add only one read-only research call and 8,000 tokens;
  they cannot change ranking, risk, capital, execution, or broker authority.
- Immature, negative, or statistically uncertain results do not receive a
  positive reward and a previously granted bonus is revoked when the bound no
  longer clears zero.

## [0.24.0] - 2026-08-27

### Changed

- Both private Assessors must estimate a defensible reference-class base rate
  before their evidence-specific inside view.
- Admission requires two positive independent probability lifts, a conservative
  expected-Alpha result after a fixed disagreement reserve, and decision-grade
  recorded research diligence.

### Safety

- Rejected Candidates stop before expression, market validation, or audit. The
  gate controls false positives; it does not establish forecast accuracy or
  profitable Alpha.

## [0.23.0] - 2026-08-27

### Added

- A point-in-time rolling capital-survival controller over the latest
  cost-adjusted SPY-relative measurement for current-policy Shadow positions.
- Collecting, probation, and preservation postures visible to implementation
  and reloaded immediately before intent.

### Safety

- Negative evidence and drawdown can reduce later synthetic Shadow size;
  favorable evidence can restore ordinary size but never add leverage.

## [0.22.0] - 2026-08-27

### Changed

- Ranking, construction, and Alpha decay use the lower independent expected
  Alpha forecast minus 25% of forecast dispersion.
- Research quality below `0.60` resolves to `Wait`; intermediate quality is
  capped at half-size starter capital.
- Forward calibration reads the exact cost-adjusted forecast frozen at entry and
  reports bounded small-sample descriptive statistics.

## [0.21.0] - 2026-08-27

### Added

- Deterministic research-process quality from actual cross-checking, independent
  source families, route diversity, and completed non-news work.
- Separate persistence of both scenario forecasts and their disagreement.

### Safety

- Process quality remains non-Evidence and cannot rescue a thesis that fails
  evidence, freshness, liquidity, readiness, or audit gates.

## [0.20.0] - 2026-08-27

### Added

- First-class Alpha-source, systematic-exposure, hedge-posture, and basis-risk
  contracts for every proposed payoff.
- Independent reclassification by a different-model Auditor and shared factor
  capacity across otherwise different tickers.

### Safety

- Unsupported pairs, spreads, baskets, and dynamic hedges resolve to `Wait`.
  Marginal admissible ideas receive starter size rather than bonus capital.

## [0.19.0] - 2026-08-26

### Added

- A mandatory new-underwriting PM decision record that separates what is priced
  in, variant view, reference class/base rate, inside view, must-be-true
  conditions, company-thesis status, security readiness, and action trigger.
- A conservative per-view edge half-life shared by ranking, expression,
  implementation audit, and portfolio construction.

### Changed

- Ranking now rejects broken, re-underwrite, not-decision-grade, legacy-missing,
  and no-independent-ready states rather than averaging away the blocker.
- Freshness and implementation Alpha decay use the shorter independent edge
  half-life instead of treating the full Opportunity horizon as durable edge.
- Expression and audit roles receive the same locked decision record and must
  match payoff purity and timing to it.
- Production Scout inputs are fitted against both the durable snapshot limit
  and the complete rendered prompt limit as registry and Mind memory grow.
- Flash Scouts retain a bounded 180-second window, while heterogeneous PM,
  debate, expression, and audit roles use a separate 300-second window.
- A transient deadline may be retried once with the same frozen input and Run
  identity; deterministic budget, schema, evidence, and policy failures are not
  retried.

### Safety

- Historical underwriting remains readable, but missing decision intelligence
  resolves to `Wait`; no legacy value is fabricated during upgrade.
- Repository-host APIs are absent from the research tool surface.
- The release does not add Agent broker tools, a live account path, or any new
  capital mutation authority.

## [0.18.0] - 2026-08-26

### Added

- A point-in-time Thesis Ledger that requires each production Candidate to
  state one to three observable causal pillars with separate confirmation and
  invalidation conditions and a resolution date inside the idea horizon.
- Stable Foundry pillar identity, semantic merge, Candidate/Evidence
  provenance, API projection, and exact follow-up questions.
- Claim-to-payoff lineage: every non-Wait expression hypothesis must identify
  the frozen thesis pillars it monetizes, and the selected IDs are frozen into
  the Position Thesis.
- Append-only position reviews with `confirming`, `weakening`, `invalidated`,
  and `unresolved` states, exact newer-Evidence binding, and durable review
  events that never rewrite original underwriting.

### Changed

- Expression and audit prompts now distinguish a listed ticker match from a
  payoff that actually isolates a tracked causal claim.
- The implementation-audit context is deliberately compacted to preserve the
  existing hard prompt and frozen-input budgets for a three-entry expression
  slate; no budget or capital boundary was loosened.
- Opportunity research agendas may carry an exact Thesis Ledger verification
  question into a later autonomous Trader Mind wake.

### Safety

- Missing, duplicated, invented, partial, or uncited pillar reviews fail closed.
- Thesis reviews remain research judgment. Agent-authored thresholds cannot
  mutate deterministic risk policy, capital limits, or the Paper boundary.
- Shadow remains the default and Tiger remains explicit Paper-only acceptance;
  no live account or live-order path was added.

## [0.17.0] - 2026-08-26

### Added

- A bounded cross-cycle research agenda derived from a prior Scout's next test
  and first rejection plus missing Evidence named by both independently locked
  Assessors.
- Explicit `explore` and `follow_up` research lineage on Candidate and no-op
  artifacts, with exact frozen parent Opportunity and question binding for
  follow-up work.
- Entry-frozen research-mode attribution and maturity-gated mode slices in the
  same point-in-time Alpha feedback used for Mind, archetype, and tool route.
- Read-only Opportunity detail fields for open research questions, contributor
  lineage, beneficiary path, counterevidence, next test, and strongest research
  diligence so a future dashboard can explain the loop.

### Changed

- Every Trader Mind now autonomously chooses between broad new exploration and
  differentiated follow-up research. Exploration remains first-class; the
  presence or rank of a prior Opportunity creates no deterministic priority.
- Per-Mind process memory records bounded explore/follow-up history, including
  an honest follow-up no-op, without promoting prior claims into Evidence.
- Foundry and downstream role context preserve research lineage across merged
  Candidates, while Shadow attribution retains each contributing Candidate's
  own lineage.
- Scout and memory contracts advance to `alta.scout-output.v3`,
  `alpha-trader-v7`, and `alta.trader-mind-memory.v3`.

### Safety

- A follow-up must copy one exact open question from a frozen prior Opportunity;
  invented parents and unregistered questions fail validation.
- Follow-up still requires current frozen or newly collected auditable Evidence
  for a Candidate. Research questions, prior Opportunities, process diligence,
  and outcome feedback remain non-Evidence and cannot bypass ranking, audit,
  market, portfolio, execution, or capital gates.
- Performance remains hidden until 30 benchmarked Mind positions and 10
  benchmarked observations per research-mode slice. No automatic policy change
  is enabled, and no live-capital path is added.

## [0.16.0] - 2026-08-26

### Added

- A typed research-diligence record derived from actual Scout tool provenance,
  completed active and non-news work, independent source families and domains,
  beneficiary-path coverage, counterevidence, and the next observable test.
- A bounded expression tournament in which the implementation PM can propose
  up to three distinct Stock, ETF, Option, or Wait payoff hypotheses. Each
  receives its own real market, portfolio-construction, Alpha-clock, and
  capital-allocation ticket before independent audit.
- Independent expression selection: approval of a multi-entry slate must name
  exactly one admissible hypothesis, while missing, invalid, ambiguous, or
  unavailable selection resolves to `Wait`.
- Execution-plan v2 fields for arrival benchmark, frozen absolute limit,
  implementation-shortfall budget, participation cap, urgency, recommended
  child slices, and a single permitted attempt.

### Changed

- Scout output now asks for a causal beneficiary path, the strongest
  disconfirming source or observation, and the next cheap test. Foundry carries
  the strongest contributing diligence record into downstream deliberation as
  process metadata rather than Evidence.
- Deliberation can distinguish cross-checked research from shallow or
  news-only work without converting process quality into an automatic approval
  score.
- The independent Auditor compares the compact market-validated slate and
  current book, then selects one expression or chooses `Wait`. The selected
  instrument is re-quoted, reconstructed, and reallocated before admission.
- Shadow fill and explicit Tiger Paper acceptance consume the exact frozen
  limit instead of deriving a new price from a later ask. An adverse move past
  the limit produces no fill rather than a market chase.
- The expression slate is capped at three so the global eight-request Massive
  cycle budget can remain fail-closed through selected-instrument refresh.
- Service status now verifies host and scheduler PIDs before reporting them as
  running, labels crash-left state as stale, and lets a stop command converge a
  dead host record to `stopped`.

### Safety

- Research diligence is explicitly non-Evidence: it records what work occurred
  but cannot establish the truth of a claim or bypass independent review.
- No Agent receives an executor, live-account path, or live-capital mode. Tiger
  remains an isolated, explicitly invoked, one-share Paper-only acceptance
  boundary.
- These changes improve research selectivity, implementation comparison, and
  execution reproducibility; they do not establish real-world Alpha.

## [0.15.0] - 2026-08-26

### Added

- A point-in-time Alpha clock that records evidence age, remaining horizon,
  time-adjusted expected net Alpha, catalyst clarity, and the next facts that
  should reprice the thesis. The current linear decay is an explicit,
  conservative research proxy rather than a fitted return model.
- Active-capital allocation that admits a Candidate into spare capacity or,
  when the book is full, compares it with the weakest fully underwritten
  incumbent using a frozen replacement hurdle.
- Guarded execution tickets with observed participation, quote freshness,
  bounded DAY limit offsets, timeout cancellation, and mandatory
  re-underwriting before any retry.
- PostgreSQL integration coverage for an idempotent full-book rotation through
  incumbent exit, replacement entry, monitoring, performance attribution, and
  replay-safe duplicate handling.

### Changed

- Portfolio admission now consumes time-adjusted rather than static expected
  net Alpha and revalidates both the candidate and mutable book immediately
  before entry.
- A full book receives only conservative prospective gross credit for the
  smallest incumbent. The incumbent is not closed until the candidate clears
  independent implementation audit, intrinsic risk checks, liquidity checks,
  and the residual-Alpha hurdle.
- Position time exits use the remaining Alpha horizon at entry. Tiger Paper
  acceptance, when explicitly enabled, consumes the same bounded execution
  ticket; normal operation remains internal Shadow.
- Existing expression and position recovery returns the durable opening ledger
  before duplicate gates, making interrupted lifecycle continuation explicitly
  idempotent.

### Safety

- Missing incumbent underwriting, stale evidence, exhausted Alpha horizon,
  inadequate replacement advantage, or invalid execution state deterministically
  resolves to `Wait` without closing an existing position.
- Rotation is ordered exit-before-entry and remains Paper-safe, but live
  brokerage accounts and live order paths are still unsupported. Capital mode
  is disabled by default and research Agents never receive an executor.
- This release improves research discipline and testability; it does not claim
  that real-world Alpha has been demonstrated.

## [0.14.0] - 2026-08-26

### Added

- A typed portfolio-construction ticket for every production expression,
  including intended Alpha, unwanted and retained exposures, expected edge,
  cost, stress loss, synthetic Shadow NAV, gross exposure, exit capacity,
  target size, and the binding constraint.
- Deterministic position, gross, per-trade loss, liquidity-participation, and
  minimum net-Alpha policies, with a second mutable-book check immediately
  before an entry intent.
- Read-only expression API access to the exact frozen implementation plan.

### Changed

- Every Trader Mind now searches a broader active-fund surface. News remains
  available but is explicitly treated as only one locator alongside market and
  options dislocations, filings, operating artifacts, public software,
  pricing, supply chains, policy transmission, and expectation primitives.
- The Expression Agent must compare stock, ETF/proxy, long option, and Wait;
  state intended Alpha and residual exposures; and explain rejected
  alternatives. Unsupported pairs, shorts, spreads, baskets, or dynamic hedges
  resolve to Wait rather than an approximate single-leg bet.
- Equity and ETF sizing consumes Massive snapshot day-volume as a bounded exit
  liquidity proxy without adding another market-data request. Long options are
  sized with premium-at-risk and open-interest participation.
- Post-audit refresh now preserves the audited instrument identity and reruns
  portfolio construction against the exact refreshed quote.
- Tiger Paper acceptance limit prices use a 25 bps execution guard instead of
  a one-percent crossing allowance; no-fill remains the safe outcome.

### Safety

- Portfolio plans never authorize an order and use only a synthetic Shadow NAV;
  live accounts and live capital remain unsupported.
- Missing independent underwriting, liquidity capacity, net edge, risk budget,
  or independent implementation audit deterministically produces Wait.
- Normal operation remains internal Shadow. Tiger is still an explicit,
  isolated, one-share Paper-only acceptance boundary.

## [0.13.0] - 2026-08-25

### Added

- A typed Alpha archetype on every production Candidate, restricted to the
  originating Trader Mind's frozen mandate.
- Immutable position-open contributor credit for the originating Candidate,
  Trader Mind, Alpha archetype, and bounded research-tool route.
- A point-in-time `/api/v1/alpha/feedback` projection for per-Mind,
  per-archetype, and research-route Shadow outcomes.

### Changed

- Later wakes give each Trader Mind only its own outcome feedback alongside
  process memory. The feedback is frozen, replayable, and explicitly
  non-Evidence.
- Position performance events carry the contributor snapshot captured at
  entry, so later Opportunity merges cannot rewrite historical research credit.
- The frozen-wake recovery and dashboard API include the same feedback snapshot
  without re-reading future state.
- Durable Scout packing now budgets the complete `{scout,input}` record rather
  than the input alone. Recovery validates the common wake identity, merges
  role-scoped snapshots, and accepts a frozen Mind version only when it is
  either current or already present in that cycle's immutable run history.
- Autonomous retries retain the interrupted cycle identity and point-in-time
  wake. On scheduler startup, expired orphan Scout runs and their jobs are
  closed through the durable failure state instead of remaining ghost work.

### Safety

- Performance values remain hidden until a Mind has 30 benchmarked closed
  Shadow positions; archetype and route slices additionally require 10 samples.
- Feedback cannot change ranking, prompts, tools, models, budgets, expression
  policy, or capital allocation automatically. Real-world Alpha remains
  unproven and normal capital mode remains disabled.
- Headline forecast probability is validated against the submitted scenario
  distribution before a role output can succeed. Exhausted or unavailable
  private judgment roles reject that Opportunity as insufficiently audited;
  they do not crash the autonomous scheduler or bypass deterministic Idle/Wait.

## [0.12.0] - 2026-08-25

### Added

- A secret-free `./alta credentials` control surface for status, validation,
  hidden-input replacement, and controlled service reload across LLM, market,
  news, and optional research-tool credential slots.
- Credential revision and configured-slot posture in the host state and
  read-only runtime API; values are never exposed.
- Bounded Trader Mind memory v2 with cumulative outcome/tool-use counters and
  two recent process lessons.

### Changed

- Credential files are selected deterministically, reject ambiguous matches,
  enforce owner-only regular files and a size bound, and are replaced with an
  fsync-backed same-directory rename.
- An active service is restarted after a successful credential replacement. A
  failed readiness check atomically restores the prior file and retries service
  recovery.
- Trader Minds use accumulated process experience to vary search routes and
  avoid repeated dead ends while re-proving every investment claim.

### Safety

- Credential values remain outside the worktree and are not accepted as CLI
  arguments, printed, persisted in service settings, or exposed to Agents.
- Mind memory remains non-Evidence and cannot change tools, budgets, ranking,
  capital policy, or executable code.

## [0.11.0] - 2026-08-25

### Added

- A shared active-research surface for every discovery Trader Mind: bounded Web
  research, global news, public social search, and public finance data, plus
  archetype-specific feed, archive, crawl, and academic tools.
- Per-Mind Alpha archetypes, research sequences, and explicit skepticism lenses.
- Bounded prior-cycle Trader Mind experience in each frozen wake, validated
  against PostgreSQL and kept separate from auditable Evidence.

### Changed

- Production discovery now fails one Mind in isolation when it completes without
  attempting an allowed active research tool; passive Evidence alone is not a
  completed Trader Mind turn.
- Completed turns persist deterministic experience summaries covering outcome,
  first rejection, completed tools, and collected-source count.
- Frozen-wake crash recovery now merges role-isolated Mind memories alongside
  Evidence without polling sources or accepting later state.

### Safety

- Trader Minds still run read-only with deny-all approvals, hard tool/token/time
  budgets, no desktop apps or unrestricted plugins, and no broker capability.
- Mind experience is process memory, never a fact, citation, rank input, or
  authorization to mutate missions, tools, policies, or capital boundaries.

## [0.10.0] - 2026-08-25

### Added

- Evidence-bound, direction-normalized bull/base/bear scenario underwriting
  versus SPY for both locked private assessments.
- Deterministic odds-aware ranking components for consensus expected Alpha,
  downside resilience, payoff asymmetry, catalyst clarity, crowding, liquidity,
  and scenario disagreement.
- Read-only underwriting detail on Opportunity/status APIs and direct-stock
  ex-ante versus forward-Shadow calibration on `/api/v1/alpha/summary`.

### Changed

- Self-reported Agent confidence remains auditable but no longer receives a
  positive ranking weight.
- Expression and independent audit receive both locked scenario summaries while
  the independent Auditor continues to be blinded to the ranking score.

### Verified

- Scenario coherence, evidence binding, migration up/down/up, ranking behavior,
  structured-role recovery, full Opportunity OS regression, and the controlled
  Shadow lifecycle pass first-party coverage.

### Safety

- Underwriting is explicitly an ex-ante research estimate, never observed
  performance. Calibration excludes options and proxy ETFs whose payoff basis is
  not comparable to pre-expression security underwriting.
- Small samples never tune prompts, routes, or weights automatically; Alpha
  remains unproven and the normal capital mode remains disabled.

## [0.9.0] - 2026-08-25

### Added

- An immutable, non-secret forward-evaluation configuration binding for every
  autonomous cycle, with explicit cohort and protocol identity.
- Indexed `cycle_id` attribution for Scout, assessment, debate, expression,
  audit, and position-monitor Agent runs.
- A bounded `/api/v1/evaluation/summary` projection for configuration drift,
  source and Agent coverage, Idle/Wait/instrument attempts, benchmark
  missingness, and minimum-sample readiness.

### Verified

- Same-cycle configuration rebinding fails closed, while deliberate changes in
  the same cohort remain visible as configuration drift.
- Migration up/down/up, Agent-run recovery, autonomous failure recovery, API,
  and full regression suites pass with the new cycle attribution.

### Safety

- Cohort fingerprints contain no credential values or machine-local workspace
  paths, responses are capped at 10,000 cycles, and evaluation is read-only.
- Sample readiness never changes model, prompt, source, ranking, or capital
  policy automatically; Alpha remains unproven.

## [0.8.0] - 2026-08-24

### Added

- A durable cross-cycle Opportunity Registry between batch Foundry and private
  assessment, with idempotent `refreshed`, `suppressed`, and
  `position_updated` events.
- Stable v2 Opportunity identity based on normalized entity, event or catalyst,
  direction, and holding-period buckets rather than free-form mechanism prose.
- Bounded prior-Opportunity memory for Scout wakes and registry/merge fields in
  the read-only dashboard API.

### Changed

- Repeated Raw content is suppressed before assessment, debate, ranking, and
  expression; genuinely new content refreshes the canonical Opportunity once.
- New Evidence for a thesis with an open Shadow position updates its canonical
  version without re-entering the expression or open-position path.
- Post-turn Scout validation now charges successful tool calls. The gateway
  remains the authoritative cap on all admitted attempts, so a model retry after
  a budget rejection no longer discards an otherwise bounded structured result.
- Read-only MCP resource discovery is separated from territory research calls;
  one unsafe source reference is removed without discarding other valid Evidence,
  and date-only freshness is conservatively normalized to UTC start-of-day.

### Verified

- Migration upgrade/downgrade, same-content suppression, new-content refresh,
  idempotent recovery, active-position update, Scout memory, and dashboard state
  pass integration coverage.
- Current suites: 136 Node tests, 130 Opportunity OS Python tests, and 25
  isolated capital tests.

### Safety

- Prior Opportunity snapshots are memory, never Evidence, and are restricted to
  the same environment and to records known before the current wake.
- Identity preserves direction, the Agent surface remains read-only, normal
  capital mode remains disabled, and Alpha remains unproven.

## [0.7.0] - 2026-08-24

### Added

- First-class `./alta service install/start/stop/restart/status/logs/uninstall`
  lifecycle for macOS launchd and Linux systemd-user.
- Automatic managed-dependency restore, database migration, endpoint-conflict
  preflight, owner-only local API token generation, and external resource-key
  loading without persisting API keys in host definitions or service settings.
- Separate liveness and readiness watchdog windows plus POSIX process-group
  cleanup for stuck App Server descendants.
- Bounded active host-service logs and a portable foreground `service run`
  fallback.

### Verified

- A real macOS LaunchAgent reached readiness and completed an autonomous Shadow
  cycle through heterogeneous audit to a safe `Wait`, without an external Agent
  or timer and without opening a position or submitting an order.
- opportunityd liveness failure recovered with a replacement PID; killing the
  host Node process rebuilt exactly one host/supervisor/child tree.
- Current suites: 136 Node tests, 127 Opportunity OS Python tests, and 25
  isolated capital tests.

### Safety

- Normal unattended operation remains Shadow-only with `capitalMode=disabled`.
- Generated host definitions and local service settings contain no API key;
  external credential directories remain owner-only, the bootstrap strips the
  directory location before launching the model process, and no Agent receives
  resource values.
- The host service now removes every Tiger setting from its runtime environment
  and forces Paper mode off; Tiger remains available only through the explicit
  bounded acceptance command.

### Security

- Moved every operator credential out of the project tree into the owner-only
  external `~/.config/alta/credentials/` boundary; the loader now rejects
  relative roots, symlinks, and group/other-readable LLM files.
- Added a pinned, checksum-verified full-history Gitleaks job to the public CI
  workflow and verified the workflow itself with zizmor.
- Updated vulnerable development/build dependencies to `pytest 9.1.1` and
  `setuptools 83.0.0`; npm and Python advisory scans now report no known
  dependency vulnerabilities.

### Changed

- Limited Dependabot to ALTA-owned package boundaries so it cannot generate
  noisy per-crate changes against the reviewed Codex source snapshot.
- Documented the protected-branch, CODEOWNER, and external-contribution policy
  for source distribution.

## [0.6.0] - 2026-08-24

### Added

- Durable per-role model routing for thesis assessment, independent
  disconfirmation, bounded moderation, expression design, and expression
  audit.
- Default heterogeneous judgment team: DeepSeek V4 Pro for underwriting and
  expression, Grok 4.6 for adversarial review and audit, and Kimi K3 for debate
  synthesis. Scouts and position monitoring remain on DeepSeek V4 Flash.
- Configuration gates that reject a same-model private debate, a same-model
  expression/audit pair, and provider/model namespace mismatches.
- Runtime observability for the complete non-secret role-to-model map.

### Verified

- Live structured calls succeeded against DeepSeek V4 Pro, Grok 4.6, and Kimi
  K3 through the pinned App Server harness.
- A controlled one-Opportunity acceptance used all five real judgment roles,
  persisted their distinct Provider/model identities, and terminated as a
  validated `Wait` with zero Shadow positions and zero Paper order events.
- Current suites: 126 Node tests, 126 Opportunity OS Python tests, and 25
  isolated capital tests.

### Safety

- Model-route changes are part of deterministic run identity; an artifact from
  a different Provider/model cannot be silently recovered as the configured
  role output.
- Research Agents still receive no market-data, database, cache, or broker
  secret and no capital mutation tool.

## [0.5.0] - 2026-08-24

### Added

- Unattended internal scheduling with periodic waiting/degraded heartbeats,
  clean Agent-runtime reconstruction after a failed cycle, and capped
  exponential recovery backoff.
- A supervisor readiness watchdog that replaces a live-but-unready child,
  records mode-0600 operational state, and defaults to continuous recovery.
- Dashboard runtime fields for next wake, retry delay, cycle completion,
  heartbeat freshness, and redacted failure posture.

### Verified

- Recovery continues after more than three consecutive cycle failures and
  eventually completes without an external Agent invoking another cycle.
- Supervisor integration covers child crash recovery, persistent readiness
  failure, explicit bounded-restart test mode, and graceful signal shutdown.
- A 24-hour event-time soak completed 49 half-hour cycles with zero failures
  and zero manual database repairs.
- Current suites: 126 Node tests, 125 Opportunity OS Python tests, and 25
  isolated capital tests.

### Safety

- Normal unattended operation remains Shadow-only. Tiger Paper mutation is
  still isolated behind the explicit one-cycle acceptance command and is not
  exposed to the scheduler, Agents, or HTTP API.
- PostgreSQL advisory ownership is rechecked before every cycle; a lost owner
  session exits for supervised recovery rather than continuing without a lock.

## [0.4.0] - 2026-08-24

### Added

- DeepSeek V4 Flash-only Opportunity OS roles with high-reasoning trader-mind
  prompts, role-bounded read-only tools, and same-frozen-input recovery.
- Deterministic 1–90 day ranking and a bounded top-three expression fallback.
- Post-audit exact-instrument quote refresh with midpoint-drift rejection.
- A separately locked `tigeropen==3.7.0` Paper executor with exact-account
  binding, one-share DAY limit orders, reconciliation, and forced-flat safety.
- Per-cycle Massive request accounting with broad discovery disabled by
  default and a verified maximum of eight requests.

### Verified

- A controlled real-data AMZN cycle completed discovery, challenge, ranking,
  expression, independent audit, Shadow entry/exit, Tiger Paper `BUY 1` and
  `SELL 1`, durable recording, and an independent zero-position/zero-open-order
  preflight.
- Current suites: 126 Node tests, 121 Opportunity OS Python tests, and 25
  isolated capital tests.

### Safety

- Live and sandbox Tiger configurations, account discovery, options, shorts,
  extended-hours orders, more than one share, and non-empty starting accounts
  are rejected.
- Start and final preflight require zero open orders; a timed-out cancellation
  must reach a terminal broker state, and partial fills fail closed.
- Research Agents still receive no provider, database, cache, or broker secret
  and no capital mutation tool.

### Changed

- Isolated the modified Codex source substrate under `vendor/openai-codex/`.
- Removed unrelated upstream monorepo tooling and duplicate SDK source from the
  ALTA publication boundary.
- Split Rust/V8 build coordination and child-process execution out of the
  project CLI, leaving explicit, independently tested module boundaries.
- Split provider-native request translation out of the HTTP gateway so request
  compatibility and gateway lifecycle/resource control have separate owners.
- Made managed Python commands forward interruption signals and wait for child
  shutdown, preventing a service from outliving its project-local launcher.
- Reworked the public README around verified capabilities, explicit non-goals,
  the agent lifecycle, dashboard contract, and reproducible acceptance evidence.
- Added Mermaid architecture diagrams for Agent isolation, collaboration,
  decision hand-offs, and deterministic safety ownership.
- Consolidated the reader-facing architecture, operations, implementation, and
  historical documentation into a consistent English documentation set.
- Clarified research-only scope, provenance, reproducibility, and security
  requirements.

## [0.3.0] - 2026-08-24

### Added

- B8.3 evidence-to-audit Opportunity lifecycle with autonomous sensing,
  point-in-time Evidence, identity/deduplication, private assessments, bounded
  discussion, ranking, expression, and independent audit.
- Stock, ETF, Option, and structured `Wait` expression contracts.
- Massive quote and Finlight news adapters with bounded resource coordination.
- Durable PostgreSQL state, cursor-based API/SSE observability, replay,
  recovery, and cost-adjusted Shadow measurement.
- Isolated Paper-only capital package with no live-account or order-mutation
  path.
- End-to-end real-data acceptance that discovered and audited a QQQ hypothesis,
  correctly terminating as `Wait` with zero positions and orders.

### Safety

- Research agents receive no provider, database, cache, or broker credentials.
- Missing or stale market evidence fails closed.
- Supported environments remain `replay`, `shadow`, and `paper` only.

## [0.2.0] - 2026-08-23

### Added

- B7 autonomous Shadow orchestration, deterministic fixtures, durable cycle
  state, and loopback observability API.

## [0.1.0] - 2026-08-22

### Added

- Initial provider-neutral Codex harness, bounded research tools, local gateway,
  and multi-agent Opportunity OS foundations.
