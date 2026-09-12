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

## Implementation boundaries

| Module         | Owns                                                                             |
| -------------- | -------------------------------------------------------------------------------- |
| `contracts.py` | Decimal quantities, explicit environment, account binding, typed snapshots       |
| `adapters/`    | Six provider-specific SDK/HTTP implementations and status normalization          |
| `transport.py` | Bounded TLS reads, no redirects, no automatic POST retries                       |
| `storage.py`   | Private atomic profiles, kernel owner locks, SQLite WAL/full-sync ledger         |
| `engine.py`    | Admission, persistent intent identity, ambiguous-outcome fencing, reconciliation |
| `__main__.py`  | Bounded write-only operator RPC, never order mutation                            |

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
