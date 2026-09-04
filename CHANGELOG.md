# Changelog

Notable ALTA changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
semantic versioning while the project remains experimental.

## [Unreleased]

### Added

- Opportunity Continuity v2 now treats a successful exact-question follow-up
  as a durable research attempt. Unchanged questions re-enter the bounded
  research queue on a horizon-aware cadence, while a changed Opportunity
  snapshot bypasses the cooldown immediately. Failed attempts remain eligible
  and thesis deadlines never move.
- Research Operations v4 reports follow-ups assigned, actually executed with
  preserved lineage, and completed as honest no-ops, both globally and by
  Trader Mind. This separates scheduling intent from real Agent work.
- Deep research now discards unrelated search-engine noise before page fetch
  and preserves a bounded direct route to explicitly allowed issuer or
  regulator domains when search providers are unavailable. A direct route is
  recorded only as a source locator, never as proof of a claim.
- Contract-aware Scout recovery now sends at most two bounded field/error codes
  into the same frozen Run after a malformed result. The original failure stays
  append-only, the renewed attempt gets a fresh durable deadline, and no model
  response text is replayed into the correction prompt.
- An expectation-gap Trader Mind may now recover from an unavailable frozen
  expectation posture only by retrieving a new finance record in that turn and
  binding its exact locator as `market_context`; missing or mismatched proof
  remains an honest `no_op`.
- Research Operations v3 distinguishes retried Runs, retries that recovered,
  terminal contract rejections, and deadline failures in the authenticated
  bilingual console.
- A global Opportunity Continuity projection scans active work before applying
  the bounded Agent context, preserves deadline-prioritized older tests, records
  expiring/stale work, and survives same-wake recovery.
- Research Attention v2 measures entity, Alpha-archetype, direction, and
  short/medium/long-horizon coverage. Under-covered lanes guide only the first
  exploratory search and never become Candidate quotas or Evidence.
- SEC submissions research now accepts a listed ticker, resolves its CIK through
  the official bounded exchange mapping, and exposes both identity and filing
  provenance without requiring another model search.

- Source-scoped durable tool Evidence and stable origin fingerprints. Deep and
  batch research now divide the bounded result window across pages, while each
  cited URL freezes its own excerpt instead of a call-wide duplicate prefix.
- A stricter research-integrity posture requiring two cited non-news calls and
  three independently frozen source records across three domains, with an
  independent counterevidence source. The operator console exposes the bounded
  origin count and source-role reuse without revealing source text or queries.
- Entry-frozen research posture and quality attribution for mature forward
  Shadow Alpha feedback, so ALTA can test whether expensive diligence quality
  survives cost-adjusted benchmark measurement rather than rewarding activity.
- The production Scout contract is now `alpha-trader-v21`, with tool catalog
  `alta-active-research-v8`, explicit anti-mirror evidence instructions, and
  domain/recency/language-scoped deep research. Multiple primary-source domains
  use OR semantics and deterministic source-quality ordering; bounded retry
  feedback corrects output contracts without weakening Evidence requirements.

- A point-in-time Research Attention Portfolio derived only from prior
  production Candidates. When one entity dominates a mature recent sample, it
  preserves exactly one continuation seat and directs the other Trader Minds
  toward independent entity coverage; same-wake recovery and persistence
  revalidate the identical frozen allocation.
- A bilingual Research Attention surface in the operator console showing the
  production sample, unique entities, top-entity share, effective breadth, and
  every current Trader Mind seat.
- The production Scout contract introduced as `alpha-trader-v16`; the new attention
  seat is explicit non-Evidence process state and exact follow-up precedence is
  part of the frozen prompt contract.

- Point-in-time execution-cost governance for Stock, ETF, and Option carriers.
  Every measurable closed Shadow position now freezes arrival-midpoint
  shortfall, both commissions, quoted spread, realized round-trip cost, and
  budget variance. After 30 comparable same-carrier closes, positive cost
  surprise plus a bounded error allowance becomes a downside-only Alpha
  reserve for future plans.
- An execution-quality surface in the bilingual operator console showing
  realized versus estimated costs, cost-budget hit rate, fill reliability, and
  the currently applied empirical reserve.

- Complete English and Simplified Chinese localization for the local operator
  console, including persistent one-click switching, locale-aware dates and
  numbers, domain-status labels, controls, errors, empty states, replay, and
  responsive mobile layouts. Saved Agent and research artifacts remain visible
  in their original language so the audit record is never rewritten.
- A write-only provider credential center for model, market-data, news, and
  research tokens. It exposes safe configuration metadata only, locks changes
  while the runtime is active, and keeps Tiger behind the disabled-capital
  Paper boundary.
