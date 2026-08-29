# Attribution and third-party boundaries

This document separates code ALTA maintains from code, packages, services, and
ideas that come from elsewhere. It complements—not replaces—the repository
[license](LICENSE), [notice](NOTICE), dependency licenses, and service terms.

## Project identity

ALTA is an independently maintained source project at
`https://github.com/kyky2347/ALTA`. It is not an OpenAI product, OpenAI release,
or endorsed investment system.

Independence does not erase provenance. ALTA contains a modified source snapshot
of OpenAI Codex and identifies that boundary explicitly below. Names and
trademarks are used only to describe compatibility or source origin.

## OpenAI Codex source substrate

ALTA uses source from [openai/codex](https://github.com/openai/codex), licensed
under Apache-2.0, as its App Server and agent-harness substrate.

| Item                 | Value                                      |
| -------------------- | ------------------------------------------ |
| Upstream repository  | `https://github.com/openai/codex`          |
| Pinned source commit | `4861236f06d0df397436531b4aa3d7fa6975959c` |
| Local boundary       | `vendor/openai-codex/codex-rs/`            |
| ALTA-modified files  | 13 Rust source or test files               |
| Detailed change list | `vendor/openai-codex/CHANGES.md`           |

The snapshot contains Codex App Server, protocol, core, sandbox, MCP, and
supporting Rust crates required to reproduce ALTA's project-local binary. ALTA's
changes add provider-neutral collaboration aliases, a project-local ALTA
identity, and associated tests. They do not claim authorship of the upstream
implementation and do not modify Codex authentication, approval semantics,
sandbox network flags, or the App Server wire protocol.

The upstream source stays in an explicit vendored boundary. Its source,
copyright notices, license, and modification record remain visible.

ALTA consumes the official `openai-codex==0.144.4` Python package from PyPI for
its App Server client. The SDK source is not duplicated in this repository.

## ALTA-maintained implementation

The primary ALTA maintenance boundary is:

| Path                           | Responsibility                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `alta`                         | Project-local command entry point                                                                       |
| `alta-src/`                    | Provider catalog, local gateway, bounded tools, storage controls, supervisor, and Node tests            |
| `alta-runtime/python/`         | Opportunity OS, evidence contracts, orchestration, durable state, API/SSE, migrations, and Python tests |
| `alta-runtime/capital-python/` | Isolated Tiger Paper-only acceptance executor and tests                                                 |
| `alta-runtime/compose.yaml`    | Loopback-only PostgreSQL and Redis services                                                             |
| `docs/`                        | Architecture, operations, implementation history, and audit records                                     |

Synthetic fixtures contain no real account, position, credential, order, or
licensed market-data payload. Historical milestone documents are retained for
engineering traceability and are labeled as archived material.

## Direct dependencies

### Python

Locked dependencies include:

- `openai-codex`, the official Codex App Server client;
- `finlight-client` and `massive`, wrapped by ALTA's bounded, raw-first adapters;
- `tigeropen==3.7.0`, used only by the separately locked Paper acceptance
  package under its declared Apache-2.0 license;
- `psycopg`, `psycopg-pool`, and `pgvector` for durable PostgreSQL state;
- `redis` and `hiredis` for coordination, with PostgreSQL remaining the source
  of truth;
- Pydantic for typed contracts; and
- Hatch, pytest, and Ruff for build and verification.

Exact versions and hashes are in `alta-runtime/python/uv.lock`. The isolated
capital package has its own `pyproject.toml` and lockfile.

### Node.js and Rust

The ALTA gateway uses Node.js standard-library APIs. The operator console uses
locked package dependencies rather than copied application code: React and
Radix UI under MIT, Lucide icons under ISC, Tailwind CSS under MIT, and the
Fontsource-packaged Geist font under SIL Open Font License 1.1. shadcn's
MIT-licensed registry tool generated the local composition primitives that ALTA
maintains in `alta-dashboard/src/components/ui/`. Prettier, Oxlint, TypeScript,
Vite, and the remaining frontend build tools are development dependencies.
Exact versions, integrity hashes, and transitive packages are recorded in
`pnpm-lock.yaml`; their own package license files remain installed with the
packages.

Rust package versions, sources, and checksums for the Codex substrate are
recorded in `vendor/openai-codex/codex-rs/Cargo.lock`. ALTA does not relicense
third-party crates as ALTA-authored code.

The raster displayed in the operator product lockup was supplied directly by
the ALTA project owner for this repository. It was copied byte-for-byte into the
frontend asset boundary and was not sourced from any compared GitHub project.

### Containers

`alta-runtime/compose.yaml` pins PostgreSQL/pgvector and Redis images by digest.
The images are not copied into this repository and remain subject to their own
licenses.

## External services and data

ALTA may call compatible APIs, but it does not include their server code, model
weights, proprietary datasets, credentials, or account content.

| Service family                 | ALTA use                                       | Explicit boundary                              |
| ------------------------------ | ---------------------------------------------- | ---------------------------------------------- |
| OpenAI Codex / Responses       | Authentication, inference, App Server protocol | No model weights or service implementation     |
| DeepSeek, xAI, Moonshot        | Optional model-provider adapters               | No provider model or server code               |
| Massive and Finlight           | Bounded market-data and news adapters          | No copied data product; responses remain local |
| Brave, Jina, SearXNG           | Optional search or reader adapters             | No embedded index or server implementation     |
| SEC, OpenAlex, Crossref, arXiv | Bounded public-source adapters                 | No bulk dataset redistribution                 |
| Tiger / `tigeropen`            | Exact-account, one-share Paper acceptance      | No SDK source copied; no live-account support  |

ALTA calls `tigeropen` through its public package API and does not copy or modify
Tiger SDK source. Operators are responsible for brokerage agreements, Paper
account rules, API terms, data licenses, rate limits,
redistribution rules, and regional requirements. A service name in code or
documentation does not imply partnership or endorsement.

## Conceptual references

The following public projects were reviewed as architecture comparisons. ALTA
does not vendor or import their code, prompts, models, fixtures, or datasets.

| Project                                                          | Concept compared                                       | Not incorporated                                         |
| ---------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Separate bullish/bearish evaluation and bounded debate | Runtime, prompts, data layer, trading code               |
| [RD-Agent](https://github.com/microsoft/RD-Agent)                | Hypothesis → experiment → feedback loop                | Automatic production promotion, implementation, datasets |
| [Qlib](https://github.com/microsoft/qlib)                        | Point-in-time research and production separation       | Runtime, models, datasets, workflows                     |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)        | Uniform expression interface; no direct LLM ordering   | Agents, prompts, ledger, executor                        |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)    | Director/scheduler and financial-tool taxonomy         | Agents, tools, prompts, datasets                         |
| [NOFX](https://github.com/NoFxAiOS/nofx)                         | Decision → risk → execution → record comparison        | AGPL code, prompts, UI, execution implementation         |

An architectural idea is not treated as copied code. Any future source
inclusion must pin the exact commit and file, verify its license, preserve its
copyright notice, and update this document before merge. Code without a clear
license is not copied.

## Required maintenance

When adding or upgrading an external component:

1. Record whether it is copied, modified, package-managed, API-only, or a
   conceptual reference.
2. Preserve applicable copyright, license, and notice material.
3. Update the relevant lockfile and verify a clean build.
4. Run secret scans over the complete history that will be published.
5. Keep real credentials, account identifiers, and licensed data out of source,
   fixtures, logs, issues, and release artifacts.

This is an engineering provenance record, not legal advice. License, trademark,
service-term, and data-rights review remains necessary before redistribution or
commercial use.
