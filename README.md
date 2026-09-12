# ALTA

## Autonomous LLM Trading Asterism

_A virtual trading platform operated by specialized LLM agents._

[![CI](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml/badge.svg)](https://github.com/kyky2347/ALTA/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Use: research only](https://img.shields.io/badge/use-research--only-orange.svg)](docs/research-scope.md)

[简体中文](README.zh-CN.md) · [繁體中文](README.zh-HK.md) ·
[Quick start](#run-locally) · [Architecture](docs/architecture/overview.md) ·
[Verification](docs/audits/operator-scout-reliability-2026-09-12.md) · [Website](https://alta.silment.com)

**Trade the opportunity. The stock, ETF, or option is only its carrier.**

ALTA turns autonomous market research into a durable, inspectable process.
Four specialist Scouts look for changes, dislocations, causal links and expectation
gaps. Independent reviewers challenge the thesis. A separate desk compares ways
to express it, while deterministic controls govern risk, authority and execution.

The ambition is a virtual research firm—not another chatbot that recommends a
ticker. The test is whether an idea survives evidence, disagreement, costs and time.

> [!IMPORTANT]
> Experimental, research-only software. Not investment advice, an order-management
> system or evidence of profitable Alpha. Autonomous execution supports internal
> **Shadow Paper** and explicitly authorized **Tiger Paper**. Additional broker
> connectors are a separate, incomplete integration—not enabled autonomous live trading.

## See the work

Current console captures, focused on recent saved research and the specialist team.
Open an image for the full view. Research hypotheses are not approved trades.

[![Opportunity workspace](docs/assets/alta-operator-console-en.jpg)](docs/assets/alta-operator-console-en.jpg)

| The research team                                                                       | Inside an opportunity                                                                                             |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| [![Agent desk](docs/assets/alta-agent-desk-en.jpg)](docs/assets/alta-agent-desk-en.jpg) | [![Opportunity evidence](docs/assets/alta-opportunity-detail-en.jpg)](docs/assets/alta-opportunity-detail-en.jpg) |
| Independent reviewers, model routes and recorded work.                                  | Original decision brief; complete lineage remains inspectable.                                                    |

| Broker connections                                                                                                | Model routing                                                                                             |
| ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| [![Broker configuration](docs/assets/alta-broker-connections-en.jpg)](docs/assets/alta-broker-connections-en.jpg) | [![Agent model settings](docs/assets/alta-model-settings-en.jpg)](docs/assets/alta-model-settings-en.jpg) |
| Six provider-specific forms; credentials and execution authority stay separate.                                   | Assign models by role while preserving independent review.                                                |

September 12, 2026 · English interface · original Agent artifacts retain their
authored language. Capture scope, record IDs and image hashes are in the
[release review](docs/audits/operator-scout-reliability-2026-09-12.md).
No credentials or account details are included.

## How the firm works

```mermaid
flowchart LR
    S["Sense<br/>4 independent Scouts"] --> F["Foundry<br/>normalize · deduplicate"]
    F --> D["Debate<br/>case · countercase"]
    D --> R["Rank<br/>urgency · portfolio fit"]
    R --> X["Express<br/>stock · ETF · option · Wait"]
    X --> A["Audit<br/>evidence · risk · authority"]
    A --> E["Execute<br/>Shadow / Tiger Paper"]
    E --> M["Monitor<br/>revalidate · exit · attribute"]
    M -. "evolve Trader Minds" .-> S
```

**LLMs decide what deserves investigation. Code decides what may change durable
state or capital.** No Agent can supply its own evidence, approve its own risk
and move broker capital. Missing evidence is a reason to wait, not improvise.

| Layer      | What is implemented                                                                                                   |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| Discovery  | 4 Scouts, 13 bounded read-only tools, date-aware search, issuer crawling, feeds, academic and archive lookups         |
| Judgment   | Independent model routes, falsifiable thesis pillars, counterevidence, portfolio-aware ranking and carrier comparison |
| Continuity | Persistent follow-up questions, catalyst deadlines, checkpoint recovery and evolving Trader Minds                     |
| Evaluation | Point-in-time forecasts, forward outcomes, benchmark-relative measures and downside-only risk calibration             |
| Operations | Three-language console, API/SSE, run history, write-only credentials, model settings and lifecycle controls           |

Scouts default to **11 tool calls, 196k chargeable tokens and 420 seconds per
attempt**, within hard caps. More budget buys verification, not an idea quota.
Sources have pacing, cancellation and nested deadlines; incomplete retrievals
stay visible. [Retrieval design and measured limits →](docs/audits/research-retrieval-review.md)

Structured drafts get one budget-bound correction in the same research context,
with exact retrieved citations and an audit trail. Insufficient or stale evidence
still leads to `Wait`—more retries are not a substitute for a current signal.

## Run locally

**Requirements:** macOS or Linux, Node.js 22+ with npm, Python 3.12, `uv`,
Docker/OrbStack and sufficient disk space. Initial installation needs internet.
Building the pinned custom harness additionally needs its Rust toolchain.

```shell
git clone https://github.com/kyky2347/ALTA.git
cd ALTA
npm run dashboard
```

The command installs locked frontend dependencies when needed, builds the current
console and opens an authenticated loopback page. In the console:

1. **API connections** — separate research/data APIs and broker connections; saved secrets are never returned.
2. **Agents → Agent models** — select available models; independent opposing roles must differ.
3. **Start** — prepare the locked backend environment and start its managed dependencies.
4. **Stop** — drain the research service and stop its managed database/cache.

Brokerage authorization is separate and off by default. A saved key does not
grant trading permission. Follow the [setup guide](docs/operations/getting-started.md)
for the Agent harness, provider requirements and troubleshooting.

Prefer explicit installation? Run `corepack pnpm install --frozen-lockfile`
before `./alta dashboard`.

### Verify without paid APIs

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

Integration tests require the managed PostgreSQL environment; a plain `pytest`
invocation without `DATABASE_URL` is not the full acceptance command.
See [Reproducibility](REPRODUCIBILITY.md) for deterministic demo/replay and clean-source verification.

## Execution: capability is not permission

| Mode / boundary             | Actual support                                                                                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shadow Paper                | ALTA-managed fills, costs, positions, monitoring and exits; no broker mutation                                                                                  |
| Tiger Paper                 | Existing adapted executor; exact account binding, explicit authorization, fresh audit and restart reconciliation                                                |
| Five pre-adapted connectors | Alpaca, IBKR, Futu/moomoo, Longbridge/Longport and Schwab: private profiles, provider-specific code and read-only checks; end-to-end account acceptance pending |

The new Tiger live connector is also unaccepted. The independent six-provider
package contains execution-engine code but is **not wired into autonomous
research**. Broker gateways, OAuth, account permissions and verification cannot
be replaced by a generic API-key field. [Provider matrix and remaining work →](docs/broker-expansion.md)

## Built for interruption

PostgreSQL is the source of truth; Redis is support state. Work is claimed by a
fenced owner, broker intent precedes submission, and uncertain orders require
reconciliation—not blind retries. The console retains its last valid snapshot
through connection loss and rejects stale control-plane edits.

September 12 verification covers **816 tests**, production frontend build,
real no-order research, authenticated API checks and clean-source installation.
The release review records failures found, repairs, final outcomes and shutdown
evidence. It is not a 24×7 uptime certification or a guarantee of profitability.

Unproven: sustained out-of-sample Alpha, every power-loss scenario, universal
browser compatibility, and additional brokers' real-account order acceptance.

## Project map

```text
alta-dashboard/                React operator console · English / 简体中文 / 繁體中文
alta-src/                      Node gateway · bounded tools · launch/control
alta-runtime/python/           research lifecycle · PostgreSQL · API/SSE
alta-runtime/capital-python/   isolated Tiger Paper executor
alta-runtime/broker-python/    isolated experimental connectors and execution library
vendor/openai-codex/            pinned, attributed Agent-harness source
docs/                          architecture · operations · verification
```

[Architecture](docs/architecture/overview.md) ·
[Operator guide](docs/operations/operator-console.md) ·
[24×7 runbook](docs/operations/autonomous-shadow.md) ·
[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License and provenance

ALTA-authored source is [Apache-2.0](LICENSE). ALTA uses a modified, pinned
Apache-2.0 [OpenAI Codex](https://github.com/openai/codex) snapshot as its local
App Server/harness, plus separately licensed packages and API integrations.
Upstream notices are retained; modifications and dependencies are documented in
[ATTRIBUTION.md](ATTRIBUTION.md), [NOTICE](NOTICE) and the
[vendored change record](vendor/openai-codex/CHANGES.md).

Independently maintained; not endorsed by OpenAI or any named data/brokerage
provider. Provider terms, exchange entitlements and data-redistribution rights
remain the operator's responsibility.
