import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import alta_capitald.paper_trade as paper_trade
from alta_capitald.__main__ import _safe_error_code
from alta_capitald import (
    PaperBoundaryError,
    PaperOrderRequest,
    PaperTradeConfig,
    TigerPaperSession,
)


def test_broker_error_code_diagnostics_are_bounded() -> None:
    safe = RuntimeError("safe")
    safe.code = 1200  # type: ignore[attr-defined]
    unsafe = RuntimeError("unsafe")
    unsafe.code = "secret\nvalue"  # type: ignore[attr-defined]

    assert _safe_error_code(safe) == "1200"
    assert _safe_error_code(unsafe) is None
    assert _safe_error_code(RuntimeError("plain")) is None


PAPER_ACCOUNT = "00000000000000000"


def config(tmp_path: Path) -> PaperTradeConfig:
    config_path = tmp_path / "tiger-paper.properties"
    config_path.write_text("synthetic=true\n")
    config_path.chmod(0o600)
    authorization_path = tmp_path / "paper-authorization.json"
    authorization_path.write_text(
        json.dumps(
            {
                "version": 2,
                "enabled": True,
                "generation": 1,
                "accountSha256": hashlib.sha256(PAPER_ACCOUNT.encode()).hexdigest(),
                "configurationSha256": hashlib.sha256(
                    config_path.read_bytes()
                ).hexdigest(),
            }
        )
    )
    authorization_path.chmod(0o600)
    return PaperTradeConfig(
        config_path=config_path,
        config_root=tmp_path,
        account_sha256=hashlib.sha256(PAPER_ACCOUNT.encode()).hexdigest(),
        owner_id="paper-test-owner",
        owner_lease_path=tmp_path / "capital.owner",
        timeout_seconds=5,
        authorization_path=authorization_path,
        authorization_generation=1,
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
        {"quantity": Decimal("0")},
        {"quantity": Decimal("1.5")},
        {"symbol": "*"},
        {"limit_price": Decimal("NaN")},
        {"expected_position_before": Decimal("-1")},
    ],
)
def test_paper_order_requires_bounded_whole_share_directional_request(
    update: dict,
) -> None:
    values = {
        "action": "BUY",
        "symbol": "SPY",
        "limit_price": Decimal("500"),
        "expected_position_before": Decimal(0),
        "client_order_id": "alta-" + "1" * 32,
        "quantity": Decimal("12"),
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
        return SimpleNamespace(account=account, update_timestamp=None, segments={})

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

    def get_orders(self, *, account, limit, is_brief):
        assert (account, limit) == (self.account, 100)
        assert isinstance(is_brief, bool)
        return []

    def preview_order(self, _order):
        return {"is_pass": True}

    def get_estimate_tradable_quantity(self, _order):
        return SimpleNamespace(
            tradable_quantity=1000,
            tradable_position_quantity=max(self.quantity, Decimal(0)),
        )

    def place_order(self, order):
        self.pending = order
        return 42

    def get_order(self, *, account, id):
        assert (account, id) == (self.account, 42)
        filled = Decimal(self.pending.quantity)
        self.quantity += filled if self.pending.action == "BUY" else -filled
        return SimpleNamespace(
            account=account,
            status="FILLED",
            filled=filled,
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


def test_session_reconciles_risk_sized_open_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_sdk(monkeypatch)

    with TigerPaperSession(config(tmp_path)) as session:
        assert session.preflight() == {
            "paper": True,
            "accountBinding": True,
            "positionCount": 0,
            "openOrderCount": 0,
            "mutationPolicy": "risk_budgeted_limit_day_v1",
            "maxOrderNotional": "10000",
        }
        opened = session.execute(
            PaperOrderRequest(
                action="BUY",
                symbol="SPY",
                limit_price=Decimal("500"),
                expected_position_before=Decimal(0),
                client_order_id="alta-" + "2" * 32,
                quantity=Decimal("12"),
                quote_known_at=datetime.now(UTC),
            )
        )
        closed = session.flatten_with_identity(
            "SPY", Decimal("495"), "alta-" + "4" * 32
        )

    assert (opened.status, opened.position_after) == ("filled", "12")
    assert (closed.status, closed.position_after) == ("filled", "0")
    assert not (tmp_path / "capital.owner").exists()


@pytest.mark.parametrize(
    ("quote_known_at", "message"),
    [
        (None, "requires a dispatch quote"),
        (datetime.now(UTC) - timedelta(seconds=11), "expired before submission"),
    ],
)
def test_open_rejects_missing_or_expired_dispatch_quote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    quote_known_at: datetime | None,
    message: str,
) -> None:
    patch_sdk(monkeypatch)

    with TigerPaperSession(config(tmp_path)) as session:
        with pytest.raises(PaperBoundaryError, match=message):
            session.execute(
                PaperOrderRequest(
                    action="BUY",
                    symbol="SPY",
                    limit_price=Decimal("500"),
                    expected_position_before=Decimal(0),
                    client_order_id="alta-" + "9" * 32,
                    quantity=Decimal("12"),
                    quote_known_at=quote_known_at,
                )
            )


def test_broker_capacity_and_preview_retain_final_order_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CapacityClient(_FakeClient):
        def get_estimate_tradable_quantity(self, _order):
            return SimpleNamespace(
                tradable_quantity=Decimal("11"),
                tradable_position_quantity=Decimal(0),
            )

    patch_sdk(monkeypatch, CapacityClient)
    request = PaperOrderRequest(
        action="BUY",
        symbol="SPY",
        limit_price=Decimal("500"),
        expected_position_before=Decimal(0),
        client_order_id="alta-" + "a" * 32,
        quantity=Decimal("12"),
        quote_known_at=datetime.now(UTC),
    )
    with TigerPaperSession(config(tmp_path)) as session:
        with pytest.raises(PaperBoundaryError, match="tradable quantity"):
            session.execute(request)

    class PreviewClient(_FakeClient):
        def preview_order(self, _order):
            return {"is_pass": False, "warning_text": "synthetic rejection"}

    patch_sdk(monkeypatch, PreviewClient)
    with TigerPaperSession(config(tmp_path)) as session:
        with pytest.raises(PaperBoundaryError, match="preview rejected"):
            session.execute(request)


def test_preflight_reports_open_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OpenOrderClient(_FakeClient):
        def get_open_orders(self, *, account):
            return [SimpleNamespace(account=account)]

    patch_sdk(monkeypatch, OpenOrderClient)

    with TigerPaperSession(config(tmp_path)) as session:
        assert session.preflight()["openOrderCount"] == 1


def test_snapshot_exposes_portfolio_without_raw_account_or_order_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SnapshotClient(_FakeClient):
        def __init__(self, client_config) -> None:
            super().__init__(client_config)
            self.quantity = Decimal("1")

        def get_prime_assets(self, *, account):
            stock = SimpleNamespace(
                currency="USD",
                cash_balance=10_000,
                cash_available_for_trade=9_000,
                net_liquidation=10_150,
                gross_position_value=150,
                buying_power=18_000,
                unrealized_pl=5,
                realized_pl=2,
                maintain_margin=45,
            )
            return SimpleNamespace(
                account=account,
                update_timestamp=1_725_000_000_000,
                segments={"S": stock},
            )

        def get_positions(self, *, account, symbol=None):
            return [
                SimpleNamespace(
                    account=account,
                    contract=SimpleNamespace(
                        symbol=symbol or "SPY", sec_type="STK", currency="USD"
                    ),
                    quantity=1,
                    average_cost=500,
                    market_price=505,
                    market_value=505,
                    unrealized_pnl=5,
                    unrealized_pnl_percent=0.01,
                    realized_pnl=2,
                    today_pnl=3,
                    salable_qty=1,
                )
            ]

        def get_orders(self, *, account, limit, is_brief):
            assert limit == 100
            return [
                SimpleNamespace(
                    account=account,
                    id=987654321,
                    contract=SimpleNamespace(
                        symbol="SPY", sec_type="STK", currency="USD"
                    ),
                    action="BUY",
                    order_type="LMT",
                    status="FILLED",
                    quantity=1,
                    filled=1,
                    remaining=0,
                    limit_price=500,
                    avg_fill_price=500,
                    commission=0.01,
                    realized_pnl=0,
                    time_in_force="DAY",
                    outside_rth=False,
                    order_time=1_725_000_000_000,
                    update_time=1_725_000_001_000,
                    trade_time=1_725_000_001_000,
                )
            ]

    patch_sdk(monkeypatch, SnapshotClient)

    with TigerPaperSession(config(tmp_path)) as session:
        snapshot = session.snapshot()

    encoded = str(snapshot)
    assert PAPER_ACCOUNT not in encoded
    assert "987654321" not in encoded
    assert (
        snapshot["accountFingerprint"]
        == hashlib.sha256(PAPER_ACCOUNT.encode()).hexdigest()[:12]
    )
    assert snapshot["assets"]["netLiquidation"] == "10150"
    assert snapshot["positions"][0]["symbol"] == "SPY"
    assert (
        snapshot["orders"][0]["reference"]
        == hashlib.sha256(b"987654321").hexdigest()[:16]
    )


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
                    client_order_id="alta-" + "3" * 32,
                    quantity=Decimal("12"),
                    quote_known_at=datetime.now(UTC),
                )
            )


