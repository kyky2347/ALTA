import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from alta_asterism.expression import (
    EvidenceVersion,
    ExpressionPolicy,
    ExpressionProposal,
    QuoteSnapshot,
    VersionBinding,
    contract_hash,
    validate_expression,
)
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

FIXTURE = Path(__file__).parents[1] / "fixtures" / "b5" / "quotes.json"


def quotes() -> dict[str, QuoteSnapshot]:
    payload = json.loads(FIXTURE.read_text())
    return {
        name: QuoteSnapshot.model_validate(value) for name, value in payload.items()
    }


def binding() -> VersionBinding:
    evidence = (
        EvidenceVersion(
            evidence_id="evidence_b5_fixture",
            version=3,
            known_at=datetime(2026, 8, 23, 13, 55, tzinfo=UTC),
        ),
    )
    return VersionBinding(
        environment="shadow",
        opportunity_id="opportunity_b5_fixture",
        opportunity_version=2,
        opportunity_snapshot_hash="f" * 64,
        evidence=evidence,
        evidence_set_hash=contract_hash(
            [item.model_dump(mode="json") for item in evidence]
        ),
    )


def proposal(kind="stock", quote_name="fresh") -> ExpressionProposal:
    selected = quotes()[quote_name]
    return ExpressionProposal(
        expression_id=f"expression_{kind}_{quote_name}",
        binding=binding(),
        kind=kind,
        symbol="DEMO",
        side="long",
        quantity=Decimal("10"),
        rationale="Fixed B5 fixture expression.",
        decision_known_at=datetime(2026, 8, 23, 14, 0, 5, tzinfo=UTC),
        quote=selected,
    )


