from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract

if TYPE_CHECKING:
    from .shadow import ShadowFill

_BPS = Decimal(10_000)
_BPS_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")


class PositionExecutionQuality(FrozenContract):
    """Entry/exit implementation shortfall frozen at the position close."""

    version: Literal["alta-execution-quality-v1"] = "alta-execution-quality-v1"
    estimated_cost_bps: Decimal = Field(ge=0)
    realized_cost_bps: Decimal = Field(ge=0)
    cost_surprise_bps: Decimal
    entry_shortfall_bps: Decimal
    exit_shortfall_bps: Decimal
    entry_commission_bps: Decimal = Field(ge=0)
    exit_commission_bps: Decimal = Field(ge=0)
    mean_quoted_spread_bps: Decimal = Field(ge=0)
    within_cost_budget: bool


@dataclass(frozen=True)
class ExecutionCostObservation:
    position_id: str
    known_at: datetime
    estimated_cost_bps: Decimal
    realized_cost_bps: Decimal


class ExecutionCostPolicy(FrozenContract):
    """One-sided reserve policy learned only from completed forward executions."""

    version: Literal["alta-execution-cost-governance-v1"] = (
        "alta-execution-cost-governance-v1"
    )
    window_size: int = Field(default=60, ge=30, le=250)
    minimum_sample: int = Field(default=30, ge=20, le=250)
    surprise_reserve_fraction: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    maximum_reserve_bps: Decimal = Field(default=Decimal("500"), ge=0)

    @model_validator(mode="after")
    def validate_policy(self) -> "ExecutionCostPolicy":
        if self.minimum_sample > self.window_size:
            raise ValueError("execution sample cannot exceed the rolling window")
        return self


class ExecutionCostGovernance(FrozenContract):
    """Frozen empirical cost reserve; it can only preserve or reduce edge."""

    policy_version: str = Field(min_length=3, max_length=64)
    source_portfolio_policy_version: str = Field(min_length=3, max_length=64)
    expression_kind: str = Field(min_length=1, max_length=32)
    posture: Literal["unscoped", "collecting", "calibrated"]
    sample_size: int = Field(ge=0)
    window_size: int = Field(ge=0)
    minimum_sample: int = Field(ge=1)
    mean_estimated_cost_bps: Decimal | None = Field(default=None, ge=0)
    mean_realized_cost_bps: Decimal | None = Field(default=None, ge=0)
    mean_cost_surprise_bps: Decimal | None = None
    mean_absolute_surprise_bps: Decimal | None = Field(default=None, ge=0)
    within_budget_rate: Decimal | None = Field(default=None, ge=0, le=1)
    alpha_reserve_bps: Decimal = Field(default=Decimal(0), ge=0)
    observed_through: datetime | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)

    @classmethod
    def unscoped(
        cls,
        source_portfolio_policy_version: str,
        expression_kind: str,
    ) -> "ExecutionCostGovernance":
        return cls(
            policy_version="alta-execution-cost-governance-v1",
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            posture="unscoped",
            sample_size=0,
            window_size=0,
            minimum_sample=30,
            reason_codes=("execution_cost_governance_not_loaded",),
        )


def build_position_execution_quality(
    *,
    estimated_cost_bps: Decimal,
    entry_fill: "ShadowFill",
    exit_fill: "ShadowFill",
) -> PositionExecutionQuality:
    """Measure adverse implementation shortfall from observed executable quotes."""

    if entry_fill.action != "open" or exit_fill.action != "close":
        raise ValueError("execution quality requires one open and one close fill")
    if entry_fill.position_id != exit_fill.position_id:
        raise ValueError("execution quality fills must belong to one position")
    if estimated_cost_bps < 0:
        raise ValueError("estimated execution cost cannot be negative")

    entry_shortfall, entry_commission, entry_spread = _fill_cost(entry_fill)
    exit_shortfall, exit_commission, exit_spread = _fill_cost(exit_fill)
    realized = entry_shortfall + exit_shortfall + entry_commission + exit_commission
    surprise = realized - estimated_cost_bps
    return PositionExecutionQuality(
        estimated_cost_bps=_quantize(estimated_cost_bps),
        realized_cost_bps=_quantize(realized),
        cost_surprise_bps=_quantize(surprise),
        entry_shortfall_bps=_quantize(entry_shortfall),
        exit_shortfall_bps=_quantize(exit_shortfall),
        entry_commission_bps=_quantize(entry_commission),
        exit_commission_bps=_quantize(exit_commission),
        mean_quoted_spread_bps=_quantize((entry_spread + exit_spread) / Decimal(2)),
        within_cost_budget=realized <= estimated_cost_bps,
    )


