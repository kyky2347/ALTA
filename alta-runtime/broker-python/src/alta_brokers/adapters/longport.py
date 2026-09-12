"""Longport/Longbridge SDK. Account/environment proof must not be guessed."""

from datetime import timedelta

from ..contracts import Order, Position, Snapshot, dispatch_guard, now, require
from ..contracts import acknowledge_order


class Longport:
    def __init__(self, profile, client=None):
        self.profile = profile
        if client is not None:
            self.client = client
            return
        from longport.openapi import Config, TradeContext

        config = Config.from_apikey(
            profile.secret("app_key"),
            profile.secret("app_secret"),
            profile.secret("access_token"),
            http_url="https://openapi.longportapp.com",
            quote_ws_url="wss://openapi-quote.longportapp.com",
            trade_ws_url="wss://openapi-trade.longportapp.com",
            enable_print_quote_packages=False,
        )
        self.client = TradeContext(config)

    @staticmethod
    def order(row):
        state = str(row.status).rsplit(".", 1)[-1]
        side = str(row.side).rsplit(".", 1)[-1].upper()
        return Order(
            order_id=row.order_id,
            client_id=row.remark or "",
            symbol=row.symbol.removesuffix(".US"),
            side=side,
            quantity=row.quantity,
            filled=row.executed_quantity,
            limit_price=row.price,
            average_price=row.executed_price if row.executed_quantity else None,
            state="filled"
            if state == "Filled"
            else "cancelled"
            if state in ("Canceled", "Expired", "PartialWithdrawal")
            else "rejected"
            if state == "Rejected"
            else "working"
            if state
            in (
                "NotReported",
                "ReplacedNotReported",
                "ProtectedNotReported",
                "VarietiesNotReported",
                "WaitToNew",
                "New",
                "WaitToReplace",
                "PendingReplace",
                "Replaced",
                "PartialFilled",
                "WaitToCancel",
                "PendingCancel",
            )
            else "unknown",
        )

    def snapshot(self):
        balances = self.client.account_balance(currency="USD")
        require(
            len(balances) == 1 and balances[0].currency == "USD",
            "usd_balance_unavailable",
        )
        a = balances[0]
        rows = self.client.stock_positions()
        orders = tuple(self.order(o) for o in self.client.today_orders())
        return Snapshot(
            binding=self.profile.binding,
            environment=self.profile.environment,
            verified_at=now(),
            currency="USD",
            equity=a.net_assets,
            cash=a.total_cash,
            buying_power=a.buy_power,
            positions=tuple(
                Position(
                    symbol=p.symbol.removesuffix(".US"),
                    quantity=p.quantity,
                    market_value=None,
                    currency=p.currency,
                )
                for c in rows.channels
                for p in c.positions
            ),
            orders=tuple(o for o in orders if o.state in ("working", "unknown")),
            # These trade SDK responses contain neither the account ID
            # nor Paper/live proof. A token name/member ID is not proof.
            account_verified=False,
            environment_verified=False,
            trading_permitted=False,
        )

    def submit(self, intent, *, acknowledge=None):
        dispatch_guard(intent)
        from longport.openapi import OrderType, OrderSide, TimeInForceType, OutsideRTH

        dispatch_guard(intent)
        result = self.client.submit_order(
            symbol=f"{intent.symbol}.US",
            order_type=OrderType.LO,
            side=OrderSide.Buy if intent.side == "BUY" else OrderSide.Sell,
            submitted_quantity=intent.quantity,
            time_in_force=TimeInForceType.Day,
            submitted_price=intent.limit_price,
            outside_rth=OutsideRTH.RTHOnly,
            remark=intent.client_id,
        )
        acknowledge_order(intent, result.order_id, acknowledge)
        return self.lookup(intent.client_id, result.order_id)

    def lookup(self, client_id, order_id):
        rows = (
            [self.client.order_detail(order_id)]
            if order_id
            else self.client.today_orders()
        )
        results = [self.order(row) for row in rows if row.remark == client_id]
        if not results and not order_id:
            end = now()
            history = self.client.history_orders(
                start_at=end - timedelta(days=89), end_at=end
            )
            require(len(history) < 1000, "order_history_incomplete")
            results = [self.order(row) for row in history if row.remark == client_id]
        require(len(results) <= 1, "duplicate_client_order")
        if order_id:
            require(len(results) == 1, "order_identity_mismatch")
            require(results[0].order_id == order_id, "order_identity_mismatch")
        return results[0] if results else None

    def cancel(self, order_id):
        self.client.cancel_order(order_id)

    def close(self):
        # TradeContext closes its bounded SDK connection when released.
        self.client = None
