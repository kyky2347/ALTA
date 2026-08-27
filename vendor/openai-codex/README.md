# OpenAI Codex source substrate

This directory contains the minimum upstream source substrate required to build
ALTA's project-local Codex App Server harness. It is vendored source, not ALTA
original code, and GitHub Linguist excludes it from ALTA's language statistics.

- Upstream: <https://github.com/openai/codex>
- Pinned upstream commit: `4861236f06d0df397436531b4aa3d7fa6975959c`
- License: Apache-2.0; see the repository root `LICENSE` and `NOTICE`
- ALTA modifications: 13 Rust source/test files, listed in `CHANGES.md`

The upstream snapshot is intentionally complete at the Rust-workspace boundary
so Cargo workspace resolution and the project-local App Server build remain
reproducible. Unrelated upstream SDKs, release automation, documentation, and
monorepo tooling are not part of ALTA's publication tree.

The source is retained because ALTA adds provider-neutral collaboration aliases
and project-local product identity while using the real Codex App Server
protocol. The Opportunity OS itself lives outside this directory in
`alta-src/` and `alta-runtime/`.

Build only the binaries ALTA uses:

```shell
./alta build
```

Do not present this directory as ALTA-authored code or remove upstream copyright
notices. Upstream syncing is an explicit review operation, never an automatic
dependency update.
