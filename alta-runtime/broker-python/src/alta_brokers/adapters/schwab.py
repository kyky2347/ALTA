"""Schwab Trader API. No Paper endpoint and no safe client-ID POST replay."""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote, urlsplit

from ..contracts import (
    BrokerError,
    Intent,
    Order,
    Position,
    Snapshot,
    dispatch_guard,
    now,
    require,
)
from ..transport import Transport


class Schwab:
    def __init__(self, profile, transport=None):
        require(profile.environment == "LIVE", "schwab_paper_unavailable")
        self.profile = profile
        self.account_hash = profile.secret("account_hash")
        require(self.account_hash.isalnum(), "account_hash_invalid")
        # OAuth refresh is an operator credential transaction, never a silent
        # mutation of the revision currently authorizing an order.
        self.http = transport or Transport(
            "https://api.schwabapi.com",
            {"Authorization": f"Bearer {profile.secret('access_token')}"},
        )
        self.path = f"/trader/v1/accounts/{quote(self.account_hash, safe='')}"

    @staticmethod
    def order(row, client_id=""):
        legs = row["orderLegCollection"]
        require(
            len(legs) == 1 and legs[0]["instruction"] in ("BUY", "SELL"),
            "unsupported_broker_order",
        )
        leg = legs[0]
        fills = [
            execution
            for activity in row.get("orderActivityCollection", [])
            if activity.get("activityType") == "EXECUTION"
            for execution in activity.get("executionLegs", [])
        ]
        filled = Decimal(str(row["filledQuantity"]))
        filled_evidence = sum((Decimal(str(f["quantity"])) for f in fills), Decimal(0))
        average = (
            sum(
                (Decimal(str(f["quantity"])) * Decimal(str(f["price"])) for f in fills),
                Decimal(0),
            )
            / filled
            if filled > 0 and filled_evidence == filled
            else None
        )
        state = row["status"]
        return Order(
            order_id=str(row["orderId"]),
            client_id=client_id,
            symbol=leg["instrument"]["symbol"],
            side=leg["instruction"],
            quantity=row["quantity"],
            filled=filled,
            limit_price=row.get("price"),
            average_price=average,
            state="filled"
            if state == "FILLED"
            else "cancelled"
            if state in ("CANCELED", "EXPIRED", "REPLACED")
            else "rejected"
            if state == "REJECTED"
            else "working"
            if state
            in (
                "QUEUED",
                "WORKING",
                "PENDING_CANCEL",
                "PENDING_ACTIVATION",
                "ACCEPTED",
                "AWAITING_PARENT_ORDER",
            )
            else "unknown",
        )

    def snapshot(self):
        payload, _ = self.http.request("GET", self.path, params={"fields": "positions"})
        require(payload is not None, "account_unavailable")
        account = payload["securitiesAccount"]
        require(
            str(account["accountNumber"]) == self.profile.account.get_secret_value(),
            "account_mismatch",
        )
        balance = account["currentBalances"]
        rows, _ = self.http.request(
            "GET",
            f"{self.path}/orders",
            params={
                "fromEnteredTime": (now() - timedelta(days=60)).isoformat(),
                "toEnteredTime": now().isoformat(),
                "maxResults": 3000,
            },
        )
        require(isinstance(rows, list) and len(rows) < 3000, "order_history_incomplete")
        orders = tuple(self.order(o) for o in rows)
        # 60-day query cannot prove absence of older GTC orders. Compare count.
        active = tuple(o for o in orders if o.state in ("working", "unknown"))
        require(account.get("roundTrips") is not None, "account_response_incomplete")
        return Snapshot(
            binding=self.profile.binding,
            environment="LIVE",
            verified_at=now(),
            currency="USD",
            equity=balance["liquidationValue"],
            cash=balance["cashBalance"],
            buying_power=balance.get(
                "buyingPower", balance.get("cashAvailableForTrading")
            ),
            positions=tuple(
                Position(
                    symbol=p["instrument"]["symbol"],
                    quantity=Decimal(str(p["longQuantity"]))
                    - Decimal(str(p["shortQuantity"])),
                    market_value=p["marketValue"],
                    currency="USD",
                )
                for p in account.get("positions", [])
            ),
            orders=active,
            account_verified=True,
            environment_verified=True,
            # A read token alone does not prove trade permission or complete GTC ownership.
            trading_permitted=False,
        )

    def submit(self, intent: Intent):
        dispatch_guard(intent)
        _, headers = self.http.request(
            "POST",
            f"{self.path}/orders",
            json={
                "orderType": "LIMIT",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "price": str(intent.limit_price),
                "orderLegCollection": [
                    {
                        "instruction": intent.side,
                        "quantity": int(intent.quantity),
                        "instrument": {"symbol": intent.symbol, "assetType": "EQUITY"},
                    }
                ],
            },
        )
        location = urlsplit(headers.get("location", ""))
        require(
            location.scheme == "https"
            and location.hostname == "api.schwabapi.com"
            and location.path.startswith(f"{self.path}/orders/"),
            "submission_outcome_unknown",
        )
        result = self.lookup(intent.client_id, location.path.rsplit("/", 1)[-1])
        require(result is not None, "submission_outcome_unknown")
        return result

    def lookup(self, client_id, order_id):
        if not order_id:
            # Never infer a matching order from symbol/quantity/time; manual orders can match.
            raise BrokerError("order_identity_requires_operator_reconciliation")
        row, _ = self.http.request(
            "GET", f"{self.path}/orders/{quote(order_id, safe='')}"
        )
        return self.order(row, client_id) if row else None

    def cancel(self, order_id):
        self.http.request("DELETE", f"{self.path}/orders/{quote(order_id, safe='')}")

    def close(self):
        self.http.close()
