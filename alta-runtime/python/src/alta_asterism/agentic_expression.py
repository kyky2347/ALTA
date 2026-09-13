import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_context import bounded_text, opportunity_context
from .agentic_position import AgenticPositionBook
from .agentic_roles import (
    StructuredRoleRunner,
    StructuredRoleUnavailable,
    canonical_hash,
)
from .alpha_governance import AlphaCapitalGovernance
from .b5_runtime import B5Runtime
from .capital_allocation import CapitalAllocationDecision
from .database import Database
from .alpha_isolation import (
    HedgePosture,
    SystematicExposure,
    audited_alpha_isolation,
    provisional_alpha_isolation,
)
from .expression import ExpressionPolicy, ExpressionProposal, validate_expression
from .expression_tournament import (
    EvaluatedExpression,
    ExpressionHypothesis,
    normalized_hypotheses,
    select_audited_expression,
)
from .foundry import OpportunityDraft
from .implementation import PortfolioRiskPolicy, TradeImplementationPlan
from .market_data import InstrumentSelection, MarketInstrument, MassiveMarketData
from .paper_execution import TigerPaperExecutor
from .paper_instruments import MAX_POST_AUDIT_DRIFT_BPS, PAPER_INVERSE_ETFS
from .portfolio_construction import PortfolioConstructor
from .research_diligence import research_quality_components
from .shadow import LedgerTransaction, PositionThesis
from .underwriting import ScenarioUnderwriting


class ExpressionRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preferred_kind: Literal["stock", "etf", "option", "wait"]
    symbol: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    rationale: str = Field(min_length=1, max_length=2_000)
    payoff_thesis: str = Field(min_length=1, max_length=2_000)
    invalidation: str = Field(min_length=1, max_length=2_000)
    required_market_data: tuple[str, ...] = Field(default=(), max_length=10)
    intended_alpha: str = Field(
        default="Isolate the Opportunity's stated variant wedge.",
        min_length=1,
        max_length=800,
    )
    unwanted_exposures: tuple[str, ...] = Field(default=(), max_length=8)
    retained_exposure: str = Field(
        default="Residual market, sector, and instrument-specific exposure remains.",
        min_length=1,
        max_length=800,
    )
    alternatives_considered: tuple[str, ...] = Field(default=(), max_length=4)
    hypotheses: tuple[ExpressionHypothesis, ...] = Field(default=(), max_length=3)


class ExpressionAuditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["approve", "wait"]
    selected_hypothesis_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_-]{0,31}$"
    )
    thesis_alignment: float = Field(ge=0, le=1)
    implementation_quality: float = Field(ge=0, le=1)
    alpha_isolation_score: float = Field(default=1.0, ge=0, le=1)
    confirmed_systematic_exposures: tuple[SystematicExposure, ...] = Field(
        default=(), max_length=8
    )
    hedge_posture: HedgePosture = "not_applicable"
    basis_risk: str = Field(default="Not classified by a legacy audit.", max_length=800)
    exposure_disagreements: tuple[str, ...] = Field(default=(), max_length=8)
    largest_failure_mode: str = Field(min_length=1, max_length=1_200)
    portfolio_conflicts: tuple[str, ...] = Field(default=(), max_length=8)
    monitoring_plan: tuple[str, ...] = Field(min_length=1, max_length=8)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def wait_does_not_select_an_instrument(self) -> "ExpressionAuditDecision":
        if self.decision == "wait" and self.selected_hypothesis_id is not None:
            raise ValueError("wait audit cannot select an expression hypothesis")
        if len(set(self.confirmed_systematic_exposures)) != len(
            self.confirmed_systematic_exposures
        ):
            raise ValueError("audited systematic exposures must be unique")
        if (
            "none" in self.confirmed_systematic_exposures
            and len(self.confirmed_systematic_exposures) != 1
        ):
            raise ValueError("none cannot be combined with audited exposures")
        return self


def _bounded_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return bounded_text(value, 320)
    if isinstance(value, dict):
        return {
            str(key): _bounded_json_value(child)
            for key, child in list(value.items())[:20]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_json_value(child) for child in value[:10]]
    return value


