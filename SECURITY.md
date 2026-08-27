# Security policy

ALTA is experimental, research-only software. It is not designed or authorized
to control live brokerage accounts or real capital.

## Reporting a vulnerability

Use a private
[repository security advisory](https://github.com/kyky2347/ALTA/security/advisories/new)
for ALTA-specific issues.
Do not place a credential, cookie, account identifier, licensed market data, or
unredacted log in any public tracker, message, source bundle, or CI output.

Report vulnerabilities reproducible in unmodified OpenAI Codex through
[OpenAI's responsible-disclosure program](https://bugcrowd.com/engagements/openai).
Report provider or brokerage account vulnerabilities through that provider's
security channel.

A useful report contains a minimal reproduction, affected version, impact
boundary, and fully redacted logs.

## Credential handling

Real provider or broker credentials may exist only outside the project tree: in
a process environment controlled by the operator, an operating-system/external
secret manager, or the owner-only external directory
`~/.config/alta/credentials/`. Project-local `.alta/secrets/` contains only
locally generated PostgreSQL and Redis passwords and remains ignored.

Never put a real secret in:

- `.env` files, source, fixtures, snapshots, or documentation;
- source archives, review messages, generated reports, or build logs;
- agent prompts, tool arguments, API/SSE payloads, or model-visible state; or
- Compose literals and shell command arguments that can be logged.

`.env.example` contains empty placeholders and non-sensitive defaults only.
Tests must use clearly synthetic values, and errors must redact authorization
headers and credential-shaped fields.

The unattended host definition contains only absolute executable/workspace
paths and lifecycle policy. Its mode-0600 service settings contain non-secret
runtime controls; LLM, Massive, and Finlight values are loaded from the external
owner-only credential boundary at process start. The generated dashboard bearer
token remains in ignored mode-0600 `.alta/secrets/` state and is never printed by
`status`.

## Enforced capability boundaries

- Supported environments are `replay`, `shadow`, and `paper`; there is no live
  mode.
- Research-agent child environments use an allowlist and exclude database,
  Redis, market-data, and broker secrets.
- Tiger is Paper-only. The system does not enumerate accounts, fall back to
  `paper=false`, or expose an HTTP order-mutation API.
- Capital code is isolated from the research runtime. Mutation is disabled by
  default and reachable only through the explicit acceptance command after all
  research and deterministic gates pass.
- The acceptance executor requires an owner-only non-symlink config, exact
  17-digit Paper account SHA-256 binding, empty starting account, one-share DAY
  limit orders, fill reconciliation, confirmed cancellation, and final
  zero-position/zero-open-order verification.
- Research Agents receive neither Tiger credentials nor the executor tool.
- Market-data access uses bounded concurrency, explicit timeouts, and
  fail-closed admission.
- The gateway, database, cache, and observability API bind to loopback by
  default.
- Host installation refuses an occupied loopback endpoint. The host manager
  restarts only the project wrapper; the inner supervisor owns one database
  scheduler and terminates a stuck App Server process group before rebuilding.
- Missing, stale, or unauditable evidence becomes `Wait`; the system never
  invents a fill from a stale historical price.
- File tools reject workspace escape, hidden runtime state, and private-key or
  certificate formats.

## Distribution security gate

Before publishing a commit or release:

```shell
./alta test
uv run --project alta-runtime/python pytest -q alta-runtime/python/tests
uv run --project alta-runtime/capital-python pytest -q \
  alta-runtime/capital-python/tests
uvx --from detect-secrets==1.5.0 detect-secrets scan \
  --all-files --no-verify /absolute/path/to/clean-clone
```

Scan the exact clean clone in redacted mode, then scan the complete Git history
with a second scanner. Compare exact local secret fingerprints without printing
their values. The most recent audit record is
[docs/audits/security-audit.md](docs/audits/security-audit.md).

Audit each supported package ecosystem from its lockfile. For the pinned Codex
snapshot, run `cargo audit --file Cargo.lock` from
`vendor/openai-codex/codex-rs/`. Advisory exceptions must be exact IDs, explain
the dependency path and exposure, and state a concrete removal condition in
both `.cargo/audit.toml` and `deny.toml`; a broad severity or vendor exemption
is not acceptable.

The optional `.gitleaks.toml` contains only exact-path exceptions for reviewed
public test fixtures in the pinned Codex snapshot. Do not replace them with a
broad vendor or file-extension exception.

If a real secret is found:

1. stop distribution;
2. revoke and rotate the credential at the provider;
3. remove it from every source and generated artifact;
4. rescan source bundles, build artifacts, logs, and caches; and
5. publish only after both the working tree and complete history are clean.

Deleting a local file does not replace provider-side credential rotation.

## Supported versions

Security fixes target the latest release on `main`. Archived milestone documents
and historical engineering records are not supported releases.

Codex sandbox and approval guidance is maintained in the official
[Codex security documentation](https://developers.openai.com/codex/agent-approvals-security/).
