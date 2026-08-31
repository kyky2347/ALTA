# Architecture overview

ALTA is opportunity-centric: agents wake because information changed, not
because a fixed analyst roster must produce a trade. Deterministic software
protects time, evidence, budgets, auditability, and the capital boundary; LLMs
retain freedom over research interpretation and expression choice.

```mermaid
flowchart TB
  host["[Code] Host service<br/>launchd · systemd-user · dependency restore"]
  supervisor["[Code] 24×7 supervisor<br/>readiness watchdog · capped restart backoff"]
  scheduler["[Code] Single-owner scheduler<br/>heartbeat · clean runtime rebuild"]
  sources["[Code] Finlight, Massive,<br/>and bounded public sources"]
  evidence["[Code] Append-only Raw + Evidence<br/>point-in-time frozen wake"]
  marketfunnel["[Code] Completed-bar research funnel<br/>relative · volume · range · breadth"]
  attention["[Code] Research Attention Portfolio<br/>one continuation · broader entity coverage"]
  mandate["[Code] Frozen portfolio research mandate<br/>stress · factor · Alpha-source · catalyst · underlying concentration"]
  scouts["[Agents] Four active Trader Minds<br/>Web · news · social · finance research"]
  thesis["[Code] Frozen Thesis Ledger<br/>claim · observable · confirm · invalidate · due"]
  diligence["[Code] Research diligence<br/>actual tools · source diversity · next test"]
  mindmemory["[Code] Per-Mind experience<br/>bounded · prior-cycle · non-Evidence"]
  foundry["[Code] Foundry + cross-cycle registry<br/>stable identity · dedup · refresh"]
  agenda["[Code] Open research agenda<br/>next test · rejection · Assessor gaps"]
  director["[Code] Research Director<br/>decision gap · horizon · unique assignment"]
  assessors["[Agents] DeepSeek Pro + Grok 4.6<br/>locked private assessment"]
  underwriting["[Agents] Two locked scenario tickets<br/>SPY-relative odds · payoff · risks"]
  decision["[Agents + Code] PM decision intelligence<br/>priced-in · variant · base rate · readiness · half-life"]
  moderator["[Agent] Kimi K3 Moderator<br/>evidence-bound, maximum two rounds"]
  ranking["[Code] 1–90 day decision-edge gate<br/>independent lift · quality · conservative Alpha"]
  expression["[Agent] DeepSeek Pro implementation PM<br/>up to three payoff hypotheses"]
  instrument["[Code] Market-validated tournament<br/>exact quote or option chain for each"]
  portfolio["[Code] Per-hypothesis construction<br/>net edge · single/book stress · gross · Alpha/factor/catalyst buckets"]
  allocation["[Code] Per-hypothesis capital test<br/>Alpha clock · dollars · stress efficiency · rotation"]
  auditor["[Agent] Independent Grok 4.6 audit<br/>Alpha source · factors · basis risk · hedge posture"]
  validation["[Code] Refresh selected instrument and revalidate<br/>absolute limit · shortfall · no chase"]
  shadow["[Code] Shadow open<br/>forward quote and fill"]
  monitor["[Agent] Position Monitor<br/>append-only pillar review"]
  measurement["[Code] Exit and measurement<br/>price · time · cost · benchmark"]
  cohort["[Code] Frozen forward cohort<br/>cycle attribution · drift · missingness"]
  feedback["[Code] PIT Alpha feedback<br/>Mind · archetype · route · research mode · maturity gates"]
  governance["[Code] Rolling Alpha capital governance<br/>drawdown · uncertainty · survival posture"]
  calibration["[Code] Mature forecast calibration<br/>overforecast reserve · directional caution"]
  paper["[Code] Optional isolated Tiger Paper mirror<br/>BUY 1 · SELL 1 · verify flat"]

  host --> supervisor --> scheduler --> sources
  sources --> evidence --> marketfunnel
  evidence --> scouts
  marketfunnel -. bounded non-Evidence question .-> scouts
  foundry -. prior production Candidates .-> attention
  attention -. frozen non-Evidence exploration seats .-> scouts
  scouts --> thesis --> diligence --> foundry --> assessors --> underwriting --> decision --> moderator
  shadow -. current PIT book · non-Evidence .-> mandate
  mandate -. later point-in-time wake .-> scouts
  mindmemory -. next frozen wake .-> scouts
  foundry --> agenda
  agenda --> director
  director -. exact parent + question · later wake .-> scouts
  moderator --> ranking --> expression --> instrument --> portfolio --> allocation --> auditor
  auditor --> validation --> shadow --> monitor --> measurement --> cohort
  measurement --> feedback
  measurement --> governance
  measurement --> calibration
  feedback -. later frozen wake · non-Evidence .-> scouts
  governance -. next pre-intent budget .-> portfolio
  calibration -. next forecast and pre-intent recheck .-> portfolio
  shadow -. explicit acceptance only .-> paper
```