def evaluate_execution_cost_governance(
    observations: tuple[ExecutionCostObservation, ...],
    *,
    source_portfolio_policy_version: str,
    expression_kind: str,
    policy: ExecutionCostPolicy | None = None,
    total_sample_size: int | None = None,
) -> ExecutionCostGovernance:
    """Convert mature forward cost surprises into a downside-only Alpha reserve."""

    policy = policy or ExecutionCostPolicy()
    if len({item.position_id for item in observations}) != len(observations):
        raise ValueError("execution observations must be unique by position")
    if total_sample_size is not None and total_sample_size < len(observations):
        raise ValueError("total sample cannot be smaller than the supplied window")
    if any(
        item.known_at.tzinfo is None or item.known_at.utcoffset() is None
        for item in observations
    ):
        raise ValueError("execution observations must be timezone-aware")
    if any(
        item.estimated_cost_bps < 0 or item.realized_cost_bps < 0
        for item in observations
    ):
        raise ValueError("execution costs cannot be negative")

    ordered = tuple(
        sorted(observations, key=lambda item: (item.known_at, item.position_id))
    )
    window = ordered[-policy.window_size :]
    sample_size = len(ordered) if total_sample_size is None else total_sample_size
    estimated = tuple(item.estimated_cost_bps for item in window)
    realized = tuple(item.realized_cost_bps for item in window)
    surprises = tuple(
        item.realized_cost_bps - item.estimated_cost_bps for item in window
    )
    mean_estimated = _mean(estimated)
    mean_realized = _mean(realized)
    mean_surprise = _mean(surprises)
    mean_absolute = _mean(tuple(abs(value) for value in surprises))
    within_budget = (
        Decimal(sum(value <= 0 for value in surprises)) / Decimal(len(surprises))
        if surprises
        else None
    )

    if len(window) < policy.minimum_sample:
        return ExecutionCostGovernance(
            policy_version=policy.version,
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            posture="collecting",
            sample_size=sample_size,
            window_size=len(window),
            minimum_sample=policy.minimum_sample,
            mean_estimated_cost_bps=mean_estimated,
            mean_realized_cost_bps=mean_realized,
            mean_cost_surprise_bps=mean_surprise,
            mean_absolute_surprise_bps=mean_absolute,
            within_budget_rate=within_budget,
            observed_through=window[-1].known_at if window else None,
            reason_codes=("execution_cost_sample_collecting",),
        )

    assert mean_surprise is not None
    assert mean_absolute is not None
    reserve = min(
        policy.maximum_reserve_bps,
        max(Decimal(0), mean_surprise)
        + mean_absolute * policy.surprise_reserve_fraction,
    )
    return ExecutionCostGovernance(
        policy_version=policy.version,
        source_portfolio_policy_version=source_portfolio_policy_version,
        expression_kind=expression_kind,
        posture="calibrated",
        sample_size=sample_size,
        window_size=len(window),
        minimum_sample=policy.minimum_sample,
        mean_estimated_cost_bps=mean_estimated,
        mean_realized_cost_bps=mean_realized,
        mean_cost_surprise_bps=mean_surprise,
        mean_absolute_surprise_bps=mean_absolute,
        within_budget_rate=within_budget,
        alpha_reserve_bps=reserve,
        observed_through=window[-1].known_at,
        reason_codes=(
            ("execution_cost_reserve_applied",)
            if reserve > 0
            else ("execution_cost_budget_conservative",)
        ),
    )


def summarize_execution_quality(
    values: tuple[PositionExecutionQuality, ...],
    *,
    open_fills: int,
    open_no_fills: int,
    exit_fills: int,
    exit_no_fills: int,
) -> dict[str, object]:
    """Aggregate TCA and fill reliability without promoting it into a claim."""

    measured = len(values)
    attempts = open_fills + open_no_fills
    return {
        "posture": (
            "unmeasured"
            if measured == 0
            else "collecting"
            if measured < ExecutionCostPolicy().minimum_sample
            else "diagnostic"
        ),
        "measuredPositions": measured,
        "minimumSample": ExecutionCostPolicy().minimum_sample,
        "meanEstimatedCostBps": _mean_text(
            tuple(item.estimated_cost_bps for item in values)
        ),
        "meanRealizedCostBps": _mean_text(
            tuple(item.realized_cost_bps for item in values)
        ),
        "meanCostSurpriseBps": _mean_text(
            tuple(item.cost_surprise_bps for item in values)
        ),
        "withinBudgetRate": _rate_text(
            sum(item.within_cost_budget for item in values), measured
        ),
        "openFillRate": _rate_text(open_fills, attempts),
        "openFills": open_fills,
        "openNoFills": open_no_fills,
        "exitFills": exit_fills,
        "exitNoFills": exit_no_fills,
        "warning": (
            "Execution quality is unavailable until a position has a complete forward open and close fill."
            if measured == 0
            else "Execution TCA is based on forward Shadow quotes and modeled fills; it is not live-market capacity or broker performance."
        ),
    }


def _fill_cost(fill: "ShadowFill") -> tuple[Decimal, Decimal, Decimal]:
    if fill.status != "filled" or fill.fill_price is None or fill.commission is None:
        raise ValueError("execution quality requires complete filled contracts")
    midpoint = (fill.quote.bid + fill.quote.ask) / Decimal(2)
    if midpoint <= 0:
        raise ValueError("execution quote midpoint must be positive")
    shortfall = (
        (fill.fill_price - midpoint) / midpoint * _BPS
        if fill.action == "open"
        else (midpoint - fill.fill_price) / midpoint * _BPS
    )
    notional = fill.fill_price * fill.quantity
    commission = fill.commission / notional * _BPS
    spread = (fill.quote.ask - fill.quote.bid) / midpoint * _BPS
    return shortfall, commission, spread


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _mean_text(values: tuple[Decimal, ...]) -> str | None:
    value = _mean(values)
    return str(_quantize(value)) if value is not None else None


def _rate_text(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return str(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            _RATE_QUANTUM, rounding=ROUND_HALF_EVEN
        )
    )


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
