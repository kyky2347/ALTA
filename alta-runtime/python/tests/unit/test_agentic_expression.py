import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from alta_asterism.alpha_governance import AlphaCapitalGovernance
from alta_asterism.agentic_expression import (
    AgenticExpressionFlow,
    ExpressionRecommendation,
    _bounded_rationale,
)
from alta_asterism.expression import QuoteSnapshot
from alta_asterism.expression_tournament import ExpressionHypothesis
from alta_asterism.implementation import PortfolioRiskPolicy
from alta_asterism.market_data import InstrumentSelection, MarketInstrument


def test_bounded_rationale_keeps_instrument_binding() -> None:
    value = {
        "agent_recommendation": {
            "preferred_kind": "option",
            "symbol": "SPY",
            "rationale": "r" * 2_000,
            "invalidation": "i" * 2_000,
        },
        "independent_audit": {
            "decision": "approve",
            "largest_failure_mode": "f" * 1_200,
            "portfolio_conflicts": ["c" * 1_000 for _ in range(8)],
            "monitoring_plan": ["m" * 1_000 for _ in range(8)],
            "rationale": "a" * 2_000,
        },
        "market_gate": "validated_liquid_option_snapshot",
        "market_instrument": {
            "underlying_symbol": "SPY",
            "contract_type": "call",
            "expiration_date": "2026-09-18",
        },
    }

    rationale = _bounded_rationale(value)
    decoded = json.loads(rationale)

    assert len(rationale.encode()) <= 3_900
    assert decoded["truncated"] is True
    assert decoded["market_instrument"] == {
        "underlying_symbol": "SPY",
        "contract_type": "call",
        "expiration_date": "2026-09-18",
    }
    assert decoded["independent_audit"]["decision"] == "approve"


def test_paper_negative_thesis_uses_only_matching_approved_inverse_etf() -> None:
    class Market:
        def __init__(self) -> None:
            self.calls = []

        def equity(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return InstrumentSelection(None, "captured")

    market = Market()
    flow = object.__new__(AgenticExpressionFlow)
    flow.paper_executor = object()
    flow.market_data = market
    flow.universe = ("TSLA", "SPY")
    recommendation = ExpressionRecommendation(
        preferred_kind="etf",
        symbol="TSLS",
        rationale="Use the approved daily inverse ETF.",
        payoff_thesis="Express a short-horizon negative TSLA view.",
        invalidation="Official evidence reverses the operating impact.",
    )
    opportunity = SimpleNamespace(
        direction="negative",
        entity_key="TSLA",
        title="TSLA operating event",
        horizon_days=2,
    )

    selected = flow._select(recommendation, opportunity)

    assert selected.reason == "captured"
    assert market.calls == [
        (
            ("etf", "TSLS"),
            {
                "underlying_symbol": "TSLA",
                "metadata": {
                    "daily_target": "-1x",
                    "path_dependency": "daily_reset",
                    "issuer_source": "https://www.direxion.com/product/daily-tsla-bull-and-bear-leveraged-single-stock-etfs",
                },
            },
        )
    ]

    mismatch = flow._select(
        recommendation,
        SimpleNamespace(
            direction="negative",
            entity_key="NVDA",
            title="NVDA operating event",
            horizon_days=2,
        ),
    )
    assert mismatch.reason == "inverse_etf_does_not_match_opportunity"


def test_post_audit_refresh_requires_same_instrument_and_bounded_drift() -> None:
    now = datetime(2026, 8, 24, 17, 30, tzinfo=UTC)

    def instrument(midpoint: str, suffix: str) -> MarketInstrument:
        mid = Decimal(midpoint)
        return MarketInstrument(
            kind="stock",
            symbol="AAPL",
            underlying_symbol="AAPL",
            quote=QuoteSnapshot(
                symbol="AAPL",
                bid=mid - Decimal("0.01"),
                ask=mid + Decimal("0.01"),
                as_of=now,
                known_at=now,
                raw_id=f"raw_{suffix}",
                raw_version=1,
                content_hash=("a" if suffix == "audit" else "b") * 64,
            ),
            quantity=Decimal("4"),
            metadata={"notional_limit": "1000"},
        )

    class Market:
        refreshed = instrument("100.50", "refresh")

        def quote(self, _kind, _symbol, *, underlying_symbol):
            assert underlying_symbol == "AAPL"
            return self.refreshed.quote

    flow = object.__new__(AgenticExpressionFlow)
    flow.paper_executor = None
    flow.market_data = Market()
    flow.universe = ("AAPL",)
    recommendation = ExpressionRecommendation(
        preferred_kind="stock",
        symbol="AAPL",
        rationale="Direct positive expression.",
        payoff_thesis="Capture the stated positive wedge.",
        invalidation="The primary-source fact reverses.",
    )
    opportunity = SimpleNamespace(direction="positive", horizon_days=10)

    refreshed = flow._refresh_after_audit(
        recommendation, opportunity, instrument("100.00", "audit")
    )

    assert refreshed.reason == "post_audit_quote_refreshed"
    assert refreshed.instrument == Market.refreshed
    Market.refreshed = instrument("102.00", "refresh")
    drifted = flow._refresh_after_audit(
        recommendation, opportunity, instrument("100.00", "audit")
    )
    assert drifted.reason == "post_audit_price_drift"


def test_expression_must_name_the_frozen_causal_pillar_it_monetizes() -> None:
    flow = object.__new__(AgenticExpressionFlow)
    recommendation = ExpressionRecommendation(
        preferred_kind="stock",
        symbol="AAPL",
        rationale="Direct expression.",
        payoff_thesis="Monetize the operating inflection.",
        invalidation="The operating metric reverses.",
        hypotheses=(
            ExpressionHypothesis(
                hypothesis_id="issuer",
                kind="stock",
                symbol="AAPL",
                payoff_thesis="Monetize the operating inflection.",
                thesis_purity=0.8,
                timing_fit=0.8,
                primary_tradeoff="Retains market beta.",
            ),
        ),
    )
    opportunity = SimpleNamespace(
        thesis_pillars=(SimpleNamespace(pillar_id="pillar_" + "a" * 32),)
    )

    with pytest.raises(ValueError, match="must map to a thesis pillar"):
        flow._evaluate_slate(
            recommendation,
            opportunity,
            (),
            AlphaCapitalGovernance.unscoped(PortfolioRiskPolicy().version),
        )
