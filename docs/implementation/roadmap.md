# Implementation roadmap

This roadmap turns the ALTA design into independently verifiable stages. It is
written for maintainers extending the current `0.26.0` baseline, not as a claim
that research Alpha has already been established.

## Current baseline

The repository already contains the complete vertical research slice:

- a project-local Codex App Server harness and bounded provider gateway;
- PostgreSQL and Redis runtime support;
- point-in-time Raw and Evidence ingestion;
- four isolated active Trader Minds with bounded per-Mind experience memory;
- a point-in-time completed-bar anomaly funnel that assigns bounded verification
  questions without manufacturing Evidence or trade direction;
- a deterministic per-Scout research-diligence record derived from actual tool
  provenance, source diversity, cross-checking, counterevidence, and next test;
- deterministic Foundry identity, deduplication, completion, and a durable
  cross-cycle Opportunity registry;
- two locked private assessments from different model families and bounded
  third-model moderation;
- two evidence-bound bull/base/bear underwriting tickets and deterministic
  research-quality/odds-aware 1–90 day ranking with at most three expression
  attempts;
- two independently locked PM decision records covering priced-in expectation,
  variant view, reference class, base rate, security readiness, must-be-true
  conditions, action trigger, and conservative edge half-life;
- a DeepSeek V4 Pro slate of up to three distinct Stock, ETF, Option, or Wait
  payoff hypotheses, each tested against actual market and portfolio data;
- independent Grok 4.6 comparison and exact selection from the admissible slate;
- exact-quote, cost, portfolio-risk, and exit-liquidity validation;
- dual-agent Alpha-source, systematic-exposure, hedge-posture, and basis-risk
  classification with deterministic purity sizing and shared-factor buckets;
- a frozen implementation ticket with synthetic Shadow NAV, loss budget,
  gross exposure, intended and unwanted exposures, target size, and binding
  constraint;
- a point-in-time Alpha clock, active capital competition against the weakest
  incumbent, and a guarded non-chasing execution ticket;
- cross-cycle Shadow monitoring, exit, and benchmark measurement;
- an optional isolated one-share Tiger Paper acceptance executor;
- an unattended scheduler with clean runtime rebuild, bounded failure backoff,
  heartbeat freshness, and a readiness watchdog;
- a one-command launchd/systemd-user service with dependency restore,
  liveness-specific process-group cleanup, and safe lifecycle commands;
- read-only JSON and SSE observability.
- immutable forward-evaluation cohort bindings, cycle-attributed Agent runs, and
  configuration, missingness, and sample-readiness projections.
- scoped ex-ante underwriting calibration against direct-stock forward Shadow
  outcomes without automatic prompt or weight tuning.
- entry-frozen Trader Mind, Alpha-archetype, and research-route attribution with
  point-in-time, maturity-gated outcome feedback.
- a delayed, symmetric, revocable research incentive that can add one read-only
  tool call and 8,000 tokens only after conservative benchmark Alpha is positive.
- a bounded autonomous explore/follow-up loop that turns prior next tests,
  rejections, and Assessor evidence gaps into exact point-in-time questions.
- a deterministic Research Director that removes expired or monitor-owned work,
  orders exact questions by decision value and horizon, prevents duplicate
  follow-up assignments, and preserves independent exploration capacity.
- an immutable Thesis Ledger whose observable causal pillars bind research,
  expression selection, position monitoring, and later follow-up work.
- rolling, current-policy Alpha capital governance that can only reduce later
  Shadow risk from prior cost-adjusted benchmarked outcomes and drawdown.

The verified release name is `FORWARD_EVIDENCE_VERIFIED`. Real-world
Alpha remains unproven.

## Sequencing principles

Every stage must preserve these rules:

1. land the smallest complete vertical change;
2. keep Agent judgment separate from deterministic invariants;
3. add a durable contract before adding another autonomous role;
4. make failure explicit and fail closed at market or capital boundaries;
5. verify replay, recovery, and clean shutdown at every stage;
6. accept a stage before beginning the next one;
7. do not turn an engineering acceptance result into an investment claim.

## Stage map

| Stage | Objective                                                  | Current state  | Gate                                                           |
| ----- | ---------------------------------------------------------- | -------------- | -------------------------------------------------------------- |
| B0    | Publication and secret boundary                            | Complete       | Tracked tree and history scan clean                            |
| B1    | Typed persistence and read API                             | Complete       | Migration, API, SSE, and restart tests                         |
| B2    | Raw-first source contracts                                 | Complete       | PIT and degraded-source tests                                  |
| B3    | Isolated Scout runtime                                     | Complete       | Four bounded independent runs and no-op path                   |
| B4    | Opportunity Foundry, challenge, and rank                   | Complete       | Reversible identity and deterministic replay                   |
| B5    | Expression and internal Shadow ledger                      | Complete       | Quote, validation, fill, and accounting tests                  |
| B6    | One-command deterministic lifecycle                        | Complete       | Demo and replay hashes match                                   |
| B7    | Autonomous scheduling and recovery                         | Complete       | Single owner, heartbeat, recovery, and SSE                     |
| B8    | Real adapters, independent audit, and Alpha measurement    | Complete       | Controlled real-data run ends safely                           |
| B9    | Explicit one-share Tiger Paper lifecycle                   | Complete       | BUY, monitor, SELL, reconcile, and verify flat                 |
| B10   | Host-managed unattended lifecycle                          | Complete       | Boot install, two-level recovery, and clean stop               |
| B11   | Cross-cycle Opportunity identity and memory                | Complete       | Repeats suppressed; new content refreshes once                 |
| B12   | Frozen forward cohorts and cycle attribution               | Complete       | Drift and missingness are measurable, not hidden               |
| B13   | Odds-aware underwriting and calibration                    | Complete       | Payoff is explicit; calibration scope is comparable            |
| B14   | Active Trader Minds and experience memory                  | Complete       | Every Mind searches; memory never becomes Evidence             |
| B15   | Atomic external credential rotation                        | Complete       | Hidden input, rollback, revision, controlled reload            |
| B16   | Point-in-time Alpha feedback and attribution               | Complete       | Entry credit frozen; small samples reveal no score             |
| B17   | Portfolio construction and execution planning              | Complete       | Tightest constraint sizes; mutable book rechecked              |
| B18   | Alpha lifecycle and active capital rotation                | Complete       | Decay and incumbent hurdle drive idempotent rotation           |
| B19   | Research diligence and expression tournament               | Complete       | Actual research and payoff alternatives are auditable          |
| B20   | Autonomous explore/follow-up research loop                 | Complete       | Exact questions close PIT research and learning loops          |
| B21   | Immutable Thesis Ledger and payoff lineage                 | Complete       | Claims survive expression and append-only monitoring           |
| B22   | PM decision intelligence and edge half-life                | Complete       | Thesis, security, action, and timing remain distinct           |
| B23   | Alpha isolation and systematic-risk capacity               | Complete       | Independent purity and shared exposure capacity gate           |
| B24   | Research-quality and forecast-disagreement discipline      | Complete       | Actual diligence and lower forecast drive decisions            |
| B25   | Evidence-to-capital integrity and forward Alpha statistics | Complete       | Uncertainty, capital quality, and frozen forecasts bind        |
| B26   | Rolling Alpha survival and capital governance              | Complete       | Negative evidence throttles; positive evidence never levers    |
| B27   | Independent decision-edge admission                        | Complete       | Every view beats base rate; conservative Alpha stays positive  |
| B28   | Delayed symmetric research incentives                      | Complete       | Mature conservative Alpha can earn bounded research only       |
| B29   | Book-aware research and stress-efficient capital           | Complete       | Frozen mandate, aggregate stress, source capacity, rotation QC |
| B30   | Completed-bar research-priority funnel                     | Local complete | PIT screen questions are replayable and cannot bypass evidence |
| B31   | Shared catalyst-risk ledger                                | Local complete | Cross-ticker event crowding binds research and entry capacity  |
| B32   | Decision-impact research director                          | Local complete | Unique PIT questions; two exploration seats remain protected   |
| B33   | Evidence-bound quality and execution comparison            | Local complete | Only cited research earns credit; guarded limits cannot chase  |
| B34   | Mature forecast-error reserve and evidence console         | Local complete | Comparable errors haircut edge; weak calibration caps capital  |
| B35   | Forward lifecycle diagnostics and legacy-risk quarantine   | Local complete | Observed paths diagnose leakage; unknown risk fails closed     |
| F1    | Sustained forward Shadow evidence                          | Next           | 6–12 week sample and documented data quality                   |
| F2    | Agent and source ablation                                  | Future         | Incremental contribution is statistically credible             |
| F3    | Unattended or broader Paper rollout                        | Not authorized | New review, operator approval, and kill controls               |

