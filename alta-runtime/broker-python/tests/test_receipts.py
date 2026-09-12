"""Provider receipts survive later failures; no real broker is contacted."""

from types import SimpleNamespace as NS

import pytest

from alta_brokers.adapters.schwab import Schwab
from alta_brokers.adapters.longport import Longport
from alta_brokers.adapters.futu import Futu
from test_order_wiring import config, intent
from test_adapters import Rows


@pytest.mark.parametrize("provider", ["schwab", "longport"])
def test_server_identity_is_reported_before_detail_request_can_fail(provider):
    seen = []

    def fail(*args, **kwargs):
        assert seen == ["123"]
        raise TimeoutError("private provider detail")

    if provider == "schwab":

        def request(method, path, **kwargs):
            if method == "POST":
                return None, {
                    "location": "https://api.schwabapi.com/trader/v1/accounts/testhash/orders/123"
                }
            return fail()

        adapter = Schwab(config("schwab", account_hash="testhash"), NS(request=request))
    else:
        adapter = Longport(
            config("longport"),
            NS(submit_order=lambda **kw: NS(order_id="123"), order_detail=fail),
        )
    with pytest.raises(TimeoutError):
        adapter.submit(intent(), acknowledge=seen.append)
    assert seen == ["123"]


def test_futu_recovers_prior_session_by_exact_order_and_client_identity():
    calls = []

    def history(**kw):
        calls.append(kw)
        return 0, Rows(
            [
                {
                    "order_id": "123",
                    "remark": intent().client_id,
                    "code": "US.AAPL",
                    "trd_side": "BUY",
                    "qty": 250,
                    "dealt_qty": 250,
                    "dealt_avg_price": 100.25,
                    "price": 100.25,
                    "order_status": "FILLED_ALL",
                }
            ]
        )

    adapter = Futu(
        config("futu", "12345678"),
        NS(
            order_list_query=lambda **kw: (0, Rows([])),
            history_order_list_query=history,
        ),
    )
    result = adapter.lookup(intent().client_id, "123")
    assert result.state == "filled" and result.filled == 250
    assert calls[0]["acc_id"] == 12345678 and calls[0]["trd_env"] == "REAL"


def test_futu_cancel_reconnect_unlocks_before_mutation_but_paper_does_not():
    for environment in ("LIVE", "PAPER"):
        calls = []
        client = NS(
            unlock_trade=lambda **kw: (calls.append("unlock") or 0, ""),
            modify_order=lambda *args, **kw: (calls.append(kw["trd_env"]) or 0, ""),
        )
        p = config("futu", "12345678", trade_password="test-only").model_copy(
            update={"environment": environment}
        )
        Futu(p, client).cancel("123")
        assert calls == (["unlock", "REAL"] if environment == "LIVE" else ["SIMULATE"])