def _bounded_rationale(value: dict, maximum_bytes: int = 3_900) -> str:
    compact = _bounded_json_value(value)
    text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str)
    encoded = text.encode()
    if len(encoded) <= maximum_bytes:
        return text
    recommendation = value.get("agent_recommendation") or {}
    audit = value.get("independent_audit") or {}
    implementation = value.get("implementation_plan") or {}
    capital_allocation = value.get("capital_allocation") or {}
    fallback = {
        "schema": "alta.expression-rationale.v3",
        "truncated": True,
        "content_hash": canonical_hash(value),
        "market_gate": bounded_text(value.get("market_gate"), 160),
        "gate": bounded_text(value.get("gate"), 160),
        "action": value.get("action"),
        "selected_hypothesis_id": value.get("selected_hypothesis_id"),
        "expression_slate": _bounded_json_value(
            [
                {
                    "hypothesis": {
                        key: (item.get("hypothesis") or {}).get(key)
                        for key in (
                            "hypothesis_id",
                            "kind",
                            "symbol",
                            "thesis_purity",
                            "timing_fit",
                            "alpha_source",
                            "systematic_exposures",
                            "hedge_posture",
                        )
                    },
                    "market_gate": item.get("market_gate"),
                    "admissible": item.get("admissible"),
                }
                for item in (value.get("expression_slate") or ())[:4]
                if isinstance(item, dict)
            ]
        ),
        "market_instrument": _bounded_json_value(value.get("market_instrument") or {}),
        "implementation_plan": {
            "status": implementation.get("status"),
            "reason_codes": implementation.get("reason_codes"),
            "target_quantity": implementation.get("target_quantity"),
            "target_notional": implementation.get("target_notional"),
            "binding_constraint": implementation.get("binding_constraint"),
            "alpha_source": implementation.get("alpha_source"),
            "systematic_exposures": implementation.get("systematic_exposures"),
            "alpha_isolation_score": implementation.get("alpha_isolation_score"),
            "alpha_isolation_multiplier": implementation.get(
                "alpha_isolation_multiplier"
            ),
            "alpha_capital_governance": {
                key: (implementation.get("alpha_capital_governance") or {}).get(key)
                for key in (
                    "posture",
                    "capital_multiplier",
                    "sample_size",
                    "window_size",
                    "max_drawdown_nav_bps",
                    "reason_codes",
                )
            },
            "exposure_binding_tag": implementation.get("exposure_binding_tag"),
            "catalyst_key": implementation.get("catalyst_key"),
            "catalyst_notional_before": implementation.get("catalyst_notional_before"),
            "catalyst_notional_limit": implementation.get("catalyst_notional_limit"),
            "catalyst_notional_after": implementation.get("catalyst_notional_after"),
        },
        "capital_allocation": {
            "status": capital_allocation.get("status"),
            "reason_code": capital_allocation.get("reason_code"),
            "incumbent_position_id": capital_allocation.get("incumbent_position_id"),
        },
        "agent_recommendation": {
            "preferred_kind": recommendation.get("preferred_kind"),
            "symbol": recommendation.get("symbol"),
            "rationale": bounded_text(recommendation.get("rationale"), 240),
            "invalidation": bounded_text(recommendation.get("invalidation"), 240),
        },
        "independent_audit": {
            "decision": audit.get("decision"),
            "largest_failure_mode": bounded_text(
                audit.get("largest_failure_mode"), 240
            ),
            "portfolio_conflicts": _bounded_json_value(
                [
                    bounded_text(str(item), 120)
                    for item in (audit.get("portfolio_conflicts") or ())[:4]
                ]
            ),
            "alpha_isolation_score": audit.get("alpha_isolation_score"),
            "confirmed_systematic_exposures": audit.get(
                "confirmed_systematic_exposures"
            ),
            "hedge_posture": audit.get("hedge_posture"),
            "monitoring_plan": _bounded_json_value(
                [
                    bounded_text(str(item), 120)
                    for item in (audit.get("monitoring_plan") or ())[:4]
                ]
            ),
            "rationale": bounded_text(audit.get("rationale"), 240),
        },
    }
    text = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text.encode()) > maximum_bytes:
        raise ValueError("expression rationale cannot fit the hard byte budget")
    return text


