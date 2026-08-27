from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from .alpha_governance import AlphaCapitalGovernance
from .alpha_isolation import (
    AlphaIsolation,
    SystematicExposure,
    legacy_alpha_isolation,
    normalize_systematic_exposure,
)
from .alpha_lifecycle import AlphaClock, build_alpha_clock
from .database import Database
from .execution_planning import build_execution_plan
from .implementation import (
    ExposureBucket,
    PortfolioRiskPolicy,
    PortfolioState,
    TradeImplementationPlan,
)
from .market_data import MarketInstrument
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

    def load_state(self) -> PortfolioState:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT GREATEST(
                        p.entry_price,
                        COALESCE(
                            (SELECT (event.payload->'observation'->'quote'->>'ask')::numeric
                             FROM ops.event event
                             WHERE event.aggregate_id = p.id
                               AND event.environment = 'shadow'
                               AND event.event_type = 'position.monitored'
                             ORDER BY event.sequence DESC LIMIT 1),
                            p.entry_price
                        )
                    ) * p.quantity,
                    p.position_thesis
                FROM research.shadow_position p
                WHERE p.environment = 'shadow' AND p.status = 'open'
                ORDER BY p.opened_at, p.id"""
            ).fetchall()
        notionals = tuple(Decimal(row[0]) for row in rows)
        exposure_totals: dict[SystematicExposure, Decimal] = {}
        for notional, raw_thesis in rows:
            implementation = (
                raw_thesis.get("implementation_plan")
                if isinstance(raw_thesis, dict)
                else None
            )
            raw_exposures = (
                implementation.get("systematic_exposures", ())
                if isinstance(implementation, dict)
                else ("unknown",)
            )
            exposures = (
                raw_exposures
                if isinstance(raw_exposures, (list, tuple))
                else ("unknown",)
            )
            for exposure in tuple(
                dict.fromkeys(
                    normalize_systematic_exposure(item)
                    for item in (exposures or ("unknown",))
                )
            ):
                exposure_totals[exposure] = exposure_totals.get(
                    exposure, Decimal(0)
                ) + Decimal(notional)
        replacement_credit = (
            min(notionals)
            if len(notionals) >= self.max_open_positions and notionals
            else Decimal(0)
        )
        return PortfolioState(
            known_open_positions=len(notionals),
            gross_notional=sum(notionals, Decimal(0)),
            prospective_replacement_credit=replacement_credit,
            exposure_buckets=tuple(
                ExposureBucket(tag=tag, gross_notional=value)
                for tag, value in sorted(exposure_totals.items())
            ),
        )

    def load_alpha_governance(self) -> AlphaCapitalGovernance:
        if self.database is None:
            return AlphaCapitalGovernance.unscoped(self.policy.version)
        return self.database.alpha_capital_governance(
            "shadow",
            reference_nav=self.policy.reference_nav,
            source_portfolio_policy_version=self.policy.version,
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
    ) -> TradeImplementationPlan:
        state = state or self.load_state()
        policy = self.policy
        capital_governance = alpha_capital_governance or self.load_alpha_governance()
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
            "reference_nav": policy.reference_nav,
            "loss_budget": loss_budget,
            "position_notional_limit": position_limit,
            "gross_notional_before": state.gross_notional,
            "gross_replacement_credit": state.prospective_replacement_credit,
            "gross_notional_limit": gross_limit,
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
        expected_alpha = consensus["uncertainty_adjusted_expected_alpha_bps"]
        cost_bps = self._cost_bps(instrument)
        expected_net_alpha = expected_alpha - cost_bps
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
            isolation_multiplier=isolation_multiplier,
            research_multiplier=research_multiplier,
            capital_multiplier=capital_governance.capital_multiplier,
        )
        if liquidity_capacity is None:
            return self._wait(
                common,
                "liquidity_capacity_unverified",
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
        isolation_multiplier: Decimal,
        research_multiplier: Decimal,
        capital_multiplier: Decimal,
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
            * min(isolation_multiplier, research_multiplier, capital_multiplier),
            "gross_nav_remaining": max(
                Decimal(0),
                gross_limit
                - state.gross_notional
                + state.prospective_replacement_credit,
            ),
            "stress_loss_budget": loss_budget / stress_fraction,
            "liquidity_exit_capacity": liquidity_capacity,
        }
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
        if plan.estimated_stress_loss > plan.loss_budget:
            reasons.append("loss_budget_changed_before_entry")
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
                reasons.append("alpha_decayed_below_entry_hurdle")
        return tuple(reasons)

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
            expected_alpha_bps=expected_alpha,
            estimated_cost_bps=cost_bps,
            expected_net_alpha_bps=expected_net_alpha,
            alpha_clock=alpha_clock,
            stress_loss_fraction=stress_fraction,
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
