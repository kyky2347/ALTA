"""Selected-provider contracts; every transport is injected, no live orders."""

import pytest

from alta_brokers.__main__ import handle
from alta_brokers.contracts import BrokerError
from alta_brokers.research_rpc import handle_research, plan_hash
from alta_brokers.routing import ExecutionRoute
from alta_brokers.storage import Profiles, owner
from test_engine import profile, quote
from test_lifecycle import BookBroker, plan


@pytest.fixture
def setup(tmp_path, monkeypatch):
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    brokers = {}
    for provider in ("tiger", "alpaca", "ibkr", "futu", "longport", "schwab"):
        config = profile(provider, "LIVE")
        profiles.save(config, "new")
        brokers[provider] = BookBroker(config)

    def connect(config):
        return brokers[config.provider]

    monkeypatch.setattr("alta_brokers.__main__.connect", connect)
    monkeypatch.setattr("alta_brokers.research_rpc.connect", connect)
    return profiles, brokers


@pytest.mark.parametrize(
    "provider", ["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"]
)
def test_selected_provider_authorization_and_restart_execution_only_uses_its_adapter(
    setup, provider
):
    profiles, brokers = setup
    config = profiles.load(provider)
    route = ExecutionRoute(profiles)
    selected = handle(
        {
            "action": "select",
            "provider": provider,
            "revision": route.state()["revision"],
            "profile_revision": config.revision,
        },
        profiles,
    )
    assert (
        selected["environment"] == "LIVE"
        and sum(b.calls for b in brokers.values()) == 0
    )
    assert (
        handle({"action": "state", "provider": provider}, profiles)["authority"]
        == "off"
    )
    handle(
        {
            "action": "authorize",
            "provider": provider,
            "revision": config.revision,
            "confirmation": f"ENABLE LIVE {config.binding[-8:]}",
        },
        profiles,
    )
    request = plan(config)
    context = {
        "provider": provider,
        "revision": config.revision,
        "route_revision": selected["revision"],
    }
    receipt = {
        "audit_id": request.audit_id,
        "plan_hash": plan_hash(request),
        "expression_hash": "1" * 64,
        "artifact_hash": "2" * 64,
    }
    assert (
        handle_research(
            {
                **context,
                "action": "stage",
                "plan": request.model_dump(mode="json"),
                "receipt": receipt,
            },
            profiles,
        )["state"]
        == "staged"
    )
    result = handle_research(
        {
            **context,
            "action": "tick",
            "plan_id": request.plan_id,
            "quote": quote().model_dump(mode="json"),
        },
        profiles,
    )
    assert result["state"] == "monitoring"
    assert brokers[provider].calls == 1
    assert sum(b.calls for b in brokers.values()) == 1
    with pytest.raises(BrokerError, match="revoke_before_broker_switch"):
        route.select(None, selected["revision"], None)
    state = handle(
        {"action": "revoke", "provider": provider, "revision": config.revision},
        profiles,
    )
    assert state["authority"] == "close_only"
    with pytest.raises(BrokerError, match="revoke_before_broker_switch"):
        route.select(None, selected["revision"], None)
    # A new RPC process / engine uses the same ledger and closes only the owned
    # filled quantity. Repeated polls do not produce a third POST.
    for _ in range(2):
        result = handle_research(
            {
                **context,
                "action": "tick",
                "plan_id": request.plan_id,
                "quote": quote().model_dump(mode="json"),
            },
            profiles,
        )
        assert result["state"] == "closed"
    assert brokers[provider].calls == 2
    assert sum(b.calls for b in brokers.values()) == 2
    assert route.select(None, selected["revision"], None)["provider"] is None


def test_wrong_provider_stale_revision_and_browser_plan_are_rejected(setup):
    profiles, _ = setup
    route = ExecutionRoute(profiles)
    alpaca = profiles.load("alpaca")
    selected = route.select("alpaca", route.state()["revision"], alpaca.revision)
    with pytest.raises(BrokerError, match="conflict"):
        route.select(None, "stale", None)
    with pytest.raises(BrokerError, match="not_selected"):
        config = profiles.load("tiger")
        handle(
            {
                "action": "authorize",
                "provider": "tiger",
                "revision": config.revision,
                "confirmation": f"ENABLE LIVE {config.binding[-8:]}",
            },
            profiles,
        )
    with pytest.raises(BrokerError, match="action_unavailable"):
        handle({"action": "stage", "plan": {}}, profiles)
    with pytest.raises(BrokerError, match="deselect_before"):
        profiles.save(alpaca, alpaca.revision)
    with owner(route.lock), pytest.raises(BrokerError, match="in_progress"):
        handle(
            {
                "action": "authorize",
                "provider": "alpaca",
                "revision": alpaca.revision,
                "confirmation": f"ENABLE LIVE {alpaca.binding[-8:]}",
            },
            profiles,
        )
    assert selected["provider"] == "alpaca"


def test_unverified_real_account_cannot_be_armed_even_with_correct_confirmation(setup):
    profiles, brokers = setup
    config = profiles.load("alpaca")
    route = ExecutionRoute(profiles)
    route.select("alpaca", route.state()["revision"], config.revision)
    brokers["alpaca"].verified = False
    with pytest.raises(BrokerError, match="identity_unverified"):
        handle(
            {
                "action": "authorize",
                "provider": "alpaca",
                "revision": config.revision,
                "confirmation": f"ENABLE LIVE {config.binding[-8:]}",
            },
            profiles,
        )
    assert sum(b.calls for b in brokers.values()) == 0
    assert (
        handle({"action": "state", "provider": "alpaca"}, profiles)["authority"]
        == "off"
    )