def test_stable_client_identity_reconciles_without_a_second_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class IdempotentClient(_FakeClient):
        placed = 0

        def __init__(self, client_config) -> None:
            super().__init__(client_config)
            self.history = []

        def get_orders(self, *, account, limit, is_brief):
            assert (account, limit) == (self.account, 100)
            return list(self.history)

        def place_order(self, order):
            type(self).placed += 1
            self.pending = order
            return 42

        def get_order(self, *, account, id):
            observed = super().get_order(account=account, id=id)
            if not self.history:
                self.history.append(
                    SimpleNamespace(
                        account=account,
                        id=id,
                        contract=self.pending.contract,
                        action=self.pending.action,
                        order_type="LMT",
                        status="FILLED",
                        quantity=self.pending.quantity,
                        filled=self.pending.quantity,
                        limit_price=self.pending.limit_price,
                        avg_fill_price=self.pending.limit_price,
                        time_in_force="DAY",
                        outside_rth=False,
                        user_mark=self.pending.user_mark,
                    )
                )
            return observed

    patch_sdk(monkeypatch, IdempotentClient)
    request = PaperOrderRequest(
        action="BUY",
        symbol="SPY",
        limit_price=Decimal("500"),
        expected_position_before=Decimal(0),
        client_order_id="alta-" + "5" * 32,
        quantity=Decimal("12"),
        quote_known_at=datetime.now(UTC),
    )
    with TigerPaperSession(config(tmp_path)) as session:
        first = session.execute(request)
        second = session.execute(request)

    assert first == second
    assert IdempotentClient.placed == 1


