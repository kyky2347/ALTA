from types import SimpleNamespace

import pytest

from alta_asterism.expression_tournament import (
    EvaluatedExpression,
    ExpressionHypothesis,
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