## B0 — publication and safety boundary

Objective: make it impossible for local credentials, generated state, or
unattributed third-party code to enter the publication tree accidentally.

Required controls:

- root ignore rules for local state, credentials, keys, certificates, databases,
  caches, and generated build output;
- example configuration contains placeholders only;
- Agent file tools reject credential roots and symlink escape;
- attribution, license, notice, security, and research-only scope are visible;
- exact source-archive secret scans run in redacted mode.

Acceptance:

- a freshly unpacked source archive contains no local absolute paths or credentials;
- remote workflows, account bindings, hooks, and deployment metadata are absent;
- the project is independently named and not represented as an OpenAI product.

## B1 — durable runtime foundation

Objective: establish typed state before adding autonomous research behavior.

Required controls:

- explicit schema migrations with no migration-on-start side effect;
- version, environment, and timezone-aware `known_at` on domain records;
- bounded append-only events and cursor-based SSE;
- loopback health, readiness, summary, and graceful shutdown;
- PostgreSQL as the source of truth and Redis as disposable support state.

Acceptance:

- empty-database upgrade, idempotent upgrade, downgrade, and re-upgrade pass;
- unsupported `live` environment values are rejected;
- service restart preserves durable state and cursor semantics.

## B2 — source and Evidence contracts

Objective: convert external information into point-in-time evidence without
letting an Agent invent provenance.

Required controls:

- store Raw before Evidence;
- hash content, identify source and locator, and preserve observation time;
- separate source health from the semantic result of “no new data”;
- enforce deadlines, pacing, circuit breakers, and bounded output;
- reject future-known or unbound Evidence.

Acceptance:

- deterministic fixtures cover healthy, degraded, rate-limited, stale, malformed,
  and unavailable sources;
- a frozen wake never sees records known after its decision time;
- source failure does not silently become an empty successful response.

## B3 — autonomous Trader Mind pool

Objective: let several independent Agent perspectives search for opportunities
without a shared-chat anchoring effect.

Required controls:

- four distinct missions, Alpha archetypes, source territories, and tool catalogs;
- a shared active Web, news, public-social, and finance research surface;
- separate App Server clients and one in-flight turn per client;
- bounded tool calls, tokens, output bytes, concurrency, and deadline;
- strict structured Candidate or no-op output;
- durable run and artifact provenance;
- per-Scout failure isolation.

Acceptance:

- all four Trader Minds can complete concurrently;
- a timed-out or invalid Scout cannot corrupt successful siblings;
- replay recovers succeeded artifacts without another model call;
- honest no-op is a first-class result.

## B4 — Foundry, challenge, and ranking

Objective: turn heterogeneous Candidates into a compact, falsifiable, ranked
Opportunity book.

Required controls:

- exact duplicate, structural merge, competing, and related identities;
- reversible merge and append-only relation events;
- completion fills only missing fields with cited Evidence;
- Thesis and Disconfirming assessments are locked before sharing;
- each private assessment owns a coherent, evidence-bound payoff distribution;
- moderation is bounded and cannot create Evidence;
- ranking gates and score components are deterministic.

Acceptance:

- input order does not change identity or rank results;
- opposite-direction ideas are not incorrectly merged;
- one private view cannot be exposed before the second is locked;
- rank replay produces the same components, score, and tie-break order.

## B5 — expression and Shadow ledger

Objective: map a research Opportunity to a bounded listed-market expression and
measure it in the internal Shadow ledger.

Required controls:

- Stock, ETF, Option, and Wait contracts;
- exact quote, freshness, spread, cost, notional, portfolio, stress-loss, and
  exit-liquidity validation;
- a synthetic Shadow NAV and explicit per-trade loss, position, gross, and
  participation budgets;
- a new post-intent quote before any simulated fill;
- conservative bid/ask and slippage handling;
- version binding across Opportunity, Evidence, Expression, position, and ledger;
- append-only balanced Shadow accounting;
- Paper-only capital package isolated from research runtime and disabled by
  default.

Acceptance:

- stale, future-known, crossed, unavailable, or costly quotes fail closed;
- duplicate execution is idempotent;
- ledger debits equal credits;
- no code path can construct or fall back to a live account;
- normal Replay, Shadow, service, and autonomous commands cannot submit an
  order.

## B6 — deterministic vertical slice

Objective: prove the entire lifecycle can run and replay from one command.

Required controls:

