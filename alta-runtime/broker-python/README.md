# Isolated broker connectors

Six concrete provider adapters, typed contracts, private credential profiles and
a durable execution-engine library. This package is separate from the research
runtime and from the existing Tiger Paper executor.

**Current operator surface: configure and verify only.** The engine is not yet
wired into autonomous research. No live order was used for development or testing.
Account acceptance is not implied by a passing connector test.

```shell
uv sync --frozen --all-extras --project alta-runtime/broker-python
uv run --frozen --all-extras --project alta-runtime/broker-python \
  pytest -q alta-runtime/broker-python/tests
```

Then open the dashboard's **API Trading → Broker connections**. Profiles are
write-only, outside the repository, with owner-only permissions. Saving is
allowed only while research is stopped. Verification performs actual broker
reads when the selected profile and required local gateway are present.

The operator subprocess accepts `catalog`, `save`, `state` and `verify` over
stdin. It has no order-placement or authorization action. SDK output is discarded;
only schema-validated account summaries and constant error codes are returned.

Account checks persist a revision-bound, redacted response locally. The dashboard
can inspect cash, equity, buying power, holdings, open orders and authorization
prerequisites without opening another SDK session. Evidence older than 30 seconds
is historical, not current permission. A failed verification invalidates the
previous success; replacing credentials invalidates evidence from the old
revision. The authorization review is **not an enable switch**: runner integration
and account acceptance remain unreleased gates.

Each adapter reports a broker-issued order identity to the durable ledger before
parsing or fetching further order details. If that later step fails, restart
recovery uses the recorded identity; it never blindly repeats the submit request.
Futu and Longport consult bounded prior-session history when a current-session
lookup has no match. History absence still does not authorize a second order.

## Implementation boundaries

`lifecycle.py` adds a restartable, single-active-plan execution kernel. A trusted
caller must implement both the independent-audit port and the realtime-quote port;
there is no default approval, synthetic quote or browser-supplied approval flag.
Plans, entry identities and exit terms are persisted before mutation. A target,
stop, time limit or close-only authority can trigger an owned exit. Uncertain
submissions reconcile by identity; an incomplete or expired exit requires review.
Closure requires matching broker positions, not just a successful submit response.
This kernel is not yet a launched worker or a production research integration.

Settled history no longer prevents reauthorization after the account is flat.
The entry notional cap cannot strand a profitable exit above that cap: sell orders
remain restricted to the exact owned quantity, a fresh quote and the price band.

| Module            | Owns                                                                             |
| ----------------- | -------------------------------------------------------------------------------- |
| `contracts.py`    | Decimal quantities, explicit environment, account binding, typed snapshots       |
| `adapters/`       | Six provider-specific SDK/HTTP implementations and status normalization          |
| `transport.py`    | Bounded TLS reads, no redirects, no automatic POST retries                       |
| `storage.py`      | Private atomic profiles, kernel owner locks, SQLite WAL/full-sync ledger         |
| `engine.py`       | Admission, persistent intent identity, ambiguous-outcome fencing, reconciliation |
| `verification.py` | Revision-bound evidence, freshness and authorization prerequisite reporting      |
| `__main__.py`     | Bounded write-only operator RPC, never order mutation                            |

The execution library currently supports whole-share USD stock limit orders,
DAY validity and regular hours. It does not claim options, leverage, shorting,
all account structures or exchange-wide compatibility. Its quote input must
come from an independently verified realtime source; it is not an LLM assertion.

Pending integration includes a trusted audit-to-order handoff, fresh quote
acquisition, durable position-monitor ownership, selected-account lifecycle,
credential rotation with existing exposure, OAuth renewal, cross-application
Tiger ownership and six real-account acceptance records. Longport proof and
Schwab permission/history gaps keep their common-engine authorization blocked.
Do not bypass these gates to demonstrate a trade.

See [the provider matrix](../../docs/broker-expansion.md) and
[attribution](../../ATTRIBUTION.md).
