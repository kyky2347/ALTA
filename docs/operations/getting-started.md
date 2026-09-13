# Getting started

This guide takes a new contributor from a fresh source directory to the
deterministic ALTA research lifecycle. Agent-backed and external-data operation
are optional later steps and require explicit credentials supplied outside the
source tree.

> [!WARNING]
> ALTA is research-only software. Use Replay and internal Shadow mode. Do not
> connect live brokerage credentials or send live orders during development and
> verification. Optional operator-authorized Broker API execution has a separate
> [setup, account-proof and risk boundary](../broker-expansion.md).

## Choose the right path

| Goal                                  | Credentials                    | External network          | Recommended command                   |
| ------------------------------------- | ------------------------------ | ------------------------- | ------------------------------------- |
| Verify the repository                 | None                           | Dependency install only   | `./alta test`                         |
| Run the deterministic lifecycle       | None                           | No source or model calls  | `python -m alta_asterism demo`        |
| Verify deterministic replay           | None                           | No source or model calls  | `python -m alta_asterism replay`      |
| Run the simulated market-session soak | None                           | No source or model calls  | `python -m alta_asterism soak`        |
| Use autonomous Agents                 | DeepSeek API key               | Model access              | `opportunityd` or `autonomous --once` |
| Use Massive or Finlight               | Explicit environment injection | Provider API              | Autonomous Shadow path                |
| Run bounded Paper acceptance          | Explicit Tiger Paper config    | Model, data, Paper broker | `alta_asterism acceptance`            |

Start with the credential-free fixture path. It verifies most structural
contracts without introducing external state or variable data.

## Prerequisites

- macOS or Linux;
- Node.js 22 or newer;
- npm; dashboard startup uses Corepack when available and otherwise bootstraps
  the lockfile's pinned pnpm version;
- `uv`;
- OrbStack or Docker Desktop for PostgreSQL and Redis;
- Rust only when rebuilding the pinned Codex harness.

The project manages Python 3.12 and application dependencies under ignored
`.alta/` state. It does not require a global Python package installation.

## Prepare and install

Start from a fresh clone:

```shell
git clone https://github.com/kyky2347/ALTA.git
cd /absolute/path/to/ALTA
corepack pnpm install --frozen-lockfile
./alta env setup --dev
```

Check the local runtime without starting a research service:

```shell
./alta status
./alta env status
```

## Run the credential-free fixture

Start PostgreSQL and Redis, apply migrations, and run the deterministic path:

```shell
./alta env up
./alta env python -m alta_asterism migrate upgrade
./alta env python -m alta_asterism demo
./alta env python -m alta_asterism replay
./alta env python -m alta_asterism soak
```

Expected properties:

- the demo completes as `MVP_RUNNING` or the explicit no-op state documented by
  the selected fixture;
- replay produces the same SHA-256 lifecycle hash;
- the soak covers a full simulated market session with no stage failure;
- no model, market-data, news, Tiger, or broker call occurs.

Stop the managed environment when finished:

```shell
./alta env down
```

## Run tests

The standard acceptance path is:

```shell
corepack pnpm check
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
```

The Node suite validates the project launcher, provider gateway, bounded tools,
resource control, sensitive-path policy, and process lifecycle. The Python suite
validates Opportunity OS contracts and integration paths. The capital suite is
separate because the Paper boundary must not become an implicit dependency of
the research runtime.

See [Reproducibility](../../REPRODUCIBILITY.md) for the clean-clone gate.

## Build the project-local Codex harness

Agent-backed operation uses the pinned source substrate under
`vendor/openai-codex/`. Install the Rust toolchain declared in
`vendor/openai-codex/codex-rs/rust-toolchain.toml`, then run:

```shell
V8_FROM_SOURCE=1 ./alta setup
./alta doctor
```

The build and runtime remain under `.alta/`. ALTA does not replace a global
`codex` executable or edit `~/.codex/config.toml`.

OpenAI authentication uses the official Codex login path:

```shell
codex login
./alta openai login status
```

Provider entry points are:

```shell
./alta openai
./alta deepseek
./alta grok
./alta kimi
./alta models
```