- frozen fixture source data and deterministic model doubles;
- all stages checkpointed with stable IDs;
- explicit `MVP_RUNNING` and `MVP_IDLE` terminal states;
- replay hash includes sources, runs, Opportunities, rank, Expression, and ledger.

Acceptance:

- demo and replay hashes match;
- injected failure at each checkpoint resumes from the original frozen wake;
- no-op and Wait paths finish successfully without creating positions.

## B7 — autonomous service

Objective: run the vertical slice repeatedly with durable ownership and a
dashboard-ready read surface.

Required controls:

- UTC scheduler with PostgreSQL advisory-lock ownership;
- waiting/degraded heartbeat freshness and bounded exponential failure backoff;
- durable source cursors and cycle checkpoints;
- unlimited-by-default supervisor recovery, graceful signal forwarding, and a
  live-but-unready watchdog;
- authenticated loopback read API and cursor SSE;
- state for every Agent, source, Opportunity, Expression, and position.

Acceptance:

- a second scheduler owner is rejected;
- process interruption does not duplicate a cycle or replace frozen Evidence;
- client SSE disconnect is a normal transport event;
- more than three consecutive cycle failures rebuild clean runtimes and can
  recover without external intervention;
- persistent readiness failure replaces the unhealthy child without a hot
  restart loop;
- shutdown leaves no child process or advisory lock.

## B8 — real-data Shadow and independent audit

Objective: use bounded real market and news adapters while maintaining the same
research and safety contracts.

Required controls:

- Finlight REST ingestion with cursor and cooldown;
- Massive snapshots, bars, exact quotes, and on-demand option chain;
- independent Expression Auditor with rank hidden;
- Position Monitor restricted to frozen falsifiers;
- forward Shadow performance and SPY benchmark measurement;
- explicit `Alpha is unproven` state before mature samples exist.

Acceptance evidence includes both the earlier refusal path and the current
actionable path. The current controlled run found an AMZN retail-advertising
Opportunity, completed private assessments, discussion, 1–90 day ranking,
expression, audit, and post-audit quote refresh, then closed its Shadow position.
The API and SSE continue to expose the lifecycle and Alpha remains unproven.

## B9 — explicit one-share Tiger Paper acceptance

Objective: prove the complete capital hand-off without widening Agent or live
account authority.

Required controls:

- separate locked package and subprocess with a child-environment allowlist;
- exact 17-digit Paper account SHA-256 binding, no enumeration or fallback;
- owner-only non-symlink config and single-owner lease;
- stock/ETF only, one share, DAY limit, no extended hours or shorts;
- broker preview, fill polling, exact-account response checks, and position
  reconciliation;
- zero positions and zero open orders before start and re-verification of both
  in `finally`;
- no Agent broker tool and no HTTP order endpoint.

Acceptance evidence in `0.4.0`:

- one real-data AMZN cycle selected a stock expression and passed independent
  audit plus deterministic quote gates;
- Tiger Paper recorded `BUY 1` from 0→1 and `SELL 1` from 1→0;
- two Paper-fill events, Shadow close, performance measurement, and an
  additional already-flat event were persisted;
- the final independent preflight reported zero positions and zero open orders;
- Massive used 8 of the configured maximum 8 requests.

This proves one bounded engineering lifecycle only. It does not authorize
continuous Paper operation or establish Alpha.

## B10 — host-managed unattended lifecycle

Objective: make autonomous Shadow operation survive terminal closure and host
login/boot without another Agent, cron job, or manual per-cycle command.

Required controls:

- one-command macOS launchd and Linux systemd-user installation;
- no credential values in host definitions or persisted service settings;
- dependency startup, migration, preflight, endpoint-conflict rejection, and
  owner-only generated API authentication;
- distinct liveness and readiness grace windows;
- whole-process-group termination for a stuck opportunityd/App Server tree;
- host crash recovery plus the existing database single-owner lock;
- bounded active service logs and synchronous clean stop/uninstall commands.

Acceptance evidence in `0.7.0`:

- a real macOS LaunchAgent restored PostgreSQL and Redis, migrated, and completed
  an autonomous live-source cycle through heterogeneous audit to safe `Wait`
  without an external Agent;
- terminating opportunityd caused liveness-specific group cleanup and one clean
  replacement child;
- killing the host Node process caused launchd to rebuild the tree with exactly
  one host, one supervisor, and one opportunityd process;
- normal service state reported `capitalMode=disabled` throughout.

The Linux unit is deterministically tested but was not host-exercised in this
macOS release. Windows supports the foreground service command only.

## B11 — cross-cycle Opportunity identity and memory

Objective: stop a 24×7 system from paying repeatedly to rediscover, debate, and
express the same underlying information while still recognizing genuine thesis
updates.

Required controls:

- stable identity independent of free-form mechanism prose and adjacent holding
  period estimates;
- exact and structural matching that preserves opposite-direction theses;
- novelty based on Raw content hashes rather than regenerated Evidence IDs;
- durable suppression and refresh events with idempotent recovery;
- bounded canonical Evidence and Candidate membership without forgetting prior
  content history;
- open-position updates that cannot create a second expression or position;
- bounded prior-Opportunity Scout memory that is never treated as Evidence;
- registry and merge state in the dashboard-ready API.

Acceptance evidence in `0.8.0`:

- a repeated Candidate with different mechanism wording and identical source
  content was suppressed before private assessment;
- genuinely new source content refreshed the canonical Opportunity exactly once
  and recovered idempotently;
- new Evidence for an open Shadow thesis incremented the canonical version while
  remaining outside the expression/open path;
- the next point-in-time wake received only recent, active, same-environment
  Opportunity memory;
- migration upgrade, downgrade, replay, API, and full regression suites passed.

## B12 — frozen forward cohorts and cycle attribution

Objective: make future performance claims falsifiable by preserving which
configuration and Agent runs produced each autonomous cycle.

Implemented controls in `0.9.0`:

- every autonomous cycle is immutably bound to a bounded, non-secret
  configuration fingerprint before research begins;
- every new Scout and judgment Run records an indexed `cycle_id`;
- the read-only evaluation projection reports configuration drift, source and
  Agent completion, Idle, Wait, instrument attempts, Shadow opens, benchmark
  coverage, and missing measurements;
- cohort responses are bounded to 10,000 recent cycles and expose truncation;
- reaching the minimum sample changes readiness only to `ready_for_review`; it
  never triggers automatic model, prompt, source, or ranking-weight changes.

This stage supplies F1's measurement substrate. It does not substitute for the
6–12 week forward observation program or establish Alpha.

## B13 — odds-aware underwriting and calibration

Objective: distinguish a high-probability story from an attractive, falsifiable
risk/reward setup before expression consumes market resources.

