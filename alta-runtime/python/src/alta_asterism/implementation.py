from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .alpha_governance import AlphaCapitalGovernance
from .alpha_isolation import AlphaSource, SystematicExposure
from .alpha_lifecycle import AlphaClock
from .execution_planning import ExecutionPlan
from .expression_base import FrozenContract


class PortfolioRiskPolicy(FrozenContract):
    """Research capital policy used to turn an idea into a bounded Shadow plan."""

    version: Literal["alta-portfolio-risk-v5"] = "alta-portfolio-risk-v5"
    reference_nav: Decimal = Field(default=Decimal("1000000"), gt=0)
    per_trade_loss_budget_bps: Decimal = Field(default=Decimal("25"), gt=0)
    max_position_nav_bps: Decimal = Field(default=Decimal("100"), gt=0)
    max_gross_nav_bps: Decimal = Field(default=Decimal("800"), gt=0)
    equity_stress_floor_bps: Decimal = Field(default=Decimal("2500"), gt=0)
    max_exit_days: int = Field(default=2, ge=1, le=20)
    adv_participation_bps: Decimal = Field(default=Decimal("500"), gt=0, le=2_000)
    option_open_interest_participation_bps: Decimal = Field(
        default=Decimal("500"), gt=0, le=2_000
    )
    min_net_alpha_bps: Decimal = Field(default=Decimal("50"), ge=0)
    min_alpha_isolation_score: Decimal = Field(default=Decimal("0.60"), ge=0, le=1)
    core_alpha_isolation_score: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    starter_size_multiplier: Decimal = Field(default=Decimal("0.50"), gt=0, le=1)
    min_research_quality_score: Decimal = Field(default=Decimal("0.60"), ge=0, le=1)
    core_research_quality_score: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    research_starter_size_multiplier: Decimal = Field(
        default=Decimal("0.50"), gt=0, le=1
    )
    max_systematic_exposure_nav_bps: Decimal = Field(default=Decimal("200"), gt=0)

    @model_validator(mode="after")
    def validate_limits(self) -> "PortfolioRiskPolicy":
        if self.max_position_nav_bps > self.max_gross_nav_bps:
            raise ValueError("position NAV limit cannot exceed gross NAV limit")
        if self.equity_stress_floor_bps > Decimal(10_000):
            raise ValueError("equity stress floor cannot exceed total notional")
        if self.min_alpha_isolation_score > self.core_alpha_isolation_score:
            raise ValueError("Alpha isolation hurdle cannot exceed the core threshold")
        if self.min_research_quality_score > self.core_research_quality_score:
            raise ValueError("research quality hurdle cannot exceed the core threshold")
        if self.max_systematic_exposure_nav_bps > self.max_gross_nav_bps:
            raise ValueError("systematic exposure limit cannot exceed gross NAV limit")
        return self

    def dollars(self, basis_points: Decimal) -> Decimal:
        return self.reference_nav * basis_points / Decimal(10_000)


class ExposureBucket(FrozenContract):
    tag: SystematicExposure
    gross_notional: Decimal = Field(ge=0)


