from datetime import timedelta
from decimal import Decimal
from secrets import token_hex

import pytest
from pydantic import SecretStr

from alta_brokers.contracts import (
    BrokerError,
    Intent,
    Order,
    Position,
    Profile,
    Quote,
    Snapshot,
    now,
)
from alta_brokers.engine import BrokerEngine
from alta_brokers.storage import Ledger, Profiles, atomic_private, owner, read_private


def profile(provider="alpaca", environment="PAPER"):
    return Profile(
        provider=provider,
        environment=environment,
        account=SecretStr("test-account"),
        credentials={
            "api_key": SecretStr(token_hex(16)),
            "api_secret": SecretStr(token_hex(16)),
        },
    )


def intent(**kwargs):
    return Intent(
        client_id="alta-" + "a" * 32,
        symbol="AAPL",
        side="BUY",
        quantity="10",
        limit_price="100.00",
        reference_id="audit-reference",
        expires_at=now() + timedelta(minutes=1),
        **kwargs,
    )


def quote(**kwargs):
    return Quote(
        symbol="AAPL", bid="99.99", ask="100", observed_at=now(), realtime=True
    ).model_copy(update=kwargs)


class Broker:
    def __init__(self, config):
        self.config = config
        self.calls = 0
        self.positions = ()
        self.result = None
        self.ambiguous = False
        self.working = False
        self.verified = True

    def snapshot(self):
        return Snapshot(
            binding=self.config.binding,
            environment=self.config.environment,
            verified_at=now(),
            currency="USD",
            equity="100000",
            cash="100000",
            buying_power="100000",
            positions=self.positions,
            orders=(),
            account_verified=self.verified,
            environment_verified=self.verified,
            trading_permitted=True,
        )

    def submit(self, request, *, acknowledge=None):
        self.calls += 1
        self.result = Order(
            order_id="test-order",
            client_id=request.client_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            limit_price=request.limit_price,
            filled=0 if self.working else request.quantity,
            average_price=None if self.working else request.limit_price,
            state="working" if self.working else "filled",
        )
        if not self.working:
            self.positions = (
                Position(
                    symbol=request.symbol,
                    quantity=request.quantity,
                    market_value="1000",
                    currency="USD",
                ),
            )
        if self.ambiguous:
            raise TimeoutError("private provider error must not escape")
        return self.result

    def lookup(self, client_id, order_id):
        return self.result

    def cancel(self, order_id):
        self.result = self.result.model_copy(update={"state": "cancelled"})

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path):
    config = profile()
    broker = Broker(config)
    engine = BrokerEngine(config, broker, tmp_path / "account")
    yield config, broker, engine
    engine.close()


def arm(config, engine):
    return engine.authorize(f"ENABLE {config.environment} {config.binding[-8:]}")


def test_no_implicit_authority_and_environment_bound_confirmation(setup):
    config, broker, engine = setup
    with pytest.raises(BrokerError, match="not_authorized"):
        engine.submit(intent(), quote())
    with pytest.raises(BrokerError, match="confirmation_required"):
        engine.authorize(f"ENABLE LIVE {config.binding[-8:]}")
    broker.verified = False
    with pytest.raises(BrokerError, match="identity_unverified"):
        arm(config, engine)
    assert broker.calls == 0


def test_fill_reuse_restart_recovery_no_duplicate_post(setup):
    config, broker, engine = setup
    arm(config, engine)
    request = intent()
    assert engine.submit(request, quote()).state == "filled"
    assert engine.submit(request, quote()).state == "filled"
    assert broker.calls == 1
    reopened = BrokerEngine(config, broker, engine.directory)
    try:
        assert reopened.reconcile()["pending_count"] == 0
        assert reopened.submit(request, quote()).state == "filled"
        assert broker.calls == 1
    finally:
        reopened.close()


def test_unknown_submission_freezes_other_orders_then_recovers(setup):
    config, broker, engine = setup
    arm(config, engine)
    broker.ambiguous = True
    request = intent()
    with pytest.raises(BrokerError, match="submission_outcome_unconfirmed") as error:
        engine.submit(request, quote())
    assert "private" not in str(error.value)
    with pytest.raises(BrokerError, match="reconciliation_required"):
        engine.submit(
            request.model_copy(update={"client_id": "alta-" + "b" * 32}), quote()
        )
    assert engine.submit(request, quote()).state == "filled"
    assert broker.calls == 1


