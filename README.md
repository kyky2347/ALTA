# ALTA

## Autonomous LLM Trading Asterism

_A virtual trading platform operated by specialized LLM agents._

[![CI](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml/badge.svg)](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Use: research only](https://img.shields.io/badge/use-research--only-orange.svg)](docs/research-scope.md)

[简体中文](README.zh-CN.md) · [繁體中文](README.zh-HK.md) ·
[Quick start](#run-locally) · [Architecture](docs/architecture/overview.md) ·
[Verification](docs/audits/broker-routing-2026-09-13.md) · [Website](https://alta.silment.com)

**Start with the opportunity. Choose the instrument that best expresses it.**

ALTA is a local, multi-agent market-research system with an operator console,
internal simulation and a separate broker execution boundary. Four specialist
Scouts pursue leads; independent reviewers challenge the evidence; a strategy
desk compares ways to act. Every handoff leaves an inspectable record.

The idea is a virtual research firm, not a chatbot that recommends a ticker:
a thesis must survive disagreement, costs and time before it deserves capital.

> [!IMPORTANT]
> Experimental research software—not investment advice, a production OMS or
> evidence of profitable Alpha. Execution has two modes: **Shadow** and
> **Broker API**. Broker orders require a verified, explicitly selected account
> and separate authorization. Six connectors exist; live-account acceptance is
> not established. [Current execution limits ↓](#two-modes-one-explicit-destination)

## What you get

ALTA brings three normally disconnected jobs into one local workspace. The
output is not just a list of securities: it is a research trail you can challenge,
an explicit decision, and a way to compare that decision with what happened next.

| Investigate                                                               | Decide                                                                              | Follow through                                                                     |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Autonomous Scouts search for changes, anomalies and unanswered questions. | Separate reviewers test the thesis; a strategy desk compares instruments and costs. | Persistent records connect monitoring, exits, forward outcomes and later research. |

For researchers, this makes disagreement and source quality inspectable. For
developers, it separates Agent judgment from scheduling, data contracts and
execution. For an operator, it provides one place to see what ran, what remains
uncertain and what—if anything—has permission to act.

## See the work

Follow an opportunity from its source evidence to reviewer decisions. Open any
image for the full view; saved hypotheses are not approved trades.

[![Opportunity workspace](docs/assets/alta-operator-console-en.jpg)](docs/assets/alta-operator-console-en.jpg)

| Research team                                                                           | Inside an opportunity                                                                                             |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| [![Agent desk](docs/assets/alta-agent-desk-en.jpg)](docs/assets/alta-agent-desk-en.jpg) | [![Opportunity evidence](docs/assets/alta-opportunity-detail-en.jpg)](docs/assets/alta-opportunity-detail-en.jpg) |
| Who investigated, which model ran and what it produced.                                 | The thesis, supporting evidence and reviewer decisions.                                                           |

| Execution controls                                                                                                               | Model routing                                                                                             |
| -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| [![Execution mode and account controls](docs/assets/alta-broker-connections-en.jpg)](docs/assets/alta-broker-connections-en.jpg) | [![Agent model settings](docs/assets/alta-model-settings-en.jpg)](docs/assets/alta-model-settings-en.jpg) |
| Two modes, an explicit destination and separate authority.                                                                       | Choose models by role while preserving independent review.                                                |

Research captures: September 12, 2026; execution setup: September 13. English UI;
Agent artifacts retain their authored language. The setup capture shows an
unauthorized configuration, not a connected broker. Scope and image hashes:
[research review](docs/audits/console-readability-2026-09-12.md) ·
[execution review](docs/audits/broker-routing-2026-09-13.md). No credentials or account details.

## Run locally

**Requirements:** macOS or Linux, Node.js 22+ with npm, Python 3.12, `uv`,
Docker/OrbStack and sufficient disk space. Initial setup needs internet; building
the pinned custom harness also needs its Rust toolchain.

```shell
git clone https://github.com/kyky2347/ALTA.git
cd ALTA
npm run dashboard
```

The command installs locked frontend dependencies when needed, builds the console
and opens an authenticated loopback page. Continue in the console:

| Step            | What to do                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------ |
| **1 · Connect** | Enter your research/data credentials. Saved secrets are never returned.                          |
| **2 · Assign**  | Choose available models under **Agents → Agent models**. Opposing review roles must differ.      |
| **3 · Start**   | Prepare the locked backend environment and start managed research services. Begin in **Shadow**. |
| **4 · Inspect** | Open a Scout record, follow its citations and compare reviewer verdicts.                         |
| **5 · Stop**    | Drain research and stop the managed database/cache. This does **not** liquidate broker holdings. |

Saving a key never grants trading permission. Model access, data entitlements and
broker account permissions are separate requirements. A healthy service may be
waiting for its next cycle; a `Wait` decision can be the correct result.

[Setup and troubleshooting](docs/operations/getting-started.md) ·
[Operator guide](docs/operations/operator-console.md) ·
[Reproducibility](REPRODUCIBILITY.md)

### Read the console like a research desk

Start with a question, not a counter. The views share record IDs, so a discovery
can be followed into the exact Run, review and event that changed its state.

| Your question                       | Where to look                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| Why is this opportunity here?       | **Research radar → detail:** source references, timestamps, thesis and decision records. |
| What are the Agents actually doing? | **Agent desk:** role, model, saved output, tool activity, context usage and latency.     |
| What changed since I last looked?   | **Activity & history:** ordered events, older pages and the replay ribbon.               |
| What is held, and why?              | **Shadow book** for internal positions; **API Trading** for the selected broker account. |
| What needs attention?               | **System overview / API connections:** source posture, health and verification results.  |

The inspector exposes submitted summaries, structured artifacts and provenance,
not a model's hidden chain-of-thought. Switching the interface language does not
rewrite the underlying research record. Historical playback and the live edge
remain distinct, so an old decision is not mistaken for new activity.

## How the firm works

```mermaid
flowchart LR
    R["Investigate<br/>Scouts → evidence → thesis"] --> J["Challenge<br/>debate → rank → trade plan"]
    J --> G{"Independent audit<br/>and execution gates"}
    G -->|Ready| E["Act & observe<br/>execute → monitor → exit"]
    G -->|Not ready| W["Wait<br/>record the missing evidence"]
    W -. "focused follow-up" .-> R
    E -. "outcomes & Trader Mind updates" .-> R
```

**Research is open-ended; authority is explicit.** LLMs choose what to investigate
and propose how to use it. Code enforces freshness, risk, account isolation and
durable transitions. A persuasive thesis cannot approve its own execution.

### Four minds, different questions

Each Scout has a Trader Mind—its research style, interests and accumulated
lessons. They share tools, not a single agenda.

| Scout              | Question                                                           |
| ------------------ | ------------------------------------------------------------------ |
| Change / event     | What changed in a filing, business or catalyst—and when?           |
| Market dislocation | Why have prices or related securities diverged?                    |
| Causal / policy    | Which second-order effects reach other businesses or industries?   |
| Expectation gap    | What does the market appear to expect, and what could overturn it? |

The toolset includes date-aware search, issuer crawling, feeds, public datasets
and archive lookups. News and social claims are leads, not verified conclusions.
Event time stays separate from retrieval time: a newly fetched page may describe
an old event. Bounded budgets, source pacing and recorded partial results keep
research inspectable. [Retrieval design and limits →](docs/audits/research-retrieval-review.md)

### Who owns each decision

```mermaid
flowchart TB
    O["One versioned opportunity<br/>same cited evidence"] --> A["Thesis assessor<br/>private, locked view"]
    O --> B["Independent challenger<br/>private, locked view"]
    A --> M["Moderator<br/>surface disagreements"]
    B --> M
    M --> R["Code-based ranking<br/>quality, uncertainty and edge gates"]
    R --> E["Expression Agent<br/>compare up to three payoff plans"]
    E --> U["Independent auditor<br/>select one plan or Wait"]
```

The assessors commit their views before seeing the other assessment. The
moderator works from those saved records; it cannot replace a missing source
with consensus. Ranking is software, not an extra Agent voting for its favorite.
Market and portfolio checks sit between a proposed expression and its audit.

Only structured, versioned artifacts cross these handoffs—not an ever-growing
shared chat. Models are configurable by role, with separate choices required
for opposing assessments and for expression versus audit. Model diversity is a
useful control, not proof that the reviewers are statistically independent.

### From an idea to an accountable decision

| Stage              | What must remain inspectable                                                              |
| ------------------ | ----------------------------------------------------------------------------------------- |
| **Thesis**         | What changed, why expectations may be wrong, a falsifier and a time horizon.              |
| **Challenge**      | Counterevidence, independent reviewer decisions and portfolio-aware ranking.              |
| **Expression**     | Eligible instruments, direction, sizing, costs and the case for waiting.                  |
| **Follow-through** | Monitoring, exits, persistent follow-up questions and catalyst deadlines.                 |
| **Learning**       | Point-in-time forecasts, forward outcomes, benchmark comparisons and Trader Mind updates. |

Stocks, ETFs and supported option expressions can be research candidates; the
broker executor has a narrower scope below. The obvious ticker may be illiquid,
already repriced or duplicate another position's risk. `Wait` preserves the
reason and next research question instead of forcing a trade.

The three-language console links evidence, Agent work, decisions and event
history by record ID. Counts of saved records, completed work and currently
running Agents are separate; none is a proxy for investment performance.

### What travels with an opportunity

An Opportunity is the durable research identity; a Candidate is an incoming
lead, and an Expression is a proposed way to act. Deduplication and later
versions keep follow-ups attached to the original question instead of turning
every wake into another apparently new idea.

```text
Opportunity · stable identity, versioned thesis
├── Evidence     sources · event/observation times · content hashes
├── Hypothesis   causal claim · falsifier · expected horizon
├── Reviews      locked assessments · disagreement · decision
├── Expression   instrument · size · cost · independent audit
└── Follow-up    open questions · observations · exit/outcome records
```

These are linked records, not fields that an Agent can freely rewrite. A reader
can trace what was known at the decision time without silently importing later
knowledge. Several headlines about one event need not become several trades.

### An opportunity can outlive a research cycle

The research agenda retains unanswered questions and catalyst deadlines.
Later wakes can assign a focused follow-up while other Scouts continue exploring.
Closing a tab does not cancel that agenda; the durable backend owns it. This is
how the design accommodates a thesis that needs days or weeks to resolve,
without keeping one chat session alive throughout.

Trader Mind experience and portfolio context guide attention, but are not
promoted into source Evidence. Forward results are attributed to the frozen
entry decision; feedback and forecast calibration have maturity gates. Existing
calibration can reduce risk when evidence deteriorates, not autonomously relax
the execution policy after a few lucky outcomes. Long-horizon reliability and
investment skill still require sustained observation.

## Two modes, one explicit destination

| Mode           | What happens                                                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Shadow**     | ALTA manages internal fills, costs, positions and exits. No broker orders.                                                           |
| **Broker API** | Audited plans use the selected broker and explicitly configured **Paper or Live account**. No automatic fallback to Tiger or Shadow. |

```text
Configure → Verify account → Save destination → Authorize → Start
               Paper / Live is an account setting, not a third mode
```

Authorization binds the provider, account, environment and configuration revision.
The backend accepts persisted research and independent audit artifacts—not
browser-supplied orders. A separate monitor refreshes quotes, reconciles orders
and manages exits without waiting for an LLM research cycle.

| Connector status                 | Current boundary                                                                                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Tiger · Alpaca · IBKR · Futu** | Conditional execution paths exist; actual account verification and explicit authorization are required. IBKR also needs a non-executing preview before each order. |
| **Longbridge / Longport**        | Authorization blocked: account/environment identity proof is incomplete.                                                                                           |
| **Schwab**                       | Authorization blocked: permission/history proof and automatic OAuth renewal are incomplete.                                                                        |

These are implementation states, **not six live-account acceptance results**.
The initial broker lifecycle supports **one active plan per account, long USD
stocks/ETFs, whole shares and DAY limit orders**. Options, shorts and multi-plan
portfolio execution are outside that boundary. The legacy Tiger Paper executor
remains isolated for compatibility, not a third selectable mode.

Use an empty, dedicated account for initial authorization. Revoke, reconcile and
resolve existing exposure before switching. Exits are software-managed, not
broker-native protective orders; downtime can delay them. **Stopping ALTA does
not close broker positions.** [Provider matrix and operating limits →](docs/broker-expansion.md)

## Under the hood

```mermaid
flowchart TB
    UI["React console · three languages"] <-->|"authenticated control & reads"| N["Node gateway<br/>launch · credentials · bounded tools"]
    N <--> P["Python research service<br/>scheduler · research lifecycle · API/SSE"]
    P <--> C["Codex App Server<br/>specialized LLM sessions"]
    P <--> DB[("PostgreSQL<br/>records · events · checkpoints")]
    P --> X{"Execution mode"}
    X --> S["Shadow<br/>internal positions & fills"]
    X --> B["Broker API<br/>selected account · separate authority · durable ledger"]
```

The browser is a control surface, not the scheduler. A managed backend owns
research and recovery; PostgreSQL preserves its records, while Redis supports
coordination. Broker intents enter isolated durable ledgers before submission.
Uncertain orders reconcile by identity rather than being blindly retried.

```text
alta-dashboard/                React console · English / 简体中文 / 繁體中文
alta-src/                      Node gateway · bounded tools · launch/control
alta-runtime/python/           research lifecycle · PostgreSQL · API/SSE
alta-runtime/capital-python/   isolated Tiger Paper executor
alta-runtime/broker-python/    isolated broker connectors and execution
vendor/openai-codex/            pinned, attributed Agent harness
docs/                          architecture · operations · verification
```

ALTA is useful for studying multi-agent judgment and building inspectable
financial workflows. It is not a low-latency trading engine or a turnkey
institutional stack. Recovery mechanisms are not a 24×7 uptime certification.

### When reality interrupts

Research progress, browser connectivity and broker state are separate concerns.
The system should not infer that an order failed merely because a response was
lost, or infer that research stopped merely because a tab disconnected.

| Interruption                          | Designed response                                                                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Browser loses its connection          | Retain the last valid in-memory snapshot, mark it stale and back off retries. Reloading a stopped backend cannot recover that browser snapshot. |
| A tool or model times out             | Use bounded retries and recorded failures; incomplete evidence cannot silently advance to execution.                                            |
| A worker or host restarts             | Recover durable work with ownership checks and restart backoff; do not create a second owner for the same work.                                 |
| An order acknowledgement is uncertain | Reconcile the persisted identity with the broker instead of submitting another order blindly.                                                   |
| Price moves while an LLM responds     | Refresh the selected instrument and rerun admission checks; a stale proposal is not permission to chase.                                        |

These are engineering mechanisms with test coverage, not a promise that every
outage is recoverable unattended. Broker sessions, fresh data and a running
backend remain necessary for software-managed exits. Unresolved positions or
ambiguous orders may require operator review before work can safely continue.

## Verify the work

The [September 13 review](docs/audits/broker-routing-2026-09-13.md) records
**916 passing tests** across Node, research, legacy Paper, broker and frontend
suites, plus lint/build checks, clean-source installation and sampled browser
checks. No real account was authorized and no broker order was sent in that
review. [Earlier no-order research run →](docs/audits/operator-scout-reliability-2026-09-12.md)

Three kinds of evidence answer different questions:

| Evidence                       | What it can establish                                                                    |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| **Software checks**            | Deterministic contracts, state transitions, recovery behavior and clean installation.    |
| **Recorded research runs**     | Which sources were reached, what Agents submitted and where a decision stopped.          |
| **Forward investment results** | Outcomes after the frozen decision, net of recorded costs and compared with a benchmark. |

A successful search is not a verified thesis; an approved thesis is not a fill;
a profitable observation is not established Alpha. Keep those measurements
separate when evaluating or extending the project.

Run the offline/contract checks without paid APIs:

```shell
./alta env setup --dev
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --frozen --project alta-runtime/capital-python pytest -q alta-runtime/capital-python/tests
uv run --frozen --all-extras --project alta-runtime/broker-python pytest -q alta-runtime/broker-python/tests
node --test alta-dashboard/tests/*.test.mjs
corepack pnpm check
./alta env down
```

Integration tests need managed PostgreSQL; plain `pytest` without `DATABASE_URL`
is not the complete check. See [Reproducibility](REPRODUCIBILITY.md) for the full
gate, deterministic replay and clean-install scope.

Still unproven: sustained out-of-sample Alpha, live-account order acceptance,
every power-loss scenario and universal browser compatibility. Test results
describe tested behavior, not a guarantee of profit or fault-free operation.

[Architecture](docs/architecture/overview.md) · [24×7 runbook](docs/operations/autonomous-shadow.md) ·
[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License and provenance

ALTA-authored source is [Apache-2.0](LICENSE). A modified, pinned
Apache-2.0 [OpenAI Codex](https://github.com/openai/codex) snapshot supplies the
local App Server/harness; ALTA owns the research lifecycle and execution policy.
Other packages and APIs retain their own licenses and terms. See
[ATTRIBUTION.md](ATTRIBUTION.md), [NOTICE](NOTICE) and the
[vendored change record](vendor/openai-codex/CHANGES.md).

Independently maintained; not endorsed by OpenAI or any named provider.
Operators remain responsible for provider terms, exchange entitlements and
data-redistribution rights.
