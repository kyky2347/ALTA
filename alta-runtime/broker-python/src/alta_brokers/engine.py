"""Durable execution admission. Provider adapters do not own risk or retries."""

import hashlib
from datetime import timedelta
from decimal import Decimal

from .contracts import BrokerError, Intent, Order, now, require
from .storage import Ledger, atomic_private, owner, read_private


class BrokerEngine:
    def __init__(self, profile, adapter, directory):
        self.profile, self.adapter, self.directory = profile, adapter, directory
        self.ledger = Ledger(directory)
        self.authority_path = directory / "authority.json"

    def _authority(self):
        if not self.authority_path.exists():
            return {"mode": "off"}
        value = read_private(self.authority_path)
        require(
            value.get("revision") == self.profile.revision
            and value.get("binding") == self.profile.binding,
            "broker_authority_invalidated",
        )
        require(
            value.get("mode") in ("off", "entries", "close_only"),
            "broker_authority_invalidated",
        )
        return value

    def _snapshot(self):
        snapshot = self.adapter.snapshot()
        require(
            snapshot.binding == self.profile.binding
            and snapshot.environment == self.profile.environment,
            "account_environment_mismatch",
        )
        age = (now() - snapshot.verified_at).total_seconds()
        require(0 <= age <= 30, "broker_snapshot_stale")
        require(
            snapshot.account_verified and snapshot.environment_verified,
            "broker_identity_unverified",
        )
        return snapshot

    def authorize(self, confirmation):
        phrase = f"ENABLE {self.profile.environment} {self.profile.binding[-8:]}"
        require(confirmation == phrase, "broker_confirmation_required")
        with owner(self.directory / "mutation.lock"):
            snapshot = self._snapshot()
            require(snapshot.trading_permitted, "broker_permission_unverified")
            require(
                not snapshot.positions
                and not snapshot.orders
                and not self.ledger.rows(),
                "broker_initial_account_must_be_empty",
            )
            atomic_private(
                self.authority_path,
                {
                    "mode": "entries",
                    "revision": self.profile.revision,
                    "binding": self.profile.binding,
                    "authorized_at": now().isoformat(),
                },
            )
        return self.state()

    def revoke(self):
        with owner(self.directory / "mutation.lock"):
            # No network is needed to stop opening risk. Keep reconciliation and
            # owned exits available until a fresh flat snapshot proves closure.
            mode = "close_only" if self.ledger.rows() else "off"
            atomic_private(
                self.authority_path,
                {
                    "mode": mode,
                    "revision": self.profile.revision,
                    "binding": self.profile.binding,
                    "revoked_at": now().isoformat(),
                },
            )
        return self.state()

    def state(self):
        rows = self.ledger.rows()
        return {
            "provider": self.profile.provider,
            "environment": self.profile.environment,
            "binding": self.profile.binding,
            "revision": self.profile.revision,
            "authority": self._authority()["mode"],
            "intent_count": len(rows),
            "pending_count": sum(
                r["state"] in ("prepared", "unknown", "working") for r in rows
            ),
            "orders": [
                {
                    "client_id": r["client_id"],
                    "state": r["state"],
                    "updated_at": r["updated_at"],
                    "error": r["error"],
                }
                for r in rows[-100:]
            ],
        }

    def verify(self):
        # An unverified identity remains observable, but cannot be authorized.
        snapshot = self.adapter.snapshot()
        public = snapshot.model_dump(mode="json")
        for order in public["orders"]:
            order["order_id"] = hashlib.sha256(order["order_id"].encode()).hexdigest()[
                :16
            ]
        atomic_private(self.directory / "snapshot.json", public)
        return {**self.state(), "snapshot": public}

    def _position_book(self):
        positions = {}
        for row in self.ledger.rows():
            if row["result"]:
                result = Order.model_validate_json(row["result"])
                positions[result.symbol] = positions.get(
                    result.symbol, Decimal(0)
                ) + result.filled * (1 if result.side == "BUY" else -1)
        return {symbol: quantity for symbol, quantity in positions.items() if quantity}

    def _match(self, intent, result):
        require(
            result.client_id == intent.client_id
            and result.symbol == intent.symbol
            and result.side == intent.side
            and result.quantity == intent.quantity
            and result.limit_price == intent.limit_price,
            "broker_order_mismatch",
        )

    def submit(self, intent, quote):
        with owner(self.directory / "mutation.lock"):
            current = self.ledger.get(intent.client_id)
            if current:
                # Verify exact reuse, but never send a second POST, even if the
                # provider's history lookup cannot yet find the first attempt.
                self.ledger.prepare(self.profile, intent)
                return self._reconcile(current)
            mode = self._authority()["mode"]
            require(
                mode == "entries" or (mode == "close_only" and intent.side == "SELL"),
                "broker_trading_not_authorized",
            )
            require(
                not any(
                    r["state"] in ("prepared", "unknown", "working")
                    for r in self.ledger.rows()
                ),
                "broker_reconciliation_required",
            )
            snapshot = self._snapshot()
            require(snapshot.trading_permitted, "broker_permission_unverified")
            require(not snapshot.orders, "broker_open_orders_require_reconciliation")
            actual = {p.symbol: p.quantity for p in snapshot.positions if p.quantity}
            require(actual == self._position_book(), "broker_position_drift")
            require(
                all(
                    p.currency == "USD" and p.quantity >= 0 for p in snapshot.positions
                ),
                "unsupported_portfolio_exposure",
            )
            age = (now() - quote.observed_at).total_seconds()
            require(
                quote.symbol == intent.symbol
                and quote.realtime
                and 0 <= age <= self.profile.max_quote_age_seconds,
                "dispatch_quote_stale_or_delayed",
            )
            require(
                (quote.ask - quote.bid) / quote.bid * 10000
                <= self.profile.max_spread_bps,
                "dispatch_spread_excessive",
            )
            require(now() < intent.expires_at, "intent_expired")
            notional = intent.quantity * intent.limit_price
            require(notional <= self.profile.max_order_notional, "order_notional_limit")
            if intent.side == "BUY":
                require(
                    intent.limit_price >= quote.ask
                    and intent.limit_price <= quote.ask * Decimal("1.005"),
                    "limit_price_outside_quote_band",
                )
                require(
                    notional * Decimal("1.01")
                    <= min(snapshot.cash, snapshot.buying_power),
                    "insufficient_cash_after_reserve",
                )
                require(
                    all(p.market_value is not None for p in snapshot.positions),
                    "position_valuation_unavailable",
                )
                gross = sum(
                    (abs(p.market_value) for p in snapshot.positions), Decimal(0)
                )
                require(
                    gross + notional <= self.profile.max_gross_notional,
                    "gross_exposure_limit",
                )
            else:
                require(
                    actual.get(intent.symbol, Decimal(0)) >= intent.quantity,
                    "sell_exceeds_owned_position",
                )
                require(
                    quote.bid * Decimal("0.995") <= intent.limit_price <= quote.bid,
                    "limit_price_outside_quote_band",
                )
            self.ledger.prepare(self.profile, intent)
            try:
                # SDK preflight/contract qualification can take seconds. Every
                # adapter must recheck this deadline immediately before mutation.
                dispatched = intent.model_copy(
                    update={
                        "expires_at": min(
                            intent.expires_at,
                            quote.observed_at
                            + timedelta(seconds=self.profile.max_quote_age_seconds),
                        )
                    }
                )
                result = self.adapter.submit(dispatched)
                self._match(intent, result)
                self.ledger.record(intent.client_id, result.state, result)
                return result
            except Exception:
                self.ledger.record(
                    intent.client_id, "unknown", error="submission_outcome_unconfirmed"
                )
                raise BrokerError("submission_outcome_unconfirmed") from None

    def _reconcile(self, row):
        intent = Intent.model_validate_json(row["request"])
        previous = Order.model_validate_json(row["result"]) if row["result"] else None
        if row["state"] in ("filled", "cancelled", "rejected"):
            return previous
        try:
            result = self.adapter.lookup(
                intent.client_id, previous.order_id if previous else None
            )
            require(result is not None, "order_not_yet_proven")
            self._match(intent, result)
            require(
                previous is None
                or (
                    result.order_id == previous.order_id
                    and result.filled >= previous.filled
                ),
                "broker_order_regressed",
            )
            self.ledger.record(intent.client_id, result.state, result)
            return result
        except Exception:
            self.ledger.record(
                intent.client_id, "unknown", error="reconciliation_unconfirmed"
            )
            raise BrokerError("reconciliation_unconfirmed") from None

    def reconcile(self):
        with owner(self.directory / "mutation.lock"):
            for row in self.ledger.rows():
                self._reconcile(row)
            snapshot = self._snapshot()
            require(
                {p.symbol: p.quantity for p in snapshot.positions if p.quantity}
                == self._position_book(),
                "broker_position_drift",
            )
            require(not snapshot.orders, "broker_orders_still_working")
            if self._authority()["mode"] == "close_only" and not snapshot.positions:
                atomic_private(
                    self.authority_path,
                    {
                        "mode": "off",
                        "revision": self.profile.revision,
                        "binding": self.profile.binding,
                    },
                )
        return self.state()

    def cancel(self, client_id):
        with owner(self.directory / "mutation.lock"):
            row = self.ledger.get(client_id)
            require(row is not None, "order_not_owned")
            result = self._reconcile(row)
            if result.state in ("working", "unknown"):
                self.ledger.record(client_id, "unknown", result, "cancellation_pending")
                try:
                    self.adapter.cancel(result.order_id)
                except Exception:
                    raise BrokerError("cancellation_unconfirmed") from None
                return self._reconcile(self.ledger.get(client_id))
            return result

    def close(self):
        try:
            self.adapter.close()
        finally:
            self.ledger.close()
