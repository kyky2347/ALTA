# ALTA publication security audit

Audit date: 2026-08-29

Target: the exact source tree and new Git history prepared for
`https://github.com/kyky2347/ALTA`

Scope: tracked first-party source, documentation, configuration, synthetic test
fixtures, the attributed Codex vendor boundary, generated-state exclusions,
credential handling, deterministic reproducibility, and final process shutdown.

## Conclusion

The reviewed publication tree contains no known real credential, API key,
broker account identifier, owner-local path, or unrelated prior-project identity.
Generated state, virtual environments, caches, databases, credentials, provider
responses, and build products are excluded from source control.

This is a bounded engineering review, not a mathematical guarantee that every
unknown secret format or software defect is impossible. Any later credential
finding requires immediate publication stop, provider-side rotation, history
remediation, and a complete rescan.

## Publication checks

| Check                                                 |                                             Result |
| ----------------------------------------------------- | -------------------------------------------------: |
| Gitleaks 8.30.1 over the exact publication tree       |                                         0 findings |
| Gitleaks 8.30.1 over the complete publication history |                                         0 findings |
| detect-secrets 1.5.0 over first-party non-test source |                                         0 findings |
| pnpm production dependency audit                      |                           no known vulnerabilities |
| pip-audit over the installed Opportunity OS runtime   |                           no known vulnerabilities |
| Synthetic fixture and credential-keyword review       |                                               PASS |
| Unrelated prior project/account identity scan         |                                         0 findings |
| First-party owner-local absolute-path scan            |                                         0 findings |
| `.env.example` non-empty credential placeholders      |                                                  0 |
| Local generated credential state                      |           present under ignored `.alta/`; 0 staged |
| Largest tracked file                                  |                                    less than 1 MiB |
| Clean tracked checkout and locked install             |                                               PASS |
| Node gateway / harness tests                          |                                         159 passed |
| Opportunity OS tests                                  |                                         264 passed |
| Isolated capital-package tests                        |                                          25 passed |
| Ruff lint and format checks                           |                                               PASS |
| Prettier and Markdown checks                          |                                               PASS |
| Deterministic demo / replay                           |                                   exact hash match |
| Accelerated 14-cycle soak                             |                 PASS; 0 failures; 0 manual repairs |
| ALTA-managed containers after verification            |                                                  0 |
| Loopback service listeners after verification         |                                                  0 |
| Research Director deployment                          | 2 unique follow-ups; 2 explore; 4/4 Runs succeeded |
| Cold operator-console clone                           |     one command; locked install/build; protocol v2 |
| Browser lifecycle acceptance                          |        Start → ready → safe stop; capital disabled |

The clean tracked checkout produced three Candidates, three Opportunities, one
audited expression, and one fully observed Shadow position. Replay reproduced
the exact SHA-256 snapshot
`16be618841b4ced276fea1c3297bd0a934093b995bce50bfadad0b74e9f9816c`.
No LLM, market-data provider, news service, Tiger endpoint, or broker order path
was called by this deterministic acceptance.

A separate 2026-08-28 service cold start did invoke the configured research
models. It exposed and fixed two context-budget failures, then completed with
two unique follow-up assignments, two independent exploration Runs, and four
successful Trader Minds. The cycle ended `MVP_IDLE`; capital remained disabled,
no broker path or order was used, and the service, listener, PostgreSQL, and
Redis were stopped. This is an orchestration acceptance, not an Alpha claim.

## Scan interpretation

The full-tree Gitleaks scan uses the repository's default rules plus narrowly
reviewed, exact-path exceptions for public upstream Codex fixtures. It has no
broad vendor, extension, or generated-directory exemption. Public certificate
fixtures required by the pinned upstream HTTP tests remain tracked; no private
key is included.

detect-secrets separately scans first-party production source, configuration,
and documentation. Tests contain intentionally obvious values such as
`fixture-secret` and `synthetic-private-key` to verify redaction and privilege
boundaries. Those values were reviewed as non-credentials, remain covered by
the complete Gitleaks scan, and are never accepted as production defaults.
Dependency lockfile hashes and attributed upstream fixtures are not interpreted
as owner credentials.

The current operator console exposes only credential configuration state,
source kind, editability, and a short one-way fingerprint. Raw provider values
are accepted through a bounded write-only request, cleared in the browser,
stored atomically outside the repository with owner-only permissions, and never
returned by the control API. Credential changes fail closed while any research
runtime process is active. Tiger remains outside this surface and capital stays
disabled.

The publication inventory is generated from Git's exact staged index, not from
the development directory. Ignored `.alta/`, `node_modules/`, `.venv/`, caches,
logs, and local service state therefore cannot enter the initial history by
accident. The root ignore rules are deliberately narrow enough to retain the
upstream Codex `secrets` source crate and public certificate fixtures required
for reproducibility.

## Credential and authority boundary

Real provider or broker credentials may exist only in an operator-controlled
process environment, operating-system secret manager, or owner-only external
`~/.config/alta/credentials/` directory. Project-local `.alta/secrets/` is
reserved for generated PostgreSQL, Redis, and dashboard values and remains
ignored.

Research child environments use an allowlist and do not inherit repository,
database, cache, market-data, or broker credentials. Repository maintenance is
an operator action. Tiger support is Paper-only, disabled by default, isolated
from the research runtime, and unavailable through the loopback HTTP API.

## Release gate

Before every later release:

1. install from a clean clone using all lockfiles;
2. run Node, Opportunity OS, capital, formatting, and lint gates;
3. verify deterministic replay and the relevant recovery paths;
4. scan both the exact tracked tree and the complete Git history in redacted
   mode with current scanners;
5. confirm generated state, credentials, account data, licensed provider
   payloads, and local paths are absent; and
6. stop ALTA and confirm zero managed containers, services, listeners, and Paper
   positions or orders.

If a real secret is found, revoke and rotate it at the provider before treating
source cleanup as complete. Deleting a file or commit does not invalidate an
already exposed credential.
