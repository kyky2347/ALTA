# Reproducibility contract

ALTA separates deterministic software verification from non-deterministic model
and market outcomes. A fresh clone must reproduce the former without requiring
an API key or brokerage account.

## What is reproducible

A fresh clone can reproduce:

- the locked Node and Python environments;
- database migrations and synthetic point-in-time fixtures;
- evidence normalization, identity, deduplication, and completion;
- two-private-assessment discussion and ranking contracts;
- Stock / ETF / Option / Wait proposal and independent audit contracts;
- deterministic replay hashes, idempotency, recovery, API/SSE behavior, and
  cost-adjusted Shadow accounting;
- autonomous recovery after repeated cycle failure, periodic heartbeats, and
  supervisor replacement of a live-but-unready child;
- secret-free launchd/systemd-user definitions, endpoint-conflict rejection,
  liveness-specific process-group cleanup, and host-service lifecycle state;
- a project-local Codex App Server binary from the pinned source snapshot; and
- all Node, Python Opportunity OS, and isolated capital-boundary tests.

A fresh clone cannot guarantee identical LLM prose, external API responses,
market conditions, future returns, or profitable Alpha.

## Locked inputs

| Layer                | Lock or pin                                                                    |
| -------------------- | ------------------------------------------------------------------------------ |
| Node.js              | `package.json` engines and `pnpm-lock.yaml`                                    |
| Python runtime       | Python 3.12 constraint and `alta-runtime/python/uv.lock`                       |
| Capital boundary     | `alta-runtime/capital-python/uv.lock`                                          |
| Codex Rust substrate | `vendor/openai-codex/UPSTREAM_COMMIT`, `rust-toolchain.toml`, and `Cargo.lock` |
| PostgreSQL and Redis | image digests in `alta-runtime/compose.yaml`                                   |
| Schema               | ordered migrations in `alta-runtime/migrations/`                               |

## Fresh-source verification

Prerequisites are macOS or Linux, Node.js 22+, pnpm 10.33+, `uv`, and OrbStack
or Docker Desktop. Rust is needed only to rebuild the custom App Server harness.
Start from a fresh clone of the canonical repository.

```shell
cd /absolute/path/to/ALTA
corepack pnpm install --frozen-lockfile
uv sync --project alta-runtime/python --frozen
uv sync --project alta-runtime/capital-python --frozen
./alta env setup --dev
./alta test
./alta env python -m pytest -q alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
```

To verify services and deterministic fixtures:

```shell
./alta env setup
./alta env python -m alta_asterism migrate upgrade
ALTA_ENVIRONMENT=shadow ALTA_MASSIVE_ENABLED=0 \
  ./alta env python -m alta_asterism doctor
./alta env python -m alta_asterism demo
./alta env python -m alta_asterism replay
./alta env python -m alta_asterism soak
./alta env down
```

The final command must leave no ALTA-managed service running.

Host installation is intentionally not part of a credential-free fresh-source
gate because it changes user login state. Its definition and lifecycle logic
are covered by the Node suite. A maintainer performing a release acceptance may
run `./alta service install`, exercise recovery, then finish with
`./alta service uninstall` and `./alta env down`. macOS launchd is the exercised
`0.7.0` host path; Linux systemd-user generation is deterministic test coverage.

## Rebuilding the agent harness

Install the Rust toolchain declared by the vendored workspace and run:

```shell
./alta build
./alta doctor
```

The V8 sandbox dependency may be built from source with
`V8_FROM_SOURCE=1 ./alta build`. Maintainers may instead pre-provision the
checksum manifest, archive, and binding in `ALTA_RUSTY_V8_CACHE_DIR`, or provide
the two absolute local-file overrides documented in the README. Build output and
runtime state remain under local `.alta/`. ALTA does not replace a global
`codex` installation or write credentials into source.

## External acceptance

Real-market Shadow acceptance is intentionally not bit-for-bit reproducible.
When external providers are enabled, the durable record must include:

- source and observation timestamps;
- raw-content hashes and normalized Evidence IDs;
- the frozen wake and policy version;
- model/provider identity and structured outputs;
- quote timestamps, instrument-resolution evidence, and refusal reasons; and
- Shadow entry/exit observations, costs, benchmark, and forward horizon;
- when explicitly enabled, sanitized Paper action/status/quantity transitions
  and final zero-position/zero-open-order verification.

The acceptance result may be `Wait` or `MVP_IDLE`. Those are valid research
outcomes, not test failures. The optional Tiger path may submit only one-share
Paper orders under the documented acceptance boundary. Live orders and real
capital are never permitted.

## Release gate

A release candidate is acceptable only when:

1. locked installs succeed from a clean clone;
2. Node, Python, capital-boundary, format, and static checks pass;
3. migrations, replay, and recovery are deterministic where specified;
4. the exact tracked tree and complete Git history pass redacted secret scans;
5. only synthetic fixtures are included;
6. research-only and no-live-capital boundaries remain accurate; and
7. the system is stopped with zero live services, zero open Paper positions,
   and no unrecorded broker mutation.

See [SECURITY.md](SECURITY.md) and the
[operations guide](docs/operations/autonomous-shadow.md) for the corresponding
safety and runtime procedures.