class AgenticExpressionFlow:
    """Lets an Agent choose payoff shape before the position lifecycle takes over."""

    PROMPT_VERSION = "agentic-expression-v13"
    AUDIT_PROMPT_VERSION = "expression-audit-v12"

    def __init__(
        self,
        database: Database,
        runner: StructuredRoleRunner,
        universe: tuple[str, ...],
        market_data: MassiveMarketData | None = None,
        *,
        audit_runner: StructuredRoleRunner | None = None,
        position_runner: StructuredRoleRunner | None = None,
        max_open_positions: int = 8,
        paper_executor: TigerPaperExecutor | None = None,
        broker_executor=None,
        acceptance_hold_seconds: int | None = None,
        portfolio_policy: PortfolioRiskPolicy | None = None,
    ) -> None:
        self.database = database
        self.expression_runner = runner
        self.audit_runner = audit_runner or runner
        self.universe = universe
        self.market_data = market_data
        self.paper_executor = paper_executor
        if paper_executor is not None and broker_executor is not None:
            raise ValueError("broker and Tiger Paper execution are mutually exclusive")
        self.broker_executor = broker_executor
        self.portfolio = PortfolioConstructor(
            database,
            portfolio_policy,
            max_open_positions=max_open_positions,
        )
        self.runtime = B5Runtime(database, capital_mode="disabled")
        self.positions = AgenticPositionBook(
            database,
            position_runner or runner,
            self.runtime,
            market_data,
            max_open_positions=max_open_positions,
            paper_executor=paper_executor,
            acceptance_hold_seconds=acceptance_hold_seconds,
            portfolio_constructor=self.portfolio,
        )
        self.defer_position_monitoring = True

    @property
    def capital_mode(self) -> str:
        if self.broker_executor is not None:
            return "broker_api"
        return (
            "tiger_paper_mirror" if self.paper_executor else self.runtime.capital_mode
        )

    def broker_context(self):
        broker = getattr(self, "broker_executor", None)
        if broker is None:
            return None
        return {
            key: broker.route[key]
            for key in (
                "provider",
                "environment",
                "binding",
                "revision",
                "profile_revision",
            )
        }

    def express(
        self, cycle_id: str, opportunity: OpportunityDraft, _wake_at: datetime
    ) -> ExpressionProposal:
        expression_id = (
            "expression_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    self.PROMPT_VERSION,
                    self.broker_context(),
                    self.expression_runner.model_provider,
                    self.expression_runner.model_id,
                    self.AUDIT_PROMPT_VERSION,
                    self.audit_runner.model_provider,
                    self.audit_runner.model_id,
                ]
            )[:32]
        )
        existing = self._existing(expression_id)
        if existing is not None:
            return existing
        run_id = (
            "run_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    self.PROMPT_VERSION,
                    self.broker_context(),
                    self.expression_runner.model_provider,
                    self.expression_runner.model_id,
                ]
            )[:32]
        )
        market_available = self.market_data is not None
        alpha_capital_governance = self.portfolio.load_alpha_governance()
        frozen_input = {
            "opportunity": opportunity_context(opportunity, narrative_bytes=480),
            "locked_underwriting": self._locked_underwriting(
                opportunity.opportunity_id
            ),
            "universe": self.universe,
            "alpha_capital_governance": alpha_capital_governance.model_dump(
                mode="json"
            ),
            "capabilities": {
                "selected_broker": self.broker_context(),
                "trusted_realtime_quote": market_available,
                "option_chain": market_available,
                "capital_mode": (
                    "broker_api"
                    if self.broker_context()
                    else "tiger_paper_mirror"
                    if self.paper_executor is not None
                    else "shadow_only"
                ),
                "allowed_expression_kinds": (
                    ("stock", "etf", "wait")
                    if self.paper_executor is not None or self.broker_context()
                    else ("stock", "etf", "option", "wait")
                ),
                "tiger_paper_mirror": self.paper_executor is not None,
                "paper_inverse_etfs": (
                    [
                        {
                            "symbol": symbol,
                            "underlying_symbol": value["underlying_symbol"],
                            "daily_target": value["daily_target"],
                            "path_dependency": (
                                "Daily reset; multi-day return can diverge materially "
                                "from the inverse of the underlying's cumulative return."
                            ),
                            "issuer_source": value["issuer_source"],
                        }
                        for symbol, value in PAPER_INVERSE_ETFS.items()
                    ]
                    if self.paper_executor is not None
                    else []
                ),
            },
        }
        result = self.expression_runner.run(
            cycle_id=cycle_id,
            run_id=run_id,
            role="expression_agent",
            prompt={
                "contract": "alta.expression-recommendation.v8",
                "mission": (
                    "Act as the implementation PM. Compare stock, ETF/proxy, long "
                    "option, and wait, then choose the cleanest supported payoff for "
                    "this Opportunity. For option, symbol means the underlying ticker; "
                    "the system selects the exact liquid contract."
                ),
                "untrusted_frozen_input": frozen_input,
                "rules": [
                    "Do not invent a quote, option chain, liquidity, or broker capability.",
                    "Do not submit an order; an isolated deterministic executor owns any later admitted Paper mutation.",
                    "Use a long put or inverse ETF for a negative thesis; never encode an unbounded short.",
                    "Select wait when the Opportunity cannot be mapped to a precise listed symbol.",
                    "Preserve thesis purity: choose the instrument whose payoff best isolates the stated variant wedge over the stated horizon.",
                    "Use locked_underwriting as two independent research estimates, not observed performance; preserve material disagreement and do not average away tail risk.",
                    "Treat alpha_capital_governance as a frozen portfolio budget derived from prior cost-adjusted Shadow outcomes; do not override, reinterpret, or lever above its multiplier.",
                    "Use each locked decision record: the expression must challenge the stated priced-in expectation, monetize the variant view and must-be-true conditions, fit the conservative edge half-life, and respect security-thesis readiness.",
                    "Do not turn a company thesis into a trade when either locked view requires re-underwriting or calls the security not decision-grade; choose wait.",
                    "Prefer a liquid simpler expression when its expected payoff is comparable; do not use optionality merely to amplify confidence.",
                    "State intended_alpha, every material unwanted exposure, the exposure deliberately retained, and concise alternatives_considered with rejection reasons.",
                    "Return hypotheses as a JSON array with one to three genuinely distinct stock, ETF/proxy, long-option, or wait payoff candidates. This bound reserves Massive request capacity for an independent post-audit quote refresh. Give each a stable short hypothesis_id, thesis_purity, timing_fit, and primary_tradeoff. The independent implementation auditor will see real market and portfolio checks before selecting one.",
                    "For every non-wait hypothesis, copy one or more exact thesis_pillar_ids from the Opportunity that its payoff actually monetizes. Do not claim a causal pillar merely because the same ticker appears. If no listed one-leg payoff cleanly maps to a supplied pillar, choose wait.",
                    "For every hypothesis classify alpha_source as idiosyncratic, earnings_revision, event, relative_value, market_structure, systematic_factor, or legacy_unclassified; legacy_unclassified is admissible only for wait.",
                    "For every hypothesis return the complete systematic_exposures set using only market_beta, sector, growth_duration, value, momentum, quality, size, volatility, rates, fx, commodity, liquidity, crowding, event_gap, none, or unknown. Use none only by itself and unknown only when choosing wait.",
                    "For every non-wait hypothesis choose requested_position_nav_bps and requested_trade_loss_nav_bps, plus a concrete sizing_rationale tied to evidence strength, payoff asymmetry, invalidation distance, liquidity, correlation, and the Alpha clock. These are your requested targets, not guarantees: deterministic portfolio and broker limits retain final authority. Do not default mechanically to one share.",
                    "State hedge_posture as unhedged_intentional, size_down, contained_by_option, requires_multi_leg, or not_applicable, and state concrete basis_risk. Do not call broad beta or factor exposure Alpha.",
                    "Compare thesis purity, catalyst timing, convexity, premium at risk, factor contamination, path dependence, liquidity, and exit feasibility; best expression is not automatically the issuer's common stock.",
                    "The current Shadow boundary supports one bounded long leg. If the thesis truly requires a short, pair, spread, basket, dynamic hedge, or uncovered option, choose wait instead of approximating it with a different bet.",
                    "When tiger_paper_mirror is true, choose only a long stock or ETF; options are not admitted by the acceptance boundary.",
                    "When selected_broker is present, plan only whole-share, long USD stock or ETF DAY limit orders. The broker ledger admits one active plan per account; no options, shorts, rotation, leverage or cross-account fallback. Respect its explicitly selected Paper or LIVE environment.",
                    "For a negative thesis in Tiger Paper, use only a supplied paper_inverse_etf whose underlying matches the Opportunity; account explicitly for daily reset and path dependence, otherwise choose wait.",
                ],
            },
            output_type=ExpressionRecommendation,
            frozen_input=frozen_input,
            evidence_ids=opportunity.evidence_ids,
            known_at=datetime.now(UTC),
            prompt_version=self.PROMPT_VERSION,
        )
        recommendation = result.value
        underwritings = self._locked_underwriting_models(opportunity.opportunity_id)
        try:
            slate = self._evaluate_slate(
                recommendation,
                opportunity,
                underwritings,
                alpha_capital_governance,
            )
        except Exception as error:
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                f"expression_slate_invalid:{type(error).__name__}",
            )
        primary = next((item for item in slate if item.ready), slate[0])
        instrument = primary.instrument
        implementation = primary.implementation
        allocation = primary.capital_allocation
        if instrument is not None and implementation is not None:
            instrument = replace(instrument, quantity=implementation.target_quantity)
        try:
            audit = self._audit(
                cycle_id,
                opportunity,
                recommendation,
                instrument,
                primary.market_gate,
                implementation,
                allocation,
                slate,
            )
        except Exception as error:
            budget_reasons = {
                "prompt_budget": "independent_audit_prompt_budget",
                "frozen_input_budget": "independent_audit_frozen_input_budget",
            }
            audit_failure = (
                budget_reasons.get(str(error))
                if isinstance(error, StructuredRoleUnavailable)
                else None
            ) or f"independent_audit_unavailable:{type(error).__name__}"
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                audit_failure,
                implementation=implementation,
                capital_allocation=allocation,
                expression_slate=slate,
            )
        if audit.decision == "wait":
            wait_reason = (
                "independent_audit_wait"
                if any(item.ready for item in slate)
                else primary.market_gate
            )
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                wait_reason,
                audit,
                implementation,
                allocation,
                slate,
            )
        try:
            selected = select_audited_expression(
                slate,
                decision=audit.decision,
                selected_hypothesis_id=audit.selected_hypothesis_id,
            )
        except ValueError:
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                "independent_audit_selection_invalid",
                audit,
                implementation,
                allocation,
                slate,
            )
        if (
            selected is None
            or selected.instrument is None
            or selected.implementation is None
            or selected.capital_allocation is None
        ):
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                "independent_audit_selected_wait",
                audit,
                implementation,
                allocation,
                slate,
            )
        instrument = replace(
            selected.instrument,
            quantity=selected.implementation.target_quantity,
        )
        isolation = audited_alpha_isolation(
            alpha_source=selected.hypothesis.alpha_source,
            proposed_exposures=selected.hypothesis.systematic_exposures,
            confirmed_exposures=audit.confirmed_systematic_exposures,
            proposed_hedge_posture=selected.hypothesis.hedge_posture,
            audited_hedge_posture=audit.hedge_posture,
            thesis_purity=selected.hypothesis.thesis_purity,
            timing_fit=selected.hypothesis.timing_fit,
            thesis_alignment=audit.thesis_alignment,
            implementation_quality=audit.implementation_quality,
            auditor_score=audit.alpha_isolation_score,
            basis_risk=audit.basis_risk or selected.hypothesis.basis_risk,
            exposure_disagreements=audit.exposure_disagreements,
        )
        implementation = selected.implementation
        allocation = selected.capital_allocation
        execution_selection = self._refresh_after_audit(
            recommendation, opportunity, instrument
        )
        if execution_selection.instrument is None:
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                execution_selection.reason,
                audit,
                implementation,
                allocation,
                slate,
            )
        instrument = execution_selection.instrument
        implementation = self.portfolio.plan(
            instrument,
            underwritings,
            intended_alpha=recommendation.intended_alpha,
            unwanted_exposures=recommendation.unwanted_exposures,
            retained_exposure=recommendation.retained_exposure,
            monitoring_triggers=tuple(
                dict.fromkeys((recommendation.invalidation, *audit.monitoring_plan))
            )[:8],
            known_at=datetime.now(UTC),
            evidence_freshness_at=(opportunity.freshness_at or opportunity.known_at),
            horizon_days=opportunity.horizon_days,
            next_pricing_facts=tuple(filter(None, (opportunity.first_rejection,))),
            paper_mirror=self.paper_executor is not None,
            alpha_isolation=isolation,
            research_quality_score=research_quality_components(
                opportunity.research_diligence
            )["research_quality"],
            alpha_capital_governance=alpha_capital_governance,
            catalyst_key=opportunity.catalyst_key,
            requested_position_nav_bps=selected.hypothesis.requested_position_nav_bps,
            requested_trade_loss_nav_bps=(
                selected.hypothesis.requested_trade_loss_nav_bps
            ),
            sizing_rationale=selected.hypothesis.sizing_rationale,
        )
        if implementation.status == "wait":
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                "post_audit_portfolio_construction:"
                + ",".join(implementation.reason_codes),
                audit,
                implementation,
                expression_slate=slate,
            )
        allocation = self.positions.assess_capital(implementation, datetime.now(UTC))
        if allocation.status == "wait":
            return self._persist_wait(
                expression_id,
                opportunity,
                recommendation,
                "capital_allocation:" + allocation.reason_code,
                audit,
                implementation,
                allocation,
                slate,
            )
        instrument = replace(instrument, quantity=implementation.target_quantity)
        proposal = ExpressionProposal(
            expression_id=expression_id,
            binding=self.runtime.expressions.binding_for(opportunity.opportunity_id),
            kind=instrument.kind,
            symbol=instrument.symbol,
            side="long",
            quantity=instrument.quantity,
            rationale=_bounded_rationale(
                {
                    "agent_recommendation": recommendation.model_dump(mode="json"),
                    "independent_audit": audit.model_dump(mode="json"),
                    "market_gate": selected.market_gate,
                    "execution_quote_gate": execution_selection.reason,
                    "selected_hypothesis_id": selected.hypothesis.hypothesis_id,
                    "expression_slate": [item.prompt_value() for item in slate],
                    "market_instrument": {
                        "underlying_symbol": instrument.underlying_symbol,
                        **instrument.metadata,
                    },
                    "implementation_plan": implementation.model_dump(mode="json"),
                    "capital_allocation": allocation.model_dump(mode="json"),
                }
            ),
            decision_known_at=datetime.now(UTC),
            quote=instrument.quote,
            implementation_plan=implementation,
            thesis_pillar_ids=selected.hypothesis.thesis_pillar_ids,
        )
        validation = validate_expression(proposal, ExpressionPolicy())
        self.runtime.expressions.persist(proposal, validation)
        if validation.status == "validated":
            self.positions.record_capital_decision(cycle_id, expression_id, allocation)
            return proposal
        wait_id = (
            "expression_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    "market-rejected-wait-v4",
                    self.expression_runner.model_provider,
                    self.expression_runner.model_id,
                    self.audit_runner.model_provider,
                    self.audit_runner.model_id,
                ]
            )[:32]
        )
        return self._persist_wait(
            wait_id,
            opportunity,
            recommendation,
            "market_validation_rejected:" + ",".join(validation.reason_codes),
            audit,
            implementation,
            allocation,
            slate,
        )

    def _evaluate_slate(
        self,
        recommendation: ExpressionRecommendation,
        opportunity: OpportunityDraft,
        underwritings: tuple[ScenarioUnderwriting, ...],
        alpha_capital_governance: AlphaCapitalGovernance,
    ) -> tuple[EvaluatedExpression, ...]:
        hypotheses = normalized_hypotheses(
            recommendation.hypotheses,
            preferred_kind=recommendation.preferred_kind,
            preferred_symbol=recommendation.symbol,
            payoff_thesis=recommendation.payoff_thesis,
        )
        available_pillars = {item.pillar_id for item in opportunity.thesis_pillars}
        for hypothesis in hypotheses:
            selected_pillars = set(hypothesis.thesis_pillar_ids)
            if not selected_pillars.issubset(available_pillars):
                raise ValueError("expression cites an unavailable thesis pillar")
            if (
                opportunity.thesis_pillars
                and hypothesis.kind != "wait"
                and not selected_pillars
            ):
                raise ValueError("instrument expression must map to a thesis pillar")
        evaluated = []
        research_quality = research_quality_components(opportunity.research_diligence)[
            "research_quality"
        ]
        for hypothesis in hypotheses:
            try:
                selection = self._select_hypothesis(hypothesis, opportunity)
            except Exception as error:
                selection = InstrumentSelection(
                    None, f"market_data_unavailable:{type(error).__name__}"
                )
            if selection.instrument is None:
                evaluated.append(
                    EvaluatedExpression(
                        hypothesis=hypothesis,
                        market_gate=selection.reason,
                        instrument=None,
                        implementation=None,
                        capital_allocation=None,
                    )
                )
                continue
            provisional_isolation = provisional_alpha_isolation(
                alpha_source=hypothesis.alpha_source,
                systematic_exposures=hypothesis.systematic_exposures,
                hedge_posture=hypothesis.hedge_posture,
                thesis_purity=hypothesis.thesis_purity,
                timing_fit=hypothesis.timing_fit,
                basis_risk=hypothesis.basis_risk,
            )
            plan = self.portfolio.plan(
                selection.instrument,
                underwritings,
                intended_alpha=recommendation.intended_alpha,
                unwanted_exposures=recommendation.unwanted_exposures,
                retained_exposure=recommendation.retained_exposure,
                monitoring_triggers=(recommendation.invalidation,),
                known_at=datetime.now(UTC),
                evidence_freshness_at=(
                    opportunity.freshness_at or opportunity.known_at
                ),
                horizon_days=opportunity.horizon_days,
                next_pricing_facts=tuple(
                    filter(None, (opportunity.first_rejection, opportunity.next_test))
                ),
                paper_mirror=self.paper_executor is not None,
                alpha_isolation=provisional_isolation,
                research_quality_score=research_quality,
                alpha_capital_governance=alpha_capital_governance,
                catalyst_key=opportunity.catalyst_key,
                requested_position_nav_bps=hypothesis.requested_position_nav_bps,
                requested_trade_loss_nav_bps=(hypothesis.requested_trade_loss_nav_bps),
                sizing_rationale=hypothesis.sizing_rationale,
            )
            allocation = self.positions.assess_capital(plan, datetime.now(UTC))
            instrument = (
                replace(selection.instrument, quantity=plan.target_quantity)
                if plan.status == "ready"
                else selection.instrument
            )
            evaluated.append(
                EvaluatedExpression(
                    hypothesis=hypothesis,
                    market_gate=selection.reason,
                    instrument=instrument,
                    implementation=plan,
                    capital_allocation=allocation,
                )
            )
        return tuple(evaluated)

    def _select(
        self,
        recommendation: ExpressionRecommendation,
        opportunity: OpportunityDraft,
    ) -> InstrumentSelection:
        hypothesis = normalized_hypotheses(
            (),
            preferred_kind=recommendation.preferred_kind,
            preferred_symbol=recommendation.symbol,
            payoff_thesis=recommendation.payoff_thesis,
        )[0]
        return self._select_hypothesis(hypothesis, opportunity)

    def _select_hypothesis(
        self,
        hypothesis: ExpressionHypothesis,
        opportunity: OpportunityDraft,
    ) -> InstrumentSelection:
        if hypothesis.kind == "wait":
            return InstrumentSelection(None, "agent_selected_wait")
        if self.market_data is None:
            return InstrumentSelection(None, "trusted_realtime_quote_unavailable")
        if hypothesis.symbol is None:
            return InstrumentSelection(None, "precise_symbol_unavailable")
        if hypothesis.kind == "option":
            if self.broker_context():
                return InstrumentSelection(None, "broker_execution_equity_only")
            if self.paper_executor is not None:
                return InstrumentSelection(None, "paper_acceptance_equity_only")
            return self.market_data.option(
                hypothesis.symbol,
                opportunity.direction,
                opportunity.horizon_days,
            )
        if self.paper_executor is not None:
            symbol = hypothesis.symbol.upper()
            inverse = PAPER_INVERSE_ETFS.get(symbol)
            if inverse is not None:
                searchable = " ".join(
                    filter(None, (opportunity.entity_key, opportunity.title))
                ).upper()
                if opportunity.direction != "negative" or not any(
                    alias in searchable for alias in inverse["aliases"]
                ):
                    return InstrumentSelection(
                        None, "inverse_etf_does_not_match_opportunity"
                    )
                return self.market_data.equity(
                    "etf",
                    symbol,
                    underlying_symbol=inverse["underlying_symbol"],
                    metadata={
                        "daily_target": inverse["daily_target"],
                        "path_dependency": "daily_reset",
                        "issuer_source": inverse["issuer_source"],
                    },
                )
            if opportunity.direction == "negative":
                return InstrumentSelection(
                    None, "negative_thesis_requires_approved_inverse_etf"
                )
            if symbol not in self.universe:
                return InstrumentSelection(None, "symbol_outside_approved_universe")
        return self.market_data.equity(hypothesis.kind, hypothesis.symbol)

    def _refresh_after_audit(
        self,
        recommendation: ExpressionRecommendation,
        opportunity: OpportunityDraft,
        audited: MarketInstrument,
    ) -> InstrumentSelection:
        if self.market_data is None:
            return InstrumentSelection(None, "post_audit_market_data_unavailable")
        quote = self.market_data.quote(
            audited.kind,
            audited.symbol,
            underlying_symbol=audited.underlying_symbol,
        )
        if quote is None:
            return InstrumentSelection(None, "post_audit_quote_unavailable")
        refreshed = replace(audited, quote=quote)
        if (
            refreshed.kind != audited.kind
            or refreshed.symbol != audited.symbol
            or refreshed.underlying_symbol != audited.underlying_symbol
        ):
            return InstrumentSelection(None, "post_audit_instrument_changed")
        audited_midpoint = (audited.quote.bid + audited.quote.ask) / Decimal(2)
        refreshed_midpoint = (refreshed.quote.bid + refreshed.quote.ask) / Decimal(2)
        drift_bps = (
            abs(refreshed_midpoint - audited_midpoint)
            / audited_midpoint
            * Decimal(10_000)
        )
        if drift_bps > MAX_POST_AUDIT_DRIFT_BPS:
            return InstrumentSelection(None, "post_audit_price_drift")
        return InstrumentSelection(refreshed, "post_audit_quote_refreshed")

    def _persist_wait(
        self,
        expression_id: str,
        opportunity: OpportunityDraft,
        recommendation: ExpressionRecommendation,
        reason: str,
        audit: ExpressionAuditDecision | None = None,
        implementation: TradeImplementationPlan | None = None,
        capital_allocation: CapitalAllocationDecision | None = None,
        expression_slate: tuple[EvaluatedExpression, ...] = (),
    ) -> ExpressionProposal:
        existing = self._existing(expression_id)
        if existing is not None:
            return existing
        proposal = ExpressionProposal(
            expression_id=expression_id,
            binding=self.runtime.expressions.binding_for(opportunity.opportunity_id),
            kind="wait",
            rationale=_bounded_rationale(
                {
                    "agent_recommendation": recommendation.model_dump(mode="json"),
                    "independent_audit": (
                        audit.model_dump(mode="json") if audit is not None else None
                    ),
                    "gate": reason,
                    "action": "wait",
                    "expression_slate": [
                        item.prompt_value() for item in expression_slate
                    ],
                    "implementation_plan": (
                        implementation.model_dump(mode="json")
                        if implementation is not None
                        else None
                    ),
                    "capital_allocation": (
                        capital_allocation.model_dump(mode="json")
                        if capital_allocation is not None
                        else None
                    ),
                }
            ),
            decision_known_at=datetime.now(UTC),
            implementation_plan=implementation,
        )
        self.runtime.expressions.persist(
            proposal, validate_expression(proposal, ExpressionPolicy())
        )
        return proposal

    def _audit(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        recommendation: ExpressionRecommendation,
        instrument: MarketInstrument | None,
        market_gate: str,
        implementation: TradeImplementationPlan | None,
        capital_allocation: CapitalAllocationDecision | None = None,
        expression_slate: tuple[EvaluatedExpression, ...] = (),
    ) -> ExpressionAuditDecision:
        run_id = (
            "run_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    self.AUDIT_PROMPT_VERSION,
                    self.broker_context(),
                    self.audit_runner.model_provider,
                    self.audit_runner.model_id,
                ]
            )[:32]
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT p.id, p.symbol, e.kind, e.rationale, p.position_thesis
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.environment = 'shadow' AND p.status = 'open'
                ORDER BY p.opened_at, p.id LIMIT 8"""
            ).fetchall()
        portfolio = []
        for position_id, symbol, kind, rationale, position_thesis in rows:
            try:
                parsed = json.loads(rationale)
            except (TypeError, ValueError):
                parsed = {}
            market_instrument = parsed.get("market_instrument") or {}
            incumbent_plan = (
                position_thesis.get("implementation_plan")
                if isinstance(position_thesis, dict)
                else None
            ) or {}
            portfolio.append(
                {
                    "position_id": position_id,
                    "symbol": symbol,
                    "kind": kind,
                    "underlying_symbol": market_instrument.get("underlying_symbol"),
                    "intended_alpha": bounded_text(
                        incumbent_plan.get("intended_alpha"), 160
                    ),
                    "alpha_source": incumbent_plan.get("alpha_source"),
                    "systematic_exposures": incumbent_plan.get(
                        "systematic_exposures", []
                    ),
                    "alpha_isolation_score": incumbent_plan.get(
                        "alpha_isolation_score"
                    ),
                    "target_notional": incumbent_plan.get("target_notional"),
                }
            )
        slate_values = [item.audit_value() for item in expression_slate]
        selected_instrument = None
        if instrument is not None:
            selected_instrument = {
                "kind": instrument.kind,
                "symbol": instrument.symbol,
                "underlying_symbol": instrument.underlying_symbol,
                "quantity": str(instrument.quantity),
                "quote": {
                    "bid": str(instrument.quote.bid),
                    "ask": str(instrument.quote.ask),
                    "as_of": instrument.quote.as_of.isoformat(),
                    "known_at": instrument.quote.known_at.isoformat(),
                },
            }
        # The implementation desk needs a decision brief, not a second copy of
        # the full research memo.  Keep this hand-off deliberately compact so
        # the replayable JSONB record stays inside the same byte boundary that
        # PostgreSQL enforces.
        audit_opportunity = opportunity_context(opportunity, narrative_bytes=96)
        for field in (
            "research_mode",
            "parent_opportunity_id",
            "research_question",
            "beneficiary_path",
            "disconfirming_evidence",
            "next_test",
            "research_diligence",
            # Durable identity and display metadata are already bound by the
            # opportunity ID and the run input hash.  Repeating them consumes
            # scarce audit context without changing the implementation call.
            "version",
            "snapshot_hash",
            "title",
            "entity_key",
            "prediction",
        ):
            audit_opportunity.pop(field, None)
        audit_recommendation = {
            "intended_alpha": bounded_text(recommendation.intended_alpha, 180),
            "unwanted_exposures": tuple(
                bounded_text(item, 120) for item in recommendation.unwanted_exposures
            ),
            "retained_exposure": bounded_text(recommendation.retained_exposure, 180),
        }
        if not expression_slate:
            audit_recommendation.update(
                {
                    "preferred_kind": recommendation.preferred_kind,
                    "symbol": recommendation.symbol,
                    "rationale": bounded_text(recommendation.rationale, 240),
                    "payoff_thesis": bounded_text(recommendation.payoff_thesis, 240),
                    "invalidation": bounded_text(recommendation.invalidation, 200),
                    "alternatives_considered": tuple(
                        bounded_text(item, 160)
                        for item in recommendation.alternatives_considered
                    ),
                }
            )
        frozen_input = {
            "opportunity": audit_opportunity,
            "broker_execution": self.broker_context(),
            "broker_opportunity_binding": {
                "version": opportunity.version,
                "snapshot_hash": opportunity.snapshot_hash,
            }
            if self.broker_context()
            else None,
            "locked_underwriting": self._locked_underwriting(
                opportunity.opportunity_id, compact=True
            ),
            "proposed_expression": {
                "recommendation": audit_recommendation,
                "selected_instrument": (
                    None if expression_slate else selected_instrument
                ),
                "market_gate": market_gate,
                "implementation_plan": (
                    None
                    if expression_slate
                    else (
                        implementation.model_dump(mode="json")
                        if implementation is not None
                        else None
                    )
                ),
                "capital_allocation": (
                    None
                    if expression_slate
                    else (
                        {
                            "status": capital_allocation.status,
                            "reason_code": capital_allocation.reason_code,
                            "incumbent_position_id": (
                                capital_allocation.incumbent_position_id
                            ),
                            "advantage_bps": (
                                str(capital_allocation.advantage_bps)
                                if capital_allocation.advantage_bps is not None
                                else None
                            ),
                        }
                        if capital_allocation is not None
                        else None
                    )
                ),
                "expression_slate": slate_values,
            },
            "open_shadow_portfolio": portfolio,
            "capital_mode": (
                "broker_api"
                if self.broker_context()
                else "tiger_paper_mirror"
                if self.paper_executor is not None
                else "shadow_only"
            ),
        }
        result = self.audit_runner.run(
            cycle_id=cycle_id,
            run_id=run_id,
            role="expression_auditor",
            prompt={
                "contract": "alta.expression-audit.v6",
                "mission": (
                    "Act as an independent implementation and risk desk. Select at "
                    "most one admissible payoff hypothesis from the frozen expression "
                    "slate, approve it only when it cleanly expresses the Opportunity, "
                    "or require wait. Do not redesign the research thesis."
                ),
                "untrusted_frozen_input": frozen_input,
                "rules": [
                    "Do not infer uncited facts, liquidity, Greeks, or broker capability.",
                    "Check thesis purity, implementation cost, tail risk, time horizon, and duplicate portfolio exposure.",
                    "Compare every slate entry on quoted spread, net Alpha clock, stress, capacity, timing, path dependence, convexity, and retained exposure; ignore proposer scores.",
                    "Use each entry's decision_metrics to compare cost-adjusted Alpha dollars, Alpha per stress dollar, and remaining execution-reserve headroom. Prefer a non-dominated implementation; selecting a lower-efficiency or lower-headroom carrier requires a concrete payoff reason such as materially better thesis purity, timing fit, or bounded convexity in rationale.",
                    "Independently classify the complete systematic exposure set for the selected expression. Return it in confirmed_systematic_exposures and list every proposer disagreement in exposure_disagreements; do not silently average a disagreement away.",
                    "Score alpha_isolation_score from 0 to 1 based on whether the expected return is genuinely attributable to the frozen variant wedge rather than broad beta, sector, style, liquidity, crowding, or event-gap exposure. This score cannot be copied from thesis_purity.",
                    "Return hedge_posture and basis_risk independently. If clean Alpha requires a short, pair, spread, basket, or dynamic hedge, use requires_multi_leg and require wait because this runtime supports one bounded long leg.",
                    "Compare the selected exposure tags with every open position's stored systematic_exposures and intended_alpha; different tickers do not imply diversified risk.",
                    "On approve, selected_hypothesis_id must exactly match one admissible slate entry. On wait, selected_hypothesis_id must be null.",
                    "Challenge risk budget, net edge, binding constraint, unwanted exposure, and exit capacity.",
                    "Audit the selected agent-requested position NAV bps, trade-loss NAV bps, and sizing rationale against evidence quality, invalidation distance, payoff asymmetry, portfolio overlap, liquidity and tail stress. Approve only the deterministic risk-sized result; never replace it with a one-share token order.",
                    "Require positive time-adjusted edge after costs; the Alpha clock is underwriting, not performance.",
                    "Require a non-chasing fixed limit, no automatic repricing, and bounded liquidity participation.",
                    "For a slate, approve only an entry whose own implementation status is ready and capital allocation is not wait. Without a slate, absent or waiting top-level implementation must produce wait.",
                    "For a slate, use each entry's capital allocation. Without a slate, top-level capital_allocation wait requires wait; rotation is admissible only when its measured advantage clears the incumbent hurdle.",
                    "Require payoff and horizon to fit both locked scenarios; estimated Alpha is not realized performance.",
                    "Require the proposed payoff to challenge what is priced in, preserve the variant view, and remain useful only inside the conservative locked edge half-life.",
                    "Require wait for a broken company thesis, re-underwrite requirement, not-decision-grade security view, or when neither independent view calls the security ready.",
                    "A non-wait selection must monetize its exact frozen thesis_pillar_ids, not merely match a ticker.",
                    "Treat material scenario disagreement, crowding risk, liquidity risk, or a weak next pricing fact as reasons to require wait when the instrument cannot contain them.",
                    "Treat current quote, spread, liquidity evidence, and payoff asymmetry as implementation facts rather than narrative details.",
                    "Require wait when the instrument creates a materially different bet from the Opportunity.",
                    "Without an expression slate, a null selected_instrument or unavailable market gate requires wait; with a slate, judge each entry's own instrument and gates.",
                    "portfolio_conflicts must be a JSON array of strings; use [] when no conflict exists and never emit a placeholder string.",
                    "monitoring_plan and evidence_ids must each be JSON arrays of strings; monitoring_plan must contain at least one concrete item.",
                    "Do not place an order; the role has no capital tool and only audits the proposed implementation.",
                    "Cite only supplied Opportunity evidence_ids.",
                ],
            },
            output_type=ExpressionAuditDecision,
            frozen_input=frozen_input,
            evidence_ids=opportunity.evidence_ids,
            known_at=datetime.now(UTC),
            prompt_version=self.AUDIT_PROMPT_VERSION,
        )
        audit = result.value
        if not set(audit.evidence_ids).issubset(opportunity.evidence_ids):
            raise ValueError("expression auditor cited evidence outside the snapshot")
        if instrument is None and audit.decision != "wait":
            raise ValueError("expression auditor approved an unavailable instrument")
        if (
            implementation is not None
            and implementation.status == "wait"
            and audit.decision != "wait"
        ):
            raise ValueError("expression auditor approved a rejected implementation")
        return audit

    def _locked_underwriting_models(
        self, opportunity_id: str
    ) -> tuple[ScenarioUnderwriting, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT underwriting FROM research.assessment
                WHERE opportunity_id = %s AND assessment_kind = 'private'
                ORDER BY assessor LIMIT 2""",
                (opportunity_id,),
            ).fetchall()
        return tuple(
            ScenarioUnderwriting.model_validate(row[0])
            for row in rows
            if row[0] is not None
        )

    def _locked_underwriting(
        self, opportunity_id: str, *, compact: bool = False
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT assessor, underwriting FROM research.assessment
                WHERE opportunity_id = %s AND assessment_kind = 'private'
                ORDER BY assessor""",
                (opportunity_id,),
            ).fetchall()
        summaries = []
        for assessor, raw in rows[:2]:
            if raw is None:
                continue
            underwriting = ScenarioUnderwriting.model_validate(raw)
            decision = underwriting.decision
            narrative_bytes = 64 if compact else 200
            detail_bytes = 48 if compact else 120
            must_be_true_limit = 1 if compact else 4
            summaries.append(
                {
                    "assessor": assessor,
                    "benchmark_symbol": underwriting.benchmark_symbol,
                    "expected_alpha_bps": str(underwriting.expected_alpha_bps),
                    "bull": {
                        "probability": underwriting.bull.probability,
                        "relative_alpha_bps": underwriting.bull.relative_alpha_bps,
                    },
                    "base": {
                        "probability": underwriting.base.probability,
                        "relative_alpha_bps": underwriting.base.relative_alpha_bps,
                    },
                    "bear": {
                        "probability": underwriting.bear.probability,
                        "relative_alpha_bps": underwriting.bear.relative_alpha_bps,
                    },
                    "catalyst_clarity": underwriting.catalyst_clarity,
                    "crowding_risk": underwriting.crowding_risk,
                    "liquidity_risk": underwriting.liquidity_risk,
                    "next_pricing_fact": bounded_text(
                        underwriting.next_pricing_fact, narrative_bytes
                    ),
                    "decision": (
                        {
                            "what_is_priced_in": bounded_text(
                                decision.what_is_priced_in, narrative_bytes
                            ),
                            "variant_view": bounded_text(
                                decision.variant_view, narrative_bytes
                            ),
                            "reference_class": bounded_text(
                                decision.reference_class, detail_bytes
                            ),
                            "base_rate_probability": decision.base_rate_probability,
                            "inside_view_probability": decision.inside_view_probability,
                            "must_be_true": tuple(
                                bounded_text(item, detail_bytes)
                                for item in decision.must_be_true[:must_be_true_limit]
                            ),
                            "company_thesis_status": decision.company_thesis_status,
                            "security_thesis_readiness": (
                                decision.security_thesis_readiness
                            ),
                            "edge_half_life_days": decision.edge_half_life_days,
                            "dominant_uncertainty": bounded_text(
                                decision.dominant_uncertainty, narrative_bytes
                            ),
                            "action_trigger": bounded_text(
                                decision.action_trigger, narrative_bytes
                            ),
                        }
                        if decision is not None
                        else None
                    ),
                }
            )
        return summaries

    def open_shadow(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        proposal: ExpressionProposal,
        _wake_at: datetime,
    ) -> tuple[PositionThesis, LedgerTransaction] | None:
        if self.broker_executor is not None:
            self.broker_executor.handoff(cycle_id, proposal)
            # Broker receipts belong to the isolated broker ledger, never to a
            # manufactured Shadow fill or a Paper-only result contract.
            return None
        return self.positions.open_shadow(cycle_id, opportunity, proposal)

    def monitor_existing(
        self, cycle_id: str, _wake_at: datetime, frozen_input
    ) -> tuple[str, ...]:
        if self.broker_executor is not None:
            return self.broker_executor.monitor_once()
        return self.positions.monitor_existing(cycle_id, frozen_input)

    def monitor_and_exit(self, *_args, **_kwargs):
        raise ValueError("live positions are monitored across autonomous cycles")

    def _existing(self, expression_id: str) -> ExpressionProposal | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT payload FROM ops.event WHERE aggregate_id = %s
                AND event_type IN ('expression.validated','expression.rejected')
                ORDER BY sequence DESC LIMIT 1""",
                (expression_id,),
            ).fetchone()
        if row is None:
            return None
        return ExpressionProposal.model_validate(row[0]["expression"])
