# Broker lifecycle preparation — 12 September 2026

**Status: partial implementation, not a live-trading release.**

The maintainer approved replacing the blanket read-only development restriction
with a default-off, account-verified, explicitly authorized execution policy.
This changes what contributors may implement; it does not grant an account
trading authority or prove that a provider has passed acceptance.

## Changes

- Added a cohesive lifecycle kernel with immutable account/revision binding,
  independent audit and realtime quote ports, durable entry/exit identities,
  target/stop/time exits and explicit recovery states.
- Stage and dispatch both require independent audit verification. Caller-provided
  approval flags and synthetic live quotes are not an integration mechanism.
- A restart recovers an accepted order instead of submitting it again. A filled
  exit is not reported as closed until broker positions and the local ledger agree.
- Incomplete or expired exit attempts require review. Quote outages do not permit
  stale-price execution. These safeguards do not guarantee timely liquidation
  during an outage, an illiquid market or a broker interruption.
- Flat, settled execution history no longer prevents account reauthorization.
  Profitable exits above the entry notional cap remain possible, but are bounded
  by actual owned quantity and fresh-price checks.

The initial kernel admits one active plan per account. This is not a claim of
multi-position portfolio allocation, broker-native protective orders, options,
margin or uninterrupted execution. Stops are evaluated by the caller scheduling
the kernel; no hosted broker stop is implied.

## Validation

The broker package has 74 passing offline tests. New cases cover entry, monitoring,
restart, target exit, stop exit with a lost response, revocation, stale quotes,
audit revocation, account/revision mismatch, competing plans, profitable exits
above the entry cap and contradictory broker position evidence.

No real brokerage account was connected or authorized, and no Paper or live order
was sent in this work. A fixture labeled `LIVE` tests routing contracts; it is not
a live account. The production operator API remains configure/verify/state only.

## Remaining blockers to complete live support

1. Wire trusted production audit and quote ports into the research runner and
   supervised position-monitor worker. Neither is replaced by the kernel tests.
2. Finish provider authentication and account/permission proof, including Schwab
   OAuth renewal and Longport identity/environment evidence. The current consumed
   Longport asset responses do not prove those properties.
3. Add the corresponding working account-bound authorization controls only when
   they control that real execution lifecycle, including safe revocation and
   cross-boundary Tiger ownership.
4. Validate each intended broker/account configuration with authorized acceptance
   evidence. No result here establishes six-provider operational readiness.

Provider documentation and capability distinctions remain in
[Broker execution expansion](../broker-expansion.md). The README deliberately
retains the pre-adapted status of the five additional connectors.
