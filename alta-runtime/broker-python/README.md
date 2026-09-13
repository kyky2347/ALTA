# Isolated broker execution

Six provider adapters, private account-bound credentials and a durable execution
kernel, separate from research and the older Tiger Paper package. The dashboard
offers Shadow or Broker API; the selected account explicitly specifies Paper or
Live. No automatic provider or environment fallback exists.

**Experimental, default off.** Tiger, Alpaca, IBKR and Futu have conditional
execution paths. Longbridge identity proof and Schwab permission/history proof
and OAuth renewal remain incomplete; their authorization stays blocked. No new
live account has an acceptance record. Development tests send no live orders.

```shell
uv sync --frozen --all-extras --project alta-runtime/broker-python
uv run --frozen --all-extras --project alta-runtime/broker-python \
  pytest -q alta-runtime/broker-python/tests
```

## Two separate process interfaces

| Interface                        | Accepted operations                                                                            | Caller                                                           |
| -------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Operator RPC (`__main__.py`)     | catalog, save, state, verify, route, select, authorize, revoke, reconcile                      | Authenticated local control service                              |
| Research RPC (`research_rpc.py`) | stage an independently audited plan, inspect active plans, monitor a plan with a current quote | Trusted research backend; not exposed as browser order endpoints |

Saving credentials never enables orders. Configuration changes require stopped
research, no authority, a deselected route and settled exposure. Write-only
profiles and prior ledgers remain outside the repository. SDK output is discarded;
the console receives validated summaries and constant error codes.

## Responsibilities

| Module                       | Owns                                                                        |
| ---------------------------- | --------------------------------------------------------------------------- |
| `contracts.py`, `catalog.py` | Explicit environments, Decimal amounts and provider-specific requirements   |
| `adapters/`, `transport.py`  | SDK/HTTP normalization, bounded calls and no blind POST retry               |
| `storage.py`, `routing.py`   | Private atomic files, exact selected destination, account locks and ledger  |
| `verification.py`            | Revision-bound account evidence and current authorization prerequisites     |
| `engine.py`                  | Authorization, admission, durable intents and reconciliation                |
| `lifecycle.py`               | Persistent single-plan entry, monitoring, exit and broker-confirmed closure |
| `research_rpc.py`            | Immutable audit receipts and trusted quote/plan input                       |

The application handoff in `alta-runtime/python/` verifies PostgreSQL artifacts
and binds the exact opportunity and account revision before staging. Independent
monitoring continues between LLM turns. The browser cannot supply its own quote,
audit flag or raw order. Account checks older than 30 seconds are historical;
failed verification invalidates the previous success.

Initial execution supports one active, long USD stock/ETF plan, whole shares and
DAY limits. Stop, target, time and revocation exits are software-managed: keep the
backend running. Native protective orders, options, shorts, multi-plan portfolios
and automatic Schwab OAuth refresh are not implemented. An uncertain submission
or incomplete exit can require manual review. A passing contract test is not
real-account trading acceptance or production certification.

See [setup, provider proof and operational limits](../../docs/broker-expansion.md)
and [attribution](../../ATTRIBUTION.md).