def test_unknown_not_found_is_not_retry_permission(setup):
    config, broker, engine = setup
    arm(config, engine)
    request = intent()
    engine.ledger.prepare(config, request)  # crash immediately before/after POST
    with pytest.raises(BrokerError, match="reconciliation_unconfirmed"):
        engine.submit(request, quote())
    assert broker.calls == 0
    assert engine.state()["pending_count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"observed_at": now() - timedelta(minutes=2)},
        {"observed_at": now() + timedelta(minutes=2)},
        {"realtime": False},
        {"symbol": "MSFT"},
        {"ask": Decimal("110")},
    ],
)
def test_stale_delayed_different_or_wide_quotes_never_submit(setup, change):
    config, broker, engine = setup
    arm(config, engine)
    with pytest.raises(BrokerError):
        engine.submit(intent(), quote(**change))
    assert broker.calls == 0


def test_position_drift_and_client_identity_are_fail_closed(setup):
    config, broker, engine = setup
    arm(config, engine)
    request = intent()
    engine.submit(request, quote())
    with pytest.raises(BrokerError, match="client_id_conflict"):
        engine.submit(request.model_copy(update={"quantity": Decimal(11)}), quote())
    broker.positions = ()
    with pytest.raises(BrokerError, match="position_drift"):
        engine.reconcile()
    assert broker.calls == 1


def test_partial_cancel_reconciles_before_terminal(setup):
    config, broker, engine = setup
    arm(config, engine)
    broker.working = True
    request = intent()
    engine.submit(request, quote())
    assert engine.revoke()["authority"] == "close_only"
    result = engine.cancel(request.client_id)
    assert result.state == "cancelled"
    assert engine.reconcile()["authority"] == "off"


def test_revision_change_invalidates_authority_and_single_owner(setup):
    config, broker, engine = setup
    arm(config, engine)
    altered = config.model_copy(update={"max_order_notional": Decimal("20000")})
    other = BrokerEngine(altered, broker, engine.directory)
    try:
        with pytest.raises(BrokerError, match="authority_invalidated"):
            other.submit(intent(), quote())
        with owner(engine.directory / "mutation.lock"):
            with pytest.raises(BrokerError, match="operation_in_progress"):
                engine.submit(intent(), quote())
    finally:
        other.close()


def test_private_profile_permissions_revision_symlink_and_project_boundary(tmp_path):
    profiles = Profiles(tmp_path / "private", tmp_path / "state", tmp_path / "project")
    config = profile()
    profiles.save(config, "new")
    assert profiles.file("alpaca").stat().st_mode & 0o777 == 0o600
    assert profiles.load("alpaca").revision == config.revision
    with pytest.raises(BrokerError, match="profile_conflict"):
        profiles.save(config, "new")
    with pytest.raises(BrokerError, match="inside_project"):
        Profiles(tmp_path / "project/private", tmp_path / "state", tmp_path / "project")
    link = tmp_path / "link.json"
    link.symlink_to(profiles.file("alpaca"))
    with pytest.raises(OSError):
        read_private(link)
    with pytest.raises(BrokerError, match="symlink"):
        atomic_private(link, {})


def test_private_state_rejects_fifos_and_hardlinked_ledger(tmp_path):
    import os

    root = tmp_path / "account"
    root.mkdir(mode=0o700)
    fifo = root / "pipe"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(BrokerError, match="private_file_permissions"):
        read_private(fifo)
    with pytest.raises(BrokerError, match="owner_lock_permissions"):
        with owner(fifo):
            pytest.fail("must reject FIFO")
    source = root / "other"
    source.touch(mode=0o600)
    os.link(source, root / "ledger.sqlite3")
    with pytest.raises(BrokerError, match="ledger_permissions"):
        Ledger(root)


def test_live_profile_is_explicit_but_no_network_or_live_orders(setup):
    _, broker, engine = setup
    live = profile(environment="LIVE")
    assert live.binding != engine.profile.binding
    assert live.environment == "LIVE"
    with pytest.raises(ValueError):
        profile("schwab", "PAPER")
    assert broker.calls == 0
