"""No credentials, external sessions or orders are used by these checks."""

from datetime import timedelta
from secrets import token_hex

import pytest

from alta_brokers.__main__ import handle
from alta_brokers.contracts import BrokerError, now
from alta_brokers.storage import Profiles, atomic_private, read_private
from alta_brokers.verification import Verification
from test_engine import Broker, BrokerEngine, arm, intent, profile, quote


def test_connection_evidence_persists_and_failure_invalidates_previous_success(
    tmp_path,
):
    config = profile()
    evidence = Verification(config, tmp_path)
    evidence.save(Broker(config).snapshot())
    assert evidence.state()["fresh"]
    changed = config.model_copy(update={"max_quote_age_seconds": 9})
    assert Verification(changed, tmp_path).state()["status"] == "configuration_changed"
    evidence.failed()
    assert evidence.state() == {"status": "failed", "fresh": False, "snapshot": None}


def test_old_proof_remains_visible_but_is_not_authorization(tmp_path, monkeypatch):
    config = profile()
    engine = BrokerEngine(config, Broker(config), tmp_path)
    try:
        response = engine.verify()
        assert response["authorization_review"]["checks"]["fresh_account"]
        assert not response["authorization_review"]["eligible"]
        monkeypatch.setattr(
            "alta_brokers.verification.now", lambda: now() + timedelta(minutes=2)
        )
        stale = engine.state()
        assert stale["verification"]["status"] == "stale"
        assert stale["verification"]["snapshot"]
        assert not stale["authorization_review"]["checks"]["fresh_account"]
    finally:
        engine.close()


def test_mismatched_response_is_not_cached_as_verified(tmp_path):
    config = profile()
    evidence = Verification(config, tmp_path)
    snapshot = Broker(config).snapshot().model_copy(update={"environment": "LIVE"})
    with pytest.raises(BrokerError, match="mismatch"):
        evidence.save(snapshot)
    assert evidence.state()["status"] == "not_checked"


@pytest.mark.parametrize("record", [[], None, "broken", {"status": "invented"}])
def test_malformed_cache_is_unavailable_not_a_crashed_settings_page(tmp_path, record):
    config = profile()
    evidence = Verification(config, tmp_path)
    atomic_private(evidence.path, record)
    assert evidence.state()["fresh"] is False
    assert evidence.state()["snapshot"] is None


def test_state_rpc_never_connects_and_failed_connect_invalidates_cached_proof(
    tmp_path, monkeypatch
):
    config = profile()
    profiles = Profiles(tmp_path / "private", tmp_path / "state", tmp_path / "project")
    profiles.save(config, "new")
    evidence = Verification(config, profiles.account_dir(config))
    evidence.save(Broker(config).snapshot())

    def fail(_):
        raise BrokerError("broker_authentication_required")

    monkeypatch.setattr("alta_brokers.__main__.connect", fail)
    state = handle({"action": "state", "provider": "alpaca"}, profiles)
    assert state["verification"]["fresh"]
    with pytest.raises(BrokerError, match="authentication"):
        handle({"action": "verify", "provider": "alpaca"}, profiles)
    assert evidence.state()["status"] == "failed"


def test_receipt_survives_detail_timeout_and_restart_without_reposting(tmp_path):
    config = profile()
    broker = Broker(config)
    broker.working = True
    original = broker.submit
    seen = []

    def submit(request, *, acknowledge=None):
        result = original(request)
        acknowledge(result.order_id)
        raise TimeoutError(token_hex(20))

    def lookup(client_id, order_id):
        seen.append(order_id)
        assert order_id == "test-order"
        return broker.result

    broker.submit = submit
    broker.lookup = lookup
    engine = BrokerEngine(config, broker, tmp_path)
    arm(config, engine)
    request = intent()
    with pytest.raises(BrokerError, match="submission_outcome_unconfirmed"):
        engine.submit(request, quote())
    assert "test-order" in engine.ledger.get(intent().client_id)["result"]
    engine.close()
    reopened = BrokerEngine(config, broker, tmp_path)
    try:
        assert reopened.submit(request, quote()).state == "working"
        assert seen == ["test-order"] and broker.calls == 1
    finally:
        reopened.close()


def test_acknowledgment_does_not_allow_an_unrelated_final_order(tmp_path):
    config = profile()
    broker = Broker(config)
    original = broker.submit

    def submit(request, *, acknowledge=None):
        acknowledge("accepted-order")
        return original(request)

    broker.submit = submit
    engine = BrokerEngine(config, broker, tmp_path)
    try:
        arm(config, engine)
        with pytest.raises(BrokerError, match="submission_outcome_unconfirmed"):
            engine.submit(intent(), quote())
        assert "accepted-order" in engine.ledger.get(intent().client_id)["result"]
        assert engine.state()["pending_count"] == 1
        assert read_private(engine.authority_path)["mode"] == "entries"
    finally:
        engine.close()
