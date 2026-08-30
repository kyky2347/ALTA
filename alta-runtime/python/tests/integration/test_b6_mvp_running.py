import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import replace
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.alpha_feedback import AlphaFeedbackProjector
from alta_asterism.agentic_deliberation import AgenticDeliberator
from alta_asterism.agentic_expression import AgenticExpressionFlow
from alta_asterism.agentic_roles import StructuredRoleRunner
from alta_asterism.autonomous import AutonomousRunner
from alta_asterism.b5_runtime import _append_event, _contract_event
from alta_asterism.contracts import Environment, Event, Settings
from alta_asterism.database import Database
from alta_asterism.expression import (
    ExpressionPolicy,
    ExpressionProposal,
    QuoteSnapshot,
    contract_hash,
    validate_expression,
)
from alta_asterism.market_data import InstrumentSelection, MarketInstrument
from alta_asterism.mind_worker import ModelTurn, ToolEvidenceDiscovery
from alta_asterism.mvp_demo import run_market_session_soak
from alta_asterism.mvp_fixture import FixtureMindClient, MvpFixture
from alta_asterism.mvp_orchestrator import MvpFaultInjected, MvpOrchestrator
from alta_asterism.mvp_research_flow import ResearchRuntimeConfig
from alta_asterism.mvp_shadow_flow import MvpShadowFlow
from alta_asterism.ranking import RankingBook, RankingGate
from alta_asterism.live_source_flow import DatabaseSourceFlow
from alta_asterism.scout_repository import ScoutRepository
from alta_asterism.scouts import ToolProvenance


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_b6_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b6_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b6_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def orchestrator(database: Database, *timed_out_scouts: str):
    fixture = MvpFixture.default()
    client = FixtureMindClient(fixture, tuple(timed_out_scouts))
    return MvpOrchestrator(database, fixture, client), client


