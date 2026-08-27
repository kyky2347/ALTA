from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN, ROUND_UP
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from .alpha_lifecycle import AlphaClock
from .expression_base import FrozenContract


class ExecutableInstrument(Protocol):
    kind: str
    quote: Any
    metadata: dict[str, Any]


_BPS_QUANTUM = Decimal("0.0001")


class ExecutionPlan(FrozenContract):
    """Bounded execution instructions; never an order or an Agent capability."""

    version: Literal["alta-execution-plan-v1", "alta-execution-plan-v2"] = (
        "alta-execution-plan-v2"
    )
    mode: Literal["shadow_model", "tiger_paper_mirror"]
    status: Literal["ready", "wait"]
    order_style: Literal["guarded_limit", "none"]
    time_in_force: Literal["DAY", "NONE"]
    research_quantity: Decimal = Field(ge=0)
    acceptance_quantity: Decimal = Field(ge=0)
    entry_limit_offset_bps: Decimal = Field(ge=0, le=25)
    exit_limit_offset_bps: Decimal = Field(ge=0, le=25)
    estimated_participation_bps: Decimal | None = Field(default=None, ge=0)
    participation_cap_bps: Decimal = Field(default=Decimal("500"), gt=0, le=2_000)
    urgency: Literal["patient", "normal", "time_sensitive"] = "normal"
    arrival_benchmark: Literal["quote_midpoint"] = "quote_midpoint"
    arrival_midpoint: Decimal | None = Field(default=None, gt=0)
    arrival_spread_bps: Decimal | None = Field(default=None, ge=0)
    entry_limit_price: Decimal | None = Field(default=None, gt=0)
    implementation_shortfall_budget_bps: Decimal | None = Field(default=None, ge=0)
    recommended_child_slices: int = Field(default=1, ge=1, le=8)
    max_attempts: Literal[1] = 1
    max_quote_age_seconds: int = Field(default=60, ge=1, le=3_600)
    automatic_reprice: Literal[False] = False
    cancellation_rule: str = Field(min_length=1, max_length=240)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_execution(self) -> "ExecutionPlan":
        if self.status == "ready":
            if self.reason_codes or self.order_style != "guarded_limit":
                raise ValueError("ready execution requires one guarded limit plan")
            if self.time_in_force != "DAY":
                raise ValueError("ready execution must use DAY time in force")
            if self.research_quantity <= 0 or self.acceptance_quantity <= 0:
                raise ValueError("ready execution requires positive quantities")
            if self.version == "alta-execution-plan-v2" and any(
                value is None
                for value in (
                    self.arrival_midpoint,
                    self.arrival_spread_bps,
                    self.entry_limit_price,
                    self.implementation_shortfall_budget_bps,
                    self.estimated_participation_bps,
                )
            ):
                raise ValueError("v2 ready execution requires a complete arrival plan")
            if (
                self.estimated_participation_bps is not None
                and self.estimated_participation_bps > self.participation_cap_bps
            ):
                raise ValueError("ready execution exceeds its participation cap")
        elif not self.reason_codes:
            raise ValueError("wait execution requires a reason")
        return self


def build_execution_plan(
    instrument: ExecutableInstrument,
    *,
    target_quantity: Decimal,
    alpha_clock: AlphaClock,
    paper_mirror: bool,
    participation_cap_bps: Decimal = Decimal("500"),
) -> ExecutionPlan:
    if target_quantity <= 0:
        return ExecutionPlan(
            mode="tiger_paper_mirror" if paper_mirror else "shadow_model",
            status="wait",
            order_style="none",
            time_in_force="NONE",
            research_quantity=Decimal(0),
            acceptance_quantity=Decimal(0),
            entry_limit_offset_bps=Decimal(0),
            exit_limit_offset_bps=Decimal(0),
            participation_cap_bps=participation_cap_bps,
            cancellation_rule="No order is admissible without a positive risk size.",
            reason_codes=("risk_size_unavailable",),
        )

    urgency = (
        "time_sensitive"
        if alpha_clock.stage == "expiring"
        else ("patient" if alpha_clock.stage == "forming" else "normal")
    )
    urgency_buffer = Decimal(10) if urgency == "time_sensitive" else Decimal(5)
    entry_offset = urgency_buffer.quantize(_BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
    participation = _participation_bps(instrument, target_quantity)
    midpoint = (instrument.quote.bid + instrument.quote.ask) / Decimal(2)
    spread_bps = (
        (instrument.quote.ask - instrument.quote.bid) / midpoint * Decimal(10_000)
    ).quantize(_BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
    if participation is None or participation > participation_cap_bps:
        return ExecutionPlan(
            mode="tiger_paper_mirror" if paper_mirror else "shadow_model",
            status="wait",
            order_style="none",
            time_in_force="NONE",
            research_quantity=Decimal(0),
            acceptance_quantity=Decimal(0),
            entry_limit_offset_bps=Decimal(0),
            exit_limit_offset_bps=Decimal(0),
            estimated_participation_bps=participation,
            participation_cap_bps=participation_cap_bps,
            cancellation_rule="No order is admissible beyond observed participation.",
            reason_codes=("execution_participation_unverified",),
        )
    entry_limit_price = (
        instrument.quote.ask * (Decimal(1) + entry_offset / Decimal(10_000))
    ).quantize(Decimal("0.01"), rounding=ROUND_UP)
    slippage_allowance = Decimal(50 if instrument.kind == "option" else 5)
    shortfall_budget = (spread_bps + entry_offset + slippage_allowance).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    child_slices = max(
        1,
        min(
            8,
            int(
                (participation / Decimal(100)).to_integral_value(rounding=ROUND_CEILING)
            ),
        ),
    )
    return ExecutionPlan(
        mode="tiger_paper_mirror" if paper_mirror else "shadow_model",
        status="ready",
        order_style="guarded_limit",
        time_in_force="DAY",
        research_quantity=target_quantity,
        acceptance_quantity=Decimal(1) if paper_mirror else target_quantity,
        entry_limit_offset_bps=entry_offset,
        exit_limit_offset_bps=Decimal(25),
        estimated_participation_bps=participation,
        participation_cap_bps=participation_cap_bps,
        urgency=urgency,
        arrival_midpoint=midpoint,
        arrival_spread_bps=spread_bps,
        entry_limit_price=entry_limit_price,
        implementation_shortfall_budget_bps=shortfall_budget,
        recommended_child_slices=child_slices,
        cancellation_rule=(
            "Cancel an unfilled limit at the bounded timeout; do not chase or "
            "automatically reprice. Re-underwrite against a fresh quote."
        ),
    )


def _participation_bps(
    instrument: ExecutableInstrument, target_quantity: Decimal
) -> Decimal | None:
    if instrument.kind == "option":
        open_interest = Decimal(str(instrument.metadata.get("open_interest", "0")))
        if open_interest <= 0:
            return None
        contracts = target_quantity / Decimal(100)
        return (contracts / open_interest * Decimal(10_000)).quantize(
            _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
        )
    dollar_volume = Decimal(
        str(instrument.metadata.get("observed_day_dollar_volume", "0"))
    )
    if dollar_volume <= 0:
        return None
    target_notional = target_quantity * instrument.quote.ask
    return (target_notional / dollar_volume * Decimal(10_000)).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
