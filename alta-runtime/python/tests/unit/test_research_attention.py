from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from alta_asterism.market_research import (
    MarketResearchAgenda,
    MarketResearchSeed,
    MarketScreenObservation,
)
from alta_asterism.research_attention import (
    ResearchAttentionObservation,
    apply_research_attention_to_market_agenda,
    build_research_attention_portfolio,
)


SCOUT_IDS = (
    "change_event_scout",
    "market_dislocation_scout",
    "causal_policy_scout",
    "expectation_gap_scout",
)
WAKE_AT = datetime(2026, 8, 29, 14, tzinfo=UTC)


def observation(
    index: int,
    entity: str,
    scout_id: str,
) -> ResearchAttentionObservation:
    return ResearchAttentionObservation(
        candidate_id=f"candidate_{index}",
        scout_id=scout_id,
        entity_key=entity,
        known_at=WAKE_AT - timedelta(minutes=index + 1),
    )


def build(
    observations: tuple[ResearchAttentionObservation, ...],
):
    return build_research_attention_portfolio(
        wake_at=WAKE_AT,
        universe=("NVDA", "UNH", "SPY"),
        scout_ids=SCOUT_IDS,
        observations=observations,
    )


def test_empty_history_leaves_every_research_seat_unconstrained() -> None:
    portfolio = build(())

    assert portfolio.posture == "insufficient_sample"
    assert portfolio.sample_size == 0
    assert portfolio.top_entity is None
    assert {item.mode for item in portfolio.assignments} == {"unconstrained"}


def test_concentrated_history_preserves_one_lead_and_expands_three_seats() -> None:
    portfolio = build(
        (
            observation(0, "NVDA", "change_event_scout"),
            observation(1, "nvda", "change_event_scout"),
            observation(2, "NVDA", "market_dislocation_scout"),
            observation(3, "NVDA", "change_event_scout"),
            observation(4, "NVDA", "expectation_gap_scout"),
            observation(5, "UNH", "expectation_gap_scout"),
        )
    )

    assert portfolio.posture == "concentrated"
    assert portfolio.top_entity == "nvda"
    assert portfolio.top_entity_share == Decimal("0.8333")
    assert portfolio.unique_entities == 2
    assert portfolio.continuation_scout_id == "change_event_scout"
    assert portfolio.assignment_for("change_event_scout").mode == "continue_lead"
    expanding = tuple(
        item for item in portfolio.assignments if item.mode == "expand_coverage"
    )
    assert len(expanding) == 3
    assert all(item.deprioritized_entities == ("nvda",) for item in expanding)
    assert portfolio.for_scout("market_dislocation_scout") is portfolio


def test_balanced_history_does_not_force_artificial_diversification() -> None:
    portfolio = build(
        tuple(
            observation(index, entity, SCOUT_IDS[index])
            for index, entity in enumerate(("NVDA", "UNH", "SPY", "MSFT"))
        )
    )

    assert portfolio.posture == "balanced"
    assert portfolio.effective_breadth == Decimal("4.00")
    assert {item.mode for item in portfolio.assignments} == {"unconstrained"}


def test_future_or_current_observation_is_rejected() -> None:
    future = observation(0, "NVDA", "change_event_scout").model_copy(
        update={"known_at": WAKE_AT}
    )

    with pytest.raises(ValueError, match="must predate"):
        build((future,))


def test_market_seed_conflicting_with_expansion_seat_is_removed() -> None:
    portfolio = build(
        tuple(observation(index, "NVDA", "change_event_scout") for index in range(4))
    )
    expanding_scout = next(
        item.scout_id
        for item in portfolio.assignments
        if item.mode == "expand_coverage"
    )
    seed = MarketResearchSeed(
        seed_id="a" * 16,
        screen_type="price_volume_dislocation",
        assigned_scout_id=expanding_scout,
        symbols=("NVDA",),
        priority_score=Decimal("0.8"),
        observations=(
            MarketScreenObservation(
                symbol="NVDA",
                completed_session=date(2026, 8, 28),
                one_day_return_bps=Decimal("100"),
            ),
        ),
        research_question="Why did this completed-session move occur?",
        first_rejection="Reject if the move is only broad beta exposure.",
        required_tests=("Re-fetch the bar.", "Test the rival explanation."),
    )
    agenda = MarketResearchAgenda(
        known_at=WAKE_AT,
        posture="screen_ready",
        benchmark_symbol="SPY",
        completed_sessions=8,
        seeds=(seed,),
        snapshot_hash="b" * 64,
    )

    filtered = apply_research_attention_to_market_agenda(agenda, portfolio)

    assert filtered.seeds == ()
    assert filtered.model_copy(update={"seeds": agenda.seeds}) == agenda
