import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from alta_asterism.b5_runtime import B5Runtime, _append_event, _contract_event
from alta_asterism.contracts import Environment
from alta_asterism.agentic_position import AgenticPositionBook
from alta_asterism.alpha_governance import AlphaCapitalGovernance
from alta_asterism.alpha_lifecycle import build_alpha_clock
from alta_asterism.database import Database
from alta_asterism.expression import (
    ExpressionPolicy,
    ExpressionProposal,
    QuoteSnapshot,
    validate_expression,
)
from alta_asterism.implementation import PortfolioRiskPolicy, TradeImplementationPlan
from alta_asterism.portfolio_construction import PortfolioConstructor
from alta_asterism.shadow import (
    MonitorObservation,
    MonitorPolicy,
    PositionThesis,
    ShadowFillPolicy,
    ShadowIntent,
    close_ledger_transaction,
    evaluate_shadow_fill,
    monitor_position,
    open_ledger_transaction,
)
from alta_asterism.underwriting_calibration import frozen_expected_net_alpha_bps


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_b5_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b5_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b5_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def seed_ranked_opportunity(database: Database) -> None:
    known_at = datetime(2026, 8, 23, 13, 55, tzinfo=UTC)
    snapshot_hash = "f" * 64
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO research.run
            (id, environment, version, known_at, role, status, input_hash,
             frozen_input, budget, deadline_at, prompt_version,
             tool_catalog_version, model_provider, model_id, trace_id,
             tool_provenance, evidence_ids)
            VALUES ('run_b5_fixture','shadow',1,%s,'b5_fixture','succeeded',%s,
                    %s,%s,%s,'b5-fixture-v1','none','deterministic','fixture',
                    'trace_b5_fixture','[]'::jsonb,ARRAY['evidence_b5_fixture'])""",
            (
                known_at,
                hashlib.sha256(b"b5-fixed-input").hexdigest(),
                Jsonb({"fixture": True}),
                Jsonb({"external_calls": 0}),
                known_at,
            ),
        )
        connection.execute(
            """INSERT INTO research.raw
            (id, environment, version, known_at, source, source_key,
             content_hash, body)
            VALUES ('raw_b5_evidence','shadow',1,%s,'b5_fixture','fixed',%s,%s)""",
            (
                known_at,
                hashlib.sha256(b"b5-evidence").hexdigest(),
                Jsonb({"fixture": True}),
            ),
        )
        connection.execute(
            """INSERT INTO research.evidence
            (id, environment, version, known_at, raw_id, stance, summary)
            VALUES ('evidence_b5_fixture','shadow',3,%s,'raw_b5_evidence',
                    'support','Fixed versioned evidence for B5.')""",
            (known_at,),
        )
        connection.execute(
            """INSERT INTO research.candidate
            (id, environment, version, known_at, run_id, title, why_now,
             expectation, variant_wedge, falsifier, horizon_days, confidence,
             evidence_ids)
            VALUES ('candidate_b5_fixture','shadow',1,%s,'run_b5_fixture',
                    'B5 fixed candidate','New fixed fact','Consensus lags',
                    'Measured wedge','Reverse on failed catalyst',10,0.7,
                    ARRAY['evidence_b5_fixture'])""",
            (known_at,),
        )
        connection.execute(
            """INSERT INTO research.opportunity
            (id, environment, version, known_at, candidate_id, status, title,
             thesis, falsifier, horizon_days, member_candidate_ids, exact_key,
             structural_key, snapshot_hash, foundry_state, merge_revision,
             observed_change, mechanism, direction, expectation,
             expectation_posture, variant_wedge, why_now, first_rejection,
             prediction, investability, freshness_at, evidence_ids, completeness)
            VALUES ('opportunity_b5_fixture','shadow',2,%s,'candidate_b5_fixture',
                    'ranked','B5 fixed opportunity','Versioned fixed thesis',
                    'Reverse on failed catalyst',10,ARRAY['candidate_b5_fixture'],
                    %s,%s,%s,'active',1,'Observed fixed change',
                    'Fixed mechanism','positive','Consensus lags','available',
                    'Measured wedge','New fixed fact','Reject if reversed',
                    'Forward measure improves','ready',%s,
                    ARRAY['evidence_b5_fixture'],'complete')""",
            (known_at, "a" * 64, "b" * 64, snapshot_hash, known_at),
        )


def quote(
    *,
    bid: str,
    ask: str,
    as_of: datetime,
    known_at: datetime,
    suffix: str,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol="DEMO",
        bid=Decimal(bid),
        ask=Decimal(ask),
        as_of=as_of,
        known_at=known_at,
        raw_id=f"raw_quote_{suffix}",
        raw_version=1,
        content_hash=hashlib.sha256(suffix.encode()).hexdigest(),
    )


def implementation_plan(
    expected_net_alpha_bps: str,
    known_at: datetime,
) -> TradeImplementationPlan:
    alpha_clock = build_alpha_clock(
        known_at=known_at,
        evidence_freshness_at=known_at,
        horizon_days=30,
        raw_expected_net_alpha_bps=Decimal(expected_net_alpha_bps),
        catalyst_clarity=Decimal("0.8"),
        next_pricing_facts=("Next versioned operating update.",),
    )
    return TradeImplementationPlan(
        status="ready",
        policy_version=PortfolioRiskPolicy().version,
        intended_alpha="Issuer-specific expectation revision.",
        retained_exposure="Residual issuer exposure.",
        reference_nav=Decimal("1000000"),
        expected_net_alpha_bps=Decimal(expected_net_alpha_bps),
        alpha_clock=alpha_clock,
        loss_budget=Decimal("2500"),
        position_notional_limit=Decimal("10000"),
        gross_notional_before=Decimal("0"),
        gross_notional_limit=Decimal("80000"),
        gross_notional_after=Decimal("1000"),
        target_notional=Decimal("1000"),
        target_quantity=Decimal("10"),
        estimated_stress_loss=Decimal("250"),
        binding_constraint="stress_loss_budget",
        alpha_capital_governance=AlphaCapitalGovernance.unscoped(
            PortfolioRiskPolicy().version
        ),
    )


class RotationMarket:
    def quote(self, _kind, symbol, *, underlying_symbol=None):
        del underlying_symbol
        known_at = datetime.now(UTC)
        return QuoteSnapshot(
            symbol=symbol,
            bid=Decimal("99.90"),
            ask=Decimal("100.00"),
            as_of=known_at,
            known_at=known_at,
            raw_id=f"raw_rotation_{symbol}",
            raw_version=1,
            content_hash=hashlib.sha256(
                f"rotation-{symbol}-{known_at.isoformat()}".encode()
            ).hexdigest(),
        )

    def forward_quote(
        self,
        _kind,
        symbol,
        *,
        committed_at,
        frozen_latency_ms,
        underlying_symbol=None,
    ):
        del frozen_latency_ms, underlying_symbol
        as_of = committed_at + timedelta(seconds=1)
        return QuoteSnapshot(
            symbol=symbol,
            bid=Decimal("99.80"),
            ask=Decimal("99.90"),
            as_of=as_of,
            known_at=as_of + timedelta(milliseconds=10),
            raw_id=f"raw_rotation_forward_{symbol}",
            raw_version=1,
            content_hash=hashlib.sha256(
                f"rotation-forward-{symbol}-{as_of.isoformat()}".encode()
            ).hexdigest(),
        )


def test_full_book_executes_idempotent_alpha_rotation(
    empty_b5_database: str,
) -> None:
    database = Database(empty_b5_database)
    database.upgrade()
    seed_ranked_opportunity(database)
    runtime = B5Runtime(database, capital_mode="disabled")
    now = datetime.now(UTC)
    entered_at = now - timedelta(days=15)
    binding = runtime.expressions.binding_for("opportunity_b5_fixture")
    entry_quote = quote(
        bid="99.90",
        ask="100.00",
        as_of=entered_at,
        known_at=entered_at + timedelta(seconds=1),
        suffix="rotation-entry",
    )
    validation_quote = quote(
        bid="99.90",
        ask="100.00",
        as_of=entered_at - timedelta(seconds=4),
        known_at=entered_at - timedelta(seconds=3),
        suffix="rotation-validation",
    )
    incumbent_plan = implementation_plan("200", entered_at)
    proposal = ExpressionProposal(
        expression_id="expression_rotation_incumbent",
        binding=binding,
        kind="stock",
        symbol="DEMO",
        side="long",
        quantity=Decimal("10"),
        rationale="Frozen incumbent for capital-competition integration.",
        decision_known_at=entered_at - timedelta(seconds=2),
        quote=validation_quote,
        implementation_plan=incumbent_plan,
    )
    validation = validate_expression(proposal, ExpressionPolicy())
    assert validation.status == "validated"
    runtime.expressions.persist(proposal, validation)
    fill_policy = ShadowFillPolicy()
    intent = ShadowIntent(
        intent_id="intent_rotation_incumbent",
        position_id="shadow_rotation_incumbent",
        action="open",
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=proposal.hash(),
        binding=binding,
        symbol="DEMO",
        quantity=proposal.quantity,
        committed_at=entered_at - timedelta(seconds=1),
        policy_version=fill_policy.version,
    )
    fill = evaluate_shadow_fill(intent, entry_quote, fill_policy)
    ledger = open_ledger_transaction(fill)
    thesis = PositionThesis(
        thesis_id="thesis_rotation_incumbent",
        position_id=intent.position_id,
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=proposal.hash(),
        binding=binding,
        known_at=fill.known_at,
        entry_expectation="The incumbent has 200 bps of underwritten net Alpha.",
        why_now="Frozen integration evidence.",
        invalidation_condition="The measured mechanism reverses.",
        time_exit_at=now + timedelta(days=15),
        next_catalyst="Next versioned operating update.",
        better_opportunity_min_bps=Decimal("75"),
        implementation_plan=incumbent_plan,
    )
    runtime.shadow.open(intent, fill, ledger, thesis)

    positions = AgenticPositionBook(
        database,
        object(),  # type: ignore[arg-type]
        runtime,
        RotationMarket(),  # type: ignore[arg-type]
        max_open_positions=1,
        portfolio_constructor=PortfolioConstructor(database, max_open_positions=1),
    )
    allocation = positions.assess_capital(implementation_plan("180", now), now)

    assert allocation.status == "rotate"
    assert allocation.advantage_bps is not None
    assert allocation.advantage_bps > Decimal("75")
    assert positions.execute_rotation("cycle_alpha_rotation", allocation) is True
    assert positions.execute_rotation("cycle_alpha_rotation", allocation) is True
    with database.connect() as connection:
        state = connection.execute(
            """SELECT status, exit_decision->>'reason_code'
            FROM research.shadow_position WHERE id = %s""",
            (thesis.position_id,),
        ).fetchone()
        exits = connection.execute(
            """SELECT count(*) FROM ops.event
            WHERE aggregate_id = %s AND event_type = 'position.exit_decided'""",
            (thesis.position_id,),
        ).fetchone()[0]
    assert state == ("closed", "better_opportunity")
    assert exits == 1

    measured_at = now + timedelta(seconds=1)
    with database.connect() as connection:
        position_thesis = connection.execute(
            """SELECT position_thesis FROM research.shadow_position
            WHERE id = %s""",
            (thesis.position_id,),
        ).fetchone()[0]
        _append_event(
            connection,
            _contract_event(
                event_type="position.performance.measured",
                aggregate_type="shadow_position",
                aggregate_id=thesis.position_id,
                environment=Environment.SHADOW,
                known_at=measured_at,
                payload={
                    "position_id": thesis.position_id,
                    "opportunity_id": "opportunity_b5_fixture",
                    "net_pnl": "10",
                    "net_return_bps": "100",
                    "realized_alpha_bps": "50",
                    "cost_adjusted": True,
                    "path_diagnostics": {
                        "version": "alta-path-diagnostics-v1",
                        "price_observations": 3,
                        "opened_at": now.isoformat(),
                        "closed_at": measured_at.isoformat(),
                        "maximum_favorable_excursion_bps": "180",
                        "maximum_adverse_excursion_bps": "-70",
                        "maximum_drawdown_bps": "120",
                        "net_return_bps": "100",
                        "exit_capture_ratio": "0.5556",
                        "time_to_best_seconds": 1,
                        "holding_seconds": 1,
                    },
                    "execution_quality": {
                        "version": "alta-execution-quality-v1",
                        "estimated_cost_bps": "20",
                        "realized_cost_bps": "30",
                        "cost_surprise_bps": "10",
                        "entry_shortfall_bps": "12",
                        "exit_shortfall_bps": "14",
                        "entry_commission_bps": "2",
                        "exit_commission_bps": "2",
                        "mean_quoted_spread_bps": "10",
                        "within_cost_budget": False,
                    },
                },
                correlation_id="opportunity_b5_fixture",
            ),
        )

    frozen_forecast = frozen_expected_net_alpha_bps(position_thesis)
    assert frozen_forecast is not None
    alpha_summary = database.alpha_summary(Environment.SHADOW.value)
    calibration = alpha_summary["underwritingCalibration"]
    assert calibration["sampleSize"] == 1
    assert calibration["meanExpectedAlphaBps"] == str(
        frozen_forecast.quantize(Decimal("0.01"))
    )
    assert calibration["meanRealizedAlphaBps"] == "50.00"
    assert alpha_summary["alphaEvidence"]["posture"] == "insufficient_sample"
    assert alpha_summary["capitalGovernance"]["posture"] == "collecting"
    assert alpha_summary["capitalGovernance"]["sampleSize"] == 1
    assert alpha_summary["capitalGovernance"]["capitalMultiplier"] == "0.50"
    forecast_governance = alpha_summary["forecastCalibrationGovernance"]
    assert forecast_governance["posture"] == "collecting"
    assert forecast_governance["sampleSize"] == 1
    assert forecast_governance["alphaReserveBps"] == "0"
    assert forecast_governance["capitalMultiplier"] == "1"
    path_diagnostics = alpha_summary["pathDiagnostics"]
    assert path_diagnostics["posture"] == "collecting"
    assert path_diagnostics["measuredPositions"] == 1
    assert path_diagnostics["meanMaximumFavorableExcursionBps"] == "180.00"
    assert path_diagnostics["meanMaximumAdverseExcursionBps"] == "-70.00"
    assert path_diagnostics["meanExitCaptureRatio"] == "0.5556"
    execution_quality = alpha_summary["executionQuality"]
    assert execution_quality["posture"] == "collecting"
    assert execution_quality["measuredPositions"] == 1
    assert execution_quality["meanRealizedCostBps"] == "30.00"
    assert execution_quality["meanCostSurpriseBps"] == "10.00"
    stock_execution = alpha_summary["executionCostGovernance"]["stock"]
    assert stock_execution["posture"] == "collecting"
    assert stock_execution["sampleSize"] == 1
    assert stock_execution["alphaReserveBps"] == "0"
    assert "unproven" in alpha_summary["warning"].lower()


def test_b8_option_expression_persists_with_contract_costs(
    empty_b5_database: str,
) -> None:
    database = Database(empty_b5_database)
    database.upgrade()
    seed_ranked_opportunity(database)
    runtime = B5Runtime(database, capital_mode="disabled")
    decision_at = datetime(2026, 8, 23, 14, 0, 5, tzinfo=UTC)
    option_quote = QuoteSnapshot(
        symbol="O:DEMO260918C00100000",
        bid=Decimal("4.90"),
        ask=Decimal("5.10"),
        as_of=datetime(2026, 8, 23, 14, 0, 2, tzinfo=UTC),
        known_at=datetime(2026, 8, 23, 14, 0, 3, tzinfo=UTC),
        raw_id="raw_option_quote_b8",
        raw_version=1,
        content_hash=hashlib.sha256(b"b8-option-quote").hexdigest(),
    )
    proposal = ExpressionProposal(
        expression_id="expression_b8_option_fixture",
        binding=runtime.expressions.binding_for("opportunity_b5_fixture"),
        kind="option",
        symbol=option_quote.symbol,
        side="long",
        quantity=Decimal("200"),
        rationale="Two long contracts represented as 200 share-equivalent units.",
        decision_known_at=decision_at,
        quote=option_quote,
    )

    validation = validate_expression(proposal, ExpressionPolicy())
    runtime.expressions.persist(proposal, validation)

    assert validation.status == "validated"
    assert validation.estimated_commission == Decimal("1.30")
    with database.connect() as connection:
        assert connection.execute(
            "SELECT kind, status FROM research.expression WHERE id = %s",
            (proposal.expression_id,),
        ).fetchone() == ("option", "validated")


def test_tiger_disabled_main_e2e_expression_shadow_monitor_exit_is_idempotent(
    empty_b5_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALTA_TIGER_MODE", "disabled")
    database = Database(empty_b5_database)
    database.upgrade()
    seed_ranked_opportunity(database)
    runtime = B5Runtime(database, capital_mode="disabled")
    assert runtime.capital_mode == "disabled"
    assert "alta_capitald" not in sys.modules
    with pytest.raises(ValueError, match="requires capital mode disabled"):
        B5Runtime(database, capital_mode="read_only")  # type: ignore[arg-type]

    binding = runtime.expressions.binding_for("opportunity_b5_fixture")
    decision_at = datetime(2026, 8, 23, 14, 0, 5, tzinfo=UTC)
    proposal = ExpressionProposal(
        expression_id="expression_b5_fixture",
        binding=binding,
        kind="stock",
        symbol="DEMO",
        side="long",
        quantity=Decimal("10"),
        rationale="Fixed Stock expression for the B5 main loop.",
        decision_known_at=decision_at,
        quote=quote(
            bid="99.90",
            ask="100.10",
            as_of=datetime(2026, 8, 23, 14, 0, tzinfo=UTC),
            known_at=datetime(2026, 8, 23, 14, 0, 3, tzinfo=UTC),
            suffix="validation",
        ),
    )
    validation = validate_expression(proposal, ExpressionPolicy())
    assert validation.status == "validated"
    runtime.expressions.persist(proposal, validation)
    runtime.expressions.persist(proposal, validation)

    fill_policy = ShadowFillPolicy()
    open_intent = ShadowIntent(
        intent_id="intent_b5_open",
        position_id="shadow_b5_fixture",
        action="open",
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=proposal.hash(),
        binding=binding,
        symbol="DEMO",
        quantity=proposal.quantity,
        committed_at=datetime(2026, 8, 23, 14, 0, 6, tzinfo=UTC),
        policy_version=fill_policy.version,
    )
    entry_quote = quote(
        bid="100.00",
        ask="100.20",
        as_of=datetime(2026, 8, 23, 14, 0, 7, tzinfo=UTC),
        known_at=datetime(2026, 8, 23, 14, 0, 8, tzinfo=UTC),
        suffix="entry",
    )
    open_fill = evaluate_shadow_fill(open_intent, entry_quote, fill_policy)
    open_ledger = open_ledger_transaction(open_fill)
    thesis = PositionThesis(
        thesis_id="thesis_b5_fixture",
        position_id=open_intent.position_id,
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=proposal.hash(),
        binding=binding,
        known_at=open_fill.known_at,
        entry_expectation="The fixed catalyst changes forward expectations.",
        why_now="Versioned evidence arrived before entry.",
        invalidation_condition="The fixed catalyst reverses.",
        time_exit_at=datetime(2026, 8, 30, 14, tzinfo=UTC),
        next_catalyst="Next versioned evidence update.",
        better_opportunity_min_bps=Decimal("75"),
    )
    runtime.shadow.open(open_intent, open_fill, open_ledger, thesis)
    runtime.shadow.open(open_intent, open_fill, open_ledger, thesis)

    hold_quote = quote(
        bid="101.00",
        ask="101.20",
        as_of=datetime(2026, 8, 24, 14, 0, 7, tzinfo=UTC),
        known_at=datetime(2026, 8, 24, 14, 0, 8, tzinfo=UTC),
        suffix="hold",
    )
    hold_observation = MonitorObservation(
        observation_id="observation_b5_hold",
        position_id=thesis.position_id,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        thesis_hash=thesis.hash(),
        binding=binding,
        known_at=datetime(2026, 8, 24, 14, 0, 9, tzinfo=UTC),
        quote=hold_quote,
    )
    hold = monitor_position(thesis, hold_observation, MonitorPolicy())
    assert (hold.action, hold.reason_code) == ("hold", "hold")
    runtime.shadow.record_monitor(hold_observation, hold)

    exit_quote = quote(
        bid="104.80",
        ask="105.00",
        as_of=datetime(2026, 8, 30, 14, 0, 11, tzinfo=UTC),
        known_at=datetime(2026, 8, 30, 14, 0, 12, tzinfo=UTC),
        suffix="exit",
    )
    exit_observation = MonitorObservation(
        observation_id="observation_b5_exit",
        position_id=thesis.position_id,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        thesis_hash=thesis.hash(),
        binding=binding,
        known_at=datetime(2026, 8, 30, 14, 0, 13, tzinfo=UTC),
        quote=exit_quote,
    )
    exit_decision = monitor_position(thesis, exit_observation, MonitorPolicy())
    assert (exit_decision.action, exit_decision.reason_code) == (
        "exit",
        "time_exit",
    )
    runtime.shadow.record_monitor(exit_observation, exit_decision)
    close_intent = ShadowIntent(
        intent_id="intent_b5_close",
        position_id=thesis.position_id,
        action="close",
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=proposal.hash(),
        binding=binding,
        symbol="DEMO",
        quantity=proposal.quantity,
        committed_at=datetime(2026, 8, 30, 14, 0, 14, tzinfo=UTC),
        policy_version=fill_policy.version,
    )
    close_quote = quote(
        bid="104.70",
        ask="104.90",
        as_of=datetime(2026, 8, 30, 14, 0, 15, tzinfo=UTC),
        known_at=datetime(2026, 8, 30, 14, 0, 16, tzinfo=UTC),
        suffix="close",
    )
    close_fill = evaluate_shadow_fill(close_intent, close_quote, fill_policy)
    cost_basis = next(
        line.debit for line in open_ledger.lines if line.account == "position"
    )
    close_ledger = close_ledger_transaction(close_fill, position_cost_basis=cost_basis)
    runtime.shadow.close(close_intent, close_fill, close_ledger, exit_decision)
    runtime.shadow.close(close_intent, close_fill, close_ledger, exit_decision)

    ledger = runtime.shadow.ledger(thesis.position_id)
    with database.connect() as connection:
        position = connection.execute(
            """SELECT status, version, opportunity_id, opportunity_version,
            opportunity_snapshot_hash, evidence_set_hash, binding_hash,
            expression_version, expression_hash, entry_transaction_id,
            exit_transaction_id, thesis_hash FROM research.shadow_position"""
        ).fetchone()
        event_types = connection.execute(
            """SELECT event_type FROM ops.event
            WHERE aggregate_id IN (%s,%s) ORDER BY sequence""",
            (proposal.expression_id, thesis.position_id),
        ).fetchall()
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """UPDATE ops.event SET event_type = 'changed'
                WHERE event_type = 'shadow.ledger.posted'"""
            )
        connection.rollback()

    assert position == (
        "closed",
        2,
        binding.opportunity_id,
        binding.opportunity_version,
        binding.opportunity_snapshot_hash,
        binding.evidence_set_hash,
        binding.hash(),
        proposal.version,
        proposal.hash(),
        open_ledger.transaction_id,
        close_ledger.transaction_id,
        thesis.hash(),
    )
    assert [item.action for item in ledger] == ["open", "close"]
    assert sum(item.quantity_delta for item in ledger) == 0
    assert all(
        sum(line.debit for line in item.lines)
        == sum(line.credit for line in item.lines)
        for item in ledger
    )
    assert event_types == [
        ("expression.validated",),
        ("shadow.intent.committed",),
        ("shadow.fill.recorded",),
        ("shadow.ledger.posted",),
        ("position.thesis.opened",),
        ("position.monitored",),
        ("position.monitored",),
        ("shadow.exit_intent.committed",),
        ("shadow.exit_fill.recorded",),
        ("shadow.ledger.posted",),
        ("position.exit_decided",),
    ]