class HybridAgentClient:
    def __init__(
        self,
        fixture: MvpFixture,
        *,
        audit_decision: str = "approve",
        expression_hypotheses: list[dict] | None = None,
        audit_selection: str | None = None,
    ) -> None:
        self.scouts = FixtureMindClient(fixture)
        self.role_calls: list[str] = []
        self.audit_decision = audit_decision
        self.expression_hypotheses = expression_hypotheses
        self.audit_selection = audit_selection

    def run(self, spec, prompt: str, schema: dict) -> ModelTurn:
        if hasattr(spec, "frozen_input"):
            turn = self.scouts.run(spec, prompt, schema)
            payload = json.loads(turn.final_response)
            if payload.get("kind") != "candidate":
                return turn
            payload.update(
                {
                    "beneficiary_path": "The measured change reaches issuer revenue.",
                    "disconfirming_evidence": "The next primary update may reverse the change.",
                    "next_test": "Verify the next issuer operating update.",
                }
            )
            tools = tuple(
                ToolProvenance(
                    tool_call_id=f"fixture_tool_{index}",
                    tool_name=tool_name,
                    status="completed",
                    arguments_hash=character * 64,
                )
                for index, (tool_name, character) in enumerate(
                    (
                        ("alta_web_search", "a"),
                        ("alta_finance_data", "b"),
                        ("alta_news_search", "c"),
                    ),
                    start=1,
                )
            )
            discoveries = tuple(
                ToolEvidenceDiscovery(
                    tool_call_id=tools[index].tool_call_id,
                    tool_name=tools[index].tool_name,
                    source_locator=f"https://source{index + 1}.example/research",
                    content={
                        "fixture": index + 1,
                        "result_text": f"Fixture research result {index + 1}.",
                    },
                    content_hash=character * 64,
                )
                for index, character in enumerate(("d", "e", "f"))
            )
            payload["tool_evidence_refs"] = [
                {
                    "tool_call_id": discovery.tool_call_id,
                    "source_locator": discovery.source_locator,
                }
                for discovery in discoveries
            ]
            return replace(
                turn,
                final_response=json.dumps(payload, separators=(",", ":")),
                tools=tools,
                discovered_evidence=discoveries,
            )
        role = spec.scout.scout_id
        self.role_calls.append(role)
        frozen = json.loads(prompt)["untrusted_frozen_input"]
        if role in {"thesis_assessor", "disconfirming_assessor"}:
            evidence_ids = frozen["opportunity"]["evidence_ids"]
            payload = {
                "forecast_probability": (0.68 if role == "thesis_assessor" else 0.62),
                "evidence_quality": 0.7,
                "variant_wedge_quality": 0.64,
                "strongest_support": "The frozen evidence supports the mechanism.",
                "strongest_disconfirmation": "The effect may already be priced.",
                "first_rejection": "Reject on the frozen falsifier.",
                "missing_evidence": ["next primary update"],
                "recommendation": ("advance" if role == "thesis_assessor" else "wait"),
                "confidence": 0.61,
                "evidence_ids": evidence_ids,
                "rationale": "Independent fixture role reasoning.",
                "underwriting": {
                    "benchmark_symbol": "SPY",
                    "bull": {
                        "probability": 0.2,
                        "relative_alpha_bps": 750,
                        "trigger": "The catalyst propagates faster than expected.",
                        "evidence_ids": evidence_ids,
                    },
                    "base": {
                        "probability": (0.48 if role == "thesis_assessor" else 0.42),
                        "relative_alpha_bps": 180,
                        "trigger": "The mechanism partially reaches the prediction.",
                        "evidence_ids": evidence_ids,
                    },
                    "bear": {
                        "probability": (0.32 if role == "thesis_assessor" else 0.38),
                        "relative_alpha_bps": -200,
                        "trigger": "The next update confirms the rejection condition.",
                        "evidence_ids": evidence_ids,
                    },
                    "catalyst_clarity": 0.65,
                    "crowding_risk": 0.3,
                    "liquidity_risk": 0.2,
                    "next_pricing_fact": "The next primary operating update.",
                    "decision": {
                        "what_is_priced_in": "A normal propagation path is priced in.",
                        "variant_view": "The frozen evidence supports a faster path.",
                        "reference_class": "Comparable expectation revisions.",
                        "base_rate_probability": 0.5,
                        "inside_view_probability": (
                            0.68 if role == "thesis_assessor" else 0.62
                        ),
                        "must_be_true": [
                            "The mechanism reaches the next measured prediction."
                        ],
                        "company_thesis_status": (
                            "intact" if role == "thesis_assessor" else "watch"
                        ),
                        "security_thesis_readiness": (
                            "ready" if role == "thesis_assessor" else "conditional"
                        ),
                        "edge_half_life_days": 20,
                        "dominant_uncertainty": "The speed of causal propagation.",
                        "action_trigger": "Re-underwrite at the next operating update.",
                    },
                },
            }
        elif role == "discussion_moderator":
            payload = {"rounds": []}
        elif role == "expression_agent":
            pillar_ids = [
                item["pillar_id"]
                for item in frozen["opportunity"].get("thesis_pillars", [])
            ]
            hypotheses = self.expression_hypotheses or [
                {
                    "hypothesis_id": "issuer_stock",
                    "kind": "stock",
                    "symbol": "DEMO",
                    "payoff_thesis": "Upside follows if the catalyst propagates.",
                    "thesis_purity": 0.8,
                    "timing_fit": 0.7,
                    "primary_tradeoff": "Direct exposure retains market beta.",
                }
            ]
            hypotheses = [
                {
                    **item,
                    "alpha_source": item.get("alpha_source", "event"),
                    "systematic_exposures": item.get(
                        "systematic_exposures",
                        ["market_beta"] if item["kind"] != "wait" else ["unknown"],
                    ),
                    "hedge_posture": item.get(
                        "hedge_posture",
                        "unhedged_intentional"
                        if item["kind"] != "wait"
                        else "not_applicable",
                    ),
                    "basis_risk": item.get(
                        "basis_risk",
                        "Broad market beta can overwhelm the fixture event payoff.",
                    ),
                    "thesis_pillar_ids": (
                        item.get("thesis_pillar_ids", pillar_ids[:1])
                        if item["kind"] != "wait"
                        else []
                    ),
                }
                for item in hypotheses
            ]
            payload = {
                "preferred_kind": "stock",
                "symbol": "DEMO",
                "rationale": "Direct exposure best matches the causal thesis.",
                "payoff_thesis": "Upside follows if the catalyst propagates.",
                "invalidation": "Exit if the frozen falsifier triggers.",
                "required_market_data": ["trusted realtime bid/ask"],
                "hypotheses": hypotheses,
            }
        elif role == "expression_auditor":
            slate = frozen["proposed_expression"].get("expression_slate", [])
            unavailable = frozen["proposed_expression"][
                "selected_instrument"
            ] is None and not any(item.get("admissible") for item in slate)
            selected = next(
                (
                    item["hypothesis"]
                    for item in slate
                    if item["hypothesis"]["hypothesis_id"] == self.audit_selection
                ),
                {},
            )
            payload = {
                "decision": "wait" if unavailable else self.audit_decision,
                "selected_hypothesis_id": (
                    None if unavailable else self.audit_selection
                ),
                "thesis_alignment": 0.78,
                "implementation_quality": 0.72,
                "alpha_isolation_score": 0.82,
                "confirmed_systematic_exposures": selected.get(
                    "systematic_exposures", []
                ),
                "hedge_posture": selected.get("hedge_posture", "not_applicable"),
                "basis_risk": selected.get(
                    "basis_risk", "No approved expression is available."
                ),
                "exposure_disagreements": [],
                "largest_failure_mode": "The selected beta may dilute the catalyst.",
                "portfolio_conflicts": [],
                "monitoring_plan": ["Monitor the frozen falsifier."],
                "evidence_ids": frozen["opportunity"]["evidence_ids"],
                "rationale": "Independent fixture implementation audit.",
            }
        else:
            raise AssertionError(f"unexpected role {role}")
        call = len(self.role_calls)
        return ModelTurn(
            final_response=json.dumps(payload),
            thread_id=f"role_thread_{call}",
            turn_id=f"role_turn_{call}",
            total_tokens=300,
            tools=(),
            usage={"total_tokens": 300},
            latency_ms=5,
        )


