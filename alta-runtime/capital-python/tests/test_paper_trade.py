import hashlib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import alta_capitald.paper_trade as paper_trade
from alta_capitald import (
    PaperBoundaryError,
    PaperOrderRequest,
    PaperTradeConfig,
    TigerPaperSession,
)

PAPER_ACCOUNT = "00000000000000000"


def config(tmp_path: Path) -> PaperTradeConfig:
    config_path = tmp_path / "tiger-paper.properties"
    config_path.write_text("synthetic=true\n")
    config_path.chmod(0o600)
    return PaperTradeConfig(
        config_path=config_path,
        config_root=tmp_path,
        account_sha256=hashlib.sha256(PAPER_ACCOUNT.encode()).hexdigest(),
        owner_id="paper-test-owner",
        owner_lease_path=tmp_path / "capital.owner",
        timeout_seconds=5,
    )


def test_paper_trade_config_requires_exact_private_binding(tmp_path: Path) -> None:
    values = config(tmp_path).__dict__
    with pytest.raises(PaperBoundaryError):
        PaperTradeConfig(**(values | {"account_sha256": "0" * 63}))
    with pytest.raises(PaperBoundaryError):
        PaperTradeConfig(**(values | {"config_path": Path("relative")}))
    values["config_path"].chmod(0o644)
    with pytest.raises(PaperBoundaryError, match="owner-only"):
        PaperTradeConfig(**values)


@pytest.mark.parametrize(
    "update",
    [
        {"quantity": Decimal("2")},
        {"symbol": "*"},
        {"limit_price": Decimal("NaN")},
        {"expected_position_before": Decimal("-1")},
    ],
)
def test_paper_order_is_one_share_limit_only(update: dict) -> None:
    values = {
        "action": "BUY",
        "symbol": "SPY",
        "limit_price": Decimal("500"),
        "expected_position_before": Decimal(0),
    }
    with pytest.raises(PaperBoundaryError):
        PaperOrderRequest(**(values | update))


class _FakeConfig:
    def __init__(self, **_kwargs) -> None:
        self.account = PAPER_ACCOUNT
        self.is_paper = True
        self.tiger_id = "synthetic-tiger-id"
        self.private_key = "synthetic-private-key"
        self._sandbox_debug = False


class _FakeClient:
    def __init__(self, config) -> None:
        self.account = config.account
        self.quantity = Decimal(0)
        self.pending = None

    def get_prime_assets(self, *, account):
        return SimpleNamespace(account=account)

    def get_positions(self, *, account, symbol=None):
        if self.quantity == 0:
            return []
        return [
            SimpleNamespace(
                account=account,
                contract=SimpleNamespace(symbol=symbol or "SPY"),
                quantity=self.quantity,
            )
        ]

    def get_open_orders(self, *, account):
        assert account == self.account
        return []

    def preview_order(self, _order):
        return {}

    def place_order(self, order):
        self.pending = order
        return 42

    def get_order(self, *, account, id):
        assert (account, id) == (self.account, 42)
        self.quantity += 1 if self.pending.action == "BUY" else -1
        return SimpleNamespace(
            account=account,
            status="FILLED",
            filled=1,
            avg_fill_price=self.pending.limit_price,
        )

    def cancel_order(self, **_kwargs):
        raise AssertionError("a filled order must not be cancelled")


def _order(account, contract, action, quantity, limit_price, **_kwargs):
    return SimpleNamespace(
        account=account,
        contract=contract,
        action=action,
        quantity=quantity,
        limit_price=limit_price,
        outside_rth=None,
    )


def patch_sdk(monkeypatch: pytest.MonkeyPatch, client_type=_FakeClient) -> None:
    monkeypatch.setattr(paper_trade, "TigerOpenClientConfig", _FakeConfig)
    monkeypatch.setattr(paper_trade, "TradeClient", client_type)
    monkeypatch.setattr(
        paper_trade,
        "stock_contract",
        lambda symbol, currency: SimpleNamespace(symbol=symbol, currency=currency),
    )
    monkeypatch.setattr(paper_trade, "limit_order", _order)


def test_session_reconciles_one_share_open_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_sdk(monkeypatch)

    with TigerPaperSession(config(tmp_path)) as session:
        assert session.preflight() == {
            "paper": True,
            "accountBinding": True,
            "positionCount": 0,
            "openOrderCount": 0,
            "mutationPolicy": "one_share_limit_day",
        }
        opened = session.execute(
            PaperOrderRequest(
                action="BUY",
                symbol="SPY",
                limit_price=Decimal("500"),
                expected_position_before=Decimal(0),
            )
        )
        closed = session.flatten("SPY", Decimal("495"))

    assert (opened.status, opened.position_after) == ("filled", "1")
    assert (closed.status, closed.position_after) == ("filled", "0")
    assert not (tmp_path / "capital.owner").exists()


def test_preflight_reports_open_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OpenOrderClient(_FakeClient):
        def get_open_orders(self, *, account):
            return [SimpleNamespace(account=account)]

    patch_sdk(monkeypatch, OpenOrderClient)

    with TigerPaperSession(config(tmp_path)) as session:
        assert session.preflight()["openOrderCount"] == 1


def test_unconfirmed_cancel_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PendingClient(_FakeClient):
        def get_order(self, *, account, id):
            assert (account, id) == (self.account, 42)
            return SimpleNamespace(account=account, status="NEW", filled=0)

        def cancel_order(self, *, account, id):
            assert (account, id) == (self.account, 42)

    clock = iter(range(100))
    patch_sdk(monkeypatch, PendingClient)
    monkeypatch.setattr(paper_trade.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(paper_trade.time, "sleep", lambda _seconds: None)

    with TigerPaperSession(config(tmp_path)) as session:
        with pytest.raises(PaperBoundaryError, match="cancellation was not confirmed"):
            session.execute(
                PaperOrderRequest(
                    action="BUY",
                    symbol="SPY",
                    limit_price=Decimal("500"),
                    expected_position_before=Decimal(0),
                )
            )