def test_stock_etf_option_and_wait_expression_shapes() -> None:
    policy = ExpressionPolicy()
    stock = validate_expression(proposal("stock"), policy)
    etf = validate_expression(proposal("etf"), policy)
    option = validate_expression(proposal("option"), policy)
    wait_proposal = ExpressionProposal(
        expression_id="expression_wait_fixture",
        binding=binding(),
        kind="wait",
        rationale="Wait for the next versioned evidence update.",
        decision_known_at=datetime(2026, 8, 23, 14, 0, 5, tzinfo=UTC),
    )
    wait = validate_expression(wait_proposal, policy)

    assert (
        stock.status,
        etf.status,
        option.status,
        wait.status,
        wait.reason_codes,
    ) == (
        "validated",
        "validated",
        "validated",
        "validated",
        ("wait_selected",),
    )
    with pytest.raises(ValidationError):
        ExpressionProposal(
            expression_id="expression_invalid_wait",
            binding=binding(),
            kind="wait",
            symbol="DEMO",
            side="long",
            quantity=1,
            quote=quotes()["fresh"],
            rationale="Invalid fixture.",
            decision_known_at=datetime(2026, 8, 23, 14, 0, 5, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("quote_name", "reason"),
    [("wide", "spread_too_wide"), ("stale", "price_stale")],
)
def test_price_freshness_spread_and_cost_reject_deterministically(
    quote_name: str, reason: str
) -> None:
    result = validate_expression(proposal(quote_name=quote_name), ExpressionPolicy())

    assert result.status == "rejected"
    assert reason in result.reason_codes
    if quote_name == "wide":
        assert "estimated_cost_too_high" in result.reason_codes


def test_future_known_quote_is_rejected_without_optimism() -> None:
    future = quotes()["fresh"].model_copy(
        update={"known_at": datetime(2026, 8, 23, 14, 0, 6, tzinfo=UTC)}
    )
    value = proposal().model_copy(update={"quote": future})

    result = validate_expression(value, ExpressionPolicy())

    assert result.reason_codes == ("quote_not_known_at_decision",)


def test_shadow_fill_is_latency_gated_conservative_and_double_entry_balanced() -> None:
    policy = ShadowFillPolicy()
    validation = validate_expression(proposal(), ExpressionPolicy())
    intent = ShadowIntent(
        intent_id="intent_open_fixture",
        position_id="shadow_b5_fixture",
        action="open",
        expression_id=validation.expression_id,
        expression_version=validation.expression_version,
        expression_hash=validation.expression_hash,
        binding=validation.binding,
        symbol="DEMO",
        quantity=Decimal("10"),
        committed_at=datetime(2026, 8, 23, 14, 0, 6, tzinfo=UTC),
        policy_version=policy.version,
    )
    too_early = quotes()["entry"].model_copy(
        update={
            "as_of": intent.committed_at + timedelta(milliseconds=100),
            "known_at": intent.committed_at + timedelta(milliseconds=500),
        }
    )

    no_fill = evaluate_shadow_fill(intent, too_early, policy)
    fill = evaluate_shadow_fill(intent, quotes()["entry"], policy)
    ledger = open_ledger_transaction(fill)

    assert (no_fill.status, no_fill.reason_code) == (
        "no_fill",
        "quote_not_after_frozen_latency",
    )
    assert fill.fill_price > quotes()["entry"].ask
    assert sum(line.debit for line in ledger.lines) == sum(
        line.credit for line in ledger.lines
    )
    assert ledger.quantity_delta == Decimal("10")


def test_shadow_fill_does_not_chase_beyond_the_frozen_absolute_limit() -> None:
    policy = ShadowFillPolicy()
    validation = validate_expression(proposal(), ExpressionPolicy())
    intent = ShadowIntent(
        intent_id="intent_guarded_limit",
        position_id="shadow_guarded_limit",
        action="open",
        expression_id=validation.expression_id,
        expression_version=validation.expression_version,
        expression_hash=validation.expression_hash,
        binding=validation.binding,
        symbol="DEMO",
        quantity=Decimal("10"),
        committed_at=datetime(2026, 8, 23, 14, 0, 6, tzinfo=UTC),
        policy_version=policy.version,
        limit_price=quotes()["entry"].ask,
    )

    marketable = evaluate_shadow_fill(intent, quotes()["entry"], policy)
    moved_away = quotes()["entry"].model_copy(
        update={
            "bid": quotes()["entry"].bid + Decimal("0.10"),
            "ask": quotes()["entry"].ask + Decimal("0.10"),
        }
    )
    rejected = evaluate_shadow_fill(intent, moved_away, policy)

    assert marketable.status == "filled"
    assert marketable.fill_price == intent.limit_price
    assert rejected.status == "no_fill"
    assert rejected.reason_code == "guarded_limit_not_market"


def test_position_thesis_monitor_exit_priority_and_close_ledger() -> None:
    fill_policy = ShadowFillPolicy()
    validation = validate_expression(proposal(), ExpressionPolicy())
    open_intent = ShadowIntent(
        intent_id="intent_open_monitor",
        position_id="shadow_monitor_fixture",
        action="open",
        expression_id=validation.expression_id,
        expression_version=validation.expression_version,
        expression_hash=validation.expression_hash,
        binding=validation.binding,
        symbol="DEMO",
        quantity=Decimal("10"),
        committed_at=datetime(2026, 8, 23, 14, 0, 6, tzinfo=UTC),
        policy_version=fill_policy.version,
    )
    open_fill = evaluate_shadow_fill(open_intent, quotes()["entry"], fill_policy)
    thesis = PositionThesis(
        thesis_id="thesis_monitor_fixture",
        position_id=open_intent.position_id,
        expression_id=open_intent.expression_id,
        expression_version=open_intent.expression_version,
        expression_hash=open_intent.expression_hash,
        binding=open_intent.binding,
        known_at=open_fill.known_at,
        entry_expectation="The fixed catalyst changes forward expectations.",
        why_now="Versioned evidence arrived before entry.",
        invalidation_condition="The measured catalyst reverses.",
        time_exit_at=datetime(2026, 8, 30, 14, tzinfo=UTC),
        next_catalyst="Next fixed fixture update.",
        better_opportunity_min_bps=Decimal("75"),
    )
    observation = MonitorObservation(
        observation_id="observation_exit_fixture",
        position_id=thesis.position_id,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        thesis_hash=thesis.hash(),
        binding=thesis.binding,
        known_at=datetime(2026, 8, 30, 14, 0, 13, tzinfo=UTC),
        quote=quotes()["exit"],
        falsifier_triggered=True,
        better_opportunity_advantage_bps=Decimal("100"),
    )
    decision = monitor_position(thesis, observation, MonitorPolicy())
    close_intent = ShadowIntent(
        intent_id="intent_close_monitor",
        position_id=thesis.position_id,
        action="close",
        expression_id=thesis.expression_id,
        expression_version=thesis.expression_version,
        expression_hash=thesis.expression_hash,
        binding=thesis.binding,
        symbol="DEMO",
        quantity=Decimal("10"),
        committed_at=datetime(2026, 8, 30, 14, 0, 14, tzinfo=UTC),
        policy_version=fill_policy.version,
    )
    close_quote = quotes()["exit"].model_copy(
        update={
            "as_of": datetime(2026, 8, 30, 14, 0, 15, tzinfo=UTC),
            "known_at": datetime(2026, 8, 30, 14, 0, 16, tzinfo=UTC),
            "raw_id": "raw_quote_close",
            "content_hash": "1" * 64,
        }
    )
    close_fill = evaluate_shadow_fill(close_intent, close_quote, fill_policy)
    open_ledger = open_ledger_transaction(open_fill)
    cost_basis = next(
        line.debit for line in open_ledger.lines if line.account == "position"
    )
    close_ledger = close_ledger_transaction(close_fill, position_cost_basis=cost_basis)

    assert (decision.action, decision.reason_code) == (
        "exit",
        "thesis_invalidated",
    )
    assert close_fill.fill_price < close_quote.bid
    assert sum(line.debit for line in close_ledger.lines) == sum(
        line.credit for line in close_ledger.lines
    )
    assert close_ledger.quantity_delta == Decimal("-10")