- One-command foreground console preparation: `./alta dashboard` now installs
  frozen frontend dependencies and rebuilds stale assets automatically. A first
  Start from the UI prepares and installs the user-level research service.
- The supplied brand artwork is included byte-for-byte in the operator shell,
  with responsive containment and an explicit ALTA product lockup.

### Fixed

- Autonomous startup now reconciles unfinished evaluation bindings before it
  can create a new cycle. The oldest compatible frozen wake resumes; bindings
  without an immutable snapshot, with a changed evaluation contract, or later
  duplicate bindings fail closed with explicit terminal records.
- Retry-scheduled pipeline failures are no longer projected as terminal cycle
  outcomes, preventing a recoverable attempt from appearing as a completed
  failure in the forward-evaluation ledger and operator console.
- Oversized Scout inputs may now shed the redundant global continuity
  projection only after preserving the role-specific drive and exact follow-up,
  so an exploratory seat cannot fail before its Run is persisted.
- Both research and control-plane Paper commands prefer the provisioned,
  isolated Capital interpreter and fall back to locked `uv run` only when the
  managed environment is absent.
- The operator console now refreshes credential health and Paper-capital state
  on a bounded auxiliary cadence, renews active HttpOnly sessions, and uses the
  scheduler's durable current cycle in the header, opportunity field, and
  decision-ledger filter. Optional-panel failure no longer creates a request
  storm or leaves a once-loaded status stale indefinitely.
- Exact follow-up assignments can no longer disappear when a Scout prompt is
  reduced to its durable byte budget. Follow-up prompts use a compact,
  mode-specific contract that preserves the parent Opportunity, question,
  deadline, lineage, evidence roles, and company-thesis/security-readiness
  distinction; an impossible fit now fails explicitly instead of silently
  becoming broad exploration.
- Tool provenance now stops and deduplicates inside a single text payload, so a
  research response with more than ten URLs cannot overflow the durable
  ten-source boundary before the Scout result is parsed.
- The production Scout new-token envelope is 88,000: still below the 100,000
  global contract, but above the observed 80,162-token five-stage research
  turn that had already paid its retrieval cost before a 64,000-token rejection.
- Scout retries now replace the in-memory Run specification with the same
  renewed deadline already written to PostgreSQL. An invalid or incomplete
  first response can no longer make a later attempt inherit an expired local
  deadline and be misclassified as an infrastructure timeout.
- The one-command dashboard bootstrap now pins an isolated pnpm linker layout,
  so a user's global hoisted-linker configuration cannot produce dangling
  workspace executables on another machine.
- Follow-up no-op results bind harmlessly truncated provider question text back
  to the sole frozen assignment; Candidate question identity remains strict.
- Long Opportunity and Candidate identifiers can no longer widen flow columns
  or hide neighboring cards. Desktop, tablet, and mobile layouts keep content
  within their stage and expose long identifiers with truncation.

- CI Actions now use Node 24-compatible, immutable official release SHAs, so
  publication checks no longer depend on GitHub's temporary Node 20 fallback.

- A stopped runtime can no longer leave the workspace context labeled as an
  active cycle. The console now identifies retained data as a saved snapshot,
  while preserving the original durable record statuses for audit.

- Completed-bar research seeds that conflict with a frozen coverage-expansion
  seat are removed before the wake, and an exploratory Candidate that violates
  its own seat now fails before persistence. Exact Research Director follow-ups
  retain priority.

- Execution-cost governance is reloaded immediately before an entry intent, so
  a plan cannot trade against a newly tighter empirical cost reserve.

- Long-lived databases can no longer abort a new autonomous cycle when combined
  Evidence, Opportunity memory, Trader Mind memory, feedback, and book context
  exceed the 16 KiB immutable Scout hand-off. The hard budget remains enforced;
  lower-priority process context is shed deterministically and replayably.

## [0.26.0] - 2026-08-29

### Added

- Forward lifecycle diagnostics for every measurable closed Shadow position,
  using only observations captured during the holding interval. The Alpha API
  and operator console now expose maximum favorable/adverse excursion, observed
  drawdown, exit capture, time to best, and positive-excursion misses.
- A mature-sample forecast calibration controller that compares entry-frozen,
  cost-adjusted direct-stock Alpha forecasts with later benchmark-relative
  Shadow outcomes. After 30 comparable closes it deducts an overforecast/error
  reserve from new underwriting; weak directional calibration also caps size.
- A forward-Alpha evidence surface in the local operator console showing sample
  maturity, confidence interval, forecast error, directional calibration,
  applied reserve, and the tightest evidence-driven capital posture.
- A deterministic Research Director that removes expired and monitor-owned
  work, prioritizes exact Opportunity questions by decision gap and remaining
  horizon, assigns different follow-ups to different Trader Minds, and reserves
  at least two independent-discovery seats.
