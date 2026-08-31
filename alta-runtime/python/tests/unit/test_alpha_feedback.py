from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alta_asterism.alpha_feedback import (
    AlphaOutcomeObservation,
    build_alpha_feedback,
    load_alpha_contributors,
)


def observations(count: int) -> tuple[AlphaOutcomeObservation, ...]:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    return tuple(
        AlphaOutcomeObservation(
            position_id=f"position_{index:03d}",
            scout_id="change_event_scout",
            alpha_archetype="revision inflection",
            research_route=("alta_news_search", "alta_finance_data"),
            research_posture="cross_checked",
            research_quality_score=Decimal("0.84"),
            known_at=start + timedelta(hours=index),
            net_return_bps=Decimal(index - 10),
            realized_alpha_bps=Decimal(index - 15),
        )
        for index in range(count)
    )


def test_alpha_feedback_hides_small_sample_performance() -> None:
    feedback = build_alpha_feedback(observations(29))[0]

    assert feedback.benchmarked_positions == 29
    assert feedback.mature is False
    assert feedback.mean_net_return_bps is None
    assert feedback.mean_realized_alpha_bps is None
    assert feedback.alpha_lower_confidence_bps is None
    assert feedback.positive_alpha_rate is None
    assert feedback.worst_realized_alpha_bps is None
    assert feedback.archetypes[0].mature is False
    assert feedback.archetypes[0].mean_realized_alpha_bps is None
    assert feedback.research_routes[0].mean_realized_alpha_bps is None
    assert feedback.research_modes[0].research_mode == "explore"
    assert feedback.research_modes[0].mean_realized_alpha_bps is None
    assert feedback.research_quality[0].research_posture == "cross_checked"
    assert feedback.research_quality[0].mean_frozen_research_quality == Decimal("0.84")
    assert feedback.research_quality[0].mean_realized_alpha_bps is None


def test_alpha_feedback_unlocks_only_after_mind_and_slice_maturity() -> None:
    feedback = build_alpha_feedback(observations(30))[0]

    assert feedback.mature is True
    assert feedback.mean_net_return_bps == Decimal("4.5")
    assert feedback.mean_realized_alpha_bps == Decimal("-0.5")
    assert feedback.alpha_lower_confidence_bps < feedback.mean_realized_alpha_bps
    assert feedback.positive_alpha_rate == Decimal(14) / Decimal(30)
    assert feedback.worst_realized_alpha_bps == Decimal(-15)
    assert feedback.archetypes[0].mature is True
    assert feedback.research_routes[0].mature is True
    assert feedback.research_modes[0].mature is True
    assert feedback.research_quality[0].mature is True
    assert feedback.research_quality[0].mean_realized_alpha_bps == Decimal("-0.5")
    assert len(feedback.snapshot_hash) == 64


def test_alpha_feedback_lower_bound_equals_constant_realized_alpha() -> None:
    constant = tuple(
        item.model_copy(update={"realized_alpha_bps": Decimal("25")})
        for item in observations(30)
    )

    feedback = build_alpha_feedback(constant)[0]

    assert feedback.mean_realized_alpha_bps == Decimal("25")
    assert feedback.alpha_lower_confidence_bps == Decimal("25")


def test_alpha_feedback_deduplicates_repeated_contributor_credit() -> None:
    first = observations(30)[0]
    duplicated = (
        *observations(30),
        first,
        first.model_copy(
            update={
                "alpha_archetype": "capital-allocation catalyst",
                "research_route": ("alta_web_research", "alta_finance_data"),
            }
        ),
    )

    feedback = build_alpha_feedback(duplicated)[0]

    assert feedback.closed_positions == 30
    assert feedback.benchmarked_positions == 30
    assert {item.alpha_archetype for item in feedback.archetypes} == {
        "revision inflection",
        "capital-allocation catalyst",
    }


def test_research_mode_feedback_requires_mind_and_slice_maturity() -> None:
    split = tuple(
        item.model_copy(
            update={"research_mode": "follow_up" if index < 10 else "explore"}
        )
        for index, item in enumerate(observations(30))
    )

    feedback = build_alpha_feedback(split)[0]
    modes = {item.research_mode: item for item in feedback.research_modes}

    assert modes["follow_up"].benchmarked_positions == 10
    assert modes["follow_up"].mature is True
    assert modes["follow_up"].mean_realized_alpha_bps is not None
    assert modes["explore"].benchmarked_positions == 20
    assert modes["explore"].mature is True


def test_alpha_feedback_is_order_independent() -> None:
    chronological = build_alpha_feedback(observations(30))[0]
    reversed_input = build_alpha_feedback(tuple(reversed(observations(30))))[0]

    assert reversed_input == chronological
    assert reversed_input.snapshot_hash == chronological.snapshot_hash


def test_contributor_freezes_research_quality_for_forward_attribution() -> None:
    diligence = {
        "version": "alta-research-diligence-v3",
        "posture": "cross_checked",
        "completed_tool_calls": 4,
        "active_research_calls": 4,
        "cited_research_calls": 4,
        "non_news_research_calls": 3,
        "source_families": ["primary_web", "market_data", "news_locator"],
        "independent_source_domains": ["a.example", "b.example", "c.example"],
        "independent_evidence_origins": ["a" * 64, "b" * 64, "c" * 64],
        "cited_source_count": 4,
        "source_role_collisions": 0,
        "evidence_roles": [
            "primary_fact",
            "mechanism",
            "market_context",
            "counterevidence",
        ],
        "counterevidence_source_distinct": True,
        "beneficiary_path_declared": True,
        "counterevidence_declared": True,
        "next_test_declared": True,
        "reason_codes": [],
    }

    class Connection:
        def execute(self, *_args):
            return self

        def fetchall(self):
            return [
                (
                    "candidate_quality",
                    "change_event_scout",
                    "revision inflection",
                    [
                        {
                            "tool_name": "alta_web_batch_fetch",
                            "status": "completed",
                        },
                        {
                            "tool_name": "alta_finance_data",
                            "status": "completed",
                        },
                    ],
                    ["revision inflection"],
                    {"research_mode": "explore", "research_diligence": diligence},
                )
            ]

    contributor = load_alpha_contributors(Connection(), ("candidate_quality",))[0]

    assert contributor.research_posture == "cross_checked"
    assert contributor.research_quality_score == Decimal(1)
