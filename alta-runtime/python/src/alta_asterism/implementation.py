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

    version: Literal["alta-portfolio-risk-v7"] = "alta-portfolio-risk-v7"
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
    max_portfolio_stress_nav_bps: Decimal = Field(default=Decimal("100"), gt=0)
    max_alpha_source_nav_bps: Decimal = Field(default=Decimal("300"), gt=0)
    max_catalyst_nav_bps: Decimal = Field(default=Decimal("200"), gt=0)
    min_rotation_efficiency_improvement: Decimal = Field(
        default=Decimal("0.10"), ge=0, le=5
    )

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
        if self.max_portfolio_stress_nav_bps > self.max_gross_nav_bps:
            raise ValueError("portfolio stress limit cannot exceed gross NAV limit")
        if self.max_alpha_source_nav_bps > self.max_gross_nav_bps:
            raise ValueError("Alpha source limit cannot exceed gross NAV limit")
        if self.max_catalyst_nav_bps > self.max_gross_nav_bps:
            raise ValueError("catalyst limit cannot exceed gross NAV limit")
        return self

    def dollars(self, basis_points: Decimal) -> Decimal:
        return self.reference_nav * basis_points / Decimal(10_000)


class ExposureBucket(FrozenContract):
    tag: SystematicExposure
    gross_notional: Decimal = Field(ge=0)


class AlphaSourceBucket(FrozenContract):
    source: AlphaSource
    open_positions: int = Field(ge=0, le=8)
    gross_notional: Decimal = Field(ge=0)
    estimated_stress_loss: Decimal = Field(ge=0)


class CatalystBucket(FrozenContract):
    catalyst_key: str = Field(min_length=1, max_length=128)
    open_positions: int = Field(ge=0, le=8)
    gross_notional: Decimal = Field(ge=0)
    estimated_stress_loss: Decimal = Field(ge=0)


class PortfolioState(FrozenContract):
    known_open_positions: int = Field(default=0, ge=0)
    gross_notional: Decimal = Field(default=Decimal(0), ge=0)
    prospective_replacement_credit: Decimal = Field(default=Decimal(0), ge=0)
    aggregate_stress_loss: Decimal = Field(default=Decimal(0), ge=0)
    prospective_replacement_stress_credit: Decimal = Field(default=Decimal(0), ge=0)
    exposure_buckets: tuple[ExposureBucket, ...] = Field(default=(), max_length=32)
    alpha_source_buckets: tuple[AlphaSourceBucket, ...] = Field(
        default=(), max_length=8
    )
    catalyst_buckets: tuple[CatalystBucket, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_exposure_buckets(self) -> "PortfolioState":
        tags = [item.tag for item in self.exposure_buckets]
        if len(tags) != len(set(tags)):
            raise ValueError("portfolio exposure buckets must be unique")
        sources = [item.source for item in self.alpha_source_buckets]
        if len(sources) != len(set(sources)):
            raise ValueError("portfolio Alpha source buckets must be unique")
        catalysts = [item.catalyst_key for item in self.catalyst_buckets]
        if len(catalysts) != len(set(catalysts)):
            raise ValueError("portfolio catalyst buckets must be unique")
        if self.prospective_replacement_credit > self.gross_notional:
            raise ValueError("portfolio replacement credit cannot exceed gross")
        if self.prospective_replacement_stress_credit > self.aggregate_stress_loss:
            raise ValueError("stress replacement credit cannot exceed aggregate stress")
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
    portfolio_stress_loss_before: Decimal | None = Field(default=None, ge=0)
    portfolio_stress_replacement_credit: Decimal | None = Field(default=None, ge=0)
    portfolio_stress_loss_limit: Decimal | None = Field(default=None, ge=0)
    portfolio_stress_loss_after: Decimal | None = Field(default=None, ge=0)
    alpha_source_notional_before: Decimal | None = Field(default=None, ge=0)
    alpha_source_notional_limit: Decimal | None = Field(default=None, ge=0)
    alpha_source_notional_after: Decimal | None = Field(default=None, ge=0)
    catalyst_key: str = Field(
        default="legacy-unclassified",
        min_length=1,
        max_length=128,
    )
    catalyst_notional_before: Decimal | None = Field(default=None, ge=0)
    catalyst_notional_limit: Decimal | None = Field(default=None, ge=0)
    catalyst_notional_after: Decimal | None = Field(default=None, ge=0)
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
            stress_bridge = (
                self.portfolio_stress_loss_before,
                self.portfolio_stress_replacement_credit,
                self.portfolio_stress_loss_limit,
                self.portfolio_stress_loss_after,
            )
            if any(value is not None for value in stress_bridge):
                if any(value is None for value in stress_bridge):
                    raise ValueError("portfolio stress bridge must be complete")
                stress_before, stress_credit, stress_limit, stress_after = stress_bridge
                assert stress_before is not None
                assert stress_credit is not None
                assert stress_limit is not None
                assert stress_after is not None
                if stress_credit > stress_before:
                    raise ValueError("stress replacement credit exceeds current stress")
                if (
                    stress_after
                    != stress_before - stress_credit + self.estimated_stress_loss
                ):
                    raise ValueError("portfolio stress bridge is inconsistent")
                if stress_after > stress_limit:
                    raise ValueError("ready implementation exceeds portfolio stress")
            source_bridge = (
                self.alpha_source_notional_before,
                self.alpha_source_notional_limit,
                self.alpha_source_notional_after,
            )
            if any(value is not None for value in source_bridge):
                if any(value is None for value in source_bridge):
                    raise ValueError("Alpha source bridge must be complete")
                source_before, source_limit, source_after = source_bridge
                assert source_before is not None
                assert source_limit is not None
                assert source_after is not None
                if source_after != source_before + self.target_notional:
                    raise ValueError("Alpha source bridge is inconsistent")
                if source_after > source_limit:
                    raise ValueError(
                        "ready implementation exceeds Alpha source capacity"
                    )
            catalyst_bridge = (
                self.catalyst_notional_before,
                self.catalyst_notional_limit,
                self.catalyst_notional_after,
            )
            if any(value is not None for value in catalyst_bridge):
                if any(value is None for value in catalyst_bridge):
                    raise ValueError("catalyst bridge must be complete")
                catalyst_before, catalyst_limit, catalyst_after = catalyst_bridge
                assert catalyst_before is not None
                assert catalyst_limit is not None
                assert catalyst_after is not None
                if catalyst_after != catalyst_before + self.target_notional:
                    raise ValueError("catalyst bridge is inconsistent")
                if catalyst_after > catalyst_limit:
                    raise ValueError("ready implementation exceeds catalyst capacity")
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