`[Agent]` nodes own hypotheses and bounded judgment. `[Code]` nodes own source
provenance, immutable identity, scoring mechanics, quotes, safety gates, and
measurement. The App Server harness starts and supervises the Agent turns but
does not collapse their independent contexts into a shared chat.

## Decision hand-offs

```mermaid
sequenceDiagram
  participant O as Cycle orchestrator (code)
  participant D as Research Director (code)
  participant S as Active Trader Minds (4 Agents)
  participant F as Foundry and registry (code)
  participant A as Private Assessors (2 Agents)
  participant M as Moderator (Agent)
  participant R as Ranker (code)
  participant E as Expression Agent
  participant K as Portfolio Constructor (code)
  participant L as Capital Allocator (code)
  participant U as Independent Auditor
  participant G as Market and Shadow gate (code)
  participant V as Alpha capital governance (code)
  participant Q as Forecast calibration (code)
  participant P as Position Monitor Agent
  participant C as Isolated Paper executor (code)

  O->>D: Frozen open questions, state, horizon, and idle streak
  D-->>S: Unique exact follow-ups plus at least two independent exploration seats
  O->>S: Frozen wake, attention seat, completed-bar seed, portfolio mandate, prior experience, mature feedback, revocable incentive, and per-role tools
  S->>S: Explore independently or test only the exact assigned question
  S-->>F: Candidate or no-op plus research record and falsifiable pillars
  F->>F: Compare durable identity and Raw content history
  F-->>O: Persist bounded registry memory and open questions for the next frozen wake
  S-->>O: Persist per-Mind experience separately from Evidence
  F->>A: Versioned Opportunity and cited Evidence
  A-->>F: Two locked scenarios plus priced-in, variant, base-rate, readiness, and half-life records
  F->>M: Opportunity plus both locked views
  M-->>R: Bounded discussion artifact plus deterministic research-quality record
  R->>E: Opportunity plus both scenario and decision tickets; rank score remains hidden
  E-->>G: Up to three pillar-bound payoffs with Alpha source, systematic exposures, hedge posture, and basis risk
  loop Each distinct hypothesis within the cycle request budget
    G->>G: Obtain exact quote or filtered option chain
  G->>K: Instrument, locked tickets, and current Shadow book
    V-->>K: Current-policy rolling capital multiplier
    Q-->>K: Comparable mature forecast-error reserve and size multiplier
    K-->>G: Tightest single/book stress, gross, liquidity, purity, Alpha-source, shared-factor, shared-catalyst, and cross-carrier underlying capacity, or Wait
    G->>L: Time-adjusted edge and incumbent frozen tickets
    L-->>G: Admit, Wait, or replace after bps, Alpha-dollar, and stress-efficiency hurdles
  end
  G->>U: Admissible slate, implementation tickets, and bounded open book
  U-->>G: Independently reclassify exposures and select exactly one hypothesis or Wait
  G->>G: Refresh selected quote, rerun construction/allocation, and freeze execution
  G-->>O: Durable Wait or Shadow-open event
  opt Explicit Tiger Paper acceptance
    G->>C: One-share limit intent after every gate passes
    C-->>G: Paper fill and exact-position reconciliation
  end
  G->>P: Frozen selected pillars plus newer frozen Evidence
  P-->>G: Append-only pillar states and a bound invalidation flag
  G-->>O: Deterministic hold or exit plus measurement
  O->>V: Latest cost-adjusted, benchmarked close per position
  O->>Q: Entry-frozen forecast paired with comparable forward outcome
  O->>O: Attribute result to entry-frozen Mind, archetype, route, and research mode
  O-->>S: Same-Mind feedback on a later PIT wake after maturity gates
```

