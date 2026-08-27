from decimal import Decimal

import pytest
from pydantic import ValidationError

from alta_asterism.underwriting import (
    DecisionIntelligence,
    ScenarioCase,
    ScenarioUnderwriting,
    consensus_decision,
    consensus_underwriting,
)


def underwriting(
    *,
    bull_probability: float,
    base_probability: float,
    bear_probability: float,
    bull_alpha: int,
    base_alpha: int,
    bear_alpha: int,
) -> ScenarioUnderwriting:
    def case(probability: float, alpha: int, label: str) -> ScenarioCase:
        return ScenarioCase(
            probability=probability,
            relative_alpha_bps=alpha,
            trigger=f"{label} trigger is observed.",
            evidence_ids=("evidence_fixture",),
        )

    return ScenarioUnderwriting(
        bull=case(bull_probability, bull_alpha, "Bull"),
        base=case(base_probability, base_alpha, "Base"),
        bear=case(bear_probability, bear_alpha, "Bear"),
        catalyst_clarity=0.7,
        crowding_risk=0.3,
        liquidity_risk=0.2,
        next_pricing_fact="The next versioned primary update.",
        decision=DecisionIntelligence(
            what_is_priced_in="The base case assumes a normal evidence path.",
            variant_view="The frozen evidence supports a faster revision path.",
            reference_class="Comparable expectation revisions.",
            base_rate_probability=0.5,
            inside_view_probability=bull_probability + base_probability,
            must_be_true=("The next operating update confirms the mechanism.",),
            company_thesis_status="intact",
            security_thesis_readiness="ready",
            edge_half_life_days=30,
            dominant_uncertainty="The timing of the next revision.",
            action_trigger="Re-underwrite at the next primary update.",
        ),
    )


def test_scenario_underwriting_is_a_coherent_probability_distribution() -> None:
    value = underwriting(
        bull_probability=0.2,
        base_probability=0.5,
        bear_probability=0.3,
        bull_alpha=1_000,
        base_alpha=200,
        bear_alpha=-500,
    )

    assert value.expected_alpha_bps == Decimal(150)
    assert value.expected_upside_bps == Decimal(300)
    assert value.expected_downside_bps == Decimal(150)
    assert value.positive_alpha_probability == Decimal("0.7")
    assert value.evidence_ids == ("evidence_fixture",)


@pytest.mark.parametrize(
    "updates",
    (
        {"bear_probability": 0.2},
        {"bull_alpha": -1},
        {"base_alpha": 1_100},
        {"bear_alpha": 0},
    ),
)
def test_scenario_underwriting_rejects_incoherent_odds(updates: dict) -> None:
    arguments = {
        "bull_probability": 0.2,
        "base_probability": 0.5,
        "bear_probability": 0.3,
        "bull_alpha": 1_000,
        "base_alpha": 200,
        "bear_alpha": -500,
        **updates,
    }
    with pytest.raises(ValidationError):
        underwriting(**arguments)


def test_consensus_materializes_alpha_downside_skew_and_model_disagreement() -> None:
    first = underwriting(
        bull_probability=0.2,
        base_probability=0.5,
        bear_probability=0.3,
        bull_alpha=1_000,
        base_alpha=200,
        bear_alpha=-500,
    )
    second = underwriting(
        bull_probability=0.2,
        base_probability=0.4,
        bear_probability=0.4,
        bull_alpha=600,
        base_alpha=100,
        bear_alpha=-600,
    )

    result = consensus_underwriting((first, second))

    assert result["consensus_expected_alpha_bps"] == Decimal(35)
    assert result["conservative_expected_alpha_bps"] == Decimal(-80)
    assert result["forecast_dispersion_bps"] == Decimal(230)
    assert result["forecast_uncertainty_reserve_bps"] == Decimal("57.50")
    assert result["uncertainty_adjusted_expected_alpha_bps"] == Decimal("-137.50")
    assert result["expected_alpha_score"] == Decimal("0.43125")
    assert result["scenario_disagreement"] == Decimal("0.115")
    assert Decimal(0) < result["payoff_asymmetry"] < Decimal(1)
    assert Decimal(0) < result["downside_resilience"] < Decimal(1)


def test_decision_consensus_preserves_base_rates_and_conservative_half_life() -> None:
    first = underwriting(
        bull_probability=0.2,
        base_probability=0.5,
        bear_probability=0.3,
        bull_alpha=1_000,
        base_alpha=200,
        bear_alpha=-500,
    )
    second = underwriting(
        bull_probability=0.2,
        base_probability=0.4,
        bear_probability=0.4,
        bull_alpha=600,
        base_alpha=100,
        bear_alpha=-600,
    ).model_copy(
        update={
            "decision": first.decision.model_copy(
                update={
                    "security_thesis_readiness": "conditional",
                    "edge_half_life_days": 12,
                    "base_rate_probability": 0.4,
                    "inside_view_probability": 0.6,
                }
            )
        }
    )

    result = consensus_decision((first, second))

    assert result.status == "conditional"
    assert result.edge_half_life_days == 12
    assert result.base_rate_probability_range == (0.4, 0.5)
    assert result.inside_view_probability_range == (0.6, 0.7)
    assert result.reason_codes == ()


def test_decision_consensus_waits_when_no_independent_view_is_ready() -> None:
    first = underwriting(
        bull_probability=0.2,
        base_probability=0.5,
        bear_probability=0.3,
        bull_alpha=1_000,
        base_alpha=200,
        bear_alpha=-500,
    )
    conditional = first.model_copy(
        update={
            "decision": first.decision.model_copy(
                update={"security_thesis_readiness": "conditional"}
            )
        }
    )

    result = consensus_decision((conditional, conditional))

    assert result.status == "wait"
    assert result.reason_codes == ("independent_security_readiness_unavailable",)


def test_legacy_underwriting_without_decision_intelligence_fails_closed() -> None:
    current = underwriting(
        bull_probability=0.2,
        base_probability=0.5,
        bear_probability=0.3,
        bull_alpha=1_000,
        base_alpha=200,
        bear_alpha=-500,
    )
    legacy = current.model_copy(update={"decision": None})

    result = consensus_decision((legacy, current))

    assert result.status == "wait"
    assert result.reason_codes == ("decision_intelligence_missing",)