Implemented controls in `0.10.0`:

- both private Assessors independently commit SPY-relative bull/base/bear odds,
  payoff magnitude, catalyst clarity, crowding, liquidity, and next pricing fact;
- scenario coherence and Evidence binding are schema-validated and immutable;
- deterministic ranking includes expected Alpha, downside resilience, payoff
  asymmetry, implementation risks, and cross-model scenario disagreement;
- self-reported confidence remains visible but receives no positive rank weight;
- Expression and Audit see the locked scenario summaries while Audit remains
  blinded to rank;
- the Alpha API compares frozen ex-ante consensus with realized forward Alpha
  only for directly comparable stock expressions and warns on small samples.

This stage improves research discipline, not realized performance. It does not
authorize live capital or automatic model, prompt, route, or weight adaptation.

## B14 — active Trader Minds and experience memory

Objective: make every discovery Mind search for new information instead of only
summarizing passively supplied Evidence, while preserving point-in-time and
replay guarantees.

Implemented controls in `0.11.0` and evolved in `0.12.0`:

- all four Minds can call bounded Web research, global news, public social
  search, and public finance tools; specialist feed, archive, crawl, and academic
  tools follow each Mind's Alpha archetypes;
- the production runtime requires at least one active research attempt per Mind
  and isolates a skipped-search failure from successful siblings;
- the gateway remains authoritative for the six-call cap, deadline, read-only
  sandbox, tool allowlist, and secret-free child environment;
- completed turns evolve a deterministic bounded state with outcome/tool-use
  counts and two recent process lessons;
- only prior-cycle, same-environment experience is frozen into the next wake;
  it is validated against PostgreSQL and explicitly cannot support a Candidate;
- interrupted-cycle recovery merges per-Mind snapshots from the original wake
  without polling newer sources.

This is process adaptation, not autonomous strategy mutation. It does not let a
Mind rewrite its immutable mission, tools, budget, rank policy, or capital
boundary, and it does not establish Alpha.

## B15 — atomic external credential rotation

Objective: make API-key replacement operationally simple without exposing a
secret to Agents, shell arguments, the worktree, service definitions, or logs.

Implemented controls in `0.12.0`:

- value-free status and validation across LLM, market/news, and optional
  research-tool slots;
- hidden terminal or bounded standard-input ingestion, never a CLI value;
- deterministic single-file selection with ambiguity, symlink, permission, and
  size rejection;
- fsync-backed same-directory atomic replacement and owner-only permissions;
- controlled active-service restart, readiness enforcement, rollback to the
  previous file, and recovery retry;
- non-secret revision and configured-slot observability in host and runtime
  state.

## B16 — point-in-time Alpha feedback and attribution

Objective: let Trader Minds learn from realized research outcomes without
rewriting history, leaking future state, or turning small samples into an
automatic strategy mutation.

Implemented controls in `0.13.0`:

- every production Candidate selects exactly one Alpha archetype from its
  originating Mind's frozen mandate;
- Shadow entry freezes Candidate, Mind, archetype, and completed bounded
  research-tool route in the immutable Position Thesis;
- closed, cost-adjusted, benchmark-relative performance keeps that entry-time
  credit even if the canonical Opportunity is merged later;
- a strict prior-time projection is frozen into later wakes and returned only
  to the same Mind as non-Evidence;
- Mind-level values require 30 benchmarked closes, while archetype and route
  values also require 10 observations;
- the runtime and read-only API expose maturity and coverage. B28 later adds one
  narrowly bounded research-budget reward; models, ranking, expression, risk,
  capital, and broker policy remain outside the feedback path.

## B17 — portfolio construction and execution planning

Objective: prevent a good research idea from becoming a bad trade because the
instrument, sizing, liquidity, or aggregate-book exposure was chosen casually.

Implemented controls in `0.14.0`:

- the implementation role compares direct stock, ETF/proxy, long option, and
  Wait while naming intended Alpha, unwanted exposures, retained exposure, and
  rejected alternatives;
- two independent scenario tickets feed a deterministic expected-edge and
  stress-loss calculation; transaction cost is deducted before direct stock or
  ETF admission;
- target size is the smallest of market-data notional, single-position NAV,
  remaining gross NAV, stress-loss budget, and bounded exit capacity;
- equity and ETF exit capacity uses the current Massive snapshot day-volume as
  an explicit proxy, while option capacity uses open interest and premium at
  risk; neither is represented as institutional ADV or guaranteed liquidity;
- the independent Auditor sees the complete plan, post-audit quote refresh
  reruns construction, and the position book rechecks mutable gross exposure
  immediately before creating an entry intent;
- the implementation ticket is frozen into the Expression and Position Thesis
  and projected by the read-only expression API.

This does not implement an institutional optimizer, prime-broker inventory,
borrow, factor covariance, multi-leg execution, or live capital. A thesis that
requires those capabilities resolves to Wait.

## B18 — Alpha lifecycle and active capital rotation

Objective: make scarce research capital compare opportunities through time
instead of admitting isolated trades until a position-count limit is reached.

Implemented controls in `0.15.0`:

- every implementation freezes Evidence freshness, stated horizon, assessed
  catalyst clarity, next pricing facts, raw expected net Alpha, and a transparent
  linear remaining-horizon proxy; the proxy is deliberately labeled as
  underwriting, not realized performance or a learned decay curve;
- entry fails closed when time-adjusted expected net Alpha falls below the
  portfolio hurdle, including a final recheck immediately before intent;
- a full book grants only the smallest current-position notional as conservative
  prospective replacement credit while sizing the candidate;
- the candidate then competes with the incumbent whose frozen expected net
  Alpha has the least remaining time-adjusted value; missing incumbent
  underwriting prevents rotation;
- replacement requires the candidate advantage to clear the incumbent's frozen
  `better_opportunity` hurdle, then exits the incumbent through the ordinary
  monitored forward-quote and balanced-ledger state transition;
- rotation is idempotent, and the candidate is rechecked against the post-exit
  book before any new entry intent;
- the execution ticket records observed participation, a guarded DAY limit,
  a maximum 25 bps offset, timeout cancellation, and no automatic repricing;
  the isolated Tiger Paper mirror consumes the same bounded offset while
  retaining its one-share acceptance limit.

This is active allocation discipline, not proof of Alpha and not an optimizer.
Correlation, factor, crowding, and catalyst-date fields remain evidence-quality
gaps unless reliable point-in-time sources are connected; the independent
Auditor can force Wait rather than letting a string label masquerade as a risk
model.

## B19 — research diligence and expression tournament

