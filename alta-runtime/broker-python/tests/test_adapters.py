from datetime import timedelta
from types import SimpleNamespace as NS
from secrets import token_hex

import httpx
import pytest
from pydantic import SecretStr

from alta_brokers.adapters.alpaca import Alpaca
from alta_brokers.adapters.schwab import Schwab
from alta_brokers.adapters.tiger import Tiger, private_key_pem
from alta_brokers.adapters.futu import Futu
from alta_brokers.adapters.ibkr import InteractiveBrokers
from alta_brokers.adapters.longport import Longport
from alta_brokers.contracts import BrokerError, Intent, Profile, now
from alta_brokers.transport import Transport


def profile(
    provider="alpaca", environment="PAPER", account="test-account", **credentials
):
    return Profile(
        provider=provider,
        environment=environment,
        account=SecretStr(account),
        credentials={k: SecretStr(v) for k, v in credentials.items()},
    )


def request():
    return Intent(
        client_id="alta-" + "a" * 32,
        symbol="AAPL",
        side="BUY",
        quantity="25",
        limit_price="100",
        expires_at=now() + timedelta(seconds=10),
        reference_id="audit-reference",
    )


class HTTP:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return next(self.responses), {}

    def close(self):
        pass


def alpaca_order(**changes):
    return dict(
        id="order-one",
        client_order_id=request().client_id,
        symbol="AAPL",
        side="buy",
        qty="25",
        filled_qty="0",
        limit_price="100",
        filled_avg_price=None,
        status="new",
        **changes,
    )


def test_alpaca_environment_fixed_account_proof_and_wire_order():
    config = profile(api_key=token_hex(16), api_secret=token_hex(16))
    client = Alpaca(config)
    try:
        assert client.http.base == "https://paper-api.alpaca.markets"
    finally:
        client.close()
    transport = HTTP(
        [
            {
                "id": "test-account",
                "currency": "USD",
                "equity": "10000",
                "cash": "10000",
                "buying_power": "10000",
                "status": "ACTIVE",
                "trading_blocked": False,
                "account_blocked": False,
            },
            [],
            [],
            {"class": "us_equity", "tradable": True},
            alpaca_order(),
        ]
    )
    adapter = Alpaca(config, transport)
    assert adapter.snapshot().account_verified
    assert adapter.submit(request()).state == "working"
    wire = transport.calls[-1][1]["json"]
    assert (
        wire["qty"] == "25"
        and wire["type"] == "limit"
        and wire["extended_hours"] is False
    )


def test_alpaca_expired_preflight_never_reaches_post():
    transport = HTTP([{"class": "us_equity", "tradable": True}])
    with pytest.raises(BrokerError, match="deadline_expired"):
        Alpaca(profile(), transport).submit(
            request().model_copy(update={"expires_at": now() - timedelta(seconds=1)})
        )
    assert transport.calls == []


def test_tiger_cross_environment_and_account_are_blocked():
    with pytest.raises(BrokerError, match="environment_mismatch"):
        Tiger(profile("tiger", "LIVE", "0" * 17), client=NS())
    adapter = Tiger(
        profile("tiger", "PAPER", "0" * 17),
        client=NS(get_prime_assets=lambda **_: NS(account="other")),
    )
    with pytest.raises(BrokerError, match="account_mismatch"):
        adapter.snapshot()


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, mode):
        assert mode == "records"
        return self.rows


def test_futu_explicit_account_and_environment_not_first_account():
    config = profile("futu", "PAPER", "1000")
    adapter = Futu(
        config,
        NS(get_acc_list=lambda: (0, Rows([{"acc_id": 1000, "trd_env": "REAL"}]))),
    )
    with pytest.raises(BrokerError, match="environment_mismatch"):
        adapter.snapshot()
    result = Futu.order(
        dict(
            order_id="one",
            remark="alta-" + "a" * 32,
            code="US.AAPL",
            trd_side="BUY",
            qty=25,
            dealt_qty=10,
            dealt_avg_price=100,
            price=100,
            order_status="CANCELLED_PART",
        )
    )
    assert result.state == "cancelled" and result.filled == 10


def test_ibkr_permanent_identity_and_partial_fills():
    config = profile("ibkr", "PAPER", "DU1000", client_id="71")
    adapter = InteractiveBrokers(config, client=NS())
    trade = NS(
        order=NS(
            account="DU1000",
            permId=99,
            orderRef=request().client_id,
            action="BUY",
            totalQuantity=25,
            lmtPrice=100,
            orderType="LMT",
        ),
        contract=NS(symbol="AAPL"),
        orderStatus=NS(status="Submitted", filled=5, avgFillPrice=100),
    )
    result = adapter.order(trade)
    assert result.order_id == "99" and result.state == "working" and result.filled == 5
    trade.order.account = "U1000"
    with pytest.raises(BrokerError, match="account_mismatch"):
        adapter.order(trade)


def test_longport_never_manufactures_account_or_environment_proof():
    client = NS(
        account_balance=lambda **_: [
            NS(currency="USD", net_assets=10000, total_cash=10000, buy_power=10000)
        ],
        stock_positions=lambda: NS(channels=[]),
        today_orders=lambda: [],
    )
    result = Longport(profile("longport"), client).snapshot()
    assert (
        not result.account_verified
        and not result.environment_verified
        and not result.trading_permitted
    )


def test_schwab_missing_order_id_cannot_be_retried_or_inferred():
    adapter = Schwab(profile("schwab", "LIVE", account_hash="testhash"), HTTP([]))
    with pytest.raises(BrokerError, match="operator_reconciliation"):
        adapter.lookup(request().client_id, None)
    assert adapter.http.calls == []


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_http_transport_no_redirect_retry_or_secret_echo(status):
    calls = []
    secret = token_hex(20)

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"secret": secret},
            headers={"location": "https://invalid.example"},
        )

    client = httpx.Client(
        base_url="https://broker.example", transport=httpx.MockTransport(handler)
    )
    transport = Transport("https://broker.example", {}, client)
    try:
        with pytest.raises(BrokerError) as error:
            transport.request("POST", "/orders", json={})
        assert secret not in str(error.value) and len(calls) == 1
    finally:
        transport.close()


def test_official_sdk_imports_and_order_enum_compatibility():
    from longport.openapi import Config, OrderType, OutsideRTH
    from ib_async import LimitOrder
    from futu import SecurityFirm
    from tigeropen.common.util.order_utils import limit_order

    assert callable(Config.from_apikey)
    assert OrderType.LO is not None and OutsideRTH.RTHOnly is not None
    assert SecurityFirm.FUTUSECURITIES and LimitOrder and callable(limit_order)


def test_tiger_key_accepts_pem_browser_and_properties_formats_without_echo():
    import base64
    from Crypto.PublicKey import RSA

    key = RSA.generate(2048)
    pem = key.export_key(format="PEM", pkcs=8).decode()
    variants = [
        pem,
        pem.replace("\n", ""),
        pem.replace("\n", "\\n"),
        base64.b64encode(key.export_key(format="DER", pkcs=8)).decode(),
    ]
    assert all(RSA.import_key(private_key_pem(value)) == key for value in variants)
    with pytest.raises(BrokerError, match="tiger_key_invalid"):
        private_key_pem(key.public_key().export_key().decode())