def test_fixture_e2e_replay_is_stable_and_projects_every_mvp_stage(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    runtime, client = orchestrator(database)
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)

    first = runtime.run("b6-baseline", wake_at)
    replay = runtime.run("b6-baseline", wake_at)
    status = database.mvp_status()
    opportunity_detail = database.opportunity_detail(first.opportunity_ids[0], "shadow")

    assert (first.status, first.replayed, replay.replayed) == (
        "MVP_RUNNING",
        False,
        True,
    )
    assert first.replay_hash == replay.replay_hash
    assert client.calls == [
        "change_event_scout",
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
    ]
    assert first.source_postures["massive"] == "disabled"
    assert len(first.candidate_ids) == len(first.opportunity_ids) == 3
    assert status["status"] == "MVP_RUNNING"
    assert {item["role"] for item in status["runs"]}.issuperset(
        {
            "change_event_scout",
            "market_dislocation_scout",
            "causal_policy_scout",
            "expectation_gap_scout",
            "thesis_assessor",
            "disconfirming_assessor",
        }
    )
    assert {item["id"] for item in status["agents"]} == {
        "change_event_scout",
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
        "thesis_assessor",
        "disconfirming_assessor",
    }
    assert all(status[key] for key in ("candidates", "opportunities", "ranks"))
    assert status["expressions"][0]["status"] == "closed"
    assert status["shadowPositions"][0]["status"] == "closed"
    with database.connect() as connection:
        counts = connection.execute(
            """SELECT
            (SELECT count(*) FROM research.run),
            (SELECT count(*) FROM research.candidate),
            (SELECT count(*) FROM research.opportunity),
            (SELECT count(*) FROM research.assessment),
            (SELECT count(*) FROM research.rank),
            (SELECT count(*) FROM research.expression),
            (SELECT count(*) FROM research.shadow_position),
            (SELECT count(*) FROM ops.event
                WHERE event_type = 'shadow.ledger.posted')"""
        ).fetchone()
        stages = connection.execute(
            """SELECT payload->>'stage' FROM ops.event
            WHERE aggregate_id = 'b6-baseline'
            AND event_type = 'mvp.stage.completed' ORDER BY sequence"""
        ).fetchall()
        contributors = connection.execute(
            """SELECT position_thesis->'alpha_contributors'
            FROM research.shadow_position"""
        ).fetchone()[0]
        thesis_pillars = connection.execute(
            """SELECT position_thesis->'thesis_pillars'
            FROM research.shadow_position"""
        ).fetchone()[0]
    assert counts == (10, 3, 3, 6, 3, 1, 1, 2)
    assert [item[0] for item in stages] == [
        "schedule_wake",
        "scouts",
        "foundry",
        "private_assessment_debate",
        "ranking",
        "expression",
        "shadow_open",
        "monitor_exit",
    ]
    assert contributors
    assert contributors[0]["alpha_archetype"] != "legacy_unclassified"
    assert contributors[0]["research_mode"] == "explore"
    assert opportunity_detail is not None and opportunity_detail["thesisPillars"]
    assert opportunity_detail["thesisPillars"][0]["pillar_id"].startswith("pillar_")
    assert thesis_pillars and thesis_pillars[0]["pillar_id"].startswith("pillar_")
    cadence_runner = AutonomousRunner(
        database,
        Settings(
            DATABASE_URL=empty_b6_database,
            REDIS_URL="redis://127.0.0.1:1/0",
            ALTA_ENVIRONMENT="shadow",
        ),
    )
    assert cadence_runner._next_cycle_interval() == (1_800, "base_research")


