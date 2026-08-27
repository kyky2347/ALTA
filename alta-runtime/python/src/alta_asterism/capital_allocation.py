from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract
from .implementation import TradeImplementationPlan

_BPS_QUANTUM = Decimal("0.0001")


class IncumbentAlpha(FrozenContract):
    position_id: str = Field(min_length=3, max_length=128)
    entered_at: datetime
    time_exit_at: datetime
    expected_net_alpha_bps_at_entry: Decimal | None = None
    replacement_hurdle_bps: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_times(self) -> "IncumbentAlpha":
        for value in (self.entered_at, self.time_exit_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("incumbent Alpha times must be timezone-aware")
        if self.time_exit_at <= self.entered_at:
            raise ValueError("incumbent exit must follow entry")
        return self


class CapitalAllocationDecision(FrozenContract):
    version: Literal["alta-capital-competition-v1"] = "alta-capital-competition-v1"
    status: Literal["admit", "wait", "rotate"]
    known_at: datetime
    open_positions: int = Field(ge=0)
    max_open_positions: int = Field(ge=1, le=8)
    candidate_expected_net_alpha_bps: Decimal | None = None
    incumbent_position_id: str | None = None
    incumbent_remaining_alpha_bps: Decimal | None = None
    advantage_bps: Decimal | None = None
    required_advantage_bps: Decimal | None = Field(default=None, ge=0)
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
) -> CapitalAllocationDecision:
    """Admits free capacity or rotates only through a measurable Alpha hurdle."""

    candidate_alpha = _candidate_alpha(plan)
    common = {
        "known_at": known_at,
        "open_positions": len(incumbents),
        "max_open_positions": max_open_positions,
        "candidate_expected_net_alpha_bps": candidate_alpha,
    }
    if plan is None or plan.status != "ready" or candidate_alpha is None:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="candidate_alpha_unavailable",
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
        (incumbent, _remaining_alpha(incumbent, known_at)) for incumbent in incumbents
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
    incumbent, residual = min(
        residuals,
        key=lambda item: (
            item[1] if item[1] is not None else Decimal("Infinity"),
            item[0].position_id,
        ),
    )
    if residual is None:
        raise ValueError("unavailable incumbent Alpha escaped its gate")
    advantage = (candidate_alpha - residual).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    comparison = {
        "incumbent_position_id": incumbent.position_id,
        "incumbent_remaining_alpha_bps": residual,
        "advantage_bps": advantage,
        "required_advantage_bps": incumbent.replacement_hurdle_bps,
    }
    if advantage < incumbent.replacement_hurdle_bps:
        return CapitalAllocationDecision(
            status="wait",
            reason_code="portfolio_alpha_hurdle_not_cleared",
            **common,
            **comparison,
        )
    return CapitalAllocationDecision(
        status="rotate",
        reason_code="superior_audited_opportunity",
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
