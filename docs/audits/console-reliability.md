# Console and runtime reliability review

Local verification: September 9, 2026. This is a bounded engineering review,
not an availability certification, independent security audit, or evidence
of investment performance. No repository publication or brokerage operation
was performed during this review.

## What changed

| Failure mode                                                                                | Implemented correction                                                                                                                                     |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cached research could retain a current freshness label for up to five minutes after expiry. | Recompute clock-dependent freshness on each API read, without reloading the database projection or mutating its shared cache.                              |
| Database connection failures could terminate an HTTP request without a structured response. | Return a sanitized, retryable 503 for connection failures. Liveness remains independent of storage availability.                                           |
| A malformed or far-future heartbeat could crash readiness or pass it incorrectly.           | Reject invalid timestamps, timezone-free values, and future timestamps beyond the small clock-skew allowance.                                              |
| Browser disconnects and oversized responses could retain upstream work.                     | Cancel reads on response-socket closure, enforce body size and timeout bounds, and release stream readers.                                                 |
| Malformed successful responses could replace valid frontend data.                           | Validate response envelopes and the critical read-model structures before publishing them to React state. Preserve the previous snapshot on failure.       |
| A slow poll could overwrite an acknowledged credential or capital-control result.           | Fence read completions with revisions; acknowledged writes invalidate older reads and their errors.                                                        |
| Secure-session retry logic was duplicated across controls.                                  | Use one mutation path. Only a definitive pre-execution CSRF rejection permits one retry; timeouts and uncertain outcomes are never automatically replayed. |
| Small mobile inputs could trigger automatic focus zoom.                                     | Use a 16px mobile input floor while preserving the existing responsive layout.                                                                             |

Brokerage authorization, position sizing, research strategy, and execution
rules were not relaxed. Upstream transport handling and snapshot fencing are
separate modules rather than additional responsibilities in the main console.

Signal labels are not quote-service guarantees: the current policy calls an
anchor up to 15 minutes old `live` and up to four calendar days old `current`,
allowing the last completed session across long weekends. Older anchors expire;
missing and future anchors cannot qualify. Freshness alone does not authorize
an expression or a broker action. Execution still has its own quote/risk checks.

## Verification

| Check                                                                                                 | Observed result                                                                                                                         |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Node first-party tests                                                                                | 201 passed                                                                                                                              |
| Python runtime tests, using managed PostgreSQL and Redis                                              | 386 passed                                                                                                                              |
| Isolated Paper package tests                                                                          | 38 passed                                                                                                                               |
| Dashboard unit tests                                                                                  | 19 passed                                                                                                                               |
| TypeScript, dashboard lint, production build, formatting and Markdown lint                            | Passed                                                                                                                                  |
| Seven authenticated read routes through PostgreSQL, Python HTTP, Node gateway and frontend validation | Passed in a read-only replay deployment                                                                                                 |
| Seven views, English and Chinese, six widths from 320px to 1920px                                     | 84 combinations passed in Chromium; no page-width overflow or script errors observed                                                    |
| Browser fault injection                                                                               | Malformed response retained the last good snapshot; delayed reads were rejected; CSRF renewed once; uncertain mutation was not replayed |

The real-stack smoke used a separately bound local service with autonomous
research and Tiger disabled. Brokerage and credential mutation scenarios used
intercepted synthetic browser responses or test doubles, not provider calls.
The synthetic UI preview is labeled; its opportunities, balances and results
are not performance evidence.

The managed dashboard was restarted to load the updated gateway. The temporary
replay service and gateway were stopped, and the managed test environment was
taken down afterward. The existing dashboard remains available; the autonomous
research service and scheduler remain stopped.

## Sensitive-data review

An offline detect-secrets 1.5.0 scan covered first-party Node, Python and
dashboard source/tests plus both READMEs. Reported candidates were reviewed as
test sentinels, descriptive text, code keywords and synthetic preview
fingerprints. No real credential was identified in that inspected scope.
The scan did not contact providers to validate candidate strings and did not
inspect the external credential store or the complete Git history. This is
not a replacement for the full pre-publication security procedure.

## Remaining verification work

- Run a multi-day soak with real provider latency, quota exhaustion and outages.
- Verify on physical Safari/iOS and Firefox installations; Chromium viewport
  checks do not establish universal browser compatibility.
- Exercise real host power-loss and reboot recovery. Automated stale-owner,
  interrupted-operation and restart tests cover specific modeled failures,
  not every filesystem or hardware failure.
- Load-test very large historical ledgers and multi-tab usage. Explicitly
  expanded history still warrants a bounded-window or pagination redesign
  before extremely long interactive sessions.
- Validate richer optional response payloads and lazy-loaded view recovery.
  Critical structure validation is not an exhaustive schema for every nested
  research artifact.
- Revalidate Tiger Paper connectivity separately before permitting brokerage
  execution. This review did not establish current broker availability.

The passed checks increase confidence in these specific contracts. They do
not prove zero bugs, uninterrupted operation, profitable trading, or alpha.