def test_closed_shadow_alpha_feedback_is_point_in_time_and_maturity_gated(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)
    runtime, _ = orchestrator(database)
    result = runtime.run("b6-alpha-feedback", wake_at)
    measured_at = wake_at + timedelta(seconds=40)
    with database.connect() as connection:
        contributors = connection.execute(
            """SELECT position_thesis->'alpha_contributors'
            FROM research.shadow_position WHERE id = %s""",
            (result.shadow_position_id,),
        ).fetchone()[0]
        _append_event(
            connection,
            _contract_event(
                event_type="position.performance.measured",
                aggregate_type="shadow_position",
                aggregate_id=result.shadow_position_id,
                environment=Environment.SHADOW,
                known_at=measured_at,
                payload={
                    "position_id": result.shadow_position_id,
                    "opportunity_id": result.selected_opportunity_id,
                    "net_pnl": "10",
                    "net_return_bps": "100",
                    "realized_alpha_bps": "50",
                    "cost_adjusted": True,
                    "alpha_contributors": contributors,
                },
                correlation_id=result.selected_opportunity_id,
            ),
        )

    projector = AlphaFeedbackProjector(database)
    assert projector.at(Environment.SHADOW, measured_at) == ()
    projected = projector.at(
        Environment.SHADOW, measured_at + timedelta(microseconds=1)
    )
    assert projected
    assert all(item.mature is False for item in projected)
    assert all(item.mean_realized_alpha_bps is None for item in projected)
    assert all(item.research_modes[0].research_mode == "explore" for item in projected)

    frozen, _ = DatabaseSourceFlow(database, ("SPY",)).schedule_and_wake(
        "cycle_feedback_freeze", measured_at + timedelta(seconds=1), {}
    )
    assert frozen.alpha_feedback == projected
    scoped = frozen.for_scout(
        projected[0].scout_id,
        (),
    )
    assert scoped.research_incentives[0].state == "calibrating"
    assert scoped.research_incentives[0].bonus_tool_calls == 0
    ScoutRepository(database).validate_frozen_input(scoped)
    tampered = scoped.model_copy(
        update={
            "research_incentives": (
                scoped.research_incentives[0].model_copy(
                    update={"directive": "Invented research reward."}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="does not match outcomes"):
        ScoutRepository(database).validate_frozen_input(tampered)
    rejected, _ = orchestrator(database)
    with pytest.raises(ValueError, match="Massive remains disabled"):
        rejected.run(
            "b6-massive-rejected",
            wake_at,
            source_overrides={"massive": "healthy"},
        )


def test_expression_falls_back_to_next_ranked_actionable_opportunity(
    empty_b6_database: str,
) -> None:
    class FirstWaitShadowFlow(MvpShadowFlow):
        def __init__(self, database: Database, fixture: MvpFixture) -> None:
            super().__init__(database, fixture)
            self.attempted_opportunity_ids: list[str] = []

        def express(self, demo_id, opportunity, wake_at):
            self.attempted_opportunity_ids.append(opportunity.opportunity_id)
            if len(self.attempted_opportunity_ids) > 1:
                return super().express(demo_id, opportunity, wake_at)
            proposal = ExpressionProposal(
                expression_id=(
                    "expression_"
                    + contract_hash([demo_id, opportunity.opportunity_id, "wait"])[:32]
                ),
                binding=self.runtime.expressions.binding_for(
                    opportunity.opportunity_id
                ),
                kind="wait",
                rationale="Top-ranked fixture is not currently actionable.",
                decision_known_at=wake_at + timedelta(seconds=16),
            )
            self.runtime.expressions.persist(
                proposal, validate_expression(proposal, ExpressionPolicy())
            )
            return proposal

    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = FixtureMindClient(fixture)
    shadow = FirstWaitShadowFlow(database, fixture)
    runtime = MvpOrchestrator(database, fixture, client, shadow_flow=shadow)

    result = runtime.run(
        "b6-expression-fallback",
        datetime(2026, 8, 24, 13, 30, tzinfo=UTC),
    )

    assert result.shadow_position_id is not None
    assert result.top_opportunity_id == shadow.attempted_opportunity_ids[0]
    assert result.selected_opportunity_id == shadow.attempted_opportunity_ids[1]
    assert result.selected_opportunity_id != result.top_opportunity_id
    with database.connect() as connection:
        snapshot = connection.execute(
            """SELECT payload->'snapshot' FROM ops.event
            WHERE aggregate_id = %s AND event_type = 'mvp.pipeline.completed'""",
            (result.demo_id,),
        ).fetchone()[0]
    assert [item[2] for item in snapshot["expression_attempts"]] == [
        "wait",
        "stock",
    ]


def test_agentic_assessment_discussion_and_expression_recover_without_recall(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = HybridAgentClient(fixture)
    roles = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-agentic-model",
    )
    runtime = MvpOrchestrator(
        database,
        fixture,
        client,
        shadow_flow=AgenticExpressionFlow(database, roles, fixture.universe),
        research_config=ResearchRuntimeConfig(max_tool_calls=3),
        role_runner=roles,
    )
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)

    first = runtime.run("b6-agentic", wake_at)
    calls_after_first = tuple(client.role_calls)
    replay = runtime.run("b6-agentic", wake_at)

    assert first.shadow_position_id is None
    assert replay.replayed is True and replay.replay_hash == first.replay_hash
    assert tuple(client.role_calls) == calls_after_first
    assert client.role_calls.count("thesis_assessor") == 3
    assert client.role_calls.count("disconfirming_assessor") == 3
    assert client.role_calls.count("discussion_moderator") == 3
    assert client.role_calls.count("expression_agent") == 3
    assert client.role_calls.count("expression_auditor") == 3
    with database.connect() as connection:
        expression = connection.execute(
            """SELECT kind, status, rationale FROM research.expression
            WHERE id = %s""",
            (first.expression_id,),
        ).fetchone()
        role_runs = connection.execute(
            """SELECT count(*), count(*) FILTER (WHERE status = 'succeeded')
            FROM research.run WHERE output_kind = 'role_output'"""
        ).fetchone()
    assert expression[0:2] == ("wait", "validated")
    assert "trusted_realtime_quote_unavailable" in expression[2]
    assert role_runs == (15, 15)


def test_judgment_roles_persist_heterogeneous_model_routes(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = HybridAgentClient(fixture)

    def runner(provider: str, model: str) -> StructuredRoleRunner:
        return StructuredRoleRunner(
            database,
            client,
            model_provider=provider,
            model_id=model,
        )

    thesis = runner("deepseek", "deepseek-v4-pro")
    disconfirming = runner("grok", "grok-4.6")
    moderator = runner("kimi", "kimi-k3")
    expression = runner("deepseek", "deepseek-v4-pro")
    audit = runner("grok", "grok-4.6")
    deliberator = AgenticDeliberator(
        database,
        thesis,
        thesis_runner=thesis,
        disconfirming_runner=disconfirming,
        moderator_runner=moderator,
    )
    runtime = MvpOrchestrator(
        database,
        fixture,
        client,
        shadow_flow=AgenticExpressionFlow(
            database,
            expression,
            fixture.universe,
            audit_runner=audit,
        ),
        research_config=ResearchRuntimeConfig(max_tool_calls=3),
        deliberator=deliberator,
    )

    result = runtime.run(
        "b6-heterogeneous-models",
        datetime(2026, 8, 24, 13, 30, tzinfo=UTC),
    )

    assert result.status == "MVP_RUNNING"
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT role, model_provider, model_id FROM research.run
            WHERE role IN ('thesis_assessor','disconfirming_assessor',
              'discussion_moderator','expression_agent','expression_auditor')
            GROUP BY role, model_provider, model_id ORDER BY role"""
        ).fetchall()
    assert rows == [
        ("disconfirming_assessor", "grok", "grok-4.6"),
        ("discussion_moderator", "kimi", "kimi-k3"),
        ("expression_agent", "deepseek", "deepseek-v4-pro"),
        ("expression_auditor", "grok", "grok-4.6"),
        ("thesis_assessor", "deepseek", "deepseek-v4-pro"),
    ]


def test_all_ranking_gates_rejected_complete_idle_without_expression(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    runtime, _client = orchestrator(database)
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)

    def reject_all(_demo_id, opportunities, _assessments, _discussions, _wake_at):
        return RankingBook(
            ranking_run_id="ranking_all_rejected_fixture",
            known_at=wake_at + timedelta(seconds=12),
            items=(),
            gates=tuple(
                RankingGate(
                    opportunity_id=item.opportunity_id,
                    status="rejected",
                    reason_codes=("outside_1_90_day_horizon",),
                )
                for item in opportunities
            ),
        )

    runtime.research.rank = reject_all
    result = runtime.run("b6-all-ranking-rejected", wake_at)

    assert result.status == "MVP_IDLE"
    assert len(result.opportunity_ids) == 3
    assert result.top_opportunity_id is None
    assert result.expression_id is None
    with database.connect() as connection:
        stages = connection.execute(
            """SELECT event_type, payload->>'stage', payload->>'reason'
            FROM ops.event WHERE aggregate_id = 'b6-all-ranking-rejected'
              AND event_type LIKE 'mvp.stage.%' ORDER BY sequence"""
        ).fetchall()
        completion = connection.execute(
            """SELECT payload->'snapshot'->>'idle_reason'
            FROM ops.event WHERE aggregate_id = 'b6-all-ranking-rejected'
              AND event_type = 'mvp.pipeline.completed'"""
        ).fetchone()[0]
    assert stages[-3:] == [
        ("mvp.stage.skipped", "expression", "no_opportunity_ranked"),
        ("mvp.stage.skipped", "shadow_open", "no_opportunity_ranked"),
        ("mvp.stage.skipped", "monitor_exit", "no_opportunity_ranked"),
    ]
    assert completion == "no_opportunity_ranked"


def test_incomplete_cycle_recovers_frozen_wake_without_polling_sources(
    empty_b6_database: str,
) -> None:
    class SourceMustNotRun:
        def schedule_and_wake(self, *_args, **_kwargs):
            raise AssertionError("recovery must not poll or rebuild source evidence")

    database = Database(empty_b6_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)
    interrupted, _ = orchestrator(database)
    interrupted.use_wall_clock = True
    with pytest.raises(MvpFaultInjected, match="scouts"):
        interrupted.run("b6-frozen-wake-recovery", wake_at, fault_after_stage="scouts")
    with database.connect() as connection:
        run_count = connection.execute(
            "SELECT count(*) FROM research.run WHERE job_id IS NOT NULL"
        ).fetchone()[0]

    recovered, _ = orchestrator(database)
    recovered.use_wall_clock = True
    recovered.source = SourceMustNotRun()
    result = recovered.run("b6-frozen-wake-recovery", wake_at)

    assert result.status == "MVP_RUNNING"
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM research.run WHERE job_id IS NOT NULL"
            ).fetchone()[0]
            == run_count
        )


def test_independent_expression_auditor_can_require_wait_before_shadow_open(
    empty_b6_database: str,
) -> None:
    class AuditMarket:
        def equity(self, kind, symbol):
            now = datetime.now(UTC)
            quote = QuoteSnapshot(
                symbol=symbol,
                bid=Decimal("99.90"),
                ask=Decimal("100.00"),
                as_of=now - timedelta(milliseconds=10),
                known_at=now,
                raw_id="raw_expression_audit_fixture",
                raw_version=1,
                content_hash="a" * 64,
            )
            return InstrumentSelection(
                MarketInstrument(
                    kind=kind,
                    symbol=symbol,
                    underlying_symbol=symbol,
                    quote=quote,
                    quantity=Decimal("10"),
                    metadata={
                        "notional_limit": "1000",
                        "observed_day_dollar_volume": "100000000",
                    },
                ),
                "validated_equity_snapshot",
            )

        def option(self, *_args):
            raise AssertionError("fixture expression selected equity")

    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = HybridAgentClient(fixture, audit_decision="wait")
    roles = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-agentic-model",
    )
    runtime = MvpOrchestrator(
        database,
        fixture,
        client,
        shadow_flow=AgenticExpressionFlow(
            database,
            roles,
            fixture.universe,
            AuditMarket(),
        ),
        research_config=ResearchRuntimeConfig(max_tool_calls=3),
        role_runner=roles,
    )

    result = runtime.run(
        "b6-expression-audit",
        datetime.now(UTC) - timedelta(minutes=1),
    )

    assert result.shadow_position_id is None
    assert client.role_calls.count("expression_auditor") == 3
    with database.connect() as connection:
        expression = connection.execute(
            """SELECT kind, status, rationale FROM research.expression
            WHERE id = %s""",
            (result.expression_id,),
        ).fetchone()
        audit_input = connection.execute(
            """SELECT frozen_input FROM research.run
            WHERE role = 'expression_auditor'"""
        ).fetchone()[0]
    rationale = json.loads(expression[2])
    detail = database.expression_detail(result.expression_id, "shadow")
    assert expression[0:2] == ("wait", "validated")
    assert rationale["gate"] == "independent_audit_wait"
    assert rationale["implementation_plan"]["status"] == "ready"
    assert detail is not None
    assert Decimal(detail["implementationPlan"]["target_quantity"]) == Decimal("10")
    assert rationale["independent_audit"]["decision"] == "wait"
    assert "ranking" not in audit_input


def test_expression_auditor_selects_from_a_market_validated_payoff_slate(
    empty_b6_database: str,
) -> None:
    class TournamentMarket:
        @staticmethod
        def _quote(symbol: str, *, after: datetime | None = None) -> QuoteSnapshot:
            known_at = (after + timedelta(seconds=1)) if after else datetime.now(UTC)
            return QuoteSnapshot(
                symbol=symbol,
                bid=Decimal("99.99"),
                ask=Decimal("100.00"),
                as_of=known_at - timedelta(milliseconds=1),
                known_at=known_at,
                raw_id=f"raw_tournament_{symbol.lower()}",
                raw_version=1,
                content_hash=("a" if symbol == "DEMO" else "b") * 64,
            )

        def equity(self, kind, symbol, **kwargs):
            return InstrumentSelection(
                MarketInstrument(
                    kind=kind,
                    symbol=symbol,
                    underlying_symbol=kwargs.get("underlying_symbol", symbol),
                    quote=self._quote(symbol),
                    quantity=Decimal("10"),
                    metadata={
                        "notional_limit": "1000",
                        "observed_day_dollar_volume": "100000000",
                        **kwargs.get("metadata", {}),
                    },
                ),
                "validated_equity_snapshot",
            )

        def option(self, *_args):
            raise AssertionError("fixture tournament did not request an option")

        def quote(self, _kind, symbol, *, underlying_symbol=None):
            assert underlying_symbol in {None, "DEMO", "SPY"}
            return self._quote(symbol)

        def forward_quote(
            self,
            _kind,
            symbol,
            *,
            committed_at,
            frozen_latency_ms,
            underlying_symbol,
        ):
            assert frozen_latency_ms >= 0 and underlying_symbol in {"DEMO", "SPY"}
            return self._quote(symbol, after=committed_at)

    hypotheses = [
        {
            "hypothesis_id": "issuer_stock",
            "kind": "stock",
            "symbol": "DEMO",
            "payoff_thesis": "Direct issuer upside with retained market beta.",
            "thesis_purity": 0.8,
            "timing_fit": 0.7,
            "primary_tradeoff": "Issuer-specific downside remains.",
        },
        {
            "hypothesis_id": "liquid_proxy",
            "kind": "etf",
            "symbol": "SPY",
            "payoff_thesis": "Liquid proxy for the bounded fixture catalyst.",
            "thesis_purity": 0.6,
            "timing_fit": 0.9,
            "primary_tradeoff": "Proxy basis risk dilutes issuer Alpha.",
        },
    ]
    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = HybridAgentClient(
        fixture,
        expression_hypotheses=hypotheses,
        audit_selection="liquid_proxy",
    )
    roles = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-agentic-model",
    )
    runtime = MvpOrchestrator(
        database,
        fixture,
        client,
        shadow_flow=AgenticExpressionFlow(
            database,
            roles,
            fixture.universe,
            TournamentMarket(),
        ),
        research_config=ResearchRuntimeConfig(max_tool_calls=3),
        role_runner=roles,
    )

    result = runtime.run(
        "b6-expression-tournament",
        datetime.now(UTC) - timedelta(minutes=1),
    )

    with database.connect() as connection:
        kind, symbol, rationale = connection.execute(
            "SELECT kind, symbol, rationale FROM research.expression WHERE id = %s",
            (result.expression_id,),
        ).fetchone()
    payload = json.loads(rationale)
    assert (kind, symbol) == ("etf", "SPY"), payload.get("gate", payload)
    assert payload["selected_hypothesis_id"] == "liquid_proxy"
    assert len(payload["expression_slate"]) == 2


def test_expression_market_failure_is_audited_wait_not_pipeline_failure(
    empty_b6_database: str,
) -> None:
    class FailingMarket:
        def equity(self, _kind, _symbol):
            raise RuntimeError("upstream detail must not escape")

        def option(self, *_args):
            raise RuntimeError("upstream detail must not escape")

    database = Database(empty_b6_database)
    database.upgrade()
    fixture = MvpFixture.default()
    client = HybridAgentClient(fixture)
    roles = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-agentic-model",
    )
    runtime = MvpOrchestrator(
        database,
        fixture,
        client,
        shadow_flow=AgenticExpressionFlow(
            database,
            roles,
            fixture.universe,
            FailingMarket(),
        ),
        research_config=ResearchRuntimeConfig(max_tool_calls=3),
        role_runner=roles,
    )

    result = runtime.run(
        "b6-expression-market-failure",
        datetime(2026, 8, 24, 13, 30, tzinfo=UTC),
    )

    assert result.shadow_position_id is None
    assert client.role_calls.count("expression_auditor") == 3
    with database.connect() as connection:
        rationale = connection.execute(
            "SELECT rationale FROM research.expression WHERE id = %s",
            (result.expression_id,),
        ).fetchone()[0]
    payload = json.loads(rationale)
    assert payload["gate"] == "market_data_unavailable:RuntimeError"
    assert payload["independent_audit"]["decision"] == "wait"
    assert "upstream detail" not in rationale


@pytest.mark.parametrize("fault_after", ["scouts", "monitor_exit"])
def test_pipeline_recovers_after_crash_without_manual_database_repair(
    empty_b6_database: str, fault_after: str
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)
    before, before_client = orchestrator(database)

    with pytest.raises(MvpFaultInjected, match=fault_after):
        before.run(
            f"b6-crash-{fault_after.replace('_', '-')}",
            wake_at,
            fault_after_stage=fault_after,
        )

    recovered, recovered_client = orchestrator(database)
    result = recovered.run(f"b6-crash-{fault_after.replace('_', '-')}", wake_at)
    with database.connect() as connection:
        terminal = connection.execute(
            """SELECT o.status, e.status, p.status
            FROM research.shadow_position p
            JOIN research.expression e ON e.id = p.expression_id
            JOIN research.opportunity o ON o.id = p.opportunity_id"""
        ).fetchone()
        completion_count = connection.execute(
            """SELECT count(*) FROM ops.event
            WHERE event_type = 'mvp.pipeline.completed'"""
        ).fetchone()[0]
    assert result.status == "MVP_RUNNING"
    assert terminal == ("closed", "closed", "closed")
    assert completion_count == 1
    assert before_client.calls == [
        "change_event_scout",
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
    ]
    assert recovered_client.calls == []


@pytest.mark.parametrize(
    ("demo_id", "source_overrides", "timed_out", "expected"),
    [
        (
            "b6-source-off",
            {"official_policy": "disabled"},
            (),
            ("official_policy", "disabled"),
        ),
        (
            "b6-finlight-stale",
            {"finlight": "stale"},
            (),
            ("finlight", "stale"),
        ),
        (
            "b6-agent-timeout",
            {},
            ("causal_policy_scout",),
            ("causal_policy_scout", "failed"),
        ),
    ],
)
def test_source_and_agent_failures_degrade_without_blocking_mvp(
    empty_b6_database: str,
    demo_id: str,
    source_overrides: dict,
    timed_out: tuple[str, ...],
    expected: tuple[str, str],
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    runtime, _ = orchestrator(database, *timed_out)

    result = runtime.run(
        demo_id,
        datetime(2026, 8, 24, 13, 30, tzinfo=UTC),
        source_overrides=source_overrides,
    )

    assert result.status == "MVP_RUNNING"
    if expected[0].endswith("scout"):
        assert result.scout_statuses[expected[0]] == expected[1]
        with database.connect() as connection:
            assert (
                connection.execute(
                    """SELECT error_code FROM research.run WHERE role = %s""",
                    (expected[0],),
                ).fetchone()[0]
                == "deadline_exceeded"
            )
    else:
        assert result.source_postures[expected[0]] == expected[1]
    assert result.source_postures["massive"] == "disabled"
    assert result.candidate_ids


def free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return value.getsockname()[1]


def request_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as result:
        return json.load(result)


def wait_until(operation, timeout: float = 10):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return operation()
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"operation did not become ready: {last_error}")


def test_one_click_demo_api_sse_reconnect_and_supervisor_crash_recovery(
    empty_b6_database: str, tmp_path: Path
) -> None:
    port = free_port()
    state_file = tmp_path / "b6-supervisor.json"
    env = {
        **os.environ,
        "DATABASE_URL": empty_b6_database,
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "ALTA_ENVIRONMENT": "shadow",
    }
    demo = subprocess.run(
        [sys.executable, "-m", "alta_asterism", "demo", "--demo-id", "b6-cli"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    replay = subprocess.run(
        [sys.executable, "-m", "alta_asterism", "replay", "--demo-id", "b6-cli"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    first = json.loads(demo.stdout)
    second = json.loads(replay.stdout)
    assert (first["status"], first["replayed"], second["replayed"]) == (
        "MVP_RUNNING",
        False,
        True,
    )
    assert first["replay_hash"] == second["replay_hash"]

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "alta_asterism",
            "supervisor",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--state-file",
            str(state_file),
            "--max-restarts",
            "2",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        status = wait_until(lambda: request_json(port, "/api/v1/mvp/status"))
        assert status["data"]["status"] == "MVP_RUNNING"
        assert status["data"]["runs"]
        assert status["data"]["agents"]
        assert status["data"]["candidates"]
        assert status["data"]["opportunities"]
        assert status["data"]["ranks"]
        assert status["data"]["expressions"]
        assert status["data"]["shadowPositions"]
        assert status["data"]["assessments"]
        assert status["data"]["discussions"]
        run_detail = request_json(
            port, f"/api/v1/runs/{status['data']['runs'][0]['id']}"
        )
        assert run_detail["data"]["frozenInput"]
        assert run_detail["data"]["modelId"]
        opportunity_detail = request_json(
            port,
            f"/api/v1/opportunities/{status['data']['opportunities'][0]['id']}",
        )
        assert opportunity_detail["data"]["assessments"]
        assert opportunity_detail["data"]["ranks"]
        assert opportunity_detail["data"]["researchLineage"]["mode"] == "explore"
        assert opportunity_detail["data"]["researchContributors"]
        assert opportunity_detail["data"]["openResearchQuestions"]
        expression_detail = request_json(
            port,
            f"/api/v1/expressions/{status['data']['expressions'][0]['id']}",
        )
        assert expression_detail["data"]["validation"]
        assert expression_detail["data"]["shadowPosition"]
        runtime = request_json(port, "/api/v1/system/runtime")
        assert runtime["data"]["minds"]
        assert runtime["data"]["researchAttention"] == {
            "version": "alta-research-attention-v1",
            "knownAt": runtime["data"]["researchAttention"]["knownAt"],
            "observedThrough": None,
            "maximumWindow": 64,
            "minimumSample": 4,
            "concentrationThreshold": "0.50",
            "sampleSize": 0,
            "uniqueEntities": 0,
            "topEntity": None,
            "topEntityShare": None,
            "concentrationHhi": None,
            "effectiveBreadth": None,
            "posture": "insufficient_sample",
            "continuationScoutId": None,
            "assignments": [
                {
                    "scoutId": scout_id,
                    "mode": "unconstrained",
                    "deprioritizedEntities": [],
                    "directive": "Explore independently; no production Candidate concentration sample is mature.",
                }
                for scout_id in (
                    "change_event_scout",
                    "market_dislocation_scout",
                    "causal_policy_scout",
                    "expectation_gap_scout",
                )
            ],
            "warning": "Research attention breadth is descriptive process control, not Evidence, Alpha, rank, or permission to trade.",
        }
        assert runtime["data"]["config"]["capitalMode"] == "disabled"
        assert runtime["data"]["config"]["credentials"] == {
            "revision": "unmanaged",
            "configuredSlots": [],
            "reloadMode": "atomic_replace_then_restart",
            "valuesExposed": False,
        }
        assert runtime["data"]["config"]["autonomousHeartbeatSeconds"] == 30
        assert runtime["data"]["config"]["autonomousFollowUpIntervalSeconds"] == 900
        assert runtime["data"]["config"]["autonomousPositionIntervalSeconds"] == 300
        assert runtime["data"]["config"]["cadenceReason"] is None
        assert runtime["data"]["config"]["nextIntervalSeconds"] is None
        assert runtime["data"]["config"]["autonomousCycleTimeoutSeconds"] == 3_600
        assert runtime["data"]["config"]["shadowPortfolioPolicy"] == {
            "referenceNav": "1000000",
            "tradeLossBudgetBps": "25",
            "maxPositionNavBps": "100",
            "maxGrossNavBps": "800",
            "maxUnderlyingNavBps": "150",
            "equityStressFloorBps": "2500",
            "maxExitDays": 2,
            "advParticipationBps": "500",
            "minNetAlphaBps": "50",
            "navSource": "synthetic_shadow_reference",
        }
        assert runtime["data"]["config"]["traderMinds"] == {
            "count": 4,
            "promptVersion": "alpha-trader-v16",
            "toolCatalogVersion": "alta-active-research-v4",
            "activeResearchRequired": True,
            "memoryMode": "bounded_non_evidence",
            "coreActiveTools": [
                "alta_web_search",
                "alta_web_research",
                "alta_news_search",
                "alta_social_search",
                "alta_finance_data",
            ],
            "alphaFeedback": {
                "mode": "mature_pit_non_evidence",
                "minimumMindBenchmarkedPositions": 30,
                "minimumSliceBenchmarkedPositions": 10,
                "automaticPolicyChanges": False,
                "automaticResearchBudgetChanges": True,
                "researchIncentive": {
                    "mode": "delayed_symmetric_alpha_v1",
                    "alphaLowerBoundZ": "2.241",
                    "maximumBonusToolCalls": 1,
                    "maximumBonusTokens": 8_000,
                    "capitalInfluence": False,
                    "rankingInfluence": False,
                    "brokerInfluence": False,
                },
            },
        }
        alpha_feedback = request_json(port, "/api/v1/alpha/feedback")
        assert alpha_feedback["data"]["automaticPolicyChanges"] is False
        assert alpha_feedback["data"]["automaticResearchBudgetChanges"] is True
        assert alpha_feedback["data"]["incentivePolicy"] == {
            "mode": "delayed_symmetric_alpha_v1",
            "alphaLowerBoundZ": "2.241",
            "maximumBonusToolCalls": 1,
            "maximumBonusTokens": 8_000,
            "capitalInfluence": False,
            "rankingInfluence": False,
            "brokerInfluence": False,
        }
        assert len(alpha_feedback["data"]["researchIncentives"]) == 4
        assert all(
            item["state"] == "prospective"
            for item in alpha_feedback["data"]["researchIncentives"]
        )
        assert (
            next(
                item
                for item in status["data"]["sources"]
                if item["source_id"] == "massive"
            )["posture"]
            == "disabled"
        )

        database = Database(empty_b6_database)
        cursor = database.append_event(
            Event(
                id="event_b6_sse_reconnect",
                environment="shadow",
                version=1,
                known_at=datetime(2026, 8, 24, 14, tzinfo=UTC),
                aggregate_type="mvp_pipeline",
                aggregate_id="b6-cli",
                event_type="mvp.service.recovered",
                payload={"status": "ready"},
            )
        )
        reconnect = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/stream",
            headers={"Last-Event-ID": str(cursor - 1)},
        )
        with urllib.request.urlopen(reconnect, timeout=2) as response:
            stream = response.read().decode()
        assert f"id: {cursor}" in stream
        assert "mvp.service.recovered" in stream
        assert '"payload":{"status":"ready"}' in stream

        first_child = wait_until(
            lambda: (
                state["childPid"]
                if (state := json.loads(state_file.read_text()))["state"] == "running"
                else (_ for _ in ()).throw(OSError("not ready"))
            )
        )
        os.kill(first_child, signal.SIGTERM)
        second_child = wait_until(
            lambda: (
                state["childPid"]
                if (state := json.loads(state_file.read_text()))["state"] == "running"
                and state["childPid"] != first_child
                else (_ for _ in ()).throw(OSError("not restarted"))
            )
        )
        assert second_child != first_child
        assert (
            wait_until(lambda: request_json(port, "/api/v1/mvp/status"))["data"][
                "status"
            ]
            == "MVP_RUNNING"
        )
    finally:
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()
        assert process.returncode == 0, stderr


def test_complete_market_session_event_time_soak_has_no_manual_repairs(
    empty_b6_database: str,
) -> None:
    database = Database(empty_b6_database)
    database.upgrade()
    start = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)

    result = run_market_session_soak(
        database,
        "b6-test-soak",
        start,
        start + timedelta(hours=6, minutes=30),
        cadence_minutes=30,
    )

    assert (
        result.status,
        result.event_time_duration_seconds,
        result.cycles,
        result.failures,
        result.manual_database_repairs,
    ) == ("PASS", 23_400, 14, (), 0)
    assert len(result.replay_hashes) == 14
