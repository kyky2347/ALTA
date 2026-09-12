# Broker account review and receipt recovery

Date: 12 September 2026. Scope: local changes only; no repository publication.

## Result and boundary

This change improves the separate multi-broker connector package and its operator
interface. It does **not** complete autonomous execution for the five additional
brokers. No real-account acceptance record was available and no broker order was
sent during this work. Existing Tiger Paper execution remains separate.

The operator API still supports configuration, cached state and read-only broker
verification. The new authorization dialog reviews prerequisites; it cannot
enable trading. This follows the repository's requirement that account acceptance
and research-runner integration precede exposing broker mutations.

## Implemented

- Persist revision-bound account evidence outside source control. Failed checks
  invalidate previous success; evidence older than 30 seconds is historical.
  Malformed cache records fail closed without crashing the settings page.
- Show verified balances, holdings, orders and individual authorization
  prerequisites in English, Simplified Chinese and Traditional Chinese.
  Reading cached state does not open an SDK connection. Raw broker order IDs and
  third-party order remarks do not cross into this view.
- Persist the broker-issued order ID before subsequent parsing or order-detail
  reads. An uncertain outcome stays fenced; restart reconciliation uses that ID
  instead of blindly repeating a submission.
- Add bounded previous-session history lookup for Futu and Longport. A missing
  history match never permits resubmission. Futu reconnect cancellation unlocks
  the selected live connection; Paper does not use live unlock.
- Validate Schwab order-location responses before retaining an order identity.
  Keep SDK errors, credentials and raw account identifiers behind the private
  connector boundary.

## Verification

| Check                                                  | Result      |
| ------------------------------------------------------ | ----------- |
| First-party Node suite                                 | 304 passed  |
| Research runtime suite with local PostgreSQL and Redis | 423 passed  |
| Existing Tiger Paper package                           | 38 passed   |
| Isolated broker package, all optional dependencies     | 65 passed   |
| Frontend tests                                         | 42 passed   |
| Frontend production build and static checks            | Passed      |
| Research and broker Python lint / formatting           | Passed      |
| Changed-source secret scans                            | No findings |

The broker tests use controlled SDK/HTTP doubles, not funded accounts. They cover
lost detail responses after acknowledgment, restart without reposting, conflicting
order IDs, prior-session recovery, stale or invalidated evidence and invalid cache
records. They do not establish broker availability, real fills or profitability.

The local dashboard was inspected in all three languages, including the
authorization dialog at desktop and narrow viewport sizes. No synthetic broker
account was configured in the running operator console. Existing cached Tiger
Paper information is not a new account verification.

The test dashboard, research service and managed PostgreSQL/Redis were stopped
after verification. The dashboard and research ports were confirmed unbound;
the pre-test autonomous-start setting was restored without starting research.

## Still required for the requested complete trading workflow

1. Connect audited research expressions to this execution boundary with trusted
   fresh quotes and durable ownership of monitoring and exits. Adapter methods
   alone do not provide that lifecycle.
2. Complete provider-specific proof gaps: IBKR trade permission, Longport account
   and environment identity, and Schwab trade permission and complete open-order
   evidence. Missing evidence must not be inferred from a successful balance read.
3. Implement and verify the applicable credential/session lifecycle, including
   Schwab OAuth login and renewal. IBKR and Futu additionally require the user's
   authenticated TWS/IB Gateway and OpenD; an API-key field cannot replace them.
4. Independently validate account-bound authorization, initial-account ownership,
   credential rotation with exposure, concurrent Tiger ownership and recovery
   through partial fills, disconnects and restarts before releasing execution.

Official references and provider-specific requirements are maintained in
[Broker execution expansion](../broker-expansion.md). No interface test or
documentation review is presented as live-account acceptance.
