from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alta_asterism.alpha_governance import (
    CapitalPerformanceObservation,
    evaluate_alpha_capital_governance,
)


NOW = datetime(2026, 8, 26, 14, tzinfo=UTC)


def observations(
    alphas: tuple[Decimal, ...],
    *,
    pnl: tuple[Decimal, ...] | None = None,
    prefix: str = "position",
) -> tuple[CapitalPerformanceObservation, ...]:
    pnl = pnl or tuple(Decimal("100") for _ in alphas)
    return tuple(
        CapitalPerformanceObservation(
            position_id=f"{prefix}_{index}",
            known_at=NOW + timedelta(days=index),
            net_pnl=pnl[index],
            realized_alpha_bps=alpha,
        )
        for index, alpha in enumerate(alphas)
    )


def evaluate(values: tuple[CapitalPerformanceObservation, ...]):
    return evaluate_alpha_capital_governance(
        values,
        reference_nav=Decimal("1000000"),
        source_portfolio_policy_version="alta-portfolio-risk-v8",
    )


def test_unproven_forward_sample_stays_at_collecting_size() -> None:
    result = evaluate(())

    assert result.posture == "collecting"
    assert result.capital_multiplier == Decimal("0.50")
    assert result.reason_codes == ("forward_alpha_sample_collecting",)


def test_recent_negative_alpha_moves_the_book_to_probation() -> None:
    result = evaluate(observations(tuple(Decimal("-5") for _ in range(10))))

    assert result.posture == "probation"
    assert result.capital_multiplier == Decimal("0.50")
    assert "recent_mean_alpha_negative" in result.reason_codes


def test_mature_negative_alpha_keeps_only_an_exploration_budget() -> None:
    result = evaluate(
        observations(tuple(Decimal(-100 - index % 3) for index in range(30)))
    )

    assert result.posture == "preservation"
    assert result.capital_multiplier == Decimal("0.10")
    assert "negative_alpha_confidence_interval" in result.reason_codes


def test_rolling_drawdown_triggers_capital_preservation_before_maturity() -> None:
    result = evaluate(
        observations(
            (Decimal("100"), Decimal("100")),
            pnl=(Decimal("1000"), Decimal("-12000")),
        )
    )

    assert result.max_drawdown_nav_bps == Decimal("120")
    assert result.posture == "preservation"
    assert result.capital_multiplier == Decimal("0.10")
    assert "rolling_shadow_drawdown_limit" in result.reason_codes


def test_positive_evidence_restores_normal_but_never_bonus_capital() -> None:
    negative = observations(
        tuple(Decimal("-100") for _ in range(30)),
        pnl=tuple(Decimal("-100") for _ in range(30)),
        prefix="old",
    )
    positive = tuple(
        CapitalPerformanceObservation(
            position_id=f"new_{index}",
            known_at=NOW + timedelta(days=30 + index),
            net_pnl=Decimal("100"),
            realized_alpha_bps=Decimal(100 + index % 3),
        )
        for index in range(30)
    )

    result = evaluate(negative + positive)

    assert result.sample_size == 60
    assert result.window_size == 30
    assert result.posture == "normal"
    assert result.capital_multiplier == Decimal(1)
    assert result.evidence_posture == "positive_signal_requires_external_validation"


def test_duplicate_positions_cannot_inflate_the_governance_sample() -> None:
    item = observations((Decimal("10"),))[0]

    with pytest.raises(ValueError, match="unique by position"):
        evaluate((item, item))
