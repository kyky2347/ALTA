# Broker connectors and research radar review

September 12, 2026. A bounded engineering review, not a production certification,
profitability claim or real-account acceptance certificate.

## Delivered scope

- **One verified adaptation: the existing Tiger Paper executor. Five pre-adapted
  connectors: Alpaca, IBKR, Futu/moomoo, Longbridge/Longport and Schwab.** The new
  Tiger live connector is also pending acceptance. No live order was sent.
- The separate broker package contains provider-specific SDK/HTTP methods and
  an account-bound execution-engine library. The operator exposes private profile
  saving and read-only verification, not order submission or live authorization.
- Credentials travel over stdin to an isolated process, never command arguments.
  Provider/model/repository credentials are not inherited indiscriminately.
  SDK output is discarded, errors are constant codes, profiles are owner-only,
  and settings writes require session, origin, CSRF, revision and host-lease checks.
- The engine tests cover durable pre-submit identity, quote deadlines, ambiguous
  submissions, restart reconciliation, partial fills, position drift, cash/notional
  limits and close-only revocation. Unknown outcomes are not retry permission.
- All six order entry methods reject expired intents before SDK work. Wiring
  tests preserve a 250-share request; they do not replace Agent sizing with one
  share. Futu uses an explicit regular session and rejects zero account IDs that
  OpenD would otherwise treat as index-based selection. An IBKR connection alone
  is not evidence of trading permission.
- The sidebar is **API Trading / API 交易**, with explicit underlying Paper
  authority. The language menu is **English / 简体中文 / 繁體中文**.
- Research radar separates recent Scout work, candidate leads and saved
  opportunities. It searches real titles/IDs, offers seven-day and bounded full
  snapshot scopes, and opens environment-bound candidate evidence projections.
  Current failures are not removed by a success-only filter. More records are
  never presented as more approved trades.
- Scout token totals are labelled recorded cumulative usage, not a current
  context-window size. This follows the additive database definition and does
  not claim billing accuracy.

## Verification

| Gate                                                  | Result                             |
| ----------------------------------------------------- | ---------------------------------- |
| First-party Node                                      | 225 passed                         |
| Research Python, isolated PostgreSQL                  | 391 passed                         |
| Existing Tiger Paper package                          | 38 passed                          |
| Separate broker package, locked SDK extras            | 44 passed                          |
| Dashboard                                             | 33 passed                          |
| TypeScript, frontend lint, Markdown, format and build | Passed                             |
| Broker dialog, 6 providers × 3 languages × 4 widths   | 72 combinations passed in Chromium |
| Research radar, 3 languages × 4 widths                | 12 combinations passed in Chromium |

Browser widths were 320, 390, 768 and 1600 px. Checks covered overflow, exact
language labels, recent/full scope, candidate inspection, stopped-runtime save
gating and unconfigured verification controls. Futu Paper does not request a
live trading password. Browser brokerage mutations were blocked during captures.

The research API and PostgreSQL tests include wrong-environment denial for a
candidate, evidence content hashes, SSE reconnect and supervisor crash recovery.
An initial candidate query used a nonexistent direct timestamp column; the
full regression caught it. It was corrected to read the frozen snapshot field,
then the targeted test and all 389 research tests passed.

Another production-build check exposed missing lazy chunks in an already-open
tab after replacing `dist`. Builds now retain content-hashed assets needed by
old tabs, and build freshness includes Vite/TypeScript configuration. Operators
can clean old build assets while the console is stopped and old tabs are closed.

## Observed research and brokerage state

The live local research cycle started at 13:31 UTC on September 12. Four Scouts
completed; the runtime reported `MVP_IDLE`, zero consecutive cycle failures and
a scheduled next wake. It did not create a new approved trade. The seven-day
radar contained one opportunity and its candidate lead, not two independent
investment theses. The bounded full snapshot contained older records; captures
did not re-date those records or present them as newly discovered opportunities.

The subsequent [retrieval review](research-retrieval-review.md) explains the low
candidate yield, records the local repairs, and documents an additional genuine
forming Opportunity from the 14:12 UTC cycle. That record is not a trade approval.

A previously interrupted cycle was quarantined on restart because its frozen
configuration no longer matched. That durable recovery record remains in the
audit history; the scheduler moved to a fresh cycle rather than resume with
different inputs. This is distinct from claiming uninterrupted operation.

The existing Tiger Paper refresh at 13:19 UTC returned zero positions and zero
open orders. Two historical orders in the response were not counted as open.
Only sanitized counts and timestamps were used in this report. That read probe
does not validate the new live Tiger adapter or any other provider account.

## Publication and reproducibility

The distributable inventory excludes private runtime state, credential folders,
licensed provider responses, local `output/`, unrelated `showcase/` HTML and
website configuration. Unused previous README images were moved to ignored
local output storage; all three READMEs reference the current language-matched
set. Public images use the research UI, not credential/account screens.

Offline, redacted Gitleaks 8.30.1 scans checked the distributable working tree
and all locally available Git commits using the reviewed existing fixture
allowlist. Known local model/resource secret values were also compared against
the distributable files in memory, without printing them. No matches were found.
These checks are bounded evidence, not a guarantee about arbitrary external
files or unobserved remote references.

## Remaining work before additional broker execution

1. Connect trusted audit output, independently refreshed quotes, durable position
   monitoring and exit ownership to the new execution engine. The library alone
   is not the autonomous lifecycle.
2. Complete provider-specific identity/permission evidence, long-lived OAuth
   renewal, gateway session recovery and credential rotation with existing risk.
   Longport identity/environment proof, IBKR permission proof and Schwab
   permission/complete-order history remain blocking conditions.
3. Obtain operator-owned account credentials, market permissions and any local
   gateways for each provider. Complete recorded account-specific acceptance;
   never infer that one broker's Paper test proves another broker's live trading.
4. Extend beyond the current common contract: whole-share USD stocks, limit DAY
   orders during regular hours. Options, shorting, leverage, multiple currencies
   and arbitrary account structures are not covered by these new connectors.
5. Run multi-day soak, physical power-loss and native Safari/Firefox checks.
   The current evidence is shorter and narrower than institutional availability.

Primary provider references and exact implementation status are maintained in
the [broker matrix](../broker-expansion.md). SDK licenses and the community
IBKR wrapper attribution are recorded in [ATTRIBUTION](../../ATTRIBUTION.md).