Third-party providers require their documented environment variables. Do not
place real values in source, Markdown, examples, fixtures, logs, or distributed
`.env` files.

## Secret handling

Inject credentials from an operating-system secret manager, an external helper,
the owner-only `~/.config/alta/credentials/` directory, or the parent process
environment. `ALTA_CREDENTIALS_DIR` may select another absolute external root.
Never place credentials inside the repository, even in an ignored directory.
The application and Agent child environments have different privilege scopes.

Use `./alta credentials status` for a value-free inventory and
`./alta credentials set <slot>` for hidden-input, atomic replacement. Use
`./alta credentials reload` after an external secret manager changes a file.
The status includes one truncated, combined revision so operators can see
whether a running host needs a reload; it never exposes a value or an
individual-key fingerprint.

Agents do not receive:

- Massive or Finlight API keys;
- database or Redis credentials;
- Tiger configuration or account identifiers;
- provider credentials that are not required by the local gateway child;
- access to the external credential directory through ALTA file tools.

`.env.example` is a schema reference only and must contain placeholders. Before
publication, scan the exact tracked tree and complete Git history in redacted
mode.

## Bounded research tools

The local gateway exposes a provider-neutral, read-only research surface. The
general ALTA harness supports multiple model providers. Scouts and position
monitoring default to DeepSeek V4 Flash; assessment, moderation, expression,
and audit use the heterogeneous routes documented in the
[Opportunity OS architecture](../architecture/opportunity-os.md). These roles
autonomously call ALTA's internal MCP tools; desktop ChatGPT/Codex plugins are
not injected into isolated research turns. Tool families include:

| Family      | Representative capability                         | Main boundary                            |
| ----------- | ------------------------------------------------- | ---------------------------------------- |
| Core Web    | Search, fetch, and same-origin crawl              | Public URLs, bounded pages and bytes     |
| Research    | Federated queries and batch fetch                 | Bounded fan-out and partial failure      |
| Discovery   | Sitemap, feed, and public archive lookup          | Bounded records and depth                |
| Academic    | OpenAlex, Crossref, and arXiv federation          | Bounded results and deduplication        |
| Social      | Login-free public discovery and bounded reads     | No login or access-control bypass        |
| News        | Aggregators, publishers, and primary institutions | Independent source deadlines             |
| Finance     | Market, macro, filings, plus optional Finnhub     | One explicit source per call             |
| TradingView | Deterministic display navigation                  | Navigation only; no content scraping     |
| Local files | Bounded parsing of supported workspace files      | Workspace-only and sensitive-path denial |

All network paths enforce public-URL checks, concurrency, deadlines, output
caps, caching, circuit breakers, and cancellation. They do not bypass login,
paywalls, CAPTCHAs, private channels, site policy, or private network boundaries.

The detailed source behavior lives in the code and tests. Keep this guide at the
stable user-contract level so it does not become an outdated inventory.

## Start the read-only service

For fixture-backed local API development:

```shell
./alta env up
./alta env python -m alta_asterism migrate upgrade
./alta env python -m alta_asterism opportunityd --host 127.0.0.1
```

The service binds to loopback and exposes health plus a read-only `/api/v1`
surface. Configure `ALTA_API_TOKEN` when another local process needs access.

Key endpoints:

| Endpoint                     | Purpose                                                 |
| ---------------------------- | ------------------------------------------------------- |
| `/health/live`               | Process liveness                                        |
| `/health/ready`              | Dependency and heartbeat readiness                      |
| `/api/v1/system/summary`     | Durable object counts                                   |
| `/api/v1/system/runtime`     | Sources, Agents, safety, and measurement state          |
| `/api/v1/mvp/status`         | Current and recent cycles                               |
| `/api/v1/alpha/summary`      | Forward Shadow measurement and underwriting calibration |
| `/api/v1/evaluation/summary` | Frozen cohort quality and readiness                     |
| `/api/v1/stream`             | Cursor-based server-sent events                         |

No order endpoint exists.

## Start autonomous Shadow research

Read [Autonomous Shadow operations](autonomous-shadow.md) before enabling real
adapters. The minimum configuration shape is:

```shell
export ALTA_ENVIRONMENT=shadow
export ALTA_AUTONOMOUS_ENABLED=true
export ALTA_AGENT_PROVIDER=deepseek
export ALTA_AGENT_MODEL=deepseek-v4-flash
export ALTA_AGENT_REASONING_EFFORT=high
export ALTA_THESIS_PROVIDER=deepseek
export ALTA_THESIS_MODEL=deepseek-v4-pro
export ALTA_DISCONFIRMING_PROVIDER=grok
export ALTA_DISCONFIRMING_MODEL=grok-4.6
export ALTA_MODERATOR_PROVIDER=kimi
export ALTA_MODERATOR_MODEL=kimi-k3
export ALTA_EXPRESSION_PROVIDER=deepseek
export ALTA_EXPRESSION_MODEL=deepseek-v4-pro
export ALTA_AUDIT_PROVIDER=grok
export ALTA_AUDIT_MODEL=grok-4.6
export ALTA_AGENT_DEADLINE_SECONDS=180
export ALTA_REASONING_AGENT_DEADLINE_SECONDS=300
export ALTA_SCOUT_CONCURRENCY=4
export ALTA_MASSIVE_ENABLED=true
export ALTA_MASSIVE_DISCOVERY_ENABLED=false
export ALTA_MASSIVE_MAX_REQUESTS_PER_CYCLE=8
# Inject MASSIVE_API_KEY and optional FINLIGHT_API_KEY externally.

./alta env up
./alta env python -m alta_asterism migrate upgrade
./alta env python -m alta_asterism doctor
./alta env python -m alta_asterism autonomous --once
```

Use one controlled cycle before starting a long-running supervisor. A normal
result may be `MVP_IDLE`, a structured `Wait`, or no-fill. Those outcomes are
evidence that the refusal path works, not operational failures.

Then install the self-scheduling, self-recovering host service once:

```shell
./alta service install
./alta service status
```

The installer uses macOS launchd or Linux systemd-user, restores managed
dependencies, refuses an occupied loopback endpoint, and waits for readiness.
The scheduler owns the cadence internally; cron or another Agent must not call
`autonomous --once` repeatedly. Use `./alta service run` only as a portable
foreground fallback.

The optional risk-sized Tiger Paper acceptance is documented separately in the
[operations runbook](autonomous-shadow.md). It is never enabled by these normal
service commands and must not receive live credentials.

## Safe shutdown

Stop the host service and wait for child completion. Then run:

```shell
./alta service stop
./alta service status
./alta env status
./alta env down
```

Verify:

- all supervisors report `stopped`;
- PostgreSQL and Redis report `stopped` when no longer needed;
- no App Server, API, scheduler, or Agent child remains;
- the scheduler advisory lock is released;
- temporary Agent workspaces contain no credential material.

Do not use force-kill as the routine shutdown path because it bypasses durable
cycle and child-process cleanup.

## Troubleshooting

### `doctor` reports a missing key

The enabled adapter requires explicit external injection. Either inject the key
for a controlled Shadow run or disable that adapter for a fixture-only research
experiment. Do not copy the key into the repository.

### A cycle finishes as `MVP_IDLE`

This is expected when no Candidate survives the Opportunity gates. Inspect the
read API for Scout outcomes, source posture, and gate reasons.

### An expression becomes `Wait`

Inspect the Expression detail for unavailable market data, stale quotes, spread,
cost, instrument selection, portfolio conflict, or Auditor rationale. `Wait` is
a durable action plan, not a missing result.

### A Shadow intent receives no fill

ALTA requires a real quote observed after intent and frozen latency. It never
uses an earlier quote to manufacture a simulated fill.

### A source is degraded

Check its deadline, rate limit, circuit state, and cursor. A partial source
failure should remain visible while independent sources continue.

### Replay differs from the original hash

Treat this as a release blocker. Confirm that the same fixture, migration,
versioned contracts, and frozen wake were used. Do not update a golden hash
until the behavioral difference is understood.

## Next reading

- [Architecture overview](../architecture/overview.md)
- [Detailed Opportunity OS design](../architecture/opportunity-os.md)
- [Implementation roadmap](../implementation/roadmap.md)
- [Security policy](../../SECURITY.md)
- [Research scope and non-goals](../research-scope.md)