- A portfolio-wide catalyst-risk ledger that groups different instruments by
  their normalized causal catalyst, exposes saturated catalyst clusters to the
  frozen research mandate, and applies a shared notional limit during
  construction and immediately before entry.
- A shared canonical UTF-8 JSON budget registry for Scout snapshots, Scout
  prompts, private-role inputs, and private-role prompts.
- Exponential in-process retry gates for optional Finlight and Massive
  connectors so a degraded upstream is not hammered on every autonomous wake.
- A frozen, point-in-time market research agenda built from completed Massive
  daily bars. It screens relative return, price-volume behavior, range, breadth,
  and dispersion into at most one verification question per Trader Mind.
- A frozen, non-Evidence portfolio research mandate that exposes current book
  stress, saturated Alpha sources, systematic exposures, and bounded
  diversification search targets to every live Trader Mind wake.
- Aggregate portfolio stress-loss and per-Alpha-source capacity in deterministic
  position construction and pre-intent revalidation.

### Changed

- Managed Python execution deadlines now keep the wrapper event loop alive until
  the child exits or the explicit timeout fires, giving Linux and macOS the same
  hard-deadline behavior.
- Legacy or malformed open positions without a trustworthy implementation-risk
  ticket now consume their full current notional as stress loss instead of
  receiving a favorable zero-risk assumption.
- Alpha evidence queries and forecast/capital governance now live behind a
  narrow reporting persistence boundary instead of expanding the core database
  adapter. The operator shell likewise delegates the Shadow evidence book to a
  focused component; public API fields, replay semantics, and safety posture are
  unchanged.
- Open-question construction now preserves a disconfirming Assessor gap before
  lower-value thesis prompts can consume the bounded agenda, and the Scout
  contract is `alpha-trader-v15`.
- The portfolio policy is now `alta-portfolio-risk-v7`. A ready implementation
  carries a complete catalyst-notional bridge, while legacy positions are
  conservatively assigned to `legacy-unclassified` rather than assumed
  independent.
- Production Candidates must now be decision-complete before Foundry admission:
  identity, changed fact, mechanism, direction, first rejection, prediction,
  beneficiary path, counterevidence, next test, investability, and freshness are
  all explicit or the Scout returns `no_op`.
- Invalid structured Scout output, a missed active-research requirement, or a
  transient App Server failure receives at most two fresh bounded retries under
  the same durable Run identity. Every prior failure remains append-only and
  auditable.
- Private assessment is no longer invoked for Opportunities that deterministic
  horizon, evidence, completeness, expectation, or research-quality gates
  already know cannot enter the ranking book.
- The production discovery allowance is four research calls and 40,000 charged
  tokens per Mind; private judgment roles are capped at 30,000 charged tokens.
  Mature, outcome-backed incentives remain the only bounded expansion path.
- Same-wake recovery now reunifies per-Mind research incentives and scoped
  market-screen seeds instead of inheriting only the first Scout's subset.
- Per-Mind snapshots now carry only their assigned follow-up parent and question;
  recovery reunifies those scoped views, and prospective incentives are shed
  before an assigned parent when prompt pressure requires compaction.
- Full-book replacement now compares remaining Alpha bps, expected Alpha
  dollars, and expected Alpha per dollar of stress loss instead of rotating on
  a bps hurdle alone.

### Safety

- Research-attention state is non-Evidence process allocation. It cannot alter
  confidence, ranking, instrument choice, capital, execution, or broker access;
  insufficient and balanced samples remain unconstrained.

- Lifecycle diagnostics are descriptive forward evidence only. They cannot
  tune an exit, alter a rank, change capital, or authorize a broker action, and
  malformed diagnostics cannot block close accounting.
- Forecast calibration is downside-only: immature samples cannot tune forecasts,
  favorable errors cannot create a negative reserve or extra leverage, and a
  tighter reserve or capital posture forces pre-intent replanning.
- Research queue scores and assignments are frozen non-Evidence process state;
  they cannot enter ranking, expression, capital, or execution, and tampered or
  substituted follow-ups fail before persistence.
- These changes affect research reliability and cost control only. They do not
  loosen `Wait`, capital, market-data, Paper-account, or broker boundaries.
- Market-screen seeds exclude incomplete current-session and future-known rows,
  are revalidated against PostgreSQL, and cannot be cited as Evidence or bypass
  causal research, independent assessment, expression audit, or capital gates.
- Portfolio context cannot become Evidence, lower research standards, rank an
  Opportunity, select an instrument, or authorize capital. Missing incumbent
  risk-capital records fail closed to `Wait`.

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