Objective: improve the probability that scarce implementation effort is spent
on causal, cross-checked research and on the best available listed payoff,
rather than on the first plausible narrative or ticker.

Implemented controls in `0.16.0`:

- each completed Scout turn derives a typed process record from its actual tool
  calls, discoveries, source locators, and structured output;
- the record distinguishes active and non-news work, independent source
  families and domains, beneficiary-path coverage, disconfirming evidence, and
  the next observable test;
- Foundry and downstream deliberation retain the strongest contributing record
  as non-Evidence process metadata; it informs judgment but never invents a
  fact or deterministically approves a Candidate;
- the implementation PM may propose at most three distinct payoff hypotheses,
  preserving enough global Massive budget for selected-instrument refresh;
- each hypothesis receives its own real quote or option-chain gate,
  tightest-constraint construction ticket, time-adjusted Alpha calculation,
  and capital-allocation decision before the independent Auditor sees it;
- approval must identify exactly one admissible hypothesis; unavailable,
  ambiguous, over-budget, or invalid selection resolves to `Wait`;
- the selected instrument is re-quoted and re-underwritten, and its execution
  plan freezes the arrival midpoint, absolute limit, shortfall budget,
  participation cap, child-slice guidance, single attempt, and no-reprice rule;
- Shadow fill and the isolated Tiger Paper mirror consume the same frozen
  absolute limit, so a later quote cannot silently turn a limit plan into a
  market chase.

These controls improve process selectivity and implementation fidelity. They
do not prove Alpha, estimate crowding, provide institutional borrow, implement
multi-leg execution, or authorize unattended Paper trading.

## B20 — autonomous explore/follow-up research loop

Objective: let scarce research attention close the highest-information gaps
from prior work without turning the system into a queue of inherited theses or
sacrificing broad opportunity discovery.

Implemented controls in `0.17.0`:

- each recent active Opportunity exposes at most two deterministic open
  questions sourced from the prior `next_test`, `first_rejection`, and both
  locked Assessors' `missing_evidence`;
- each Trader Mind autonomously chooses `explore` or `follow_up`; no quota,
  deterministic priority, rank bonus, or automatic exploitation ratio exists;
- a follow-up Candidate or no-op must copy the exact frozen parent Opportunity
  and one exact open question; invented lineage fails before persistence;
- follow-up Candidates still require current frozen or newly collected Evidence,
  stable identity keys, and the same Foundry, deliberation, expression, audit,
  market, portfolio, execution, and capital gates as new exploration;
- lineage persists through Candidate and Opportunity contracts, downstream
  Agent context, entry-frozen contributor credit, API projection, and replay;
- per-Mind experience records bounded mode history, while cost-adjusted
  explore/follow-up outcome values remain hidden until both the 30-position Mind
  and 10-position mode-slice maturity gates are met;
- mode feedback is non-Evidence and cannot change models, ranking, expressions,
  risk limits, execution, or capital. B28 later adds one bounded aggregate
  research-budget incentive without changing the explore/follow-up ratio.

This closes a research-process loop, not a return-optimization loop. The next
step remains sustained forward Shadow evidence, followed by controlled ablation
of exploration, follow-up, source, and role contributions.

## B21 — immutable Thesis Ledger and claim-to-payoff lineage

Objective: preserve the original investment underwriting as falsifiable claims
and make later research, expression selection, and monitoring accountable to
the same point-in-time causal record.

Implemented controls in `0.18.0`:

- each production Candidate carries one to three causal pillars with a concrete
  observable, separate confirmation and invalidation conditions, and a due date
  inside the Opportunity horizon;
- Foundry assigns stable semantic identity, merges duplicate pillars, preserves
  Candidate and Evidence provenance, and caps the Opportunity ledger at four;
- open research agendas may expose an exact pillar verification question without
  treating the claim or prior Opportunity as Evidence or deterministic priority;
- each non-Wait expression hypothesis must name the frozen pillar IDs its payoff
  actually monetizes; missing or invented bindings produce a durable `Wait`;
- the independently selected binding is frozen into the Position Thesis;
- later Position Monitor runs append one evidence-bound state per selected
  pillar—confirming, weakening, invalidated, or unresolved—without mutating the
  original text;
- only a complete, exact, newer-Evidence-bound invalidation can feed the existing
  deterministic exit policy; partial and malformed reviews degrade safely;
- pillar IDs are included in position measurement for future controlled
  calibration, but cannot tune prompts, models, ranking, risk, or capital.

This adds thesis accountability and error diagnosis. It does not make a model's
forecast true, convert subjective thresholds into deterministic limits, or
establish profitable Alpha.

## B22 — PM decision intelligence and edge half-life

Objective: prevent a plausible company story or favorable scenario average from
becoming a security action without an explicit expectation, reference class,
readiness judgment, and time-decay record.

Implemented controls in `0.19.0`:

- each new private Assessor locks what is priced in, a distinct variant view,
  its reference class, the class base rate, and an evidence-specific inside view;
- each record names one to four must-be-true conditions, company-thesis status,
  security-thesis readiness, dominant uncertainty, action trigger, and edge
  half-life;
- scenario probability and inside-view probability must remain coherent;
- `advance` is invalid when the company thesis is impaired/broken or the
  security thesis is not `ready`;
- deterministic synthesis preserves both records, rejects broken,
  not-decision-grade, re-underwrite, and no-independent-ready states, and never
  averages a blocker away;
- ranking freshness and portfolio Alpha decay use the shorter locked half-life;
- the Expression PM and different-model Auditor receive the same locked decision
  fields and must match payoff, priced-in challenge, variant, timing, and
  readiness;
- pre-`0.19.0` underwriting remains readable but fails closed to `Wait` rather
  than receiving fabricated upgrade values.

This stage makes judgment more falsifiable and action discipline more
professional. It cannot guarantee Alpha; only sustained independent forward
Shadow evidence and later controlled ablation can evaluate whether the added
process improves realized cost-adjusted results.

## B23 — Alpha isolation and systematic-risk capacity

Objective: prevent broad beta, sector, style, macro, liquidity, crowding, or
event-gap exposure from being mislabeled as differentiated Alpha merely because
positions use different tickers.

Implemented controls in `0.20.0`:

- each payoff hypothesis classifies its Alpha source, complete systematic
  exposure set, hedge posture, and concrete basis risk;
- a different-model Auditor independently confirms those fields and records
  disagreements instead of averaging them away;
- the portfolio score is the minimum of proposer purity/timing and independent
  thesis, implementation, and isolation judgments, so confidence cannot create
  risk capacity;
- audited scores below `0.60`, unclassified exposure, audit disagreement, and
  required multi-leg hedges fail closed to `Wait`;
