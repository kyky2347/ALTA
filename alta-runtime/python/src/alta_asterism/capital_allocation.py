from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal, NamedTuple

from pydantic import Field, model_validator

from .expression_base import FrozenContract
from .implementation import TradeImplementationPlan

_BPS_QUANTUM = Decimal("0.0001")


class _RotationCandidate(NamedTuple):
    incumbent: "IncumbentAlpha"
    remaining_alpha_bps: Decimal
    remaining_alpha_dollars: Decimal
    stress_efficiency: Decimal
    advantage_bps: Decimal
    efficiency_improvement: Decimal


class IncumbentAlpha(FrozenContract):
    position_id: str = Field(min_length=3, max_length=128)
    entered_at: datetime
    time_exit_at: datetime
    expected_net_alpha_bps_at_entry: Decimal | None = None
    replacement_hurdle_bps: Decimal = Field(ge=0)
    current_notional: Decimal | None = Field(default=None, gt=0)
    estimated_stress_loss: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_times(self) -> "IncumbentAlpha":
        for value in (self.entered_at, self.time_exit_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("incumbent Alpha times must be timezone-aware")
        if self.time_exit_at <= self.entered_at:
            raise ValueError("incumbent exit must follow entry")
        return self


class CapitalAllocationDecision(FrozenContract):
    version: Literal["alta-capital-competition-v2"] = "alta-capital-competition-v2"
    status: Literal["admit", "wait", "rotate"]
    known_at: datetime
    open_positions: int = Field(ge=0)
    max_open_positions: int = Field(ge=1, le=8)
    candidate_expected_net_alpha_bps: Decimal | None = None
    candidate_expected_alpha_dollars: Decimal | None = None
    candidate_stress_efficiency: Decimal | None = None
    incumbent_position_id: str | None = None
    incumbent_remaining_alpha_bps: Decimal | None = None
    incumbent_remaining_alpha_dollars: Decimal | None = None
    incumbent_stress_efficiency: Decimal | None = None
    advantage_bps: Decimal | None = None
    required_advantage_bps: Decimal | None = Field(default=None, ge=0)
    efficiency_improvement: Decimal | None = None
    required_efficiency_improvement: Decimal | None = Field(default=None, ge=0)
    reason_code: str = Field(min_length=1, max_length=96)

    @model_validator(mode="after")
    def validate_decision(self) -> "CapitalAllocationDecision":
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("capital allocation known_at must be timezone-aware")
        if self.status == "rotate" and any(
            value is None
            for value in (
                self.incumbent_position_id,
                self.incumbent_remaining_alpha_bps,
                self.advantage_bps,
                self.required_advantage_bps,
                self.candidate_expected_alpha_dollars,
                self.candidate_stress_efficiency,
                self.incumbent_remaining_alpha_dollars,
                self.incumbent_stress_efficiency,
                self.efficiency_improvement,
                self.required_efficiency_improvement,
            )
        ):
            raise ValueError("rotation requires a complete incumbent comparison")
        return self


def allocate_capital(
    *,
    plan: TradeImplementationPlan | None,
    incumbents: tuple[IncumbentAlpha, ...],
    max_open_positions: int,
    known_at: datetime,
    min_efficiency_improvement: Decimal = Decimal("0.10"),
) -> CapitalAllocationDecision:
    """Admits free capacity or rotates through return and stress-capital hurdles."""

    if not Decimal(0) <= min_efficiency_improvement <= Decimal(5):
        raise ValueError("minimum efficiency improvement must be between zero and five")

    candidate_alpha = _candidate_alpha(plan)
    candidate_metrics = _risk_metrics(
        candidate_alpha,
        plan.target_notional if plan is not None else None,
        plan.estimated_stress_loss if plan is not None else None,
    )
    common = {
        "known_at": known_at,
        "open_positions": len(incumbents),
        "max_open_positions": max_open_positions,
        "candidate_expected_net_alpha_bps": candidate_alpha,
        "candidate_expected_alpha_dollars": (
            candidate_metrics[0] if candidate_metrics is not None else None
        ),
        "candidate_stress_efficiency": (
            candidate_metrics[1] if candidate_metrics is not None else None
        ),
    }
    if plan is None or plan.status != "ready" or candidate_alpha is None:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="candidate_alpha_unavailable",
            **common,
        )
    if candidate_metrics is None:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="candidate_risk_capital_unavailable",
            **common,
        )
    if len(incumbents) < max_open_positions:
        return CapitalAllocationDecision(
            status="admit",
            reason_code="portfolio_capacity_available",
            **common,
        )
    if len(incumbents) > max_open_positions:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="portfolio_position_limit_breached",
            **common,
        )
    residuals = tuple(
        (
            incumbent,
            _remaining_alpha(incumbent, known_at),
        )
        for incumbent in incumbents
    )
    unavailable = next(
        (incumbent for incumbent, residual in residuals if residual is None),
        None,
    )
    if unavailable is not None:
        return CapitalAllocationDecision(
            status="wait",
            incumbent_position_id=unavailable.position_id,
            reason_code="incumbent_alpha_unavailable",
            **common,
        )
    comparisons = tuple(
        (
            incumbent,
            residual,
            _risk_metrics(
                residual,
                incumbent.current_notional,
                incumbent.estimated_stress_loss,
            ),
        )
        for incumbent, residual in residuals
    )
    risk_unavailable = next(
        (incumbent for incumbent, _, metrics in comparisons if metrics is None), None
    )
    if risk_unavailable is not None:
        return CapitalAllocationDecision(
            status="wait",
            incumbent_position_id=risk_unavailable.position_id,
            reason_code="incumbent_risk_capital_unavailable",
            **common,
        )
    candidate_alpha_dollars, candidate_efficiency = candidate_metrics
    rotation_candidates = tuple(
        sorted(
            (
                _rotation_candidate(
                    incumbent=incumbent,
                    remaining_alpha_bps=residual,
                    incumbent_metrics=metrics,
                    candidate_alpha_bps=candidate_alpha,
                    candidate_efficiency=candidate_efficiency,
                )
                for incumbent, residual, metrics in comparisons
                if residual is not None and metrics is not None
            ),
            key=lambda item: (
                item.stress_efficiency,
                item.remaining_alpha_dollars,
                item.incumbent.position_id,
            ),
        )
    )
    eligible = next(
        (
            item
            for item in rotation_candidates
            if item.advantage_bps >= item.incumbent.replacement_hurdle_bps
            and candidate_alpha_dollars >= item.remaining_alpha_dollars
            and item.efficiency_improvement >= min_efficiency_improvement
        ),
        None,
    )
    selected = eligible or rotation_candidates[0]
    comparison = _comparison_fields(selected, min_efficiency_improvement)
    if eligible is not None:
        return CapitalAllocationDecision(
            status="rotate",
            reason_code="superior_audited_opportunity",
            **common,
            **comparison,
        )
    if selected.advantage_bps < selected.incumbent.replacement_hurdle_bps:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="portfolio_alpha_hurdle_not_cleared",
            **common,
            **comparison,
        )
    if candidate_alpha_dollars < selected.remaining_alpha_dollars:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="portfolio_expected_alpha_dollars_not_improved",
            **common,
            **comparison,
        )
    return CapitalAllocationDecision(
        status="wait",
        reason_code="portfolio_stress_efficiency_not_improved",
        **common,
        **comparison,
    )


