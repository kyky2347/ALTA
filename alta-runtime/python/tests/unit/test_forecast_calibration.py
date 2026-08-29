from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alta_asterism.forecast_calibration import (
    ForecastCalibrationObservation,
    ForecastCalibrationPolicy,
    evaluate_forecast_calibration,
)


NOW = datetime(2026, 8, 29, tzinfo=UTC)


def observations(
    count: int,
    *,
    expected: Decimal = Decimal("100"),
    realized: Decimal = Decimal("20"),
) -> tuple[ForecastCalibrationObservation, ...]:
    return tuple(
        ForecastCalibrationObservation(
            position_id=f"position-{index}",
            known_at=NOW + timedelta(days=index),
            expected_alpha_bps=expected,
            realized_alpha_bps=realized,
        )
        for index in range(count)
    )


def test_small_forward_sample_is_descriptive_and_cannot_change_underwriting() -> None:
    result = evaluate_forecast_calibration(
        observations(29),
        source_portfolio_policy_version="alta-portfolio-risk-v7",
    )

    assert result.posture == "collecting"
    assert result.alpha_reserve_bps == 0
    assert result.capital_multiplier == 1
    assert result.sample_size == 29


def test_mature_overforecasting_builds_a_downside_only_alpha_reserve() -> None:
    result = evaluate_forecast_calibration(
        observations(30),
        source_portfolio_policy_version="alta-portfolio-risk-v7",
    )

    assert result.posture == "calibrated"
    assert result.mean_forecast_error_bps == Decimal("-80")
    assert result.mean_absolute_error_bps == Decimal("80")
    assert result.alpha_reserve_bps == Decimal("100")
    assert result.capital_multiplier == 1


def test_calibration_never_rewards_favorable_bias_with_negative_reserve() -> None:
    result = evaluate_forecast_calibration(
        observations(30, expected=Decimal("100"), realized=Decimal("200")),
        source_portfolio_policy_version="alta-portfolio-risk-v7",
    )

    assert result.mean_forecast_error_bps == Decimal("100")
    assert result.alpha_reserve_bps == Decimal("25")
    assert result.capital_multiplier == 1


def test_weak_directional_calibration_tightens_but_never_levers_capital() -> None:
    mixed = tuple(
        ForecastCalibrationObservation(
            position_id=f"position-{index}",
            known_at=NOW + timedelta(days=index),
            expected_alpha_bps=Decimal("100"),
            realized_alpha_bps=Decimal("50") if index < 10 else Decimal("-50"),
        )
        for index in range(30)
    )
    result = evaluate_forecast_calibration(
        mixed,
        source_portfolio_policy_version="alta-portfolio-risk-v7",
    )

    assert result.posture == "caution"
    assert result.directional_hit_rate == Decimal(1) / Decimal(3)
    assert result.capital_multiplier == Decimal("0.50")
    assert result.alpha_reserve_bps > 0


def test_calibration_is_point_in_time_and_uses_only_the_bounded_latest_window() -> None:
    policy = ForecastCalibrationPolicy(window_size=30, minimum_sample=30)
    result = evaluate_forecast_calibration(
        observations(45),
        source_portfolio_policy_version="alta-portfolio-risk-v7",
        policy=policy,
        total_sample_size=100,
    )

    assert result.sample_size == 100
    assert result.window_size == 30
    assert result.observed_through == NOW + timedelta(days=44)


def test_calibration_rejects_duplicate_or_timeless_evidence() -> None:
    duplicate = observations(1) * 2
    with pytest.raises(ValueError, match="unique"):
        evaluate_forecast_calibration(
            duplicate,
            source_portfolio_policy_version="alta-portfolio-risk-v7",
        )

    timeless = (
        ForecastCalibrationObservation(
            position_id="timeless",
            known_at=datetime(2026, 8, 29),
            expected_alpha_bps=Decimal("100"),
            realized_alpha_bps=Decimal("50"),
        ),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_forecast_calibration(
            timeless,
            source_portfolio_policy_version="alta-portfolio-risk-v7",
        )
