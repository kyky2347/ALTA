# Execution-mode and console review

Local review: September 12, 2026. No GitHub operation or live order was performed.
This is a bounded implementation review, not institutional certification or
evidence of investment returns.

## Delivered

- A refined existing Silment / ALTA wordmark lockup, with unchanged source artwork.
- A real execution-authority selector for internal Shadow versus existing Tiger
  Paper. Requested, effective, blocked and close-only states are distinct.
- Write-only Tiger credential input in all three interface languages. Strict
  field validation, RSA validation, atomic owner-only external storage, rollback,
  environment-override rejection and account-change checks protect replacement.
  No stored secret is returned to the browser; saving does not authorize orders.
- Same-origin session and CSRF checks, a shared host lease, runtime liveness
  checks, capital-operation locking and optimistic revisions protect mutations.
- Invalid requested authority blocks startup rather than silently falling back
  to Shadow. Read-only diagnosis and shutdown may still obtain a non-mutating
  dependency environment. They do not grant execution authority.
- The old duplicate enable switch has been removed. Explicit revocation remains
  available while research is running, including the existing drain-only path.
- An explicit 24-hour Agent view keeps running tasks visible, shows the number
  of older records outside the view, and offers the complete saved role snapshot.
  It does not filter recent failures by status or alter source records.
- Opportunity reviewers require an explicit assessment or discussion Run binding.
  Global role snapshots and accumulated Scout context no longer masquerade as
  reviews or input-token usage for a different opportunity.

## Verification

| Check                                               | Result                                                                                                                 |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| First-party Node suite                              | 214 passed                                                                                                             |
| Python research runtime                             | 389 passed, using isolated PostgreSQL                                                                                  |
| Isolated Tiger Paper package                        | 38 passed                                                                                                              |
| Dashboard contracts and projections                 | 27 passed                                                                                                              |
| Total                                               | 668 tests passed                                                                                                       |
| TypeScript, frontend lint, Markdown, Prettier, Ruff | Passed                                                                                                                 |
| Browser input and error handling                    | Three languages; invalid key rejected, draft retained on error and cleared on close                                    |
| Responsive credential dialog                        | Within 320, 390, 768 and 1600 px viewports in Chromium                                                                 |
| Security boundary                                   | Unauthenticated and CSRF-invalid writes rejected; active runtime and concurrent lease rejected                         |
| Storage boundary                                    | Owner-only file and directory, rollback, stale revision, account-swap, weak key and symlink-to-repository tests passed |

The final browser confirmation waited for the existing 100 ms dialog animation
and responsive layout before measuring. Earlier harness attempts hit a command
argument limit and an exit-animation race; reducing the passed locale payload
and waiting for dialog closure corrected the test harness. Separate browser
contexts are required when testing two operators on the same hostname because
browser cookies are not port-scoped. A cross-console 401 was not a broker failure.

Browser mutation checks used an isolated operator that rejected all broker
network calls, not the user's account configuration. These are not claims of
new broker connectivity or an end-to-end order acceptance test.

## Security scope

Offline Gitleaks 8.30.1 found no secret in the 6,245-file distributable snapshot
or all 24 locally available Git commits at the scan point. It used the existing
reviewed upstream-fixture allowlist and redacted output. Private ignored runtime
state, external credentials, local browser output and unrelated showcase files
were excluded. The repository and history were not contacted remotely.

Documentation screenshots use the running research service through a read-only
operator, with matching English, Simplified Chinese and Hong Kong Traditional
Chinese interfaces. Original Agent artifacts retain their original language.
The capture was taken during cycle `live-20260912-122000-056138`: one Scout was
running and three had completed. The opportunity detail was a saved September 11
research record, not a new execution approval or a broker trade.
The recent view is explicit; older records and genuine failure states remain
accessible. No credential or account page is used as a public screenshot.

## Deployment and remaining work

Only the existing managed dashboard was refreshed. The research host and
scheduler were left running with their existing configuration and capital
authority. Research-side projection changes load on the next research restart;
the frontend safely handles an older response without fabricating bindings.

The additional five brokerage adapters and Tiger live execution are **not
implemented**. The maintainer's authorization to develop live capability is
recorded in the engineering policy, not treated as evidence of a working live
executor. The [six-provider expansion boundary](../broker-expansion.md) specifies
the remaining account, authority, ledger, recovery and acceptance requirements.

Temporary operators, browser contexts, scan copies and isolated PostgreSQL
containers are removed after this review. Long-running reliability, physical
power loss, Safari/Firefox and six real broker account acceptances remain
unverified. No live trade, profit, or Alpha claim follows from these tests.
