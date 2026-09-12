"""Alpaca Trading API v2. Separate fixed endpoints, never an inferred environment."""

from urllib.parse import quote

from ..contracts import Intent, Order, Position, Snapshot, dispatch_guard, now, require
from ..transport import Transport
from ..contracts import acknowledge_order


class Alpaca:
    def __init__(self, profile, transport=None):
        self.profile = profile
        self.http = transport or Transport(
            "https://paper-api.alpaca.markets"
            if profile.environment == "PAPER"
            else "https://api.alpaca.markets",
            {
                "APCA-API-KEY-ID": profile.secret("api_key"),
                "APCA-API-SECRET-KEY": profile.secret("api_secret"),
            },
        )

    @staticmethod
    def order(row):
        state = row["status"]
        return Order(
            order_id=str(row["id"]),
            client_id=row["client_order_id"],
            symbol=row["symbol"],
            side=row["side"].upper(),
            quantity=row["qty"],
            filled=row["filled_qty"],
            limit_price=row.get("limit_price"),
            average_price=row.get("filled_avg_price"),
            state=(
                "filled"
                if state == "filled"
                else "cancelled"
                if state in ("canceled", "expired", "replaced")
                else "rejected"
                if state == "rejected"
                else "working"
                if state
                in (
                    "new",
                    "accepted",
                    "pending_new",
                    "partially_filled",
                    "pending_cancel",
                    "pending_replace",
                    "accepted_for_bidding",
                )
                else "unknown"
            ),
        )

    def snapshot(self):
        account, _ = self.http.request("GET", "/v2/account")
        require(account is not None, "account_unavailable")
        require(
            str(account["id"]) == self.profile.account.get_secret_value(),
            "account_mismatch",
        )
        positions, _ = self.http.request("GET", "/v2/positions")
        orders, _ = self.http.request(
            "GET", "/v2/orders", params={"status": "open", "limit": 500}
        )
        require(
            isinstance(positions, list) and isinstance(orders, list),
            "snapshot_incomplete",
        )
        require(len(orders) < 500, "order_pagination_required")
        return Snapshot(
            binding=self.profile.binding,
            environment=self.profile.environment,
            verified_at=now(),
            currency=account["currency"],
            equity=account["equity"],
            cash=account["cash"],
            buying_power=account["buying_power"],
            account_verified=True,
            environment_verified=True,
            trading_permitted=(
                account["status"] == "ACTIVE"
                and account.get("trading_blocked") is False
                and account.get("account_blocked") is False
            ),
            positions=tuple(
                Position(
                    symbol=p["symbol"],
                    quantity=p["qty"],
                    market_value=p["market_value"],
                    currency="USD",
                )
                for p in positions
            ),
            orders=tuple(self.order(o) for o in orders),
        )

    def submit(self, intent: Intent, *, acknowledge=None):
        dispatch_guard(intent)
        asset, _ = self.http.request(
            "GET", f"/v2/assets/{quote(intent.symbol, safe='')}"
        )
        require(
            asset is not None
            and asset.get("tradable") is True
            and asset.get("class") == "us_equity",
            "instrument_not_tradable",
        )
        dispatch_guard(intent)
        row, _ = self.http.request(
            "POST",
            "/v2/orders",
            json={
                "symbol": intent.symbol,
                "qty": str(intent.quantity),
                "side": intent.side.lower(),
                "type": "limit",
                "time_in_force": "day",
                "limit_price": str(intent.limit_price),
                "extended_hours": False,
                "client_order_id": intent.client_id,
            },
        )
        acknowledge_order(
            intent, row.get("id") if isinstance(row, dict) else None, acknowledge
        )
        return self.order(row)

    def lookup(self, client_id, order_id):
        row, _ = self.http.request(
            "GET",
            f"/v2/orders/{quote(order_id, safe='')}"
            if order_id
            else "/v2/orders:by_client_order_id",
            params={} if order_id else {"client_order_id": client_id},
        )
        if row is None:
            return None
        result = self.order(row)
        require(result.client_id == client_id, "order_identity_mismatch")
        return result

    def cancel(self, order_id):
        self.http.request("DELETE", f"/v2/orders/{quote(order_id, safe='')}")

    def close(self):
        self.http.close()
