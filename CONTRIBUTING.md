# Contributing to ALTA

ALTA welcomes focused research-engineering contributions. The project is
experimental and research-only: changes must not introduce live brokerage
control, weaken the explicit risk-bounded Paper acceptance without a separate
design review, or claim proven Alpha.

## Before making a change

1. Read the [architecture overview](docs/architecture/overview.md),
   [research scope](docs/research-scope.md), and [security policy](SECURITY.md).
2. Keep application changes in `alta-src/` or `alta-runtime/` unless the pinned
   Codex harness is demonstrably the right boundary.
3. Write a local design note first for wire-contract changes, new data
   providers, schema migrations, or changes to safety behavior.

## Development setup

```shell
corepack pnpm install --frozen-lockfile
uv sync --project alta-runtime/python --frozen
uv sync --project alta-runtime/capital-python --frozen
```

Run the checks documented in [AGENTS.md](AGENTS.md). Tests must use synthetic,
license-safe fixtures and may not depend on personal credentials.

Provider and broker credentials must remain outside the project tree. ALTA
uses environment variables or the external owner-only directory
`~/.config/alta/credentials/`; a local ignored folder is not considered a safe
long-term credential store because development tools may create private
workspace checkpoints.

## Change quality

- Keep each change focused and explain the architectural boundary affected.
- Add integration coverage for lifecycle or orchestration changes.
- Preserve point-in-time semantics, replayability, idempotency, and explicit
  refusal reasons.
- Update contracts, migrations, operations docs, and attribution together with
  behavior changes.
- Do not include generated local state, provider responses, account information,
  or copied material without a verified redistribution license.

## Pull requests

Open an issue for changes that alter contracts, schemas, model routing, data
providers, or safety policy. Keep pull requests reviewable and use the repository
template to describe behavior, safety impact, verification, and rollback.

The `main` branch is maintainer-controlled. Contributions are proposed through a
fork and pull request; opening a pull request does not grant write access. By
submitting source, you agree that it may be distributed under Apache-2.0 and
that you have the right to submit it.

Security findings belong in a private
[repository security advisory](https://github.com/kyky2347/ALTA/security/advisories/new),
never a public issue or discussion.
