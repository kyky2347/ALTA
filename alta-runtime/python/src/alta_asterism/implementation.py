from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .alpha_governance import AlphaCapitalGovernance
from .alpha_isolation import AlphaSource, SystematicExposure
from .alpha_lifecycle import AlphaClock
from .execution_planning import ExecutionPlan
from .expression_base import FrozenContract
from .forecast_calibration import ForecastCalibrationGovernance
from .execution_quality import ExecutionCostGovernance


def _validate_notional_bridge(
    label: str,
    before: Decimal | None,
    limit: Decimal | None,
    after: Decimal | None,
    target_notional: Decimal,
) -> None:
    bridge = (before, limit, after)
    if not any(value is not None for value in bridge):
        return
    if any(value is None for value in bridge):
        raise ValueError(f"{label} bridge must be complete")
    assert before is not None and limit is not None and after is not None
    if after != before + target_notional:
        raise ValueError(f"{label} bridge is inconsistent")
    if after > limit:
        raise ValueError(f"ready implementation exceeds {label} capacity")


class PortfolioRiskPolicy(FrozenContract):
    """Research capital policy used to turn an idea into a bounded Shadow plan."""

    version: Literal["alta-portfolio-risk-v8"] = "alta-portfolio-risk-v8"
    reference_nav: Decimal = Field(default=Decimal("1000000"), gt=0)
    per_trade_loss_budget_bps: Decimal = Field(default=Decimal("25"), gt=0)
    max_position_nav_bps: Decimal = Field(default=Decimal("100"), gt=0)
    max_gross_nav_bps: Decimal = Field(default=Decimal("800"), gt=0)
    max_underlying_nav_bps: Decimal = Field(default=Decimal("150"), gt=0)
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
        if self.max_underlying_nav_bps < self.max_position_nav_bps:
            raise ValueError("underlying NAV limit cannot be below position NAV limit")
        gross_bounded_limits = (
            ("position", self.max_position_nav_bps),
            ("underlying", self.max_underlying_nav_bps),
            ("systematic exposure", self.max_systematic_exposure_nav_bps),
            ("portfolio stress", self.max_portfolio_stress_nav_bps),
            ("Alpha source", self.max_alpha_source_nav_bps),
            ("catalyst", self.max_catalyst_nav_bps),
        )
        for label, value in gross_bounded_limits:
            if value > self.max_gross_nav_bps:
                raise ValueError(f"{label} NAV limit cannot exceed gross NAV limit")
        if self.equity_stress_floor_bps > Decimal(10_000):
            raise ValueError("equity stress floor cannot exceed total notional")
        if self.min_alpha_isolation_score > self.core_alpha_isolation_score:
            raise ValueError("Alpha isolation hurdle cannot exceed the core threshold")
        if self.min_research_quality_score > self.core_research_quality_score:
            raise ValueError("research quality hurdle cannot exceed the core threshold")
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


class UnderlyingBucket(FrozenContract):
    underlying_key: str = Field(pattern=r"^(?:[A-Z][A-Z0-9.:-]{0,31}|UNKNOWN)$")
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
    underlying_buckets: tuple[UnderlyingBucket, ...] = Field(default=(), max_length=16)

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
        underlyings = [item.underlying_key for item in self.underlying_buckets]
        if len(underlyings) != len(set(underlyings)):
            raise ValueError("portfolio underlying buckets must be unique")
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
    forecast_calibration_governance: ForecastCalibrationGovernance | None = None
    execution_cost_governance: ExecutionCostGovernance | None = None
    reference_nav: Decimal = Field(gt=0)
    unreserved_expected_alpha_bps: Decimal | None = None
    forecast_calibration_reserve_bps: Decimal = Field(default=Decimal(0), ge=0)
    execution_cost_reserve_bps: Decimal = Field(default=Decimal(0), ge=0)
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
    underlying_key: str = Field(
        default="UNKNOWN", pattern=r"^(?:[A-Z][A-Z0-9.:-]{0,31}|UNKNOWN)$"
    )
    underlying_notional_before: Decimal | None = Field(default=None, ge=0)
    underlying_notional_limit: Decimal | None = Field(default=None, ge=0)
    underlying_notional_after: Decimal | None = Field(default=None, ge=0)
    target_notional: Decimal = Field(ge=0)
    target_quantity: Decimal = Field(ge=0)
    estimated_stress_loss: Decimal = Field(ge=0)
    liquidity_capacity: Decimal | None = Field(default=None, ge=0)
    liquidity_source: str | None = Field(default=None, max_length=96)
    binding_constraint: str | None = Field(default=None, max_length=96)
    exposure_capacity: Decimal | None = Field(default=None, ge=0)
    exposure_binding_tag: SystematicExposure | None = None
    monitoring_triggers: tuple[str, ...] = Field(default=(), max_length=8)
    agent_requested_position_nav_bps: Decimal | None = Field(
        default=None, gt=0, le=Decimal("1000")
    )
    agent_requested_trade_loss_nav_bps: Decimal | None = Field(
        default=None, gt=0, le=Decimal("250")
    )
    agent_sizing_rationale: str | None = Field(default=None, max_length=800)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def validate_plan(self) -> "TradeImplementationPlan":
        if self.status == "wait" and not self.reason_codes:
            raise ValueError("wait implementation requires a reason")
        if self.status == "ready":
            self._validate_ready_shape()
            self._validate_ready_risk_bridges()
            self._validate_ready_sizing()
            self._validate_ready_decision_binding()
        return self

    def _validate_ready_shape(self) -> None:
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

    def _validate_ready_risk_bridges(self) -> None:
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
        bridges = (
            (
                "Alpha source",
                self.alpha_source_notional_before,
                self.alpha_source_notional_limit,
                self.alpha_source_notional_after,
            ),
            (
                "catalyst",
                self.catalyst_notional_before,
                self.catalyst_notional_limit,
                self.catalyst_notional_after,
            ),
            (
                "underlying",
                self.underlying_notional_before,
                self.underlying_notional_limit,
                self.underlying_notional_after,
            ),
        )
        for label, before, limit, after in bridges:
            _validate_notional_bridge(label, before, limit, after, self.target_notional)

    def _validate_ready_sizing(self) -> None:
        sizing_caps = (
            ("Alpha purity", self.alpha_isolation_multiplier),
            ("research quality", self.research_quality_multiplier),
            (
                "Alpha governance",
                self.alpha_capital_governance.capital_multiplier
                if self.alpha_capital_governance is not None
                else None,
            ),
            (
                "forecast calibration",
                self.forecast_calibration_governance.capital_multiplier
                if self.forecast_calibration_governance is not None
                else None,
            ),
        )
        for label, multiplier in sizing_caps:
            if (
                multiplier is not None
                and self.target_notional > self.position_notional_limit * multiplier
            ):
                raise ValueError(f"ready implementation exceeds its {label} cap")

    def _validate_ready_decision_binding(self) -> None:
        if (
            self.unreserved_expected_alpha_bps is not None
            and self.expected_alpha_bps
            != self.unreserved_expected_alpha_bps
            - self.forecast_calibration_reserve_bps
        ):
            raise ValueError("implementation forecast calibration bridge disagrees")
        if (
            self.expected_alpha_bps is not None
            and self.estimated_cost_bps is not None
            and self.expected_net_alpha_bps
            != self.expected_alpha_bps
            - self.estimated_cost_bps
            - self.execution_cost_reserve_bps
        ):
            raise ValueError("implementation execution-cost bridge disagrees")
        if self.alpha_clock is not None and (
            self.expected_net_alpha_bps != self.alpha_clock.raw_expected_net_alpha_bps
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