Only structured artifacts cross a hand-off. One shared canonical JSON budget
registry constrains every durable Agent input and complete prompt. A transient
deadline, App Server failure, missed active-research requirement, or malformed
Scout result gets at most two fresh retries with the same frozen input and
durable Run identity; every prior failure stays append-only. A failed or
unavailable dependency does not grant the next role more discretion; it narrows
the outcome to a durable `Wait` or an idle cycle.

## Trust boundaries

| Boundary     | Guarantee                                                                                                                                                                                                                                                                                            |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Evidence     | Raw-first, versioned, timestamped, source-bound, bounded                                                                                                                                                                                                                                             |
| Trader Minds | Active read-only research is required; attention seats, completed-bar seeds, prior state, and portfolio context are non-Evidence; lineage and actual diligence are recorded; repository-host APIs are absent                                                                                         |
| Thesis       | Original pillars are immutable, observable, time-bounded, source-linked, and reviewed only through append-only events                                                                                                                                                                                |
| Decision     | Company thesis, security readiness, reference class, base rate, must-be-true conditions, and edge half-life remain separate and independently locked                                                                                                                                                 |
| Ranking      | Both independent inside views must beat their own base rates, diligence must be decision-grade, and the lower expected-Alpha forecast must remain positive after a fixed dispersion reserve                                                                                                          |
| Agents       | Separate App Server turns, structured contracts, full-prompt byte fitting, no broker tools                                                                                                                                                                                                           |
| Recovery     | Host restart, process-group cleanup, same-frozen-wake rebuild, at most two auditable fresh Scout retries, and bounded optional-connector backoff                                                                                                                                                     |
| Market data  | Exact quote plus explicitly labeled liquidity proxy; absence resolves to Wait                                                                                                                                                                                                                        |
| Expression   | Up to three pillar-bound payoffs receive actual market and portfolio tickets; independent Auditor sees no rank and selects one or Wait                                                                                                                                                               |
| Portfolio    | Synthetic Shadow NAV; research-quality gate, loss, gross, liquidity, Alpha purity, shared factor/catalyst buckets, decay, incumbent competition, rolling Alpha survival, forecast calibration, carrier-specific execution-cost reserve, fail-closed legacy risk, and pre-intent recheck              |
| Execution    | Frozen arrival benchmark, absolute limit, shortfall budget, participation cap, timeout cancellation, one attempt, no automatic repricing, and append-only round-trip TCA                                                                                                                             |
| Underwriting | Evidence-bound ex-ante estimates, disagreement reserve, and the entry-frozen cost-adjusted forecast stay distinct from realized Alpha; only 30+ comparable closes may create a downside-only forecast reserve                                                                                        |
| Feedback     | Entry-frozen Mind/archetype/route/mode credit; strict PIT cutoff; 30-Mind/10-slice maturity; no auto-policy                                                                                                                                                                                          |
| Capital      | Shadow by default; optional exact-account, one-share Paper acceptance; no live mode                                                                                                                                                                                                                  |
| Operations   | Boot-managed host, loopback API, one owner, split Scout/judgment deadlines, two watchdogs, capped backoff, clean stop                                                                                                                                                                                |
| Evaluation   | Immutable configuration, Run attribution, cohort projection, latest-measurement deduplication, explicitly small-sample Alpha statistics, observed MFE/MAE/drawdown/exit capture, per-carrier execution-cost calibration, negative-evidence-only capital throttling, and visible calibration maturity |

## Runtime components

| Path                           | Responsibility                                                |
| ------------------------------ | ------------------------------------------------------------- |
| `alta-src/`                    | project-local Codex launcher, provider gateway, bounded tools |
| `alta-dashboard/`              | responsive React operator console and production static build |
| `alta-runtime/python/`         | Opportunity OS domain, agents, orchestration, API             |
| `alta-runtime/capital-python/` | isolated Tiger Paper-only acceptance executor                 |
| `alta-runtime/compose.yaml`    | loopback PostgreSQL and Redis                                 |
| `vendor/openai-codex/`         | pinned and attributed Codex Rust substrate                    |

PostgreSQL is the system of record. Redis is disposable support state. The
dashboard contract remains the read-only `/api/v1` JSON/event surface. The
bundled frontend is served by a separate loopback operator-console process,
which keeps the bearer token server-side and owns only lifecycle controls. It
does not run inside the autonomous research process. Its own user-level service
manager provides login startup and crash recovery without coupling console
availability to autonomous research. An owner-only atomic hand-off exposes an
unlogged one-time browser URL, while the persistent HttpOnly session survives a
console restart and per-process CSRF state rotates.