- scores from `0.60` up to `0.80` receive a half-size starter cap; scores at or
  above `0.80` may use the ordinary risk budget but receive no bonus leverage;
- open positions are reconstructed into shared typed exposure buckets from
  their frozen Position Thesis, and each new plan consumes the tightest
  remaining bucket even when the symbols differ;
- factor capacity is rechecked immediately before an entry intent alongside
  gross, position, stress-loss, and Alpha-decay limits;
- legacy positions remain readable and are explicitly labeled `unknown` rather
  than assigned fabricated factor history.

This is an implementable exposure taxonomy, not an institutional statistical
factor model. ALTA does not yet have sufficient point-in-time history for robust
beta estimation, covariance forecasting, or multi-leg hedge optimization; the
one-leg boundary therefore chooses `Wait` when a clean thesis requires those
capabilities.

## B24 — research-quality and forecast-disagreement discipline

Objective: prevent fluent but shallow research, or one optimistic forecast,
from outranking a broader and independently cross-checked opportunity.

Implemented controls in `0.21.0`:

- deterministic process-quality components derive only from completed tool
  provenance, independent source families, route diversity, cross-checking, and
  non-news work;
- the score is persisted with the ranking policy version but remains explicitly
  non-Evidence and cannot bypass readiness, freshness, liquidity, or audit gates;
- screen-grade diligence is capped below decision-grade, while missing or
  no-op diligence receives no quality credit;
- both independent expected-Alpha estimates and their dispersion remain visible;
- ranking, construction, and Alpha-clock admission use the lower independent
  expected-Alpha estimate, so an optimistic mean cannot cancel a negative view;
- replay and forward-cohort configuration freeze the research, ranking, and
  portfolio-risk policy versions for later attribution.

These controls target more falsifiable research and more conservative capital
admission. They do not prove that a thesis, forecast, or realized Alpha is
correct.

## B25 — evidence-to-capital integrity and forward Alpha statistics

Objective: prevent forecast disagreement, shallow diligence, duplicate
measurements, or post-hoc forecast reconstruction from overstating the quality
of a capital decision.

Implemented controls in `0.22.0`:

- ranking, construction, and the Alpha clock subtract a fixed reserve equal to
  25% of forecast dispersion from the lower independent expected-Alpha estimate;
- every component of that adjustment is persisted rather than hidden inside a
  single score;
- research quality below `0.60` rejects capital admission, while scores in
  `[0.60, 0.80)` are capped at half-size starter capital and never earn bonus
  leverage;
- post-trade calibration reads the entry-frozen, cost-adjusted implementation
  forecast and uses only the latest performance measurement per position;
- the Alpha projection reports sample size, median, dispersion, standard error,
  a descriptive 95% interval, positive rate, and worst/best observations;
- fewer than 30 benchmarked closes remains explicitly insufficient, while any
  later positive signal is still labeled as requiring external validation.

This stage improves measurement integrity and capital conservatism. It is not a
backtest result, a statistical proof of Alpha, or a guarantee of future returns.

## B26 — rolling Alpha survival and capital governance

Objective: prevent an autonomous Shadow process from repeatedly allocating the
same full risk budget after its own current-policy forward results become
negative or its recent book suffers a material drawdown.

Implemented controls in `0.23.0`:

- only the latest cost-adjusted, SPY-relative close for each position is used;
- observations are scoped to the exact current portfolio-policy version, so an
  incompatible historical regime cannot silently set today's risk budget;
- the controller evaluates the latest 30 unique positions and reports both the
  rolling window and the total comparable sample;
- capital is capped at 50% while fewer than 30 comparable outcomes are
  collecting, and remains at 50% probation after at least 10 observations with
  negative recent mean Alpha;
- a 100 bp synthetic-NAV rolling drawdown or a mature window whose descriptive
  95% upper Alpha bound is non-positive forces a 10% preservation posture;
- the implementation PM receives one frozen posture across its payoff slate,
  while deterministic code reloads and revalidates it immediately before intent;
- old negative results can roll out so small exploration positions permit
  recovery, but favorable evidence never creates a multiplier above 1.0;
- the policy version is frozen into forward cohorts and the complete posture is
  exposed through the read-only Alpha summary.

This is conservative sequential risk control, not a statistical proof, trading
edge, leverage rule, or promise that ALTA will outperform SPY.

## B27 — independent decision-edge admission

Objective: stop fluent but non-differentiated research before it consumes
implementation, quote, and audit capacity.

Implemented controls in `0.24.0`:

- each locked assessor estimates its own reference-class base rate before its
  evidence-specific inside view;
- both paired inside-minus-base-rate lifts must be strictly positive, so an
  optimistic assessor cannot average away an independent non-edge conclusion;
- the lower expected-Alpha forecast must remain positive after a visible reserve
  equal to 25% of forecast dispersion;
- missing, no-op, or screen-grade research diligence cannot enter the ranking
  book; the existing `0.60` decision-quality hurdle is enforced before expression;
- raw forecast probability no longer earns the probability score contribution;
  ranking uses the conservative independent lift, capped at a 25-point lift;
- rejection reason codes and conservative lift components remain deterministic,
  persisted, replayable, and visible through existing read surfaces;
- the deterministic lifecycle fixture obeys the same active-research and
  decision-edge contracts as production—there is no demonstration bypass.
- MCP catalog discovery remains under the gateway's total-call bound but does
  not consume the separate completed-research-call budget;
- private assessment input fits ordered evidence under the unchanged 8,000-byte
  hard bound and removes omitted Evidence IDs from the model-visible contract.

This stage raises the cost of a false positive. It does not validate the base
rates, prove model calibration, or establish realized Alpha.

## B28 — delayed symmetric research incentives

Objective: make Trader Minds compete for durable, cost-adjusted Alpha without
rewarding Candidate volume, confidence, turnover, or speculative risk taking.

Implemented controls in `0.25.0`:

- every Mind receives a prospective reward contract before performance is
  visible, but no budget increase before 30 benchmarked Shadow closes;
- mature feedback adds a one-sided normal-approximation lower bound with a
  four-Mind Bonferroni reserve (`z=2.241`) around mean realized Alpha, calculated
  only from closed, cost-adjusted, benchmark-relative outcomes frozen to the
  entry-time contributor;
- a strictly positive lower bound earns one additional read-only research call
  and 8,000 tokens for the next point-in-time wake; a non-positive bound removes
  the bonus and issues route-diversification guidance;
- the reward is recalculated and revocable on every wake, so later losses matter
  symmetrically and there is no permanent high-water privilege;
