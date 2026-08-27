from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alta_asterism.alpha_governance import AlphaCapitalGovernance
from alta_asterism.alpha_isolation import AlphaIsolation
from alta_asterism.expression import QuoteSnapshot
from alta_asterism.implementation import (
    ExposureBucket,
    PortfolioRiskPolicy,
    PortfolioState,
)
from alta_asterism.market_data import MarketInstrument
from alta_asterism.portfolio_construction import PortfolioConstructor
from alta_asterism.underwriting import (
    DecisionIntelligence,
    ScenarioCase,
    ScenarioUnderwriting,
)


NOW = datetime(2026, 8, 25, 14, tzinfo=UTC)


def underwriting(
    base_alpha: int,
    *,
    readiness: str = "ready",
    edge_half_life_days: int = 30,
) -> ScenarioUnderwriting:
    evidence_ids = ("evidence_portfolio",)
    return ScenarioUnderwriting(
        bull=ScenarioCase(
            probability=0.2,
            relative_alpha_bps=800,
            trigger="Catalyst resolves above the market expectation.",
            evidence_ids=evidence_ids,
        ),
        base=ScenarioCase(
            probability=0.6,
            relative_alpha_bps=base_alpha,
            trigger="The measured operating change reaches the base case.",
            evidence_ids=evidence_ids,
        ),
        bear=ScenarioCase(
            probability=0.2,
            relative_alpha_bps=-600,
            trigger="The stated falsifier is observed.",
            evidence_ids=evidence_ids,
        ),
        catalyst_clarity=0.8,
        crowding_risk=0.2,
        liquidity_risk=0.1,
        next_pricing_fact="The next versioned operating update.",
        decision=DecisionIntelligence(
            what_is_priced_in="A normal operating update is priced in.",
            variant_view="The measured revision path is faster than priced.",
            reference_class="Comparable operating revisions.",
            base_rate_probability=0.5,
            inside_view_probability=0.8 if base_alpha > 0 else 0.2,
            must_be_true=("The measured operating change persists.",),
            company_thesis_status="intact",
            security_thesis_readiness=readiness,  # type: ignore[arg-type]
            edge_half_life_days=edge_half_life_days,
            dominant_uncertainty="Persistence of the operating change.",
            action_trigger="Re-underwrite at the next operating update.",
        ),
    )


def instrument(kind: str = "stock", *, liquid: bool = True) -> MarketInstrument:
    symbol = "O:DEMO" if kind == "option" else "DEMO"
    bid = Decimal("9.99") if kind == "option" else Decimal("99.9")
    ask = Decimal("10.01") if kind == "option" else Decimal("100")
    metadata = (
        {"notional_limit": "10000", "open_interest": "1000"}
        if kind == "option"
        else {
            "notional_limit": "10000",
            **({"observed_day_dollar_volume": "200000000"} if liquid else {}),
        }
    )
    return MarketInstrument(
        kind=kind,
        symbol=symbol,
        underlying_symbol="DEMO",
        quote=QuoteSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            as_of=NOW,
            known_at=NOW,
            raw_id="raw_portfolio_quote",
            raw_version=1,
            content_hash="a" * 64,
        ),
        quantity=Decimal("500" if kind == "option" else "100"),
        metadata=metadata,
    )


def plan(
    selected: MarketInstrument,
    state: PortfolioState | None = None,
    isolation: AlphaIsolation | None = None,
    research_quality_score: Decimal | None = None,
    alpha_capital_governance: AlphaCapitalGovernance | None = None,
):
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    return constructor.plan(
        selected,
        (underwriting(300), underwriting(250)),
        intended_alpha="Issuer-specific expectation revision.",
        unwanted_exposures=("broad market beta",),
        retained_exposure="Long issuer idiosyncratic and residual sector exposure.",
        monitoring_triggers=("The operating metric misses the frozen threshold.",),
        state=state or PortfolioState(),
        alpha_isolation=isolation,
        research_quality_score=research_quality_score,
        alpha_capital_governance=alpha_capital_governance,
    )


def audited_isolation(
    score: str = "0.9",
    *,
    exposures: tuple[str, ...] = ("market_beta",),
    hedge_posture: str = "unhedged_intentional",
    reasons: tuple[str, ...] = (),
) -> AlphaIsolation:
    return AlphaIsolation(
        posture="audited",
        alpha_source="idiosyncratic",
        systematic_exposures=exposures,
        hedge_posture=hedge_posture,
        proposer_score=Decimal(score),
        auditor_score=Decimal(score),
        conservative_score=Decimal(score),
        sizing_multiplier=Decimal("0.5") if Decimal(score) < Decimal("0.8") else 1,
        basis_risk="Broad market beta can overwhelm the issuer-specific revision.",
        reason_codes=reasons,
    )


