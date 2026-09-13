# Broker routing and operator workflow review — 2026-09-13

## Scope and result

The console now offers two modes: **Shadow** and **Broker API**. The provider and
Paper/Live environment belong to an explicitly configured account. Choosing a
provider never falls back to Tiger; selecting a route or saving a key never grants
trading authority. This is an experimental integration, not live-account
acceptance or institutional reliability certification.

No real account was authorized and no Paper or live order was sent in this review.
The managed console was launched; PostgreSQL and Redis supported integration
tests. The autonomous research service was not started against operator accounts.
Broker transactions in tests used injected account books and transports.

## Changes verified

- Removed the third legacy execution-mode page. Split connection setup, saved
  destination and account-bound authorization, with provider handoff between tabs.
- Replaced the hard-coded Tiger/Paper header state with selected-route metadata.
  Missing evidence displays unknown, not a false disabled/success state.
- Added exact-route/revision checks, disarm/settle/deselect rules for credential
  rotation, independent account ledgers and explicit revocation/exit confirmation.
- Connected persisted research expressions and independent audit artifacts to the
  private execution pipe. Broker/account/opportunity mismatches and stale audits
  are rejected. Browser order/quote/audit payloads remain unavailable.
- Added independent quote/position monitoring, without consuming the research
  cycle's quote allowance. No quote means no new dispatch, not skipped cancellation.
- Held the autonomous ownership fence across bounded external operations;
  shutdown drains them before ownership release. Orphaned workers cannot begin a
  new submission after parent-process loss. Ambiguous orders reconcile by identity.
- A real-PostgreSQL integration test exposed a negative-stop calculation when
  unused account risk capacity exceeded a small position's value. Exit distance
  now uses the position's audited stress allocation, capped by the account budget.
- Shortened default Python test tracebacks so failed fixture arguments do not
  print local database connection URLs. No fixture credentials belong in reports.

## Verification

| Check                                                                     | Result     |
| ------------------------------------------------------------------------- | ---------- |
| `./alta test`                                                             | 306 passed |
| Research suite, with managed PostgreSQL                                   | 444 passed |
| Isolated broker suite, locked optional SDK environment                    | 84 passed  |
| Legacy Paper-only suite                                                   | 38 passed  |
| Frontend contract and locale tests                                        | 44 passed  |
| Research Ruff lint and formatting                                         | Passed     |
| Broker Ruff lint and formatting                                           | Passed     |
| First-party formatting, Markdown lint, frontend lint and production build | Passed     |

The broker tests cover six exact provider routes, read/authorization separation,
wrong account/environment/revision rejection, staged-plan revocation, restart
without duplicate submissions, quote expiry and broker-confirmed owned closure.
They use injected adapters, not six real broker accounts. A separate integration
test runs the research expression/audit flow against actual PostgreSQL and checks
the resulting trusted broker handoff without sending it to a broker.

Browser checks used the built local console at its natural desktop viewport and
390 × 844 mobile viewport. Inspected both mode choices, all six provider forms,
the read-only authorization review, disabled unconfigured actions and all three
language selections. The viewport override was reset. No credential was entered
or exposed in screenshots. This is sampled UI verification, not every browser.

The managed dashboard, research service, PostgreSQL and Redis were then stopped.
No listener remained on the console, backend or managed database/cache ports.
Local account credentials and state were not deleted or published.

## Screenshot record

Only the broker workflow images were refreshed in this review. Other research
images retain their separately documented September 12 provenance. These captures
show the actual setup UI while the research runtime is stopped, not a claim that
a broker is connected or an order has executed. Broker API is a draft choice;
the displayed effective mode remains Shadow until a configured route is saved.

| File under `docs/assets/`        | Language            | SHA-256                                                            |
| -------------------------------- | ------------------- | ------------------------------------------------------------------ |
| `alta-broker-connections-en.jpg` | English             | `57889761c535248b3cf48e10034b8fdf62b051dc7835fb969321f79a0f33baa7` |
| `alta-broker-connections-zh.jpg` | Simplified Chinese  | `8f65ee1a9dc32d229334be84344635c3efec2c4e4d771059c29d09b8140469e8` |
| `alta-broker-connections-hk.jpg` | Traditional Chinese | `c02066f3133bedf6c6ae0faaf47929477273018a53fb241869d4b7ec27dee8fe` |

## Remaining limitations

Longbridge account/environment proof and Schwab trade permission, complete order
history and automatic OAuth renewal are incomplete; these authorizations stay
blocked. The four conditional paths still need real-account acceptance. Broker
execution supports one active long USD stock/ETF plan, whole shares and DAY
limits—not shorts, options or multi-plan portfolio management.

Exits are software-managed, not broker-native protective orders. Service downtime,
lost sessions and unavailable quotes can delay exits; partial or unresolved exits
can require manual review. A busy revocation must be retried after inspecting its
confirmed state. Stopping the service does not liquidate broker holdings.

No claim is made about live fills, profits, Alpha, extended 24×7 soak or outage-free
operation. See [the provider matrix and operating boundary](../broker-expansion.md).
