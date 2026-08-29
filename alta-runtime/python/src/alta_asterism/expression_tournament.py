from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .alpha_isolation import AlphaSource, HedgePosture, SystematicExposure

if TYPE_CHECKING:
    from .capital_allocation import CapitalAllocationDecision
    from .implementation import TradeImplementationPlan
    from .market_data import MarketInstrument


class ExpressionHypothesis(BaseModel):
    """One PM-proposed payoff shape to test against actual market capacity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    kind: Literal["stock", "etf", "option", "wait"]
    symbol: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    payoff_thesis: str = Field(min_length=1, max_length=1_200)
    thesis_purity: float = Field(ge=0, le=1)
    timing_fit: float = Field(ge=0, le=1)
    primary_tradeoff: str = Field(min_length=1, max_length=800)
    thesis_pillar_ids: tuple[str, ...] = Field(default=(), max_length=4)
    alpha_source: AlphaSource = "legacy_unclassified"
    systematic_exposures: tuple[SystematicExposure, ...] = Field(
        default=(), max_length=8
    )
    hedge_posture: HedgePosture = "not_applicable"
    basis_risk: str = Field(
        default="Not classified by a legacy proposal.", max_length=800
    )

    @model_validator(mode="after")
    def validate_identity(self) -> "ExpressionHypothesis":
        if (self.kind == "wait") != (self.symbol is None):
            raise ValueError("only wait may omit its expression symbol")
        if len(set(self.thesis_pillar_ids)) != len(self.thesis_pillar_ids):
            raise ValueError("expression thesis pillar IDs must be unique")
        if len(set(self.systematic_exposures)) != len(self.systematic_exposures):
            raise ValueError("expression systematic exposures must be unique")
        if "none" in self.systematic_exposures and len(self.systematic_exposures) != 1:
            raise ValueError("none cannot be combined with systematic exposures")
        return self


@dataclass(frozen=True)
class EvaluatedExpression:
    hypothesis: ExpressionHypothesis
    market_gate: str
    instrument: MarketInstrument | None
    implementation: TradeImplementationPlan | None
    capital_allocation: CapitalAllocationDecision | None

    @property
    def ready(self) -> bool:
        return (
            self.instrument is not None
            and self.implementation is not None
            and self.implementation.status == "ready"
            and self.capital_allocation is not None
            and self.capital_allocation.status != "wait"
        )

    def prompt_value(self) -> dict[str, object]:
        plan = self.implementation
        allocation = self.capital_allocation
        instrument = self.instrument
        return {
            "hypothesis": {
                "hypothesis_id": self.hypothesis.hypothesis_id,
                "kind": self.hypothesis.kind,
                "symbol": self.hypothesis.symbol,
                "payoff_thesis": self.hypothesis.payoff_thesis[:160],
                "thesis_purity": self.hypothesis.thesis_purity,
                "timing_fit": self.hypothesis.timing_fit,
                "primary_tradeoff": self.hypothesis.primary_tradeoff[:120],
                "thesis_pillar_ids": self.hypothesis.thesis_pillar_ids,
                "alpha_source": self.hypothesis.alpha_source,
                "systematic_exposures": self.hypothesis.systematic_exposures,
                "hedge_posture": self.hypothesis.hedge_posture,
                "basis_risk": self.hypothesis.basis_risk[:120],
            },
            "market_gate": self.market_gate,
            "admissible": self.ready,
            "decision_metrics": _decision_metrics(plan),
            "instrument": (
                {
                    "kind": instrument.kind,
                    "symbol": instrument.symbol,
                    "underlying_symbol": instrument.underlying_symbol,
                    "quantity": str(instrument.quantity),
                    "bid": str(instrument.quote.bid),
                    "ask": str(instrument.quote.ask),
                    "quote_as_of": instrument.quote.as_of.isoformat(),
                    "metadata": {
                        key: value
                        for key, value in instrument.metadata.items()
                        if key
                        in {
                            "contract_type",
                            "expiration_date",
                            "strike_price",
                            "delta",
                            "open_interest",
                            "observed_day_dollar_volume",
                            "path_dependency",
                            "daily_target",
                        }
                    },
                }
                if instrument is not None
                else None
            ),
            "implementation": (
                {
                    "status": plan.status,
                    "reason_codes": plan.reason_codes,
                    "binding_constraint": plan.binding_constraint,
                    "exposure_binding_tag": plan.exposure_binding_tag,
                    "execution": (
                        {
                            "status": plan.execution_plan.status,
                            "order_style": plan.execution_plan.order_style,
                            "entry_limit_price": str(
                                plan.execution_plan.entry_limit_price
                            ),
                            "arrival_spread_bps": _text(
                                plan.execution_plan.arrival_spread_bps
                            ),
                            "implementation_shortfall_budget_bps": _text(
                                plan.execution_plan.implementation_shortfall_budget_bps
                            ),
                            "estimated_participation_bps": _text(
                                plan.execution_plan.estimated_participation_bps
                            ),
                            "participation_cap_bps": str(
                                plan.execution_plan.participation_cap_bps
                            ),
                            "automatic_reprice": (
                                plan.execution_plan.automatic_reprice
                            ),
                        }
                        if plan.execution_plan is not None
                        else None
                    ),
                }
                if plan is not None
                else None
            ),
            "capital_allocation": (
                {
                    "status": allocation.status,
                    "reason_code": allocation.reason_code,
                    "incumbent_position_id": allocation.incumbent_position_id,
                    "advantage_bps": _text(allocation.advantage_bps),
                    "required_advantage_bps": _text(allocation.required_advantage_bps),
                }
                if allocation is not None
                else None
            ),
        }


def normalized_hypotheses(
    hypotheses: tuple[ExpressionHypothesis, ...],
    *,
    preferred_kind: Literal["stock", "etf", "option", "wait"],
    preferred_symbol: str | None,
    payoff_thesis: str,
) -> tuple[ExpressionHypothesis, ...]:
    if hypotheses:
        if len(hypotheses) > 3:
            raise ValueError("expression slate exceeds the three-hypothesis budget")
        if len({item.hypothesis_id for item in hypotheses}) != len(hypotheses):
            raise ValueError("expression hypothesis IDs must be unique")
        identities = [(item.kind, item.symbol) for item in hypotheses]
        if len(set(identities)) != len(identities):
            raise ValueError("expression hypotheses must have unique instruments")
        return hypotheses
    return (
        ExpressionHypothesis(
            hypothesis_id="preferred",
            kind=preferred_kind,
            symbol=preferred_symbol,
            payoff_thesis=payoff_thesis,
            thesis_purity=0.5,
            timing_fit=0.5,
            primary_tradeoff="Legacy single-expression fallback; independently audit.",
        ),
    )


def select_audited_expression(
    entries: tuple[EvaluatedExpression, ...],
    *,
    decision: Literal["approve", "wait"],
    selected_hypothesis_id: str | None,
) -> EvaluatedExpression | None:
    if decision == "wait":
        return None
    ready = tuple(item for item in entries if item.ready)
    if selected_hypothesis_id is None:
        if len(ready) == 1:
            return ready[0]
        raise ValueError("audit must select one hypothesis from a multi-entry slate")
    selected = tuple(
        item
        for item in ready
        if item.hypothesis.hypothesis_id == selected_hypothesis_id
    )
    if len(selected) != 1:
        raise ValueError("audit selected an unavailable expression hypothesis")
    return selected[0]


def _text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decision_metrics(plan: TradeImplementationPlan | None) -> dict[str, str] | None:
    """Expose comparable economics without turning them into an automatic score."""

    if (
        plan is None
        or plan.status != "ready"
        or plan.alpha_clock is None
        or plan.expected_net_alpha_bps is None
        or plan.target_notional <= 0
    ):
        return None
    adjusted_alpha_bps = plan.alpha_clock.time_adjusted_expected_net_alpha_bps
    expected_alpha_dollars = plan.target_notional * adjusted_alpha_bps / Decimal(10_000)
    stress_efficiency = (
        expected_alpha_dollars / plan.estimated_stress_loss
        if plan.estimated_stress_loss > 0
        else None
    )
    execution_reserve = (
        plan.execution_plan.implementation_shortfall_budget_bps
        if plan.execution_plan is not None
        else None
    )
    execution_headroom = (
        adjusted_alpha_bps - execution_reserve
        if execution_reserve is not None
        else None
    )
    return {
        "unreserved_expected_alpha_bps": (
            _text(getattr(plan, "unreserved_expected_alpha_bps", None)) or "unavailable"
        ),
        "forecast_calibration_reserve_bps": str(
            getattr(plan, "forecast_calibration_reserve_bps", Decimal(0))
        ),
        "time_adjusted_expected_net_alpha_bps": str(adjusted_alpha_bps),
        "time_adjusted_expected_alpha_dollars": str(expected_alpha_dollars),
        "estimated_cost_bps": str(plan.estimated_cost_bps),
        "target_notional_dollars": str(plan.target_notional),
        "estimated_stress_loss_dollars": str(plan.estimated_stress_loss),
        "expected_alpha_per_stress_dollar": (
            str(stress_efficiency) if stress_efficiency is not None else "unavailable"
        ),
        "execution_reserve_headroom_bps": (
            str(execution_headroom) if execution_headroom is not None else "unavailable"
        ),
    }
