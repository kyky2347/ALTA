"""Offline lifecycle acceptance: injected ports, no credentials or network."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from alta_brokers.contracts import BrokerError, Order, Position, now
from alta_brokers.engine import BrokerEngine
from alta_brokers.lifecycle import ApprovedPlan, ExecutionLifecycle
from test_engine import Broker, arm, intent, profile, quote


class BookBroker(Broker):
    def __init__(self, config):
        super().__init__(config)
        self.receipts = {}
        self.quantity = Decimal(0)
        self.lose_ack = False

    def submit(self, request, *, acknowledge=None):
        self.calls += 1
        self.quantity += request.quantity * (1 if request.side == "BUY" else -1)
        self.positions = (
            (
                Position(
                    symbol="AAPL",
                    quantity=self.quantity,
                    market_value=self.quantity * 100,
                    currency="USD",
                ),
            )
            if self.quantity
            else ()
        )
        result = Order(
            order_id=f"receipt-{self.calls}",
            client_id=request.client_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=request.quantity,
            limit_price=request.limit_price,
            average_price=request.limit_price,
            state="filled",
        )
        self.receipts[request.client_id] = result
        acknowledge(result.order_id)
        if self.lose_ack:
            raise TimeoutError("private provider response")
        return result

    def lookup(self, client_id, order_id):
        return self.receipts.get(client_id)


def plan(config):
    return ApprovedPlan(
        plan_id="plan-" + "b" * 32,
        binding=config.binding,
        revision=config.revision,
        audit_id="independent-audit",
        audited_at=now(),
        entry=intent(),
        exit_at=now() + timedelta(days=30),
        stop_price="90",
        target_price="110",
    )


@pytest.fixture
def context(tmp_path):
    config = profile(environment="LIVE")
    broker = BookBroker(config)
    engine = BrokerEngine(config, broker, tmp_path)
    arm(config, engine)
    feed = SimpleNamespace(value=quote())
    quotes = SimpleNamespace(quote=lambda symbol: feed.value)
    audit = SimpleNamespace(verify=lambda value: True)
    worker = ExecutionLifecycle(engine, audit, quotes)
    yield config, broker, engine, worker, feed, audit, quotes
    engine.close()


def test_open_monitor_restart_target_exit_and_reauthorize(context):
    config, broker, engine, worker, feed, audit, quotes = context
    request = plan(config)
    assert worker.stage(request)["state"] == "staged"
    assert broker.calls == 0
    assert worker.tick(request.plan_id)["state"] == "monitoring"
    restarted = ExecutionLifecycle(engine, audit, quotes)
    assert restarted.stage(request)["state"] == "monitoring"
    assert restarted.tick(request.plan_id)["state"] == "monitoring"
    assert broker.calls == 1
    feed.value = quote(bid=Decimal("111"), ask=Decimal("111.01"))
    assert restarted.tick(request.plan_id)["state"] == "closed"
    assert restarted.tick(request.plan_id)["state"] == "closed"
    assert broker.calls == 2 and broker.quantity == 0
    assert engine.revoke()["authority"] == "off"
    arm(config, engine)
    assert engine.state()["authority"] == "entries"
    assert engine.state()["authorization_review"]["checks"]["clear_ledger"]
    assert engine.state()["verification"]["fresh"]


def test_revoked_unsubmitted_plan_cannot_resurrect_on_reauthorization(context):
    config, broker, engine, worker, *_ = context
    request = plan(config)
    worker.stage(request)
    assert engine.revoke()["authority"] == "off"
    arm(config, engine)
    assert worker.tick(request.plan_id)["state"] == "expired"
    assert broker.calls == 0


def test_unknown_exit_after_broker_fill_recovers_without_second_sell(context):
    config, broker, engine, worker, feed, audit, quotes = context
    request = plan(config)
    worker.stage(request)
    worker.tick(request.plan_id)
    feed.value = quote(bid=Decimal("89"), ask=Decimal("89.01"))
    broker.lose_ack = True
    with pytest.raises(BrokerError, match="submission_outcome_unconfirmed"):
        worker.tick(request.plan_id)
    assert broker.calls == 2 and broker.quantity == 0
    reopened = BrokerEngine(config, broker, engine.directory)
    try:
        restarted = ExecutionLifecycle(reopened, audit, quotes)
        assert restarted.tick(request.plan_id)["state"] == "closed"
        assert broker.calls == 2
    finally:
        reopened.close()


def test_stale_quote_cannot_open_or_close_and_does_not_lose_plan(context):
    config, broker, engine, worker, feed, _, _ = context
    request = plan(config)
    worker.stage(request)
    feed.value = quote(observed_at=now() - timedelta(minutes=1))
    with pytest.raises(BrokerError, match="stale_or_delayed"):
        worker.tick(request.plan_id)
    assert broker.calls == 0
    feed.value = quote()
    worker.tick(request.plan_id)
    engine.revoke()
    feed.value = quote(observed_at=now() - timedelta(minutes=1))
    with pytest.raises(BrokerError, match="stale_or_delayed"):
        worker.tick(request.plan_id)
    assert broker.calls == 1 and worker.state(request.plan_id)["state"] == "monitoring"
    feed.value = quote()
    assert worker.tick(request.plan_id)["state"] == "closed"
    assert engine.state()["authority"] == "off"


def test_revoked_staged_plan_never_opens(context):
    config, broker, engine, worker, _, _, _ = context
    request = plan(config)
    worker.stage(request)
    engine.revoke()
    assert worker.tick(request.plan_id)["state"] == "expired"
    assert broker.calls == 0


def test_independent_audit_must_still_pass_immediately_before_entry(context):
    config, broker, _, worker, _, audit, _ = context
    request = plan(config)
    worker.stage(request)
    audit.verify = lambda value: False
    with pytest.raises(BrokerError, match="audit_not_proven"):
        worker.tick(request.plan_id)
    assert broker.calls == 0


def test_account_revision_and_frozen_plan_terms_cannot_change(context):
    config, broker, _, worker, _, _, _ = context
    request = plan(config)
    worker.stage(request)
    with pytest.raises(BrokerError, match="identity_conflict"):
        worker.stage(request.model_copy(update={"target_price": Decimal("120")}))
    with pytest.raises(BrokerError, match="revision_mismatch"):
        worker.stage(request.model_copy(update={"revision": "0" * 64}))
    assert broker.calls == 0


def test_active_plan_prevents_competing_capital_reservations(context):
    config, broker, _, worker, _, _, _ = context
    request = plan(config)
    worker.stage(request)
    other = request.model_copy(
        update={
            "plan_id": "plan-" + "c" * 32,
            "entry": request.entry.model_copy(update={"client_id": "alta-" + "d" * 32}),
        }
    )
    with pytest.raises(BrokerError, match="requires_monitoring"):
        worker.stage(other)
    assert broker.calls == 0


def test_profitable_exit_is_not_stranded_above_the_entry_notional_limit(tmp_path):
    config = profile(environment="LIVE").model_copy(
        update={"max_order_notional": Decimal("1000")}
    )
    broker = BookBroker(config)
    engine = BrokerEngine(config, broker, tmp_path)
    feed = SimpleNamespace(value=quote())
    worker = ExecutionLifecycle(
        engine,
        SimpleNamespace(verify=lambda _: True),
        SimpleNamespace(quote=lambda _: feed.value),
    )
    try:
        arm(config, engine)
        request = plan(config)
        worker.stage(request)
        worker.tick(request.plan_id)
        feed.value = quote(bid=Decimal("111"), ask=Decimal("111.01"))
        assert worker.tick(request.plan_id)["state"] == "closed"
        assert broker.calls == 2 and broker.quantity == 0
    finally:
        engine.close()


def test_broker_position_disagreement_prevents_false_closed_result(context):
    config, broker, _, worker, feed, _, _ = context
    request = plan(config)
    worker.stage(request)
    worker.tick(request.plan_id)
    original = broker.submit

    def disagree(intent, *, acknowledge=None):
        result = original(intent, acknowledge=acknowledge)
        broker.positions = (
            Position(symbol="AAPL", quantity=1, market_value=100, currency="USD"),
        )
        return result

    broker.submit = disagree
    feed.value = quote(bid=Decimal("111"), ask=Decimal("111.01"))
    with pytest.raises(BrokerError, match="position_drift"):
        worker.tick(request.plan_id)
    assert worker.state(request.plan_id)["state"] != "closed"
    assert broker.calls == 2
