from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract


@dataclass(frozen=True)
class ForecastCalibrationObservation:
    """One point-in-time forecast paired with its later forward outcome."""

    position_id: str
    known_at: datetime
    expected_alpha_bps: Decimal
    realized_alpha_bps: Decimal


class ForecastCalibrationPolicy(FrozenContract):
    """Conservative policy for correcting repeated underwriting overconfidence."""

    version: Literal["alta-forecast-calibration-v1"] = "alta-forecast-calibration-v1"
    window_size: int = Field(default=60, ge=30, le=250)
    minimum_sample: int = Field(default=30, ge=20, le=250)
    error_reserve_fraction: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    maximum_reserve_bps: Decimal = Field(default=Decimal("500"), ge=0)
    minimum_directional_hit_rate: Decimal = Field(default=Decimal("0.45"), ge=0, le=1)
    caution_multiplier: Decimal = Field(default=Decimal("0.50"), gt=0, le=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "ForecastCalibrationPolicy":
        if self.minimum_sample > self.window_size:
            raise ValueError("calibration sample cannot exceed the rolling window")
        return self


class ForecastCalibrationGovernance(FrozenContract):
    """Frozen forecast-error reserve; it may only preserve or reduce risk."""

    policy_version: str = Field(min_length=3, max_length=64)
    source_portfolio_policy_version: str = Field(min_length=3, max_length=64)
    expression_kind: str = Field(min_length=1, max_length=32)
    posture: Literal["unscoped", "collecting", "calibrated", "caution"]
    capital_multiplier: Decimal = Field(gt=0, le=1)
    sample_size: int = Field(ge=0)
    window_size: int = Field(ge=0)
    minimum_sample: int = Field(ge=1)
    mean_forecast_error_bps: Decimal | None = None
    mean_absolute_error_bps: Decimal | None = Field(default=None, ge=0)
    directional_hit_rate: Decimal | None = Field(default=None, ge=0, le=1)
    alpha_reserve_bps: Decimal = Field(default=Decimal(0), ge=0)
    observed_through: datetime | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)

    @classmethod
    def unscoped(
        cls,
        source_portfolio_policy_version: str,
        expression_kind: str,
    ) -> "ForecastCalibrationGovernance":
        return cls(
            policy_version="alta-forecast-calibration-v1",
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            posture="unscoped",
            capital_multiplier=Decimal(1),
            sample_size=0,
            window_size=0,
            minimum_sample=30,
            reason_codes=("forecast_calibration_not_scoped",),
        )


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _directional_hit_rate(
    observations: tuple[ForecastCalibrationObservation, ...],
) -> Decimal | None:
    comparable = tuple(
        item
        for item in observations
        if item.expected_alpha_bps != 0 and item.realized_alpha_bps != 0
    )
    if not comparable:
        return None
    hits = sum(
        (item.expected_alpha_bps > 0) == (item.realized_alpha_bps > 0)
        for item in comparable
    )
    return Decimal(hits) / Decimal(len(comparable))


def evaluate_forecast_calibration(
    observations: tuple[ForecastCalibrationObservation, ...],
    *,
    source_portfolio_policy_version: str,
    expression_kind: str = "stock",
    policy: ForecastCalibrationPolicy | None = None,
    total_sample_size: int | None = None,
) -> ForecastCalibrationGovernance:
    """Build a downside-only reserve from comparable, mature forward evidence."""

    policy = policy or ForecastCalibrationPolicy()
    if len({item.position_id for item in observations}) != len(observations):
        raise ValueError("calibration observations must be unique by position")
    if total_sample_size is not None and total_sample_size < len(observations):
        raise ValueError("total sample cannot be smaller than the supplied window")
    if any(
        item.known_at.tzinfo is None or item.known_at.utcoffset() is None
        for item in observations
    ):
        raise ValueError("calibration observations must be timezone-aware")

    ordered = tuple(
        sorted(observations, key=lambda item: (item.known_at, item.position_id))
    )
    window = ordered[-policy.window_size :]
    sample_size = len(ordered) if total_sample_size is None else total_sample_size
    errors = tuple(item.realized_alpha_bps - item.expected_alpha_bps for item in window)
    mean_error = _mean(errors)
    mean_absolute_error = _mean(tuple(abs(value) for value in errors))
    hit_rate = _directional_hit_rate(window)

    if len(window) < policy.minimum_sample:
        return ForecastCalibrationGovernance(
            policy_version=policy.version,
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            posture="collecting",
            capital_multiplier=Decimal(1),
            sample_size=sample_size,
            window_size=len(window),
            minimum_sample=policy.minimum_sample,
            mean_forecast_error_bps=mean_error,
            mean_absolute_error_bps=mean_absolute_error,
            directional_hit_rate=hit_rate,
            alpha_reserve_bps=Decimal(0),
            observed_through=window[-1].known_at if window else None,
            reason_codes=("forecast_calibration_sample_collecting",),
        )

    assert mean_error is not None
    assert mean_absolute_error is not None
    overforecast_bias = max(Decimal(0), -mean_error)
    reserve = min(
        policy.maximum_reserve_bps,
        overforecast_bias + mean_absolute_error * policy.error_reserve_fraction,
    )
    caution = hit_rate is not None and hit_rate < policy.minimum_directional_hit_rate
    return ForecastCalibrationGovernance(
        policy_version=policy.version,
        source_portfolio_policy_version=source_portfolio_policy_version,
        expression_kind=expression_kind,
        posture="caution" if caution else "calibrated",
        capital_multiplier=policy.caution_multiplier if caution else Decimal(1),
        sample_size=sample_size,
        window_size=len(window),
        minimum_sample=policy.minimum_sample,
        mean_forecast_error_bps=mean_error,
        mean_absolute_error_bps=mean_absolute_error,
        directional_hit_rate=hit_rate,
        alpha_reserve_bps=reserve,
        observed_through=window[-1].known_at,
        reason_codes=(
            ("forecast_directional_calibration_weak",)
            if caution
            else ("forecast_error_reserve_applied",)
        ),
    )