def test_revoked_authorization_is_rechecked_before_each_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_sdk(monkeypatch)
    settings = config(tmp_path)
    with TigerPaperSession(settings) as session:
        authorization = json.loads(settings.authorization_path.read_text())
        authorization["enabled"] = False
        authorization["generation"] = 2
        settings.authorization_path.write_text(json.dumps(authorization))
        settings.authorization_path.chmod(0o600)
        with pytest.raises(PaperBoundaryError, match="revoked or changed"):
            session.execute(
                PaperOrderRequest(
                    action="BUY",
                    symbol="SPY",
                    limit_price=Decimal("500"),
                    expected_position_before=Decimal(0),
                    client_order_id="alta-" + "6" * 32,
                    quantity=Decimal("12"),
                    quote_known_at=datetime.now(UTC),
                )
            )


def test_drain_authorization_blocks_open_but_permits_full_position_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_sdk(monkeypatch)
    settings = config(tmp_path)
    authorization = json.loads(settings.authorization_path.read_text())
    authorization["closeOnly"] = True
    settings.authorization_path.write_text(json.dumps(authorization))
    settings.authorization_path.chmod(0o600)
    with TigerPaperSession(settings) as session:
        with pytest.raises(PaperBoundaryError, match="permits close orders only"):
            session.execute(
                PaperOrderRequest(
                    action="BUY",
                    symbol="SPY",
                    limit_price=Decimal("500"),
                    expected_position_before=Decimal(0),
                    client_order_id="alta-" + "7" * 32,
                    quantity=Decimal("12"),
                    quote_known_at=datetime.now(UTC),
                )
            )
        authorization["generation"] = 2
        settings.authorization_path.write_text(json.dumps(authorization))
        settings.authorization_path.chmod(0o600)
        session.client.quantity = Decimal(12)
        result = session.execute(
            PaperOrderRequest(
                action="SELL",
                symbol="SPY",
                limit_price=Decimal("495"),
                expected_position_before=Decimal(12),
                client_order_id="alta-" + "8" * 32,
                quantity=Decimal(12),
            )
        )
    assert result.position_after == "0"