def _candidate_alpha(plan: TradeImplementationPlan | None) -> Decimal | None:
    if plan is None:
        return None
    if plan.alpha_clock is not None:
        return plan.alpha_clock.time_adjusted_expected_net_alpha_bps
    return plan.expected_net_alpha_bps


def _remaining_alpha(incumbent: IncumbentAlpha, known_at: datetime) -> Decimal | None:
    if incumbent.expected_net_alpha_bps_at_entry is None:
        return None
    total_seconds = Decimal(
        str((incumbent.time_exit_at - incumbent.entered_at).total_seconds())
    )
    remaining_seconds = Decimal(
        str(
            max(
                0,
                (
                    incumbent.time_exit_at - max(known_at, incumbent.entered_at)
                ).total_seconds(),
            )
        )
    )
    return (
        incumbent.expected_net_alpha_bps_at_entry * remaining_seconds / total_seconds
    ).quantize(_BPS_QUANTUM, rounding=ROUND_HALF_EVEN)


def _risk_metrics(
    expected_alpha_bps: Decimal | None,
    notional: Decimal | None,
    stress_loss: Decimal | None,
) -> tuple[Decimal, Decimal] | None:
    if (
        expected_alpha_bps is None
        or notional is None
        or notional <= 0
        or stress_loss is None
        or stress_loss <= 0
    ):
        return None
    expected_alpha_dollars = (notional * expected_alpha_bps / Decimal(10_000)).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    efficiency = (expected_alpha_dollars / stress_loss).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    return expected_alpha_dollars, efficiency


def _efficiency_improvement(candidate: Decimal, incumbent: Decimal) -> Decimal:
    if incumbent <= 0:
        return Decimal(5) if candidate > incumbent else Decimal(0)
    return ((candidate / incumbent) - Decimal(1)).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )


def _rotation_candidate(
    *,
    incumbent: IncumbentAlpha,
    remaining_alpha_bps: Decimal,
    incumbent_metrics: tuple[Decimal, Decimal],
    candidate_alpha_bps: Decimal,
    candidate_efficiency: Decimal,
) -> _RotationCandidate:
    remaining_alpha_dollars, incumbent_efficiency = incumbent_metrics
    return _RotationCandidate(
        incumbent=incumbent,
        remaining_alpha_bps=remaining_alpha_bps,
        remaining_alpha_dollars=remaining_alpha_dollars,
        stress_efficiency=incumbent_efficiency,
        advantage_bps=(candidate_alpha_bps - remaining_alpha_bps).quantize(
            _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
        ),
        efficiency_improvement=_efficiency_improvement(
            candidate_efficiency, incumbent_efficiency
        ),
    )


def _comparison_fields(
    candidate: _RotationCandidate, required_efficiency: Decimal
) -> dict[str, str | Decimal]:
    return {
        "incumbent_position_id": candidate.incumbent.position_id,
        "incumbent_remaining_alpha_bps": candidate.remaining_alpha_bps,
        "advantage_bps": candidate.advantage_bps,
        "required_advantage_bps": candidate.incumbent.replacement_hurdle_bps,
        "incumbent_remaining_alpha_dollars": candidate.remaining_alpha_dollars,
        "incumbent_stress_efficiency": candidate.stress_efficiency,
        "efficiency_improvement": candidate.efficiency_improvement,
        "required_efficiency_improvement": required_efficiency,
    }
