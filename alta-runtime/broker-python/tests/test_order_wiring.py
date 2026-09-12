"""Offline SDK/HTTP contracts, not account acceptance or broker executions."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from pydantic import SecretStr

from alta_brokers.adapters.alpaca import Alpaca
from alta_brokers.adapters.futu import Futu
from alta_brokers.adapters.ibkr import InteractiveBrokers
from alta_brokers.adapters.longport import Longport
from alta_brokers.adapters.schwab import Schwab
from alta_brokers.adapters.tiger import Tiger
from alta_brokers.contracts import BrokerError, Intent, Profile, now


def intent():
    return Intent(
        client_id="alta-" + "b" * 32,
        symbol="AAPL",
        side="BUY",
        quantity="250",
        limit_price="100.25",
        reference_id="audited-test-reference",
        expires_at=now() + timedelta(seconds=20),
    )


def config(provider, account="test-account", **credentials):
    return Profile(
        provider=provider,
        environment="LIVE",
        account=SecretStr(account),
        credentials={k: SecretStr(v) for k, v in credentials.items()},
    )


@pytest.mark.parametrize(
    "adapter", [Alpaca, Tiger, Futu, InteractiveBrokers, Longport, Schwab]
)
def test_all_six_reject_expired_intent_before_any_sdk_or_network_work(adapter):
    # No constructor, no SDK session and deliberately no client attributes:
    # an expired request must be rejected before reaching any provider code.
    instance = object.__new__(adapter)
    expired = intent().model_copy(update={"expires_at": now() - timedelta(seconds=1)})
    with pytest.raises(BrokerError, match="dispatch_deadline_expired"):
        instance.submit(expired)


def test_tiger_sdk_preserves_size_account_limit_and_client_identity():
    calls = []
    placed = []

    def place(order):
        calls.append("place")
        order.id = 123
        order.status = "NEW"
        order.filled = 0
        placed.append(order)

    client = NS(
        get_estimate_tradable_quantity=lambda order: NS(tradable_quantity=1000),
        preview_order=lambda order: {"is_pass": True, "warning_text": ""},
        place_order=place,
        get_order=lambda **kw: placed[0],
        cancel_order=lambda **kw: calls.append(kw),
    )
    adapter = Tiger(config("tiger", "12345678"), client)
    result = adapter.submit(intent())
    order = placed[0]
    assert result.quantity == 250 and result.client_id == intent().client_id
    assert order.account == "12345678" and order.limit_price == 100.25
    assert order.time_in_force == "DAY" and order.outside_rth is False
    adapter.cancel(result.order_id)
    assert calls == ["place", {"id": 123, "account": "12345678"}]


class Table:
    def __init__(self, row):
        self.row = row

    def to_dict(self, kind):
        assert kind == "records"
        return [self.row]


def test_futu_unlock_is_explicit_and_regular_session_is_not_inferred():
    calls = []

    def place(**kw):
        calls.append(kw)
        return 0, Table(
            {
                **kw,
                "order_id": "123",
                "dealt_qty": 0,
                "dealt_avg_price": 0,
                "order_status": "SUBMITTED",
            }
        )

    client = NS(
        unlock_trade=lambda **kw: (calls.append("unlock") or 0, ""),
        place_order=place,
        modify_order=lambda *args, **kw: (calls.append((args, kw)) or 0, ""),
    )
    adapter = Futu(config("futu", "12345678", trade_password="test-only"), client)
    result = adapter.submit(intent())
    assert result.quantity == 250
    assert calls[0] == "unlock"
    assert calls[1]["session"] == "RTH" and calls[1]["trd_env"] == "REAL"
    assert calls[1]["acc_id"] == 12345678 and calls[1]["time_in_force"] == "DAY"
    assert calls[1]["remark"] == intent().client_id
    adapter.cancel(result.order_id)
    assert calls[-1] == (
        ("CANCEL", "123", 0, 0),
        {"trd_env": "REAL", "acc_id": 12345678},
    )


def test_futu_zero_cannot_fall_back_to_first_available_account():
    with pytest.raises(BrokerError, match="broker_account_invalid"):
        Futu(config("futu", "000"), NS())


def test_ibkr_uses_qualified_contract_what_if_and_permanent_order_identity():
    calls = []
    trades = []

    def place(contract, order):
        calls.append("place")
        order.permId = 123
        order.clientId = 81
        trade = NS(
            contract=contract,
            order=order,
            orderStatus=NS(status="Submitted", filled=0, avgFillPrice=0),
        )
        trades.append(trade)
        return trade

    client = NS(
        qualifyContracts=lambda contract: [contract],
        whatIfOrder=lambda c, o: NS(warningText="", initMarginChange="25062.50"),
        placeOrder=place,
        reqOpenOrders=lambda: trades,
        cancelOrder=lambda o: calls.append(("cancel", o.permId)),
    )
    adapter = InteractiveBrokers(config("ibkr", "U12345678", client_id="81"), client)
    result = adapter.submit(intent())
    order = trades[0].order
    assert result.order_id == "123" and result.quantity == 250
    assert order.account == "U12345678" and order.orderRef == intent().client_id
    assert order.tif == "DAY" and order.outsideRth is False and order.lmtPrice == 100.25
    adapter.cancel(result.order_id)
    assert calls == ["place", ("cancel", 123)]


def test_longport_preserves_decimal_size_and_tracks_returned_id():
    calls = []

    def submit(**kw):
        calls.append(kw)
        return NS(order_id="123")

    row = NS(
        order_id="123",
        remark=intent().client_id,
        symbol="AAPL.US",
        side="Buy",
        status="New",
        quantity=Decimal(250),
        executed_quantity=Decimal(0),
        price=Decimal("100.25"),
        executed_price=Decimal(0),
    )
    client = NS(
        submit_order=submit,
        order_detail=lambda order_id: row,
        cancel_order=lambda order_id: calls.append(order_id),
    )
    adapter = Longport(config("longport"), client)
    result = adapter.submit(intent())
    assert result.quantity == 250 and result.limit_price == Decimal("100.25")
    assert calls[0]["submitted_quantity"] == Decimal(250)
    assert calls[0]["remark"] == intent().client_id
    assert str(calls[0]["outside_rth"]).endswith("RTHOnly")
    adapter.cancel(result.order_id)
    assert calls[-1] == "123"


def test_schwab_uses_location_identity_and_never_replays_a_post():
    calls = []
    path = "/trader/v1/accounts/testhash/orders"

    def request(method, url, **kw):
        calls.append((method, url, kw))
        if method == "POST":
            return None, {"location": f"https://api.schwabapi.com{path}/123"}
        if method == "GET":
            return {
                "orderId": 123,
                "status": "WORKING",
                "quantity": 250,
                "filledQuantity": 0,
                "price": 100.25,
                "orderLegCollection": [
                    {"instruction": "BUY", "instrument": {"symbol": "AAPL"}}
                ],
            }, {}
        return None, {}

    adapter = Schwab(config("schwab", account_hash="testhash"), NS(request=request))
    result = adapter.submit(intent())
    assert result.quantity == 250 and result.order_id == "123"
    wire = calls[0][2]["json"]
    assert wire["session"] == "NORMAL" and wire["duration"] == "DAY"
    assert wire["orderLegCollection"][0]["quantity"] == 250
    adapter.cancel(result.order_id)
    assert [c[0] for c in calls] == ["POST", "GET", "DELETE"]
