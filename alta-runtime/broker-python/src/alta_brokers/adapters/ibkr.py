"""IB Gateway/TWS via ib_async. Nonzero, fixed client ID; never bind manual orders."""

import re
from decimal import Decimal

from ..contracts import Order, Position, Snapshot, dispatch_guard, now, require


class InteractiveBrokers:
    def __init__(self, profile, client=None):
        self.profile = profile
        self.account = profile.account.get_secret_value()
        require(
            bool(
                re.fullmatch(
                    r"DU\d+" if profile.environment == "PAPER" else r"U\d+",
                    self.account,
                )
            ),
            "environment_mismatch",
        )
        self.client_id = int(profile.secret("client_id"))
        require(1 <= self.client_id <= 2147483647, "client_id_invalid")
        if client is not None:
            self.client = client
            return
        from ib_async import IB

        self.client = IB()
        self.client.RequestTimeout = 15
        port = int(profile.secret("port"))
        require(1024 <= port <= 65535, "gateway_port_invalid")
        try:
            self.client.connect(
                "127.0.0.1",
                port,
                clientId=self.client_id,
                timeout=10,
                readonly=False,
                account=self.account,
                raiseSyncErrors=True,
            )
        except Exception:
            self.client.disconnect()
            raise

    def order(self, trade):
        o, status = trade.order, trade.orderStatus
        require(o.account == self.account, "account_mismatch")
        # PermId persists across gateway reconnects; local orderId does not.
        require(int(o.permId) > 0, "order_identity_pending")
        name = status.status
        return Order(
            order_id=str(o.permId),
            client_id=o.orderRef,
            symbol=trade.contract.symbol,
            side=o.action,
            quantity=o.totalQuantity,
            filled=status.filled,
            limit_price=o.lmtPrice if o.orderType == "LMT" else None,
            average_price=status.avgFillPrice if status.filled else None,
            state="filled"
            if name == "Filled"
            else "cancelled"
            if name in ("Cancelled", "ApiCancelled")
            else "rejected"
            if name == "Inactive"
            else "working"
            if name
            in (
                "PendingSubmit",
                "ApiPending",
                "PreSubmitted",
                "Submitted",
                "PendingCancel",
            )
            else "unknown",
        )

    def snapshot(self):
        require(self.account in self.client.managedAccounts(), "account_mismatch")
        # This is an exact requested account, not managedAccounts()[0].
        self.client.reqAccountSummary()
        rows = self.client.accountSummary(self.account)
        values = {
            r.tag: r.value
            for r in rows
            if r.account == self.account and r.currency == "USD"
        }
        trades = self.client.reqAllOpenOrders()
        positions = self.client.portfolio(self.account)
        return Snapshot(
            binding=self.profile.binding,
            environment=self.profile.environment,
            verified_at=now(),
            currency="USD",
            equity=values["NetLiquidation"],
            cash=values["TotalCashValue"],
            buying_power=values["BuyingPower"],
            positions=tuple(
                Position(
                    symbol=p.contract.symbol,
                    quantity=p.position,
                    market_value=p.marketValue,
                    currency=p.contract.currency,
                )
                for p in positions
            ),
            orders=tuple(
                self.order(t) for t in trades if t.order.account == self.account
            ),
            account_verified=True,
            environment_verified=True,
            # A connected read-only TWS session is not trade authorization.
            # Instrument-level what-if belongs to dispatch, not this read probe.
            trading_permitted=False,
        )

    def submit(self, intent):
        dispatch_guard(intent)
        from ib_async import Stock, LimitOrder

        contracts = self.client.qualifyContracts(Stock(intent.symbol, "SMART", "USD"))
        require(
            len(contracts) == 1 and contracts[0].symbol == intent.symbol,
            "instrument_ambiguous",
        )
        order = LimitOrder(
            intent.side,
            int(intent.quantity),
            float(intent.limit_price),
            account=self.account,
            orderRef=intent.client_id,
            tif="DAY",
            outsideRth=False,
        )
        preview = self.client.whatIfOrder(contracts[0], order)
        require(
            not preview.warningText and Decimal(preview.initMarginChange).is_finite(),
            "broker_preview_not_passed",
        )
        dispatch_guard(intent)
        trade = self.client.placeOrder(contracts[0], order)
        for _ in range(30):
            if trade.order.permId > 0:
                return self.order(trade)
            self.client.sleep(0.1)
        require(False, "submission_outcome_unknown")

    def lookup(self, client_id, order_id):
        trades = [
            *self.client.reqAllOpenOrders(),
            *self.client.reqCompletedOrders(apiOnly=False),
        ]
        matches = {
            str(t.order.permId): t
            for t in trades
            if t.order.account == self.account and t.order.orderRef == client_id
        }
        require(len(matches) <= 1, "duplicate_client_order")
        if not matches:
            return None
        result = self.order(next(iter(matches.values())))
        require(
            order_id is None or result.order_id == order_id, "order_identity_mismatch"
        )
        return result

    def cancel(self, order_id):
        matches = [
            t
            for t in self.client.reqOpenOrders()
            if t.order.account == self.account
            and str(t.order.permId) == order_id
            and t.order.clientId == self.client_id
        ]
        require(len(matches) == 1, "order_cancel_ownership_unconfirmed")
        self.client.cancelOrder(matches[0].order)

    def close(self):
        self.client.disconnect()
