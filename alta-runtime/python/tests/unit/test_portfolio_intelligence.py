from datetime import UTC, datetime
from decimal import Decimal

from alta_asterism.implementation import (
    AlphaSourceBucket,
    CatalystBucket,
    ExposureBucket,
    PortfolioRiskPolicy,
    PortfolioState,
)
from alta_asterism.portfolio_intelligence import build_portfolio_research_mandate


NOW = datetime(2026, 8, 27, 14, tzinfo=UTC)


def test_empty_book_mandate_does_not_manufacture_a_research_target() -> None:
    mandate = build_portfolio_research_mandate(
        PortfolioState(), PortfolioRiskPolicy(), NOW
    )

    assert mandate.posture == "empty_book"
    assert mandate.diversification_search_targets == ()
    assert mandate.gross_nav_bps == 0
    assert mandate.stress_nav_bps == 0


def test_constrained_book_mandate_points_research_away_from_saturation() -> None:
    state = PortfolioState(
        known_open_positions=4,
        gross_notional=Decimal("40000"),
        aggregate_stress_loss=Decimal("8500"),
        exposure_buckets=(
            ExposureBucket(tag="market_beta", gross_notional=Decimal("18000")),
        ),
        alpha_source_buckets=(
            AlphaSourceBucket(
                source="event",
                open_positions=3,
                gross_notional=Decimal("25000"),
                estimated_stress_loss=Decimal("6500"),
            ),
            AlphaSourceBucket(
                source="idiosyncratic",
                open_positions=1,
                gross_notional=Decimal("15000"),
                estimated_stress_loss=Decimal("2000"),
            ),
        ),
        catalyst_buckets=(
            CatalystBucket(
                catalyst_key="shared-policy-reset",
                open_positions=3,
                gross_notional=Decimal("17000"),
                estimated_stress_loss=Decimal("4250"),
            ),
        ),
    )

    mandate = build_portfolio_research_mandate(state, PortfolioRiskPolicy(), NOW)

    assert mandate.posture == "risk_constrained"
    assert mandate.saturated_alpha_sources == ("event",)
    assert mandate.saturated_systematic_exposures == ("market_beta",)
    assert mandate.saturated_catalyst_keys == ("shared-policy-reset",)
    assert "event" not in mandate.diversification_search_targets
    assert mandate.stress_nav_bps == Decimal("85.00")
    assert any("no-op" in item for item in mandate.research_objectives)
    assert any("saturated catalyst" in item for item in mandate.research_objectives)
