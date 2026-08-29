from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract

_BPS = Decimal(10_000)
_BPS_QUANTUM = Decimal("0.01")
_RATIO_QUANTUM = Decimal("0.0001")
MINIMUM_DIAGNOSTIC_SAMPLE = 30


class ExecutablePathObservation(FrozenContract):
    """One point-in-time price that could have been used to exit a long."""

    known_at: datetime
    executable_price: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_time(self) -> "ExecutablePathObservation":
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("path observation known_at must be timezone-aware")
        return self


class PositionPathDiagnostics(FrozenContract):
    """Observed long-position path quality; descriptive and never a trade rule."""

    version: Literal["alta-path-diagnostics-v1"] = "alta-path-diagnostics-v1"
    price_observations: int = Field(ge=1)
    opened_at: datetime
    closed_at: datetime
    maximum_favorable_excursion_bps: Decimal = Field(ge=0)
    maximum_adverse_excursion_bps: Decimal = Field(le=0)
    maximum_drawdown_bps: Decimal = Field(ge=0)
    net_return_bps: Decimal
    exit_capture_ratio: Decimal | None = None
    time_to_best_seconds: int = Field(ge=0)
    holding_seconds: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_interval(self) -> "PositionPathDiagnostics":
        for name, value in (
            ("opened_at", self.opened_at),
            ("closed_at", self.closed_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.closed_at < self.opened_at:
            raise ValueError("path diagnostics close cannot precede open")
        if self.time_to_best_seconds > self.holding_seconds:
            raise ValueError("best observation cannot occur after the holding interval")
        return self


def build_position_path_diagnostics(
    *,
    entry_price: Decimal,
    opened_at: datetime,
    observations: tuple[ExecutablePathObservation, ...],
    exit_price: Decimal,
    closed_at: datetime,
    net_return_bps: Decimal,
) -> PositionPathDiagnostics:
    """Measure the observed executable path without inventing intraperiod prices."""

    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("path prices must be positive")
    if closed_at < opened_at:
        raise ValueError("path close cannot precede open")

    bounded = tuple(
        sorted(
            (item for item in observations if opened_at <= item.known_at <= closed_at),
            key=lambda item: (item.known_at, item.executable_price),
        )
    )
    points = (
        (opened_at, entry_price),
        *((item.known_at, item.executable_price) for item in bounded),
        (closed_at, exit_price),
    )
    returns = tuple(
        (known_at, _return_bps(price, entry_price)) for known_at, price in points
    )
    maximum_favorable = max(value for _, value in returns)
    maximum_adverse = min(value for _, value in returns)
    best_at = next(
        known_at for known_at, value in returns if value == maximum_favorable
    )
    peak = returns[0][1]
    maximum_drawdown = Decimal(0)
    for _, value in returns[1:]:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, peak - value)
    exit_capture = (
        (net_return_bps / maximum_favorable).quantize(
            _RATIO_QUANTUM, rounding=ROUND_HALF_EVEN
        )
        if maximum_favorable > 0
        else None
    )
    return PositionPathDiagnostics(
        price_observations=len(bounded) + 1,
        opened_at=opened_at,
        closed_at=closed_at,
        maximum_favorable_excursion_bps=maximum_favorable,
        maximum_adverse_excursion_bps=maximum_adverse,
        maximum_drawdown_bps=maximum_drawdown,
        net_return_bps=net_return_bps.quantize(_BPS_QUANTUM),
        exit_capture_ratio=exit_capture,
        time_to_best_seconds=max(0, int((best_at - opened_at).total_seconds())),
        holding_seconds=max(0, int((closed_at - opened_at).total_seconds())),
    )


def summarize_path_diagnostics(
    values: tuple[PositionPathDiagnostics, ...],
) -> dict[str, object]:
    """Aggregate forward path evidence without converting it into an optimizer."""

    measured = len(values)
    capture_values = tuple(
        item.exit_capture_ratio
        for item in values
        if item.exit_capture_ratio is not None
    )
    positive_excursions = tuple(
        item for item in values if item.maximum_favorable_excursion_bps > 0
    )
    missed_positive = sum(item.net_return_bps <= 0 for item in positive_excursions)
    posture = (
        "unmeasured"
        if measured == 0
        else "collecting"
        if measured < MINIMUM_DIAGNOSTIC_SAMPLE
        else "diagnostic"
    )
    return {
        "posture": posture,
        "measuredPositions": measured,
        "minimumSample": MINIMUM_DIAGNOSTIC_SAMPLE,
        "meanMaximumFavorableExcursionBps": _mean_text(
            tuple(item.maximum_favorable_excursion_bps for item in values)
        ),
        "meanMaximumAdverseExcursionBps": _mean_text(
            tuple(item.maximum_adverse_excursion_bps for item in values)
        ),
        "meanMaximumDrawdownBps": _mean_text(
            tuple(item.maximum_drawdown_bps for item in values)
        ),
        "meanExitCaptureRatio": _mean_text(capture_values, quantum=_RATIO_QUANTUM),
        "positiveExcursionMissRate": (
            str(
                (Decimal(missed_positive) / Decimal(len(positive_excursions))).quantize(
                    _RATIO_QUANTUM, rounding=ROUND_HALF_EVEN
                )
            )
            if positive_excursions
            else None
        ),
        "warning": (
            "Path diagnostics are unavailable until a position has an observed exit."
            if measured == 0
            else "Observed excursions are sparse decision diagnostics, not intraday backtest data or an automatic exit rule."
        ),
    }


def _return_bps(price: Decimal, entry_price: Decimal) -> Decimal:
    return ((price - entry_price) / entry_price * _BPS).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )


def _mean_text(
    values: tuple[Decimal, ...], *, quantum: Decimal = _BPS_QUANTUM
) -> str | None:
    if not values:
        return None
    return str(
        (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
            quantum, rounding=ROUND_HALF_EVEN
        )
    )
