# ALTA publication security audit

Baseline audit date: 2026-08-31

Latest delta revalidation: 2026-09-09

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

## Publication delta — 2026-09-09

This review covers the current bilingual console, signal-freshness gates,
read-path resilience, documentation and six replacement screenshots. It does
not reuse an earlier UI capture or claim a new investment-performance result.

| Check                                                                            | Result                                                      |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Gitleaks 8.30.0, exact staged source export                                      | 0 findings under the existing reviewed rules                |
| Gitleaks 8.30.0, complete reachable history                                      | 20 existing commits scanned before publication; 0 findings  |
| Independent detect-secrets 1.5.0, complete staged export, no online verification | 705 raw matches reviewed; no operator credential identified |
| GitHub secret-scanning alerts                                                    | No alerts returned at review time                           |
| Frozen pnpm and both uv installations in an isolated source export               | Passed without copying local credential or runtime state    |
| Language-matched production-build screenshots                                    | 3 English + 3 Chinese; synthetic preview only               |
| Screenshot metadata                                                              | No PNG text or EXIF chunks                                  |

The independent scan deliberately used no new file exclusions or allowlist.
Its 705 raw matches comprise 547 package-integrity hashes in `pnpm-lock.yaml`,
28 first-party test/preview/code-literal matches, and 130 matches in unchanged
vendored source. The latter include dependency pins, non-production signing
fixtures, redaction tests, protocol identifiers, and an upstream public client
identifier. These are not ALTA operator credentials. A clean automated report
must not be manufactured by deleting test coverage or hiding the vendor tree.

The six screenshots were reviewed visually and captured through the current
production frontend's read-only preview mode. No real account, provider
payload, credential entry, local filesystem path or authentication URL was
photographed. Existing license and attribution files remain intact.

The [console reliability review](console-reliability.md) records the 644-test
local application gate, real-stack read-only smoke and browser fault tests.
Dashboard contract tests are now included explicitly in CI. No research cycle,
credential replacement, broker verification or order was requested by this
publication workflow. Existing operator services are not restarted by a push.

The scanner results are bounded evidence, not a guarantee against every
unknown secret format. Ignored runtime state and the external credential store
are excluded from publication; they are not deleted from the operator's machine.

## Publication delta — 2026-09-04

The current staged publication set was revalidated after the cycle-recovery,
Capital-launcher, console-session, auxiliary-polling, current-cycle UI, and
README changes in the unreleased section.

| Check                                                         |                               Result |
| ------------------------------------------------------------- | -----------------------------------: |
| Gitleaks 8.30.0 over exact staged export                      |                           0 findings |
| detect-secrets 1.5.0 over exact staged export                 |                           0 findings |
| Gitleaks 8.30.0 over all 18 commits                           |                           0 findings |
| Exact staged export: locked Node and Python installs          |                                 PASS |
| Node gateway / harness tests                                  |                           190 passed |
| Opportunity OS tests                                          |                           373 passed |
| Isolated capital-package tests                                |                            38 passed |
| Dashboard tests                                               |                             9 passed |
| Ruff, Prettier, Markdown, dashboard lint and production build |                                 PASS |
| pnpm production dependency audit                              |             no known vulnerabilities |
| pip-audit over both installed Python runtimes                 |             no known vulnerabilities |
| cargo-audit 0.22.2 over pinned Codex `Cargo.lock`             | 0 vulnerabilities; 0 policy warnings |

The exact staged export was produced from Git's index, not copied from the
development directory. Its frozen pnpm and uv installs and first-party Node and
dashboard suites passed without a local credential store. The capital process
was not invoked against Tiger; no broker order was submitted. The complete
18-commit history was rescanned after the publication commit and returned zero
findings before push.

GitHub's post-push advisory intake then identified four `fast-uri` advisories
and one `qs` advisory in the transitive shadcn/MCP development-tool chain. The
workspace now pins the first patched versions (`fast-uri 3.1.6` and `qs 6.16.0`)
through exact pnpm overrides and narrowly exempts only those versions from the
seven-day release-age hold. `pnpm why` confirms one patched version of each;
the Node suite, dashboard suite, lint, production build, frozen install, and
publication secret scans were repeated before the corrective push.

## Baseline publication checks — 2026-08-31

