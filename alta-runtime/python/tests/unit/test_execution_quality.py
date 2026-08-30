from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from alta_asterism.execution_quality import (
    ExecutionCostObservation,
    build_position_execution_quality,
    evaluate_execution_cost_governance,
    summarize_execution_quality,
)
from alta_asterism.expression import (
    EvidenceVersion,
    QuoteSnapshot,
    VersionBinding,
    contract_hash,
)
from alta_asterism.shadow import ShadowFill
from alta_asterism.position_performance import _execution_quality


NOW = datetime(2026, 8, 29, 14, tzinfo=UTC)


def binding() -> VersionBinding:
    evidence = (
        EvidenceVersion(
            evidence_id="evidence_execution_quality",
            version=1,
            known_at=NOW - timedelta(minutes=5),
        ),
    )
    return VersionBinding(
        environment="shadow",
        opportunity_id="opportunity_execution_quality",
        opportunity_version=1,
        opportunity_snapshot_hash="a" * 64,
        evidence=evidence,
        evidence_set_hash=contract_hash(
            [item.model_dump(mode="json") for item in evidence]
        ),
    )


def fill(action: str, *, bid: str, ask: str, price: str, commission: str) -> ShadowFill:
    known_at = NOW + timedelta(minutes=1 if action == "open" else 30)
    quote = QuoteSnapshot(
        symbol="DEMO",
        bid=Decimal(bid),
        ask=Decimal(ask),
        as_of=known_at - timedelta(seconds=1),
        known_at=known_at,
        raw_id=f"raw_{action}_execution_quality",
        raw_version=1,
        content_hash=("b" if action == "open" else "c") * 64,
    )
    return ShadowFill(
        fill_id=f"fill_{action}_execution_quality",
        intent_id=f"intent_{action}_execution_quality",
        position_id="position_execution_quality",
        action=action,  # type: ignore[arg-type]
        binding=binding(),
        status="filled",
        reason_code="forward_fixture_fill",
        known_at=known_at,
        quote=quote,
        quantity=Decimal("10"),
        fill_price=Decimal(price),
        commission=Decimal(commission),
        fill_model_version="b8-shadow-fill-v2",
    )


def observations(
    count: int, *, estimated: str = "20", realized: str = "30"
) -> tuple[ExecutionCostObservation, ...]:
    return tuple(
        ExecutionCostObservation(
            position_id=f"position-{index}",
            known_at=NOW + timedelta(days=index),
            estimated_cost_bps=Decimal(estimated),
            realized_cost_bps=Decimal(realized),
        )
        for index in range(count)
    )


def test_round_trip_quality_uses_arrival_midpoints_and_both_commissions() -> None:
    result = build_position_execution_quality(
        estimated_cost_bps=Decimal("205"),
        entry_fill=fill("open", bid="99", ask="101", price="101.05", commission="0.10"),
        exit_fill=fill(
            "close", bid="109", ask="111", price="108.95", commission="0.10"
        ),
    )

    assert result.entry_shortfall_bps == Decimal("105.00")
    assert result.exit_shortfall_bps == Decimal("95.45")
    assert result.realized_cost_bps > Decimal("202")
    assert result.within_cost_budget is True
    assert result.mean_quoted_spread_bps > 0


def test_performance_projection_reads_the_durable_open_and_close_fills() -> None:
    entry = fill("open", bid="99", ask="101", price="101.05", commission="0.10")
    exit_fill = fill("close", bid="109", ask="111", price="108.95", commission="0.10")
    thesis = SimpleNamespace(
        implementation_plan=SimpleNamespace(estimated_cost_bps=Decimal("205"))
    )

    result = _execution_quality(
        thesis,  # type: ignore[arg-type]
        [
            (entry.model_dump(mode="json"),),
            (exit_fill.model_dump(mode="json"),),
        ],
    )

    assert result is not None
    assert result.realized_cost_bps > 0
    assert result.entry_shortfall_bps == Decimal("105.00")
    assert result.exit_shortfall_bps == Decimal("95.45")


def test_small_execution_sample_is_descriptive_and_cannot_change_edge() -> None:
    result = evaluate_execution_cost_governance(
        observations(29),
        source_portfolio_policy_version="alta-portfolio-risk-v8",
        expression_kind="stock",
    )

    assert result.posture == "collecting"
    assert result.alpha_reserve_bps == 0
    assert result.sample_size == 29


def test_mature_cost_overrun_builds_a_downside_only_reserve() -> None:
    result = evaluate_execution_cost_governance(
        observations(30),
        source_portfolio_policy_version="alta-portfolio-risk-v8",
        expression_kind="stock",
    )

    assert result.posture == "calibrated"
    assert result.mean_cost_surprise_bps == Decimal("10")
    assert result.within_budget_rate == 0
    assert result.alpha_reserve_bps == Decimal("12.50")


def test_favorable_costs_never_create_a_negative_alpha_reserve() -> None:
    result = evaluate_execution_cost_governance(
        observations(30, estimated="30", realized="20"),
        source_portfolio_policy_version="alta-portfolio-risk-v8",
        expression_kind="stock",
    )

    assert result.mean_cost_surprise_bps == Decimal("-10")
    assert result.alpha_reserve_bps == Decimal("2.50")


def test_execution_summary_keeps_fill_reliability_separate_from_cost_tca() -> None:
    quality = build_position_execution_quality(
        estimated_cost_bps=Decimal("205"),
        entry_fill=fill("open", bid="99", ask="101", price="101.05", commission="0.10"),
        exit_fill=fill(
            "close", bid="109", ask="111", price="108.95", commission="0.10"
        ),
    )
    summary = summarize_execution_quality(
        (quality,), open_fills=3, open_no_fills=1, exit_fills=2, exit_no_fills=1
    )

    assert summary["posture"] == "collecting"
    assert summary["openFillRate"] == "0.7500"
    assert summary["openNoFills"] == 1
    assert summary["exitNoFills"] == 1


def test_execution_governance_rejects_duplicate_or_naive_observations() -> None:
    duplicate = observations(1)[0]
    with pytest.raises(ValueError, match="unique"):
        evaluate_execution_cost_governance(
            (duplicate, duplicate),
            source_portfolio_policy_version="alta-portfolio-risk-v8",
            expression_kind="stock",
        )
    with pytest.raises(ValueError, match="timezone"):
        evaluate_execution_cost_governance(
            (
                ExecutionCostObservation(
                    position_id="naive",
                    known_at=datetime(2026, 8, 29),
                    estimated_cost_bps=Decimal("10"),
                    realized_cost_bps=Decimal("10"),
                ),
            ),
            source_portfolio_policy_version="alta-portfolio-risk-v8",
            expression_kind="stock",
        )
