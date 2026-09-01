from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from .alpha_governance import AlphaCapitalGovernance
from .alpha_isolation import (
    AlphaIsolation,
    SystematicExposure,
    legacy_alpha_isolation,
)
from .alpha_lifecycle import AlphaClock, build_alpha_clock
from .database import Database
from .execution_planning import build_execution_plan
from .execution_quality import ExecutionCostGovernance
from .forecast_calibration import ForecastCalibrationGovernance
from .implementation import PortfolioRiskPolicy, PortfolioState, TradeImplementationPlan
from .market_data import MarketInstrument
from .opportunity_identity import normalize_catalyst_bucket
from .portfolio_state import load_portfolio_state, normalize_underlying_key
from .underwriting import (
    ScenarioUnderwriting,
    consensus_decision,
    consensus_underwriting,
)


def _spread_bps(instrument: MarketInstrument) -> Decimal:
    midpoint = (instrument.quote.bid + instrument.quote.ask) / Decimal(2)
    return (instrument.quote.ask - instrument.quote.bid) / midpoint * Decimal(10_000)


class PortfolioConstructor:
    """Applies PM constraints after an Agent has selected a payoff shape."""

    def __init__(
        self,
        database: Database,
        policy: PortfolioRiskPolicy | None = None,
        *,
        max_open_positions: int = 8,
    ) -> None:
        if not 1 <= max_open_positions <= 8:
            raise ValueError("max_open_positions must be between 1 and 8")
        self.database = database
        self.policy = policy or PortfolioRiskPolicy()
        self.max_open_positions = max_open_positions

    def load_state(self, known_at: datetime | None = None) -> PortfolioState:
        return load_portfolio_state(
            self.database,
            max_open_positions=self.max_open_positions,
            known_at=known_at,
        )

    def load_alpha_governance(self) -> AlphaCapitalGovernance:
        if self.database is None:
            return AlphaCapitalGovernance.unscoped(self.policy.version)
        return self.database.alpha_capital_governance(
            "shadow",
            reference_nav=self.policy.reference_nav,
            source_portfolio_policy_version=self.policy.version,
        )

    def load_forecast_calibration(
        self, expression_kind: str
    ) -> ForecastCalibrationGovernance:
        if expression_kind != "stock" or self.database is None:
            return ForecastCalibrationGovernance.unscoped(
                self.policy.version,
                expression_kind,
            )
        return self.database.forecast_calibration_governance(
            "shadow",
            source_portfolio_policy_version=self.policy.version,
            expression_kind=expression_kind,
        )

    def load_execution_cost_governance(
        self, expression_kind: str
    ) -> ExecutionCostGovernance:
        if self.database is None:
            return ExecutionCostGovernance.unscoped(
                self.policy.version,
                expression_kind,
            )
        return self.database.execution_cost_governance(
            "shadow",
            source_portfolio_policy_version=self.policy.version,
            expression_kind=expression_kind,
        )

    def plan(
        self,
        instrument: MarketInstrument,
        underwritings: tuple[ScenarioUnderwriting, ...],
        *,
        intended_alpha: str,
        unwanted_exposures: tuple[str, ...],
        retained_exposure: str,
        monitoring_triggers: tuple[str, ...],
        state: PortfolioState | None = None,
        known_at: datetime | None = None,
        evidence_freshness_at: datetime | None = None,
        horizon_days: int = 90,
        next_pricing_facts: tuple[str, ...] = (),
        paper_mirror: bool = False,
        alpha_isolation: AlphaIsolation | None = None,
        research_quality_score: Decimal | None = None,
        alpha_capital_governance: AlphaCapitalGovernance | None = None,
        forecast_calibration_governance: (ForecastCalibrationGovernance | None) = None,
        execution_cost_governance: ExecutionCostGovernance | None = None,
        catalyst_key: str | None = None,
        requested_position_nav_bps: Decimal | None = None,
        requested_trade_loss_nav_bps: Decimal | None = None,
        sizing_rationale: str | None = None,
    ) -> TradeImplementationPlan:
        state = state or self.load_state()
        policy = self.policy
        capital_governance = alpha_capital_governance or self.load_alpha_governance()
        forecast_calibration = (
            forecast_calibration_governance
            or self.load_forecast_calibration(instrument.kind)
        )
        execution_governance = (
            execution_cost_governance
            or self.load_execution_cost_governance(instrument.kind)
        )
        isolation = alpha_isolation or legacy_alpha_isolation()
        isolation_multiplier = (
            min(isolation.sizing_multiplier, policy.starter_size_multiplier)
            if isolation.conservative_score is not None
            and isolation.conservative_score < policy.core_alpha_isolation_score
            else Decimal(1)
        )
        research_multiplier = (
            policy.research_starter_size_multiplier
            if research_quality_score is not None
            and research_quality_score < policy.core_research_quality_score
            else Decimal(1)
        )
        loss_budget = policy.dollars(policy.per_trade_loss_budget_bps)
        position_limit = policy.dollars(policy.max_position_nav_bps)
        gross_limit = policy.dollars(policy.max_gross_nav_bps)
        portfolio_stress_limit = policy.dollars(policy.max_portfolio_stress_nav_bps)
        alpha_source_limit = policy.dollars(policy.max_alpha_source_nav_bps)
        catalyst_limit = policy.dollars(policy.max_catalyst_nav_bps)
        underlying_limit = policy.dollars(policy.max_underlying_nav_bps)
        normalized_catalyst_key = normalize_catalyst_bucket(catalyst_key)
        underlying_key = normalize_underlying_key(instrument.underlying_symbol)
        alpha_source_before = next(
            (
                item.gross_notional
                for item in state.alpha_source_buckets
                if item.source == isolation.alpha_source
            ),
            Decimal(0),
        )
        catalyst_before = next(
            (
                item.gross_notional
                for item in state.catalyst_buckets
                if item.catalyst_key == normalized_catalyst_key
            ),
            Decimal(0),
        )
        underlying_before = next(
            (
                item.gross_notional
                for item in state.underlying_buckets
                if item.underlying_key == underlying_key
            ),
            Decimal(0),
        )
        common = {
            "policy_version": policy.version,
            "intended_alpha": intended_alpha,
            "unwanted_exposures": unwanted_exposures,
            "retained_exposure": retained_exposure,
            "alpha_source": isolation.alpha_source,
            "systematic_exposures": isolation.systematic_exposures,
            "alpha_isolation_posture": isolation.posture,
            "alpha_isolation_score": isolation.conservative_score,
            "alpha_isolation_multiplier": isolation_multiplier,
            "alpha_isolation_reason_codes": isolation.reason_codes,
            "research_quality_score": research_quality_score,
            "research_quality_multiplier": research_multiplier,
            "alpha_capital_governance": capital_governance,
            "forecast_calibration_governance": forecast_calibration,
            "execution_cost_governance": execution_governance,
            "execution_cost_reserve_bps": execution_governance.alpha_reserve_bps,
            "reference_nav": policy.reference_nav,
            "loss_budget": loss_budget,
            "position_notional_limit": position_limit,
            "gross_notional_before": state.gross_notional,
            "gross_replacement_credit": state.prospective_replacement_credit,
            "gross_notional_limit": gross_limit,
            "portfolio_stress_loss_before": state.aggregate_stress_loss,
            "portfolio_stress_replacement_credit": (
                state.prospective_replacement_stress_credit
            ),
            "portfolio_stress_loss_limit": portfolio_stress_limit,
            "alpha_source_notional_before": alpha_source_before,
            "alpha_source_notional_limit": alpha_source_limit,
            "catalyst_key": normalized_catalyst_key,
            "catalyst_notional_before": catalyst_before,
            "catalyst_notional_limit": catalyst_limit,
            "underlying_key": underlying_key,
            "agent_requested_position_nav_bps": requested_position_nav_bps,
            "agent_requested_trade_loss_nav_bps": requested_trade_loss_nav_bps,
            "agent_sizing_rationale": sizing_rationale,
            "underlying_notional_before": underlying_before,
            "underlying_notional_limit": underlying_limit,
            "monitoring_triggers": monitoring_triggers,
        }
        admission_reason = self._admission_reason(
            isolation, research_quality_score, underwritings
        )
        if admission_reason is not None:
            return self._wait(common, admission_reason)

        locked = (underwritings[0], underwritings[1])
        decision = consensus_decision(locked)
        if decision.status == "wait":
            return self._wait(common, decision.reason_codes[0])
        consensus = consensus_underwriting(locked)
        unreserved_expected_alpha = consensus["uncertainty_adjusted_expected_alpha_bps"]
        calibration_reserve = forecast_calibration.alpha_reserve_bps
        expected_alpha = unreserved_expected_alpha - calibration_reserve
        cost_bps = self._cost_bps(instrument)
        expected_net_alpha = (
            expected_alpha - cost_bps - execution_governance.alpha_reserve_bps
        )
        decision_horizon_days = min(horizon_days, decision.edge_half_life_days)
        clock = build_alpha_clock(
            known_at=known_at or instrument.quote.known_at,
            evidence_freshness_at=(
                evidence_freshness_at or known_at or instrument.quote.known_at
            ),
            horizon_days=decision_horizon_days,
            raw_expected_net_alpha_bps=expected_net_alpha,
            catalyst_clarity=consensus["catalyst_clarity"],
            next_pricing_facts=(
                next_pricing_facts
                or tuple(item.next_pricing_fact for item in locked)
                + decision.action_triggers
            ),
        )
        adjusted_net_alpha = clock.time_adjusted_expected_net_alpha_bps
        alpha_reason = self._net_alpha_reason(instrument, adjusted_net_alpha)
        if alpha_reason is not None:
            return self._wait(
                common,
                alpha_reason,
                unreserved_expected_alpha=unreserved_expected_alpha,
                calibration_reserve=calibration_reserve,
                expected_alpha=expected_alpha,
                cost_bps=cost_bps,
                expected_net_alpha=expected_net_alpha,
                alpha_clock=clock,
            )

        (
            stress_fraction,
            liquidity_capacity,
            liquidity_source,
            exposure_capacity,
            exposure_binding_tag,
            constraints,
        ) = self._capacity_constraints(
            instrument=instrument,
            underwritings=locked,
            state=state,
            isolation=isolation,
            loss_budget=loss_budget,
            position_limit=position_limit,
            gross_limit=gross_limit,
            portfolio_stress_limit=portfolio_stress_limit,
            alpha_source_limit=alpha_source_limit,
            catalyst_before=catalyst_before,
            catalyst_limit=catalyst_limit,
            underlying_before=underlying_before,
            underlying_limit=underlying_limit,
            isolation_multiplier=isolation_multiplier,
            research_multiplier=research_multiplier,
            capital_multiplier=capital_governance.capital_multiplier,
            forecast_calibration_multiplier=(forecast_calibration.capital_multiplier),
            requested_position_limit=(
                policy.dollars(requested_position_nav_bps)
                if requested_position_nav_bps is not None
                else None
            ),
            requested_loss_budget=(
                policy.dollars(requested_trade_loss_nav_bps)
                if requested_trade_loss_nav_bps is not None
                else None
            ),
        )
        if liquidity_capacity is None:
            return self._wait(
                common,
                "liquidity_capacity_unverified",
                unreserved_expected_alpha=unreserved_expected_alpha,
                calibration_reserve=calibration_reserve,
                expected_alpha=expected_alpha,
                cost_bps=cost_bps,
                expected_net_alpha=expected_net_alpha,
                alpha_clock=clock,
                stress_fraction=stress_fraction,
            )

        binding_constraint, target_capacity = min(
            constraints.items(), key=lambda item: (item[1], item[0])
        )
        quantity = self._target_quantity(instrument, target_capacity)
        if quantity <= 0:
            return self._wait(
                common,
                "risk_budget_below_minimum_trade",
                unreserved_expected_alpha=unreserved_expected_alpha,
                calibration_reserve=calibration_reserve,
                expected_alpha=expected_alpha,
                cost_bps=cost_bps,
                expected_net_alpha=expected_net_alpha,
                alpha_clock=clock,
                stress_fraction=stress_fraction,
                liquidity_capacity=liquidity_capacity,
                liquidity_source=liquidity_source,
                binding_constraint=binding_constraint,
            )
        target_notional = instrument.quote.ask * quantity
        stress_loss = target_notional * stress_fraction
        execution = build_execution_plan(
            instrument,
            target_quantity=quantity,
            alpha_clock=clock,
            paper_mirror=paper_mirror,
            participation_cap_bps=(
                policy.option_open_interest_participation_bps
                if instrument.kind == "option"
                else policy.adv_participation_bps
            ),
        )
        if execution.status == "wait":
            return self._wait(
                common,
                execution.reason_codes[0],
                unreserved_expected_alpha=unreserved_expected_alpha,
                calibration_reserve=calibration_reserve,
                expected_alpha=expected_alpha,
                cost_bps=cost_bps,
                expected_net_alpha=expected_net_alpha,
                alpha_clock=clock,
                stress_fraction=stress_fraction,
                liquidity_capacity=liquidity_capacity,
                liquidity_source=liquidity_source,
                binding_constraint=binding_constraint,
            )
        return TradeImplementationPlan(
            status="ready",
            unreserved_expected_alpha_bps=unreserved_expected_alpha,
            forecast_calibration_reserve_bps=calibration_reserve,
            expected_alpha_bps=expected_alpha,
            estimated_cost_bps=cost_bps,
            expected_net_alpha_bps=expected_net_alpha,
            alpha_clock=clock,
            execution_plan=execution,
            stress_loss_fraction=stress_fraction,
            gross_notional_after=(
                state.gross_notional
                - state.prospective_replacement_credit
                + target_notional
            ),
            portfolio_stress_loss_after=(
                state.aggregate_stress_loss
                - state.prospective_replacement_stress_credit
                + stress_loss
            ),
            alpha_source_notional_after=alpha_source_before + target_notional,
            catalyst_notional_after=catalyst_before + target_notional,
            underlying_notional_after=underlying_before + target_notional,
            target_notional=target_notional,
            target_quantity=quantity,
            estimated_stress_loss=stress_loss,
            liquidity_capacity=liquidity_capacity,
            liquidity_source=liquidity_source,
            binding_constraint=binding_constraint,
            exposure_capacity=exposure_capacity,
            exposure_binding_tag=exposure_binding_tag,
            **common,
        )

    def _admission_reason(
        self,
        isolation: AlphaIsolation,
        research_quality_score: Decimal | None,
        underwritings: tuple[ScenarioUnderwriting, ...],
    ) -> str | None:
        if isolation.posture == "audited" and isolation.reason_codes:
            return isolation.reason_codes[0]
        if (
            isolation.posture == "audited"
            and isolation.conservative_score is not None
            and isolation.conservative_score < self.policy.min_alpha_isolation_score
        ):
            return "alpha_isolation_below_hurdle"
        if isolation.hedge_posture == "requires_multi_leg":
            return "alpha_requires_unsupported_multi_leg_expression"
        if (
            research_quality_score is not None
            and research_quality_score < self.policy.min_research_quality_score
        ):
            return "research_quality_below_capital_hurdle"
        if len(underwritings) != 2:
            return "independent_underwriting_unavailable"
        return None

    def _net_alpha_reason(
        self, instrument: MarketInstrument, adjusted_net_alpha: Decimal
    ) -> str | None:
        if instrument.kind == "option":
            return (
                "nonpositive_net_alpha_for_option" if adjusted_net_alpha <= 0 else None
            )
        if adjusted_net_alpha < self.policy.min_net_alpha_bps:
            return "insufficient_net_alpha_after_costs"
        return None

    def _capacity_constraints(
        self,
        *,
        instrument: MarketInstrument,
        underwritings: tuple[ScenarioUnderwriting, ScenarioUnderwriting],
        state: PortfolioState,
        isolation: AlphaIsolation,
        loss_budget: Decimal,
        position_limit: Decimal,
        gross_limit: Decimal,
        portfolio_stress_limit: Decimal,
        alpha_source_limit: Decimal,
        catalyst_before: Decimal,
        catalyst_limit: Decimal,
        underlying_before: Decimal,
        underlying_limit: Decimal,
        isolation_multiplier: Decimal,
        research_multiplier: Decimal,
        capital_multiplier: Decimal,
        forecast_calibration_multiplier: Decimal,
        requested_position_limit: Decimal | None,
        requested_loss_budget: Decimal | None,
    ) -> tuple[
        Decimal,
        Decimal | None,
        str | None,
        Decimal | None,
        SystematicExposure | None,
        dict[str, Decimal],
    ]:
        stress_fraction = self._stress_fraction(instrument, underwritings)
        liquidity_capacity, liquidity_source = self._liquidity_capacity(instrument)
        if liquidity_capacity is None:
            return stress_fraction, None, None, None, None, {}
        market_limit = Decimal(str(instrument.metadata.get("notional_limit", "0")))
        if market_limit <= 0:
            market_limit = instrument.quote.ask * instrument.quantity
        constraints = {
            "market_data_limit": market_limit,
            "position_nav_limit": position_limit
            * min(
                isolation_multiplier,
                research_multiplier,
                capital_multiplier,
                forecast_calibration_multiplier,
            ),
            "gross_nav_remaining": max(
                Decimal(0),
                gross_limit
                - state.gross_notional
                + state.prospective_replacement_credit,
            ),
            "stress_loss_budget": loss_budget / stress_fraction,
            "portfolio_stress_remaining": max(
                Decimal(0),
                portfolio_stress_limit
                - state.aggregate_stress_loss
                + state.prospective_replacement_stress_credit,
            )
            / stress_fraction,
            "alpha_source_remaining": max(
                Decimal(0),
                alpha_source_limit
                - next(
                    (
                        item.gross_notional
                        for item in state.alpha_source_buckets
                        if item.source == isolation.alpha_source
                    ),
                    Decimal(0),
                ),
            ),
            "catalyst_remaining": max(Decimal(0), catalyst_limit - catalyst_before),
            "underlying_remaining": max(
                Decimal(0), underlying_limit - underlying_before
            ),
            "liquidity_exit_capacity": liquidity_capacity,
        }
        if requested_position_limit is not None:
            constraints["agent_requested_position"] = requested_position_limit
        if requested_loss_budget is not None:
            constraints["agent_requested_trade_loss"] = (
                requested_loss_budget / stress_fraction
            )
        exposure_capacity, exposure_tag = self._exposure_capacity(state, isolation)
        if exposure_capacity is not None:
            constraints[f"systematic_exposure:{exposure_tag}"] = exposure_capacity
        return (
            stress_fraction,
            liquidity_capacity,
            liquidity_source,
            exposure_capacity,
            exposure_tag,
            constraints,
        )

    def _stress_fraction(
        self,
        instrument: MarketInstrument,
        underwritings: tuple[ScenarioUnderwriting, ScenarioUnderwriting],
    ) -> Decimal:
        if instrument.kind == "option":
            return Decimal(1)
        worst_bear_bps = min(
            Decimal(item.bear.relative_alpha_bps) for item in underwritings
        )
        return min(
            Decimal(1),
            max(
                self.policy.equity_stress_floor_bps / Decimal(10_000),
                abs(worst_bear_bps) / Decimal(10_000),
            ),
        )

    @staticmethod
    def _target_quantity(
        instrument: MarketInstrument, target_capacity: Decimal
    ) -> Decimal:
        step = Decimal(100) if instrument.kind == "option" else Decimal(1)
        quantity = (target_capacity / instrument.quote.ask / step).to_integral_value(
            rounding=ROUND_DOWN
        ) * step
        return min(quantity, instrument.quantity)

    def revalidate(
        self,
        plan: TradeImplementationPlan,
        *,
        prospective_rotation: bool = False,
    ) -> tuple[str, ...]:
        """Rechecks mutable portfolio capacity immediately before an entry intent."""

        if plan.status != "ready":
            return ("implementation_plan_not_ready",)
        state = self.load_state()
        return (
            *self._revalidate_book_limits(plan, state, prospective_rotation),
            *self._revalidate_governance(plan),
            *self._revalidate_concentration(plan, state),
            *self._revalidate_alpha_clock(plan),
        )

    def _revalidate_book_limits(
        self,
        plan: TradeImplementationPlan,
        state: PortfolioState,
        prospective_rotation: bool,
    ) -> tuple[str, ...]:
        reasons = []
        if state.known_open_positions > self.max_open_positions or (
            state.known_open_positions == self.max_open_positions
            and not prospective_rotation
        ):
            reasons.append("position_limit_changed_before_entry")
        replacement_credit = (
            plan.gross_replacement_credit if prospective_rotation else Decimal(0)
        )
        if (
            state.gross_notional - replacement_credit + plan.target_notional
            > plan.gross_notional_limit
        ):
            reasons.append("gross_limit_changed_before_entry")
        if (
            plan.target_notional
            > plan.position_notional_limit * plan.alpha_isolation_multiplier
        ):
            reasons.append("position_limit_changed_before_entry")
        if (
            plan.target_notional
            > plan.position_notional_limit * plan.research_quality_multiplier
        ):
            reasons.append("research_quality_limit_changed_before_entry")
        if plan.estimated_stress_loss > plan.loss_budget:
            reasons.append("loss_budget_changed_before_entry")
        stress_credit = (
            plan.portfolio_stress_replacement_credit
            if prospective_rotation
            and plan.portfolio_stress_replacement_credit is not None
            else Decimal(0)
        )
        if (
            plan.portfolio_stress_loss_limit is not None
            and state.aggregate_stress_loss - stress_credit + plan.estimated_stress_loss
            > plan.portfolio_stress_loss_limit
        ):
            reasons.append("portfolio_stress_limit_changed_before_entry")
        return tuple(reasons)

    def _revalidate_governance(self, plan: TradeImplementationPlan) -> tuple[str, ...]:
        reasons = []
        current_governance = self.load_alpha_governance()
        if (
            plan.alpha_capital_governance is None
            or current_governance.policy_version
            != plan.alpha_capital_governance.policy_version
            or current_governance.source_portfolio_policy_version
            != plan.alpha_capital_governance.source_portfolio_policy_version
        ):
            reasons.append("alpha_governance_policy_changed_before_entry")
        elif (
            plan.target_notional
            > plan.position_notional_limit * current_governance.capital_multiplier
        ):
            reasons.append("alpha_governance_tightened_before_entry")
        frozen_calibration = plan.forecast_calibration_governance
        if frozen_calibration is None:
            reasons.append("forecast_calibration_policy_changed_before_entry")
        else:
            current_calibration = self.load_forecast_calibration(
                frozen_calibration.expression_kind
            )
            if (
                current_calibration.policy_version != frozen_calibration.policy_version
                or current_calibration.source_portfolio_policy_version
                != frozen_calibration.source_portfolio_policy_version
                or current_calibration.expression_kind
                != frozen_calibration.expression_kind
            ):
                reasons.append("forecast_calibration_policy_changed_before_entry")
            else:
                if (
                    plan.target_notional
                    > plan.position_notional_limit
                    * current_calibration.capital_multiplier
                ):
                    reasons.append("forecast_calibration_tightened_before_entry")
                if (
                    current_calibration.alpha_reserve_bps
                    > plan.forecast_calibration_reserve_bps
                ):
                    reasons.append("forecast_calibration_reserve_changed_before_entry")
        frozen_execution = plan.execution_cost_governance
        if frozen_execution is None:
            reasons.append("execution_cost_policy_changed_before_entry")
        else:
            current_execution = self.load_execution_cost_governance(
                frozen_execution.expression_kind
            )
            if (
                current_execution.policy_version != frozen_execution.policy_version
                or current_execution.source_portfolio_policy_version
                != frozen_execution.source_portfolio_policy_version
                or current_execution.expression_kind != frozen_execution.expression_kind
            ):
                reasons.append("execution_cost_policy_changed_before_entry")
            elif current_execution.alpha_reserve_bps > plan.execution_cost_reserve_bps:
                reasons.append("execution_cost_reserve_changed_before_entry")
        return tuple(reasons)

    def _revalidate_concentration(
        self, plan: TradeImplementationPlan, state: PortfolioState
    ) -> tuple[str, ...]:
        reasons = []
        source_notional = next(
            (
                item.gross_notional
                for item in state.alpha_source_buckets
                if item.source == plan.alpha_source
            ),
            Decimal(0),
        )
        if (
            plan.alpha_source_notional_limit is not None
            and source_notional + plan.target_notional
            > plan.alpha_source_notional_limit
        ):
            reasons.append("alpha_source_limit_changed_before_entry")
        catalyst_notional = next(
            (
                item.gross_notional
                for item in state.catalyst_buckets
                if item.catalyst_key == plan.catalyst_key
            ),
            Decimal(0),
        )
        if (
            plan.catalyst_notional_limit is not None
            and catalyst_notional + plan.target_notional > plan.catalyst_notional_limit
        ):
            reasons.append("catalyst_limit_changed_before_entry")
        underlying_notional = next(
            (
                item.gross_notional
                for item in state.underlying_buckets
                if item.underlying_key == plan.underlying_key
            ),
            Decimal(0),
        )
        if (
            plan.underlying_notional_limit is not None
            and underlying_notional + plan.target_notional
            > plan.underlying_notional_limit
        ):
            reasons.append("underlying_limit_changed_before_entry")
        exposure_by_tag = {
            item.tag: item.gross_notional for item in state.exposure_buckets
        }
        exposure_limit = self.policy.dollars(
            self.policy.max_systematic_exposure_nav_bps
        )
        if any(
            exposure_by_tag.get(tag, Decimal(0)) + plan.target_notional > exposure_limit
            for tag in plan.systematic_exposures
            if tag not in {"none", "unknown"}
        ):
            reasons.append("systematic_exposure_limit_changed_before_entry")
        return tuple(reasons)

    def _revalidate_alpha_clock(self, plan: TradeImplementationPlan) -> tuple[str, ...]:
        if plan.alpha_clock is not None:
            refreshed_clock = build_alpha_clock(
                known_at=datetime.now(UTC),
                evidence_freshness_at=plan.alpha_clock.evidence_freshness_at,
                horizon_days=plan.alpha_clock.horizon_days,
                raw_expected_net_alpha_bps=(
                    plan.alpha_clock.raw_expected_net_alpha_bps
                ),
                catalyst_clarity=plan.alpha_clock.catalyst_clarity,
                next_pricing_facts=plan.alpha_clock.next_pricing_facts,
            )
            if (
                refreshed_clock.time_adjusted_expected_net_alpha_bps
                < self.policy.min_net_alpha_bps
            ):
                return ("alpha_decayed_below_entry_hurdle",)
        return ()

    def _exposure_capacity(
        self, state: PortfolioState, isolation: AlphaIsolation
    ) -> tuple[Decimal | None, SystematicExposure | None]:
        exposures = isolation.binding_exposures
        if not exposures:
            return None, None
        current = {item.tag: item.gross_notional for item in state.exposure_buckets}
        limit = self.policy.dollars(self.policy.max_systematic_exposure_nav_bps)
        capacities = {
            tag: max(Decimal(0), limit - current.get(tag, Decimal(0)))
            for tag in exposures
        }
        tag, capacity = min(capacities.items(), key=lambda item: (item[1], item[0]))
        return capacity, tag

    def _liquidity_capacity(
        self, instrument: MarketInstrument
    ) -> tuple[Decimal | None, str | None]:
        policy = self.policy
        if instrument.kind == "option":
            open_interest = Decimal(str(instrument.metadata.get("open_interest", "0")))
            if open_interest <= 0:
                return None, None
            contracts = (
                open_interest
                * policy.option_open_interest_participation_bps
                / Decimal(10_000)
            ).to_integral_value(rounding=ROUND_DOWN)
            return (
                contracts * Decimal(100) * instrument.quote.ask,
                "massive_option_open_interest",
            )
        dollar_volume = Decimal(
            str(instrument.metadata.get("observed_day_dollar_volume", "0"))
        )
        if dollar_volume <= 0:
            return None, None
        return (
            dollar_volume
            * policy.adv_participation_bps
            / Decimal(10_000)
            * Decimal(policy.max_exit_days),
            "massive_snapshot_day_volume_proxy",
        )

    @staticmethod
    def _cost_bps(instrument: MarketInstrument) -> Decimal:
        spread = _spread_bps(instrument)
        if instrument.kind == "option":
            contracts = instrument.quantity / Decimal(100)
            notional = instrument.quote.ask * instrument.quantity
            commission = max(contracts * Decimal("0.65"), Decimal("0.01"))
            return spread + Decimal(50) + commission / notional * Decimal(10_000)
        notional = instrument.quote.ask * instrument.quantity
        commission = max(notional / Decimal(10_000), Decimal("0.01"))
        return spread + Decimal(5) + commission / notional * Decimal(10_000)

    @staticmethod
    def _wait(
        common: dict,
        reason: str,
        *,
        unreserved_expected_alpha: Decimal | None = None,
        calibration_reserve: Decimal = Decimal(0),
        expected_alpha: Decimal | None = None,
        cost_bps: Decimal | None = None,
        expected_net_alpha: Decimal | None = None,
        alpha_clock: AlphaClock | None = None,
        stress_fraction: Decimal | None = None,
        liquidity_capacity: Decimal | None = None,
        liquidity_source: str | None = None,
        binding_constraint: str | None = None,
        exposure_capacity: Decimal | None = None,
        exposure_binding_tag: SystematicExposure | None = None,
    ) -> TradeImplementationPlan:
        return TradeImplementationPlan(
            status="wait",
            unreserved_expected_alpha_bps=unreserved_expected_alpha,
            forecast_calibration_reserve_bps=calibration_reserve,
            expected_alpha_bps=expected_alpha,
            estimated_cost_bps=cost_bps,
            expected_net_alpha_bps=expected_net_alpha,
            alpha_clock=alpha_clock,
            stress_loss_fraction=stress_fraction,
            portfolio_stress_loss_after=common.get("portfolio_stress_loss_before"),
            alpha_source_notional_after=common.get("alpha_source_notional_before"),
            catalyst_notional_after=common.get("catalyst_notional_before"),
            underlying_notional_after=common.get("underlying_notional_before"),
            gross_notional_after=common["gross_notional_before"],
            target_notional=Decimal(0),
            target_quantity=Decimal(0),
            estimated_stress_loss=Decimal(0),
            liquidity_capacity=liquidity_capacity,
            liquidity_source=liquidity_source,
            binding_constraint=binding_constraint,
            exposure_capacity=exposure_capacity,
            exposure_binding_tag=exposure_binding_tag,
            reason_codes=(reason,),
            **common,
        )