def test_equity_plan_sizes_to_the_tightest_portfolio_constraint() -> None:
    result = plan(
        instrument(),
        PortfolioState(known_open_positions=3, gross_notional=Decimal("75000")),
    )

    assert result.status == "ready"
    assert result.target_quantity == Decimal("50")
    assert result.target_notional == Decimal("5000")
    assert result.binding_constraint == "gross_nav_remaining"
    assert result.estimated_stress_loss == Decimal("1250")
    assert result.expected_net_alpha_bps > Decimal("50")


def test_option_plan_treats_premium_as_maximum_loss_budget() -> None:
    result = plan(instrument("option"))

    assert result.status == "ready"
    assert result.target_quantity == Decimal("200")
    assert result.target_notional == Decimal("2002.00")
    assert result.estimated_stress_loss == result.target_notional
    assert result.binding_constraint == "stress_loss_budget"


def test_missing_exit_liquidity_fails_closed_to_wait() -> None:
    result = plan(instrument(liquid=False))

    assert result.status == "wait"
    assert result.reason_codes == ("liquidity_capacity_unverified",)
    assert result.target_quantity == 0


def test_stale_edge_decays_below_hurdle_before_risk_is_allocated() -> None:
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    result = constructor.plan(
        instrument(),
        (underwriting(300), underwriting(250)),
        intended_alpha="Issuer-specific expectation revision.",
        unwanted_exposures=("broad market beta",),
        retained_exposure="Residual issuer exposure.",
        monitoring_triggers=("Next operating update.",),
        state=PortfolioState(),
        known_at=NOW,
        evidence_freshness_at=NOW - timedelta(days=89),
        horizon_days=90,
    )

    assert result.status == "wait"
    assert result.reason_codes == ("insufficient_net_alpha_after_costs",)
    assert result.alpha_clock is not None
    assert result.alpha_clock.stage == "expired"


def test_alpha_clock_uses_the_more_conservative_assessor_edge_half_life() -> None:
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    result = constructor.plan(
        instrument(),
        (
            underwriting(300, edge_half_life_days=20),
            underwriting(250, edge_half_life_days=8),
        ),
        intended_alpha="Issuer-specific expectation revision.",
        unwanted_exposures=("broad market beta",),
        retained_exposure="Residual issuer exposure.",
        monitoring_triggers=("Next operating update.",),
        state=PortfolioState(),
        known_at=NOW,
        evidence_freshness_at=NOW - timedelta(days=4),
        horizon_days=90,
    )

    assert result.alpha_clock is not None
    assert result.alpha_clock.horizon_days == 8
    assert result.alpha_clock.retention_fraction == Decimal("0.5")


def test_portfolio_waits_when_neither_security_view_is_ready() -> None:
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    result = constructor.plan(
        instrument(),
        (
            underwriting(300, readiness="conditional"),
            underwriting(250, readiness="conditional"),
        ),
        intended_alpha="Issuer-specific expectation revision.",
        unwanted_exposures=("broad market beta",),
        retained_exposure="Residual issuer exposure.",
        monitoring_triggers=("Next operating update.",),
        state=PortfolioState(),
    )

    assert result.status == "wait"
    assert result.reason_codes == ("independent_security_readiness_unavailable",)


def test_one_optimistic_assessor_cannot_cancel_a_negative_independent_view() -> None:
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    result = constructor.plan(
        instrument(),
        (underwriting(700), underwriting(-300)),
        intended_alpha="Issuer-specific expectation revision.",
        unwanted_exposures=("broad market beta",),
        retained_exposure="Residual issuer exposure.",
        monitoring_triggers=("Next operating update.",),
        state=PortfolioState(),
    )

    assert result.status == "wait"
    assert result.expected_alpha_bps == Decimal(-290)
    assert result.reason_codes == ("insufficient_net_alpha_after_costs",)


def test_ready_plan_contains_a_non_chasing_execution_instruction() -> None:
    result = plan(instrument())

    assert result.execution_plan is not None
    assert result.execution_plan.status == "ready"
    assert result.execution_plan.order_style == "guarded_limit"
    assert result.execution_plan.entry_limit_offset_bps <= Decimal("25")
    assert result.execution_plan.automatic_reprice is False
    assert result.execution_plan.version == "alta-execution-plan-v2"
    assert result.execution_plan.entry_limit_price is not None
    assert result.execution_plan.arrival_midpoint is not None
    assert result.execution_plan.implementation_shortfall_budget_bps is not None
    assert result.execution_plan.max_attempts == 1


def test_prospective_replacement_credit_preserves_the_gross_limit() -> None:
    result = plan(
        instrument(),
        PortfolioState(
            known_open_positions=8,
            gross_notional=Decimal("80000"),
            prospective_replacement_credit=Decimal("10000"),
        ),
    )

    assert result.status == "ready"
    assert result.gross_replacement_credit == Decimal("10000")
    assert result.gross_notional_after <= result.gross_notional_limit


