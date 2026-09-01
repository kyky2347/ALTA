from types import SimpleNamespace
from decimal import Decimal

import pytest

from alta_asterism.expression_tournament import (
    EvaluatedExpression,
    ExpressionHypothesis,
    _decision_metrics,
    normalized_hypotheses,
    select_audited_expression,
)


def hypothesis(identifier: str, kind: str = "stock") -> ExpressionHypothesis:
    return ExpressionHypothesis(
        hypothesis_id=identifier,
        kind=kind,
        symbol="DEMO" if kind != "wait" else None,
        payoff_thesis="Capture the frozen variant wedge.",
        thesis_purity=0.8,
        timing_fit=0.7,
        primary_tradeoff="Direct exposure retains market beta.",
        requested_position_nav_bps=(None if kind == "wait" else Decimal("150")),
        requested_trade_loss_nav_bps=(None if kind == "wait" else Decimal("40")),
        sizing_rationale="Risk size reflects the defined invalidation and liquidity.",
    )


def entry(identifier: str, *, ready: bool) -> EvaluatedExpression:
    return EvaluatedExpression(
        hypothesis=hypothesis(identifier),
        market_gate="validated" if ready else "quote_unavailable",
        instrument=SimpleNamespace() if ready else None,
        implementation=SimpleNamespace(status="ready") if ready else None,
        capital_allocation=SimpleNamespace(status="admit") if ready else None,
    )


def test_legacy_single_recommendation_becomes_one_auditable_hypothesis() -> None:
    result = normalized_hypotheses(
        (),
        preferred_kind="stock",
        preferred_symbol="DEMO",
        payoff_thesis="Direct issuer expression.",
    )

    assert len(result) == 1
    assert result[0].hypothesis_id == "preferred"
    assert result[0].symbol == "DEMO"


def test_independent_audit_must_name_one_ready_multi_entry_hypothesis() -> None:
    slate = (entry("issuer", ready=True), entry("proxy", ready=True))

    selected = select_audited_expression(
        slate,
        decision="approve",
        selected_hypothesis_id="proxy",
    )

    assert selected is slate[1]
    with pytest.raises(ValueError, match="must select one"):
        select_audited_expression(
            slate,
            decision="approve",
            selected_hypothesis_id=None,
        )


def test_audit_cannot_select_a_market_rejected_hypothesis() -> None:
    slate = (entry("issuer", ready=True), entry("proxy", ready=False))

    with pytest.raises(ValueError, match="unavailable"):
        select_audited_expression(
            slate,
            decision="approve",
            selected_hypothesis_id="proxy",
        )


def test_expression_slate_cannot_exceed_market_request_budget() -> None:
    slate = tuple(
        hypothesis("idea").model_copy(
            update={"hypothesis_id": f"idea_{index}", "symbol": symbol}
        )
        for index, symbol in enumerate(("AAPL", "MSFT", "AMZN", "GOOG"), start=1)
    )

    with pytest.raises(ValueError, match="three-hypothesis budget"):
        normalized_hypotheses(
            slate,
            preferred_kind="wait",
            preferred_symbol=None,
            payoff_thesis="Wait.",
        )


def test_expression_decision_metrics_make_cost_and_stress_tradeoffs_comparable() -> (
    None
):
    plan = SimpleNamespace(
        status="ready",
        alpha_clock=SimpleNamespace(
            time_adjusted_expected_net_alpha_bps=Decimal("120")
        ),
        expected_net_alpha_bps=Decimal("150"),
        estimated_cost_bps=Decimal("30"),
        target_notional=Decimal("10000"),
        estimated_stress_loss=Decimal("2000"),
        execution_plan=SimpleNamespace(
            implementation_shortfall_budget_bps=Decimal("20")
        ),
    )

    assert _decision_metrics(plan) == {
        "unreserved_expected_alpha_bps": "unavailable",
        "forecast_calibration_reserve_bps": "0",
        "time_adjusted_expected_net_alpha_bps": "120",
        "time_adjusted_expected_alpha_dollars": "120",
        "estimated_cost_bps": "30",
        "target_notional_dollars": "10000",
        "estimated_stress_loss_dollars": "2000",
        "expected_alpha_per_stress_dollar": "0.06",
        "execution_reserve_headroom_bps": "100",
    }
