# ALTA engineering policy

These instructions apply to automated contributors and human maintainers.

## Scope and safety

- ALTA is research-only. Do not add a live environment, live brokerage account
  discovery, or real-order mutation path.
- Keep credentials out of source, fixtures, prompts, logs, commits, and tests.
- Preserve deterministic `Wait` behavior when evidence, freshness, liquidity,
  or an independent audit is insufficient.
- Do not weaken replay, point-in-time, idempotency, recovery, or capital
  isolation to make a demonstration pass.

## Repository boundary

- The canonical source repository is `https://github.com/kyky2347/ALTA`.
- Do not discover, contact, restore, or add any earlier project remote or owner
  identity. Repository operations require an explicit maintainer request.
- Research Agents must never receive repository credentials, write access, or
  repository-host tools. Source control is an operator boundary, not a trading
  capability.
- Keep generated state, credentials, provider responses, account information,
  licensed market data, and local machine paths out of commits and CI output.

## Ownership boundaries

- `alta-src/` owns the Node gateway, bounded tools, launch control, and tests.
- `alta-runtime/python/` owns Opportunity OS application logic and API/SSE.
- `alta-runtime/capital-python/` is an isolated Paper-only package.
- `vendor/openai-codex/` is attributed third-party source. Change it only when
  ALTA cannot meet a harness requirement through an adapter.
- New application behavior belongs outside the vendored Codex tree whenever
  practical.

Keep modules cohesive, interfaces typed or schema-validated, side effects at
the edges, and durable state transitions explicit. Prefer small focused modules
over expanding central launchers or orchestrators.

## Required verification

For ALTA application changes, run the smallest relevant checks and then the
complete first-party gate:

```shell
./alta test
uv run --project alta-runtime/python pytest -q alta-runtime/python/tests
uv run --project alta-runtime/python ruff check \
  alta-runtime/python/src alta-runtime/python/tests
uv run --project alta-runtime/python ruff format --check \
  alta-runtime/python/src alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
```

If Rust source changes, also run formatting and the affected crate tests from
`vendor/openai-codex/codex-rs/`; use the local `justfile` one directory above.

Before publication, verify locked installation in a clean clone and scan the
complete Git history plus working tree for secrets. Preserve `LICENSE`,
`NOTICE`, `ATTRIBUTION.md`, and upstream copyright headers.
