"""Tiger Prime/Paper SDK adapter; independent from the existing Paper package."""

import tempfile
from decimal import Decimal

from ..contracts import Order, Position, Snapshot, dispatch_guard, now, require
from ..contracts import acknowledge_order


def private_key_pem(value):
    """Accept SDK properties, PEM and browser-pasted PEM without exposing a key."""
    import base64
    import re

    from Crypto.PublicKey import RSA

    value = value.replace("\\r", "").replace("\\n", "\n").strip()
    match = re.fullmatch(
        r"-----BEGIN (RSA PRIVATE KEY|PRIVATE KEY)-----\s*([A-Za-z0-9+/=\s]+)\s*-----END \1-----",
        value,
    )
    if match:
        value = base64.b64decode(re.sub(r"\s", "", match.group(2)), validate=True)
    elif re.fullmatch(r"[A-Za-z0-9+/=\s]+", value):
        value = base64.b64decode(re.sub(r"\s", "", value), validate=True)
    key = RSA.import_key(value)
    require(key.has_private() and key.size_in_bits() >= 2048, "tiger_key_invalid")
    return key.export_key(format="PEM", pkcs=8).decode()


class Tiger:
    def __init__(self, profile, client=None):
        self.profile = profile
        self.account = profile.account.get_secret_value()
        self.temporary = None
        require(self.account.isdigit(), "tiger_account_invalid")
        require(
            (len(self.account) == 17) == (profile.environment == "PAPER"),
            "environment_mismatch",
        )
        if client is not None:
            self.client = client
            return
        from tigeropen.tiger_open_config import TigerOpenClientConfig
        from tigeropen.trade.trade_client import TradeClient

        # Never auto-load an unrelated working-directory properties file.
        self.temporary = tempfile.TemporaryDirectory(prefix="alta-tiger-config-")
        try:
            config = TigerOpenClientConfig(
                enable_dynamic_domain=False, props_path=self.temporary.name
            )
            config.private_key = private_key_pem(profile.secret("private_key"))
            config.tiger_id = profile.secret("tiger_id")
            config.account = self.account
            config.timeout = 15
            self.client = TradeClient(config)
        except Exception:
            self.temporary.cleanup()
            raise

    def order(self, row):
        require(str(row.account) == self.account, "account_mismatch")
        status = str(getattr(row.status, "name", row.status)).upper()
        filled = Decimal(str(row.filled))
        average = getattr(row, "avg_fill_price", None)
        return Order(
            order_id=str(row.id),
            client_id=str(getattr(row, "user_mark", "") or ""),
            symbol=row.contract.symbol,
            side=row.action,
            quantity=row.quantity,
            filled=filled,
            limit_price=getattr(row, "limit_price", None),
            average_price=average if filled else None,
            state="filled"
            if status == "FILLED"
            else "cancelled"
            if status in ("CANCELLED", "EXPIRED")
            else "rejected"
            if status in ("REJECTED", "INACTIVE")
            else "working"
            if status
            in (
                "NEW",
                "HELD",
                "PENDING_NEW",
                "PARTIALLY_FILLED",
                "PENDING_CANCEL",
                "SUBMITTED",
            )
            else "unknown",
        )

    def snapshot(self):
        a = self.client.get_prime_assets(account=self.account)
        require(a is not None and str(a.account) == self.account, "account_mismatch")
        stock = a.segments.get("S")
        require(stock is not None, "stock_account_unavailable")
        rows = self.client.get_positions(account=self.account)
        orders = self.client.get_open_orders(account=self.account)
        require(rows is not None and orders is not None, "snapshot_incomplete")
        require(all(str(p.account) == self.account for p in rows), "account_mismatch")
        return Snapshot(
            binding=self.profile.binding,
            environment=self.profile.environment,
            verified_at=now(),
            currency=stock.currency,
            equity=stock.net_liquidation,
            cash=stock.cash_balance,
            buying_power=stock.buying_power,
            positions=tuple(
                Position(
                    symbol=p.contract.symbol,
                    quantity=p.quantity,
                    market_value=p.market_value,
                    currency=p.contract.currency,
                )
                for p in rows
            ),
            orders=tuple(self.order(o) for o in orders),
            account_verified=True,
            environment_verified=True,
            trading_permitted=True,
        )

    def submit(self, intent, *, acknowledge=None):
        dispatch_guard(intent)
        from tigeropen.common.util.contract_utils import stock_contract
        from tigeropen.common.util.order_utils import limit_order

        order = limit_order(
            self.account,
            stock_contract(intent.symbol, currency="USD"),
            intent.side,
            int(intent.quantity),
            float(intent.limit_price),
            time_in_force="DAY",
        )
        order.outside_rth = False
        order.user_mark = intent.client_id
        capacity = self.client.get_estimate_tradable_quantity(order)
        quantity = getattr(
            capacity,
            "tradable_quantity"
            if intent.side == "BUY"
            else "tradable_position_quantity",
            None,
        )
        require(
            quantity is not None and Decimal(str(quantity)) >= intent.quantity,
            "broker_capacity_insufficient",
        )
        preview = self.client.preview_order(order)
        passed = (
            preview.get("is_pass")
            if isinstance(preview, dict)
            else getattr(preview, "is_pass", None)
        )
        warning = (
            preview.get("warning_text")
            if isinstance(preview, dict)
            else getattr(preview, "warning_text", None)
        )
        require(passed is True and not warning, "broker_preview_not_passed")
        dispatch_guard(intent)
        self.client.place_order(order)
        acknowledge_order(intent, order.id, acknowledge)
        result = self.lookup(intent.client_id, str(order.id))
        require(result is not None, "submission_outcome_unknown")
        return result

    def lookup(self, client_id, order_id):
        if order_id:
            row = self.client.get_order(id=int(order_id), account=self.account)
            rows = [row] if row is not None else []
        else:
            rows = self.client.get_orders(
                account=self.account, limit=100, is_brief=False
            )
            require(rows is not None and len(rows) < 100, "order_history_incomplete")
        results = [
            self.order(row)
            for row in rows
            if str(getattr(row, "user_mark", "")) == client_id
        ]
        require(len(results) <= 1, "duplicate_client_order")
        if order_id and rows:
            require(len(results) == 1, "order_identity_mismatch")
        return results[0] if results else None

    def cancel(self, order_id):
        self.client.cancel_order(id=int(order_id), account=self.account)

    def close(self):
        if self.temporary:
            self.temporary.cleanup()
