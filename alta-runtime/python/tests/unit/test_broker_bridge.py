"""Trusted handoff, using injected storage/transport; never connects a broker."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from alta_asterism.agentic_roles import canonical_hash
from alta_asterism.broker_bridge import BrokerResearchBridge
from alta_asterism.broker_handoff import prepare_handoff
from alta_asterism.broker_process import BrokerExecutionError


class EvidenceDatabase:
    def __init__(self, proposal, route):
        self.route = dict(route)
        self.expression = {"binding": "test-expression"}
        self.instrument = {"symbol": "AAPL", "kind": "stock", "quantity": "10"}
        self.audit = {
            "output": {
                "decision": "approve",
                "selected_hypothesis_id": "hypothesis-test",
            }
        }
        self.proposal = proposal
        self.audited_at = proposal.decision_known_at
        self.hash = canonical_hash(self.audit)
        self.opportunity = "opportunity-test"
        self.fences = 0
        self.external_active = False

    @contextmanager
    def connect(self):
        yield self

    def execute(self, sql, _parameters=()):
        assert "UPDATE" not in sql and "DELETE" not in sql
        if "ops.event" in sql:
            return NS(fetchone=lambda: ({"expression": self.expression},))
        return NS(
            fetchall=lambda: [
                (
                    "auditor-test-run",
                    {
                        "opportunity": {"opportunity_id": self.opportunity},
                        "broker_execution": self.route,
                        "broker_opportunity_binding": {
                            "version": 1,
                            "snapshot_hash": "e" * 64,
                        },
                        "proposed_expression": {
                            "expression_slate": [
                                {
                                    "hypothesis": {"hypothesis_id": "hypothesis-test"},
                                    "instrument": self.instrument,
                                }
                            ]
                        },
                    },
                    self.audit,
                    self.hash,
                    self.audited_at,
                )
            ]
        )

    def assert_autonomous_fence(self):
        self.fences += 1

    @contextmanager
    def autonomous_external_operation(self):
        assert not self.external_active
        self.external_active = True
        try:
            yield
        finally:
            self.external_active = False


@pytest.fixture
def handoff():
    instant = datetime.now(UTC) - timedelta(seconds=1)
    proposal = NS(
        kind="stock",
        side="long",
        quantity=Decimal("10"),
        symbol="AAPL",
        expression_id="expression-test",
        binding=NS(
            opportunity_id="opportunity-test",
            opportunity_version=1,
            opportunity_snapshot_hash="e" * 64,
        ),
        decision_known_at=instant,
        rationale=json.dumps({"selected_hypothesis_id": "hypothesis-test"}),
        hash=lambda: canonical_hash({"binding": "test-expression"}),
        implementation_plan=NS(
            status="ready",
            gross_replacement_credit=0,
            loss_budget=Decimal("20"),
            estimated_stress_loss=Decimal("20"),
            expected_net_alpha_bps=Decimal("300"),
            execution_plan=NS(status="ready", entry_limit_price=Decimal("100.00")),
            alpha_clock=NS(known_at=instant, remaining_seconds=86400),
        ),
    )
    route = {
        "provider": "alpaca",
        "environment": "LIVE",
        "binding": "b" * 64,
        "profile_revision": "c" * 64,
        "revision": "d" * 64,
    }
    return EvidenceDatabase(proposal, route), route, proposal


def test_handoff_matches_isolated_broker_contract_without_size_inflation(
    handoff, monkeypatch
):
    database, route, proposal = handoff
    # Import only the adjacent pure contracts, not SDKs or a live connection.
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[3] / "broker-python/src")
    )
    from alta_brokers.lifecycle import ApprovedPlan
    from alta_brokers.research_rpc import plan_hash

    plan, receipt = prepare_handoff(database, route, "cycle-test", proposal)
    assert receipt["plan_hash"] == plan_hash(ApprovedPlan.model_validate(plan))
    assert plan["entry"]["quantity"] == "10"
    assert plan["stop_price"] == "98.00"
    assert plan["target_price"] == "103.00"
    assert prepare_handoff(database, route, "cycle-test", proposal) == (plan, receipt)


def test_unused_portfolio_risk_capacity_does_not_make_a_negative_stop(handoff):
    database, route, proposal = handoff
    proposal.implementation_plan.loss_budget = Decimal("2500")
    plan, _ = prepare_handoff(database, route, "cycle-test", proposal)
    assert plan["stop_price"] == "98.00"


@pytest.mark.parametrize(
    "fault",
    [
        "expression",
        "artifact",
        "opportunity",
        "symbol",
        "quantity",
        "wait",
        "expired",
        "option",
        "broker",
        "environment",
        "version",
        "snapshot",
        "stale_audit",
        "future_audit",
    ],
)
def test_handoff_requires_exact_independent_durable_fresh_audit(handoff, fault):
    database, route, proposal = handoff
    if fault == "expression":
        database.expression = {}
    elif fault == "artifact":
        database.hash = "0" * 64
    elif fault == "opportunity":
        database.opportunity = "other-opportunity"
    elif fault == "symbol":
        database.instrument["symbol"] = "MSFT"
    elif fault == "quantity":
        database.instrument["quantity"] = "9"
    elif fault == "wait":
        database.audit["output"]["decision"] = "wait"
    elif fault == "expired":
        proposal.decision_known_at -= timedelta(minutes=10)
    elif fault == "broker":
        database.route["provider"] = "tiger"
    elif fault == "environment":
        database.route["environment"] = "PAPER"
    elif fault == "version":
        proposal.binding.opportunity_version = 2
    elif fault == "snapshot":
        proposal.binding.opportunity_snapshot_hash = "f" * 64
    elif fault == "stale_audit":
        database.audited_at -= timedelta(minutes=10)
    elif fault == "future_audit":
        database.audited_at += timedelta(seconds=30)
    else:
        proposal.kind = "option"
    with pytest.raises(BrokerExecutionError):
        prepare_handoff(database, route, "cycle-test", proposal)


def test_monitor_shutdown_between_quote_read_and_dispatch_never_submits(handoff):
    database, route, _ = handoff
    requests = []

    class Process:
        def request(self, value, **_kwargs):
            requests.append(value)
            return {
                "plans": [
                    {"plan_id": "plan-test", "symbol": "AAPL", "state": "monitoring"}
                ]
            }

    class Market:
        def equity(self, *_args):
            bridge.stop.set()
            return NS(instrument=NS(quote=NS(as_of=datetime.now(UTC))))

    bridge = BrokerResearchBridge(database, Process(), route, Market())
    assert bridge.monitor_once() == ()
    assert [r["action"] for r in requests] == ["active"]
    assert (
        requests[0]["provider"] == "alpaca"
        and requests[0]["route_revision"] == route["revision"]
    )


def test_stale_market_data_blocks_dispatch_without_falling_back(handoff):
    database, route, _ = handoff

    class Process:
        def request(self, value, **_kwargs):
            if value["action"] == "active":
                return {
                    "plans": [
                        {
                            "plan_id": "plan-test",
                            "symbol": "AAPL",
                            "state": "monitoring",
                        }
                    ]
                }
            assert value["action"] == "tick" and value["quote"] is None
            assert database.external_active
            raise BrokerExecutionError("broker_trusted_quote_unavailable")

    market = NS(
        equity=lambda *_: NS(
            instrument=NS(quote=NS(as_of=datetime.now(UTC) - timedelta(seconds=60)))
        )
    )
    bridge = BrokerResearchBridge(database, Process(), route, market)
    events = []
    bridge._record = lambda *args: events.append(args)
    assert bridge.monitor_once() == ("plan-test",)
    assert events[0][1] == {
        "state": "blocked",
        "reason": "broker_trusted_quote_unavailable",
    }