def test_audited_alpha_isolation_sizes_a_marginal_edge_as_a_starter() -> None:
    result = plan(instrument(), isolation=audited_isolation("0.7"))

    assert result.status == "ready"
    assert result.alpha_isolation_posture == "audited"
    assert result.alpha_isolation_multiplier == Decimal("0.50")
    assert result.target_notional == Decimal("5000")
    assert result.binding_constraint == "position_nav_limit"


def test_research_quality_controls_capital_admission_and_starter_size() -> None:
    rejected = plan(instrument(), research_quality_score=Decimal("0.59"))
    starter = plan(instrument(), research_quality_score=Decimal("0.70"))

    assert rejected.status == "wait"
    assert rejected.reason_codes == ("research_quality_below_capital_hurdle",)
    assert starter.status == "ready"
    assert starter.research_quality_score == Decimal("0.70")
    assert starter.research_quality_multiplier == Decimal("0.50")
    assert starter.target_notional == Decimal("5000")
    assert starter.binding_constraint == "position_nav_limit"


def test_alpha_capital_governance_caps_unproven_and_degraded_books() -> None:
    collecting = AlphaCapitalGovernance(
        policy_version="alta-alpha-capital-governance-v1",
        source_portfolio_policy_version="alta-portfolio-risk-v5",
        posture="collecting",
        capital_multiplier=Decimal("0.50"),
        sample_size=0,
        window_size=0,
        max_drawdown_nav_bps=Decimal(0),
        evidence_posture="insufficient_sample",
        reason_codes=("forward_alpha_sample_collecting",),
    )
    preservation = collecting.model_copy(
        update={
            "posture": "preservation",
            "capital_multiplier": Decimal("0.10"),
            "reason_codes": ("negative_alpha_confidence_interval",),
        }
    )

    starter = plan(instrument(), alpha_capital_governance=collecting)
    exploration = plan(instrument(), alpha_capital_governance=preservation)

    assert starter.status == "ready"
    assert starter.target_notional == Decimal("5000")
    assert starter.alpha_capital_governance == collecting
    assert exploration.status == "ready"
    assert exploration.target_notional == Decimal("1000")
    assert exploration.binding_constraint == "position_nav_limit"


def test_entry_revalidation_rejects_a_stale_larger_governance_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = AlphaCapitalGovernance(
        policy_version="alta-alpha-capital-governance-v1",
        source_portfolio_policy_version="alta-portfolio-risk-v5",
        posture="normal",
        capital_multiplier=Decimal(1),
        sample_size=30,
        window_size=30,
        recent_mean_alpha_bps=Decimal("50"),
        confidence95_upper_alpha_bps=Decimal("80"),
        max_drawdown_nav_bps=Decimal("10"),
        evidence_posture="inconclusive",
        reason_codes=("forward_alpha_not_negative",),
    )
    preservation = normal.model_copy(
        update={
            "posture": "preservation",
            "capital_multiplier": Decimal("0.10"),
            "reason_codes": ("rolling_shadow_drawdown_limit",),
        }
    )
    ready = plan(instrument(), alpha_capital_governance=normal)
    constructor = PortfolioConstructor(None, PortfolioRiskPolicy())  # type: ignore[arg-type]
    monkeypatch.setattr(constructor, "load_state", lambda: PortfolioState())
    monkeypatch.setattr(constructor, "load_alpha_governance", lambda: preservation)

    assert "alpha_governance_tightened_before_entry" in constructor.revalidate(ready)


def test_weak_or_multi_leg_alpha_fails_closed_before_allocating_risk() -> None:
    weak = plan(instrument(), isolation=audited_isolation("0.59"))
    multi_leg = plan(
        instrument(),
        isolation=audited_isolation("0.9", hedge_posture="requires_multi_leg"),
    )

    assert weak.reason_codes == ("alpha_isolation_below_hurdle",)
    assert multi_leg.reason_codes == (
        "alpha_requires_unsupported_multi_leg_expression",
    )


def test_shared_factor_capacity_binds_across_different_instruments() -> None:
    state = PortfolioState(
        known_open_positions=2,
        gross_notional=Decimal("29000"),
        exposure_buckets=(
            ExposureBucket(tag="market_beta", gross_notional=Decimal("19500")),
        ),
    )

    result = plan(instrument(), state, audited_isolation("0.9"))

    assert result.status == "ready"
    assert result.target_notional == Decimal("500")
    assert result.binding_constraint == "systematic_exposure:market_beta"
    assert result.exposure_binding_tag == "market_beta"
    assert result.exposure_capacity == Decimal("500")