class PortfolioState(FrozenContract):
    known_open_positions: int = Field(default=0, ge=0)
    gross_notional: Decimal = Field(default=Decimal(0), ge=0)
    prospective_replacement_credit: Decimal = Field(default=Decimal(0), ge=0)
    exposure_buckets: tuple[ExposureBucket, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_exposure_buckets(self) -> "PortfolioState":
        tags = [item.tag for item in self.exposure_buckets]
        if len(tags) != len(set(tags)):
            raise ValueError("portfolio exposure buckets must be unique")
        return self


class TradeImplementationPlan(FrozenContract):
    """Frozen PM implementation record; it is a plan, never an order."""

    status: Literal["ready", "wait"]
    policy_version: str = Field(min_length=3, max_length=64)
    intended_alpha: str = Field(min_length=1, max_length=800)
    unwanted_exposures: tuple[str, ...] = Field(default=(), max_length=8)
    retained_exposure: str = Field(min_length=1, max_length=800)
    alpha_source: AlphaSource = "legacy_unclassified"
    systematic_exposures: tuple[SystematicExposure, ...] = Field(
        default=(), max_length=8
    )
    alpha_isolation_posture: Literal["legacy", "provisional", "audited"] = "legacy"
    alpha_isolation_score: Decimal | None = Field(default=None, ge=0, le=1)
    alpha_isolation_multiplier: Decimal = Field(default=Decimal(1), gt=0, le=1)
    alpha_isolation_reason_codes: tuple[str, ...] = Field(default=(), max_length=8)
    research_quality_score: Decimal | None = Field(default=None, ge=0, le=1)
    research_quality_multiplier: Decimal = Field(default=Decimal(1), gt=0, le=1)
    alpha_capital_governance: AlphaCapitalGovernance | None = None
    reference_nav: Decimal = Field(gt=0)
    expected_alpha_bps: Decimal | None = None
    estimated_cost_bps: Decimal | None = Field(default=None, ge=0)
    expected_net_alpha_bps: Decimal | None = None
    alpha_clock: AlphaClock | None = None
    execution_plan: ExecutionPlan | None = None
    stress_loss_fraction: Decimal | None = Field(default=None, ge=0, le=1)
    loss_budget: Decimal = Field(ge=0)
    position_notional_limit: Decimal = Field(ge=0)
    gross_notional_before: Decimal = Field(ge=0)
    gross_replacement_credit: Decimal = Field(default=Decimal(0), ge=0)
    gross_notional_limit: Decimal = Field(ge=0)
    gross_notional_after: Decimal = Field(ge=0)
    target_notional: Decimal = Field(ge=0)
    target_quantity: Decimal = Field(ge=0)
    estimated_stress_loss: Decimal = Field(ge=0)
    liquidity_capacity: Decimal | None = Field(default=None, ge=0)
    liquidity_source: str | None = Field(default=None, max_length=96)
    binding_constraint: str | None = Field(default=None, max_length=96)
    exposure_capacity: Decimal | None = Field(default=None, ge=0)
    exposure_binding_tag: SystematicExposure | None = None
    monitoring_triggers: tuple[str, ...] = Field(default=(), max_length=8)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def validate_plan(self) -> "TradeImplementationPlan":
        if self.status == "ready":
            if self.reason_codes:
                raise ValueError("ready implementation cannot carry rejection reasons")
            if self.target_notional <= 0 or self.target_quantity <= 0:
                raise ValueError("ready implementation requires positive size")
            expected_gross = (
                self.gross_notional_before
                - self.gross_replacement_credit
                + self.target_notional
            )
            if self.gross_replacement_credit > self.gross_notional_before:
                raise ValueError("replacement credit cannot exceed current gross")
            if self.gross_notional_after != expected_gross:
                raise ValueError("implementation gross bridge is inconsistent")
            if self.estimated_stress_loss > self.loss_budget:
                raise ValueError("ready implementation exceeds its loss budget")
            if self.gross_notional_after > self.gross_notional_limit:
                raise ValueError("ready implementation exceeds its gross limit")
            if (
                self.target_notional
                > self.position_notional_limit * self.alpha_isolation_multiplier
            ):
                raise ValueError("ready implementation exceeds its Alpha purity cap")
            if (
                self.target_notional
                > self.position_notional_limit * self.research_quality_multiplier
            ):
                raise ValueError(
                    "ready implementation exceeds its research quality cap"
                )
            if (
                self.alpha_capital_governance is not None
                and self.target_notional
                > self.position_notional_limit
                * self.alpha_capital_governance.capital_multiplier
            ):
                raise ValueError(
                    "ready implementation exceeds its Alpha governance cap"
                )
            if self.alpha_clock is not None and (
                self.expected_net_alpha_bps
                != self.alpha_clock.raw_expected_net_alpha_bps
            ):
                raise ValueError("implementation Alpha and its clock disagree")
            if self.execution_plan is not None and (
                self.execution_plan.status != "ready"
                or self.execution_plan.research_quantity != self.target_quantity
            ):
                raise ValueError("implementation and execution quantities disagree")
            if (
                self.alpha_isolation_posture == "audited"
                and self.alpha_isolation_score is None
            ):
                raise ValueError("audited implementation requires an isolation score")
            if (
                self.exposure_binding_tag is not None
                and self.exposure_binding_tag not in self.systematic_exposures
            ):
                raise ValueError("binding exposure must belong to the implementation")
        elif not self.reason_codes:
            raise ValueError("wait implementation requires a reason")
        return self