- Agent-visible reward state is non-Evidence; the Agent cannot write the outcome
  ledger, feedback projection, conservative bound, or its own budget headers;
- Candidate count, self-reported confidence, raw profit, verbosity, and turnover
  are explicitly excluded from credit, and the bonus has no path to ranking,
  expression, position size, capital posture, or broker permissions;
- the loopback API exposes prospective, calibrating, earned, and recovery states,
  the exact feedback snapshot binding, and the maximum possible bonus.

This design deliberately avoids an asymmetric activity bonus. Empirical work
shows performance-linked incentives can alter risk taking
([Chevalier and Ellison, NBER 5234](https://www.nber.org/papers/w5234)), while
long-horizon hedge-fund fees can reward gains that later reverse
([Ben-David, Birru, and Rossi, NBER 27454](https://www.nber.org/papers/w27454)).
Reward-tampering research also shows why the Agent must not control the reward
channel
([Denison et al., arXiv 2406.10162](https://arxiv.org/abs/2406.10162)). The
research bonus therefore remains small, symmetric, outcome-delayed, and outside
all capital and execution controls.

## B29 — book-aware research and stress-efficient capital

Objective: make discovery and capital competition aware of the existing book
without turning portfolio context into market Evidence or asking Agents to
optimize deterministic risk limits.

Implemented controls in the local development tree:

- every live point-in-time wake freezes a compact portfolio research mandate
  alongside Evidence, Mind memory, open questions, and incentives;
- the mandate reports book posture, gross and stress bps, saturated Alpha
  sources and systematic exposures, and up to three underrepresented search
  directions;
- the prompt contract explicitly treats that mandate as non-Evidence context:
  it may encourage an independent causal payoff, but cannot lower standards,
  force a diversification idea, rank an Opportunity, choose an instrument, or
  allocate capital;
- portfolio construction now applies both aggregate stress-loss capacity and
  per-Alpha-source notional capacity in the same tightest-constraint calculation
  used for single-trade loss, gross, liquidity, and systematic exposure;
- the exact stress and source bridge is carried in every new implementation
  plan and rechecked against the mutable book immediately before an intent;
- current open-position notional and scaled stress loss feed capital competition;
  a full-book rotation must clear the incumbent bps hurdle, preserve or improve
  expected Alpha dollars, and improve expected Alpha per dollar of stress loss;
- legacy or incomplete risk-capital records fail closed to `Wait` rather than
  being granted a favorable assumption.

The new limits remain deterministic survival and allocation controls. They do
not prove an Agent forecast, manufacture return, raise leverage, authorize a
new instrument, or change the research-only Shadow/Paper boundary.

## B30 — completed-bar research-priority funnel

Objective: turn already captured market observations into a small, auditable
research queue before expensive Agent work, without converting a technical
screen into a thesis or trading signal.

Implemented controls in the local development tree:

- only Massive daily Raw rows known by the frozen wake and belonging to a fully
  completed prior session enter the screen;
- up to eight sessions per approved symbol produce bounded one- and five-day
  return, SPY-relative return, volume-ratio, range-ratio, breadth, and dispersion
  observations;
- at most one seed is assigned to each orthogonal Trader Mind, preserving both
  route diversity and independent exploration when no seed clears the screen;
- every seed states a research question, first smart rejection, and required
  market, causal-source, and rival-explanation tests;
- seeds are non-Evidence and cannot be cited, ranked, expressed, or capitalized;
  a Trader Mind must re-fetch the observation and bind any Candidate to current
  frozen or tool-collected Evidence;
- the full agenda has a point-in-time snapshot hash, survives same-wake recovery,
  and is reprojected from PostgreSQL to reject tampering;
- incomplete current-session bars, future-known rows, stale revisions, invalid
  prices, thin history, and weak anomalies create no seed.

This stage improves research coverage and prioritization. It is not a technical
strategy, a backtest, a recommendation, or evidence that the screen forecasts
returns.

## B31 — shared catalyst-risk ledger

Objective: prevent several superficially different securities from consuming
independent risk budgets when their payoff depends on the same underlying
catalyst.

Implemented controls in the local development tree:

- every open Shadow position is joined back to its immutable Opportunity
  binding and projected into a normalized catalyst bucket;
- missing historical lineage is assigned to `legacy-unclassified`, never to an
  apparently clean independent bucket;
- the frozen portfolio research mandate names saturated catalyst clusters as
  non-Evidence context, so Trader Minds can search for genuinely independent
  payoffs without treating diversification pressure as proof;
- the portfolio constructor adds catalyst remaining capacity to the same
  tightest-constraint calculation used for loss, gross, stress, Alpha source,
  systematic exposure, and exit liquidity;
- every ready plan carries the exact catalyst key and before/limit/after bridge;
- immediately before an entry intent, the live book is reconstructed and the
  catalyst limit is checked again, preventing a concurrent or later position
  from making a previously valid plan unsafe.

This is a deterministic concentration control. It does not estimate statistical
correlation, validate the catalyst, increase leverage, or establish that a
diversified-looking book contains Alpha.

## B32 — decision-impact research director

Objective: spend scarce active-research calls on distinct unresolved decisions
without allowing a queue score to become conviction, expected return, or a
capital instruction.

Implemented controls in the local development tree:

- only `forming` and `ranked` point-in-time Opportunities enter the queue;
  expired horizons, closed or rejected work, and active Shadow positions are
  excluded because monitoring owns the latter;
- each queue item binds an immutable parent Opportunity and exact question ID;
  question identity covers origin and normalized prompt content;
- deterministic integer priority uses only Opportunity state, question origin,
  and remaining horizon, with explicit reason codes persisted beside the score;
- the queue first preserves Opportunity diversity, then admits at most two
  questions across at most two parents;
- no more than two different questions are assigned to different Trader Minds,
  and at least two of the four Minds remain in independent discovery;
- a follow-up output must copy its exact assigned parent and prompt; choosing a
  different open question fails before persistence;
- every per-Mind Run freezes the global queue and its exact assignment, the
  loopback Run API exposes that state, and same-wake recovery reconstructs the
  global view instead of inheriting one Mind's scoped mode;
- canonical revalidation rejects unchecked model-copy or priority tampering
  before the Scout batch enters durable state.

This director allocates research attention only. It cannot supply Evidence,
change a rank, choose an expression, modify a risk limit, create an intent, or
claim that a high-priority question contains Alpha.

## B33 — evidence-bound quality and execution comparison

Objective: prevent research activity from masquerading as research quality and
make payoff selection compare economically meaningful implementations without
turning deterministic metrics into an automatic trade score.

Implemented controls in the local development tree:

- source-family, independent-domain, non-news-depth, and cross-check credit is
  derived only from frozen Evidence cited by the Candidate or exact validated
  tool call/source pairs that it binds;
- completed but unbound browsing remains recorded as process cost and produces
  an explicit screen-grade reason instead of silently increasing quality;
- collected tool results are still promoted to append-only Evidence, while the
  durable Scout artifact retains their exact validated provenance for replay;
- every market-valid expression exposes time-adjusted expected Alpha dollars,
  expected Alpha per stress-loss dollar, estimated costs, target notional, and
  execution-reserve headroom to the independent implementation Auditor;
- these economics remain separate fields rather than a blended score, so a
  lower-efficiency carrier may be selected only for a stated payoff reason such
  as materially better thesis purity, timing fit, or bounded convexity;
- guarded buy limits use the observed ask as a hard ceiling, automatic repricing
  remains disabled, and the execution contract rejects a limit that chases
  above the captured market.

This stage improves evidence discipline and implementation comparability. It
does not prove the forecasts, select trades mechanically, authorize live
capital, or establish that the system produces Alpha.

## B34 — mature forecast-error reserve and evidence console

Objective: turn sufficiently mature forward forecast errors into a conservative
new-trade control, while making the evidence quality visible without presenting
Shadow results as proven performance.

Implemented controls in the local development tree:

- calibration uses only closed, cost-adjusted, SPY-relative Shadow outcomes
  paired with the exact net-Alpha forecast frozen at entry;
- the first scope is direct stock under the same portfolio-policy version, so
  incomparable ETF and option payoff distributions cannot contaminate the
  reserve;
- fewer than 30 comparable observations remain descriptive and apply neither a
  forecast haircut nor a calibration-derived size change;
- after maturity, the reserve equals historical overforecast bias plus 25% of
  rolling mean absolute error, capped at 500 basis points, and is deducted
  before costs and Alpha decay;
- a directional hit rate below 45% caps new position size at one half; favorable
  calibration may restore ordinary size but can never add leverage;
- the calibration policy, sample, reserve, and capital posture are frozen into
  every implementation plan and reloaded immediately before intent; a tighter
  result requires replanning;
- the Shadow-book console exposes comparable closes, confidence interval,
  realized Alpha, forecast error, directional hit rate, reserve, and the
  tightest evidence-driven capital multiplier, including empty and immature
  states.

The thresholds are conservative frozen policy parameters, not parameters fitted
to the current sample. This stage reduces repeated overconfidence and makes the
proof burden operationally visible. It does not establish positive Alpha.

## B35 — forward lifecycle diagnostics and legacy-risk quarantine

Objective: separate discovery quality from implementation and exit leakage,
while preventing incomplete historical records from understating portfolio
risk.

Implemented controls in the local development tree:

- every completed Shadow position derives a point-in-time lifecycle diagnostic
  from executable bid observations captured while the position was open and the
  actual close price;
- the diagnostic records maximum favorable excursion, maximum adverse
  excursion, observed peak-to-trough drawdown, exit capture, time to best
  observed price, and holding time without interpolating missing intraday data;
- the Alpha summary and Shadow-book console aggregate those fields and expose a
  positive-excursion miss rate so research, timing, and exit leakage can be
  investigated separately;
- fewer than 30 measured positions remain explicitly `collecting`; the metrics
  are descriptive at every sample size and do not tune prompts, exit rules,
  ranking weights, or capital;
- malformed path observations are skipped rather than blocking durable close
  accounting or final performance measurement;
- legacy or malformed open positions without a trustworthy stress ticket are
  charged their full current notional as stress loss, and valid scaled stress is
  clamped between zero and current notional.

This stage deliberately refuses automatic policy optimization. Strategy
selection across many signals or exit variants can create severe multiple-test
bias, and implementation costs can erase apparently attractive gross returns.
See Novy-Marx's
[multiple-signal backtest analysis](https://www.nber.org/papers/w21329), Bailey
and López de Prado's
[Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
and the Review of Financial Studies work on the
[implementable efficient frontier](https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhag022/8524346).
The lifecycle fields are an audit surface for a later preregistered study, not
evidence that ALTA has discovered a profitable exit policy.

## F1 — sustained forward Shadow evidence

This is the next meaningful stage. It is an observation program, not a one-week
feature sprint.

Minimum operating plan:

1. run one controlled cycle and one full market-session soak;
2. operate continuously for 6–12 weeks;
3. target at least 30–50 independent, cost-adjusted, benchmarkable closed Shadow
   observations before making directional performance claims;
4. report missingness, source uptime, Agent completion, no-op, Wait, no-fill,
   exposure, and cost data alongside returns;
5. freeze model, prompt, policy, and source versions during each evaluation
   window unless a safety issue requires a recorded change.

Acceptance requires a data-quality review and an honest conclusion, including a
negative or inconclusive result.

## F2 — ablation and attribution

Only after F1 has enough data should ALTA compare:

- each Scout removed in turn;
- Moderator enabled versus deterministic aggregation only;
- Expression Auditor enabled versus deterministic gates only;
- individual sources and source families;
- model and prompt versions;
- ranked versus unranked Opportunities.

The goal is to estimate incremental contribution, not reward Agents for verbose
artifacts or high confidence.

## F3 — unattended or broader Paper rollout

The project authorizes only the explicit one-cycle acceptance above. Any
scheduled, continuous, multi-position, larger-size, options, or portfolio-level
Paper proposal must be reviewed as a separate capital system with:

- an isolated process and credential scope;
- an exact Paper account allowlist with no discovery or fallback;
- idempotent order intents, acknowledgements, reconciliation, and kill switch;
- independent risk limits and operator step-up authorization;
- no live-account type or endpoint;
- extensive failure injection and a reversible rollout.

Nothing in the current roadmap authorizes that broader work, and live trading
remains a permanent non-goal.

## Verification matrix

Before accepting any future stage, run the checks appropriate to the affected
layers:

```shell
corepack pnpm check
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
./alta env python -m alta_asterism demo
./alta env python -m alta_asterism replay
./alta env python -m alta_asterism soak
./alta env down
```

Also verify:

- fresh unpacked-source locked dependency installation;
- migration up/down/up for schema changes;
- deterministic replay and failure recovery;
- loopback API authentication and bounded responses;
- signal-driven shutdown with no remaining child processes;
- distributable-source archive secret scans;
- documentation, license, attribution, and research-only claims.

See [Reproducibility](../../REPRODUCIBILITY.md) for the release definition and
[Autonomous Shadow operations](../operations/autonomous-shadow.md) for the
production-shaped research loop.