| Check                                                 |                                                 Result |
| ----------------------------------------------------- | -----------------------------------------------------: |
| Gitleaks 8.30.1 over the exact publication tree       |                                             0 findings |
| Gitleaks 8.30.1 over the complete publication history |                                             0 findings |
| detect-secrets 1.5.0 over exact distributable source  |                                             0 findings |
| pnpm production dependency audit                      |                               no known vulnerabilities |
| pip-audit over the installed Opportunity OS runtime   |                               no known vulnerabilities |
| Synthetic fixture and credential-keyword review       |                                                   PASS |
| Unrelated prior project/account identity scan         |                                             0 findings |
| First-party owner-local absolute-path scan            |                                             0 findings |
| `.env.example` non-empty credential placeholders      |                                                      0 |
| Local generated credential state                      |               present under ignored `.alta/`; 0 staged |
| Largest tracked file                                  |                                        less than 1 MiB |
| Clean tracked checkout and locked install             |                                                   PASS |
| Node gateway / harness tests                          |                                             183 passed |
| Opportunity OS tests                                  |                                             313 passed |
| Isolated capital-package tests                        |                                              27 passed |
| Ruff lint and format checks                           |                                                   PASS |
| Prettier and Markdown checks                          |                                                   PASS |
| Browser offline/reconnect and safe-stop state         |                                                   PASS |
| Deterministic demo / replay                           |                                       exact hash match |
| Accelerated 14-cycle soak                             |                     PASS; 0 failures; 0 manual repairs |
| ALTA-managed containers after verification            |                                                      0 |
| Loopback service listeners after verification         |                                                      0 |
| Research Director deployment                          |     2 unique follow-ups; 2 explore; 4/4 Runs succeeded |
| Cold operator-console clone                           |         one command; locked install/build; protocol v4 |
| Browser lifecycle acceptance                          |            Start → ready → safe stop; capital disabled |
| Current-build README screenshots                      | synthetic preview; no tokens, accounts, or local paths |

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

A bounded 2026-08-29 EDT smoke also verified the authenticated v8 portfolio
risk envelope, responsive bilingual console, autonomous idle completion, and
zero consecutive failures with capital disabled. It exposed and fixed a
durable-role byte-accounting mismatch between compact application JSON and
PostgreSQL `jsonb::text`. The dashboard, service, data stores, and loopback
listeners were verified stopped afterward.

A later same-day bounded smoke verified the authenticated execution-quality
and carrier-specific cost-governance contracts against the live local service.
The bilingual console rendered the new TCA surface without horizontal overflow
at 1440, 768, and 390 CSS pixels, produced no browser-console errors, and kept
mobile control and inspector-tab heights at 44 pixels. Capital remained
disabled. The dashboard, Agent scheduler, service, PostgreSQL, Redis, and both
loopback listeners were verified stopped afterward.

The 2026-08-31 bounded production follow-up smoke froze two different exact
questions and two independent exploration seats. All four Runs succeeded, both
follow-up outputs preserved their assigned lineage, one failed source route was
isolated, and every Mind returned an honest `no_op`. No Candidate, Opportunity,
assessment, rank, expression, position, capital mutation, or order was created.
Research Operations v4 exposed 2 assigned / 2 executed / 2 no-op follow-ups.
The bilingual current-build console and its safe-stop control were verified at
desktop and 390 CSS pixels; the browser, dashboard, Agent tree, service,
PostgreSQL, Redis, and loopback listeners were stopped afterward.

## Scan interpretation

The full-tree Gitleaks scan uses the repository's default rules plus narrowly
reviewed, exact-path exceptions for public upstream Codex fixtures. It has no
broad vendor, extension, or generated-directory exemption. Public certificate
fixtures required by the pinned upstream HTTP tests remain tracked. Upstream
signing tests also contain fixed, non-production private-key literals; these
must never be used as operational credentials.

detect-secrets separately scans the exact distributable source inventory,
including tests and the attributed vendor snapshot. Tests contain intentionally
obvious values such as `fixture-secret` and `synthetic-private-key` to verify
redaction and privilege boundaries; neither scanner classifies them as real
credentials. Dependency lockfile hashes and attributed upstream fixtures are
not interpreted as owner credentials. A separate exact-identity pass found no
owner-local path, private owner email, unrelated legacy account, or unrelated
legacy repository identity. The three current-build PNGs expose no author,
creator, or description metadata and were visually reviewed before publication.

The current operator console exposes only credential configuration state,
source kind, editability, and a short one-way fingerprint. Raw provider values
are accepted through a bounded write-only request, cleared in the browser,
stored atomically outside the repository with owner-only permissions, and never
returned by the control API. Credential changes fail closed while any research
runtime process is active. Provider-health verification is bounded to fixed
read-only endpoints and persists only a schema-filtered status, HTTP code,
latency, and timestamp. Response bodies, headers, credential-bearing URLs, raw
transport errors, and tokens are discarded before the result reaches the
browser; a credential revision change invalidates the old result. Its dedicated
capital surface can authorize or revoke
only Tiger Paper execution and returns a strict projection of assets, positions,
recent orders, fingerprints, and authorization audit events. It never returns a
broker credential, account number, configuration path, or raw order identifier,
and it has no manual order-entry route.

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
an operator action. Tiger support is Paper-only, disabled by default, and
isolated behind an exact-account/configuration-bound executor. The authenticated
loopback API can change the durable authorization and request a sanitized
read-only broker snapshot; it cannot submit, alter, or cancel an order. Only the
bounded runtime executor can mirror an already-audited expression, and Agents
receive neither the broker credential nor an order tool.

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
