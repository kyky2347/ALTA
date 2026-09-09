import json
from datetime import timedelta
from pathlib import Path

import pytest

from alta_asterism.deliberation import (
    BeliefUpdate,
    DiscussionCandidate,
    DiscussionPolicy,
    DiscussionRound,
    PrivateAssessment,
    run_short_discussion,
    select_discussion_candidates,
    validate_private_pair,
)
from alta_asterism.foundry import (
    CandidateDraft,
    CompletionPatch,
    OpportunityDraft,
    apply_completion,
    deduplicate,
)
from alta_asterism.ranking import build_ranking_book, pre_assessment_rejections
from alta_asterism.research_diligence import ResearchDiligence
from alta_asterism.underwriting import (
    DecisionIntelligence,
    ScenarioCase,
    ScenarioUnderwriting,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "b4" / "foundry_cases.json"


def decision_grade_diligence() -> ResearchDiligence:
    return ResearchDiligence(
        posture="cross_checked",
        completed_tool_calls=4,
        active_research_calls=4,
        cited_research_calls=4,
        non_news_research_calls=3,
        source_families=("primary_web", "market_data", "versioned_web"),
        independent_source_domains=(
            "issuer.example",
            "exchange.example",
            "regulator.example",
        ),
        independent_evidence_origins=(
            "a" * 64,
            "b" * 64,
            "c" * 64,
        ),
        beneficiary_path_declared=True,
        counterevidence_declared=True,
        next_test_declared=True,
        evidence_roles=(
            "primary_fact",
            "mechanism",
            "market_context",
            "counterevidence",
        ),
        counterevidence_source_distinct=True,
    )


def scenario_underwriting(
    evidence_ids: tuple[str, ...],
    positive_probability: float,
    *,
    bull_alpha: int = 800,
    base_alpha: int = 200,
    bear_alpha: int = -600,
) -> ScenarioUnderwriting:
    return ScenarioUnderwriting(
        bull=ScenarioCase(
            probability=0.2,
            relative_alpha_bps=bull_alpha,
            trigger="The catalyst propagates faster than the priced path.",
            evidence_ids=evidence_ids,
        ),
        base=ScenarioCase(
            probability=round(positive_probability - 0.2, 2),
            relative_alpha_bps=base_alpha,
            trigger="The causal mechanism partially reaches the prediction.",
            evidence_ids=evidence_ids,
        ),
        bear=ScenarioCase(
            probability=round(1 - positive_probability, 2),
            relative_alpha_bps=bear_alpha,
            trigger="The frozen rejection condition is confirmed.",
            evidence_ids=evidence_ids,
        ),
        catalyst_clarity=0.7,
        crowding_risk=0.25,
        liquidity_risk=0.15,
        next_pricing_fact="The next primary operating update.",
        decision=DecisionIntelligence(
            what_is_priced_in="The market assumes the ordinary propagation path.",
            variant_view="The frozen catalyst can propagate faster than priced.",
            reference_class="Comparable catalyst propagation events.",
            base_rate_probability=0.5,
            inside_view_probability=positive_probability,
            must_be_true=("The causal mechanism reaches the stated prediction.",),
            company_thesis_status="intact",
            security_thesis_readiness="ready",
            edge_half_life_days=20,
            dominant_uncertainty="The speed of causal propagation.",
            action_trigger="Re-underwrite at the next operating update.",
        ),
    )


def fixture_opportunity() -> OpportunityDraft:
    payload = json.loads(FIXTURE.read_text())
    candidates = [CandidateDraft.model_validate(item) for item in payload["candidates"]]
    patch = CompletionPatch.model_validate(payload["completion_patch"])
    candidates = [
        apply_completion(item, patch)
        if item.candidate_id == patch.candidate_id
        else item
        for item in candidates
    ]
    result = deduplicate(payload["batch_id"], tuple(candidates))
    opportunity = next(
        item
        for item in result.opportunities
        if item.member_candidate_ids == ("candidate_wrong_positive",)
    )
    return opportunity.model_copy(
        update={"research_diligence": decision_grade_diligence()}
    )


def assessments_for(
    opportunity: OpportunityDraft,
    probabilities: tuple[float, float] = (0.78, 0.65),
) -> tuple[PrivateAssessment, ...]:
    locked_at = opportunity.known_at + timedelta(minutes=1)
    return tuple(
        PrivateAssessment(
            assessment_id=f"assessment_{opportunity.opportunity_id}_{assessor}",
            opportunity_id=opportunity.opportunity_id,
            run_id=f"run_{assessor}",
            assessor=assessor,
            snapshot_hash=opportunity.snapshot_hash,
            forecast_probability=probability,
            evidence_quality=0.8 if index == 0 else 0.65,
            variant_wedge_quality=0.72 if index == 0 else 0.58,
            strongest_support="Frozen primary evidence supports the mechanism.",
            strongest_disconfirmation="The operating condition can bind first.",
            first_rejection=opportunity.first_rejection or "Reject on missing field.",
            missing_evidence=("future operating update",),
            recommendation="advance" if index == 0 else "wait",
            confidence=0.7 if index == 0 else 0.6,
            evidence_ids=opportunity.evidence_ids,
            rationale="Independent structured fixture assessment.",
            underwriting=scenario_underwriting(opportunity.evidence_ids, probability),
            locked_at=locked_at,
            prompt_version="b4-private-fixture-v1",
            model_id="deterministic-fixture",
        )
        for index, (assessor, probability) in enumerate(
            zip(
                ("thesis_assessor", "disconfirming_assessor"),
                probabilities,
                strict=True,
            )
        )
    )


def test_expired_signal_is_blocked_before_assessment_and_ranking() -> None:
    opportunity = fixture_opportunity()
    assert opportunity.freshness_at is not None
    decision_at = opportunity.freshness_at + timedelta(days=5)

    assert "signal_freshness_expired" in pre_assessment_rejections(
        opportunity, decision_at
    )
    book = build_ranking_book(
        "ranking_expired_signal",
        (opportunity,),
        {opportunity.opportunity_id: assessments_for(opportunity)},
        {},
        decision_at,
    )

    assert book.items == ()
    assert book.gates[0].status == "rejected"
    assert "signal_freshness_expired" in book.gates[0].reason_codes


def test_private_pair_and_discussion_selection_resist_anchoring() -> None:
    opportunity = fixture_opportunity()
    assessments = assessments_for(opportunity)

    assert validate_private_pair(opportunity, tuple(reversed(assessments))) == tuple(
        sorted(assessments, key=lambda item: item.assessor)
    )
    candidates = tuple(
        DiscussionCandidate(
            opportunity_id=f"opportunity_{index}",
            preliminary_position=index,
            disagreement=0.4 if index in {7, 8} else 0.1,
        )
        for index in range(1, 9)
    )
    selected = select_discussion_candidates(candidates, DiscussionPolicy())
    assert len(selected) == 5
    assert selected[:2] == ("opportunity_7", "opportunity_8")
    assert set(selected).issubset(
        {
            "opportunity_1",
            "opportunity_2",
            "opportunity_3",
            "opportunity_4",
            "opportunity_5",
            "opportunity_7",
            "opportunity_8",
        }
    )

    with pytest.raises(ValueError, match="anchored"):
        run_short_discussion(
            opportunity,
            assessments,
            preliminary_position=1,
            rounds=(
                DiscussionRound(
                    round_number=1,
                    summary="Stale update fixture.",
                    belief_updates=(
                        BeliefUpdate(
                            assessor="thesis_assessor",
                            before_probability=0.5,
                            after_probability=0.6,
                            evidence_ids=opportunity.evidence_ids,
                            rationale="Uses a stale starting probability.",
                        ),
                    ),
                ),
            ),
            policy=DiscussionPolicy(),
        )


def test_short_discussion_stops_on_no_information_and_rejects_new_evidence() -> None:
    opportunity = fixture_opportunity()
    assessments = assessments_for(opportunity)
    rounds = (
        DiscussionRound(round_number=1, summary="No new testable information."),
        DiscussionRound(
            round_number=2,
            summary="This round must never be consumed.",
            testable_claims=("A later claim",),
        ),
    )

    outcome = run_short_discussion(
        opportunity,
        assessments,
        preliminary_position=1,
        rounds=rounds,
        policy=DiscussionPolicy(),
    )

    assert outcome.stop_reason == "no_information_gain"
    assert [item.round_number for item in outcome.rounds] == [1]
    with pytest.raises(ValueError, match="frozen evidence"):
        run_short_discussion(
            opportunity,
            assessments,
            preliminary_position=1,
            rounds=(
                DiscussionRound(
                    round_number=1,
                    summary="Attempts to manufacture evidence.",
                    evidence_ids=("discussion_is_not_evidence",),
                ),
            ),
            policy=DiscussionPolicy(),
        )
    with pytest.raises(ValueError, match="require frozen evidence provenance"):
        run_short_discussion(
            opportunity,
            assessments,
            preliminary_position=1,
            rounds=(
                DiscussionRound(
                    round_number=1,
                    summary="Attempts an unsupported material probability change.",
                    belief_updates=(
                        BeliefUpdate(
                            assessor="thesis_assessor",
                            before_probability=assessments[0].forecast_probability,
                            after_probability=0.5,
                            rationale="No evidence was cited.",
                        ),
                    ),
                ),
            ),
            policy=DiscussionPolicy(),
        )


@pytest.mark.parametrize(
    ("rounds", "expected"),
    (
        (
            (
                DiscussionRound(
                    round_number=1,
                    summary="The frozen falsifier is triggered.",
                    hard_falsifier_triggered=True,
                ),
            ),
            "hard_falsifier",
        ),
        (
            (
                DiscussionRound(
                    round_number=1,
                    summary="The disagreement is reduced to a future fact.",
                    awaiting_future_fact=True,
                ),
            ),
            "awaiting_future_fact",
        ),
        (
            (
                DiscussionRound(
                    round_number=1,
                    summary="First bounded claim.",
                    testable_claims=("Claim one",),
                ),
                DiscussionRound(
                    round_number=2,
                    summary="Second bounded claim.",
                    testable_claims=("Claim two",),
                ),
            ),
            "max_rounds",
        ),
        ((), "no_information_gain"),
    ),
)
def test_short_discussion_fixed_stop_conditions(
    rounds: tuple[DiscussionRound, ...], expected: str
) -> None:
    opportunity = fixture_opportunity()
    outcome = run_short_discussion(
        opportunity,
        assessments_for(opportunity),
        preliminary_position=1,
        rounds=rounds,
        policy=DiscussionPolicy(),
    )

    assert outcome.stop_reason == expected


def test_short_discussion_does_not_start_outside_top_five_without_disagreement() -> (
    None
):
    opportunity = fixture_opportunity()
    outcome = run_short_discussion(
        opportunity,
        assessments_for(opportunity, probabilities=(0.6, 0.55)),
        preliminary_position=6,
        rounds=(
            DiscussionRound(
                round_number=1,
                summary="This round is outside the discussion policy.",
                testable_claims=("Should not start",),
            ),
        ),
        policy=DiscussionPolicy(),
    )

    assert outcome.eligible is False
    assert outcome.rounds == ()
    assert outcome.stop_reason == "ineligible"


def test_single_1_90_day_book_degrades_or_rejects_missing_critical_fields() -> None:
    opportunity = fixture_opportunity()
    degraded = OpportunityDraft.model_validate(
        {
            **opportunity.model_dump(mode="json"),
            "opportunity_id": "opportunity_degraded",
            "candidate_id": opportunity.candidate_id,
            "member_candidate_ids": opportunity.member_candidate_ids,
            "mechanism": None,
            "completeness": "enriching",
        }
    )
    unavailable = OpportunityDraft.model_validate(
        {
            **opportunity.model_dump(mode="json"),
            "opportunity_id": "opportunity_unavailable",
            "expectation_posture": "unavailable",
        }
    )
    outside_horizon = OpportunityDraft.model_validate(
        {
            **opportunity.model_dump(mode="json"),
            "opportunity_id": "opportunity_outside_horizon",
            "horizon_days": 91,
        }
    )
    opportunities = (opportunity, degraded, unavailable, outside_horizon)
    assessments = {item.opportunity_id: assessments_for(item) for item in opportunities}

    book = build_ranking_book(
        "ranking_fixture_v1",
        opportunities,
        assessments,
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )
    repeated = build_ranking_book(
        "ranking_fixture_v1",
        tuple(reversed(opportunities)),
        assessments,
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )

    assert book == repeated
    assert [(item.opportunity_id, item.position) for item in book.items] == [
        (opportunity.opportunity_id, 1)
    ]
    gates = {item.opportunity_id: item for item in book.gates}
    assert gates["opportunity_degraded"].status == "degraded"
    assert gates["opportunity_degraded"].reason_codes == ("mechanism_missing",)
    assert gates["opportunity_unavailable"].status == "rejected"
    assert (
        "expectation_posture_unavailable"
        in gates["opportunity_unavailable"].reason_codes
    )
    assert gates["opportunity_outside_horizon"].status == "rejected"
    assert gates["opportunity_outside_horizon"].reason_codes == (
        "outside_1_90_day_horizon",
    )
    assert book.book == "opportunity_1_90d"
    assert (book.horizon_min_days, book.horizon_max_days) == (1, 90)


def test_ranking_prefers_better_odds_over_higher_raw_probability() -> None:
    template = fixture_opportunity()
    high_probability = template.model_copy(
        update={
            "opportunity_id": "opportunity_high_probability",
            "snapshot_hash": "d" * 64,
        }
    )
    better_odds = template.model_copy(
        update={
            "opportunity_id": "opportunity_better_odds",
            "snapshot_hash": "e" * 64,
        }
    )

    probability_pair = tuple(
        item.model_copy(
            update={
                "underwriting": scenario_underwriting(
                    item.evidence_ids,
                    item.forecast_probability,
                    bull_alpha=600,
                    base_alpha=200,
                    bear_alpha=-600,
                )
            }
        )
        for item in assessments_for(high_probability, probabilities=(0.85, 0.8))
    )
    odds_pair = tuple(
        item.model_copy(
            update={
                "underwriting": scenario_underwriting(
                    item.evidence_ids,
                    item.forecast_probability,
                    bull_alpha=2_500,
                    base_alpha=1_000,
                    bear_alpha=-500,
                )
            }
        )
        for item in assessments_for(better_odds, probabilities=(0.58, 0.52))
    )

    book = build_ranking_book(
        "ranking_odds_aware_fixture",
        (high_probability, better_odds),
        {
            high_probability.opportunity_id: probability_pair,
            better_odds.opportunity_id: odds_pair,
        },
        discussions={},
        known_at=template.known_at + timedelta(minutes=2),
    )

    assert [item.opportunity_id for item in book.items] == [
        better_odds.opportunity_id,
        high_probability.opportunity_id,
    ]
    assert (
        book.items[0].components["consensus_expected_alpha_bps"]
        > book.items[1].components["consensus_expected_alpha_bps"]
    )
    assert book.items[0].components["edge_half_life_days"] == 20
    assert "base_rate_probability" in book.items[0].components


def test_ranking_rewards_cross_checked_non_news_research() -> None:
    template = fixture_opportunity()
    strong = template.model_copy(
        update={
            "opportunity_id": "opportunity_cross_checked",
            "snapshot_hash": "a" * 64,
            "research_diligence": ResearchDiligence(
                posture="cross_checked",
                completed_tool_calls=4,
                active_research_calls=4,
                cited_research_calls=4,
                non_news_research_calls=3,
                source_families=("primary_web", "market_data", "versioned_web"),
                independent_source_domains=(
                    "issuer.example",
                    "exchange.example",
                    "regulator.example",
                ),
                independent_evidence_origins=(
                    "a" * 64,
                    "b" * 64,
                    "c" * 64,
                ),
                beneficiary_path_declared=True,
                counterevidence_declared=True,
                next_test_declared=True,
                evidence_roles=(
                    "primary_fact",
                    "mechanism",
                    "market_context",
                    "counterevidence",
                ),
                counterevidence_source_distinct=True,
            ),
        }
    )
    screen = template.model_copy(
        update={
            "opportunity_id": "opportunity_screen_grade",
            "snapshot_hash": "b" * 64,
            "research_diligence": ResearchDiligence(
                posture="screen_grade",
                completed_tool_calls=1,
                active_research_calls=1,
                non_news_research_calls=0,
                source_families=("news_locator",),
                independent_source_domains=("publisher.example",),
                reason_codes=("non_news_research_depth_limited",),
            ),
        }
    )
    book = build_ranking_book(
        "ranking_research_quality_fixture",
        (screen, strong),
        {
            strong.opportunity_id: assessments_for(strong, (0.7, 0.65)),
            screen.opportunity_id: assessments_for(screen, (0.7, 0.65)),
        },
        discussions={},
        known_at=template.known_at + timedelta(minutes=2),
    )

    assert [item.opportunity_id for item in book.items] == [strong.opportunity_id]
    assert book.items[0].components["research_quality"] > 0.9
    screen_gate = next(
        item for item in book.gates if item.opportunity_id == screen.opportunity_id
    )
    assert screen_gate.status == "rejected"
    assert screen_gate.reason_codes == ("research_quality_below_decision_hurdle",)
    assert pre_assessment_rejections(strong) == ()
    assert pre_assessment_rejections(screen) == (
        "research_quality_below_decision_hurdle",
    )


def test_ranking_rejects_when_each_assessor_cannot_beat_its_base_rate() -> None:
    opportunity = fixture_opportunity()
    book = build_ranking_book(
        "ranking_independent_edge_fixture",
        (opportunity,),
        {opportunity.opportunity_id: assessments_for(opportunity, (0.78, 0.43))},
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )

    assert book.items == ()
    assert book.gates[0].status == "rejected"
    assert "independent_variant_edge_absent" in book.gates[0].reason_codes


def test_ranking_rejects_nonpositive_uncertainty_adjusted_alpha() -> None:
    opportunity = fixture_opportunity()
    assessments = tuple(
        item.model_copy(
            update={
                "underwriting": scenario_underwriting(
                    item.evidence_ids,
                    item.forecast_probability,
                    bull_alpha=100,
                    base_alpha=10,
                    bear_alpha=-1_000,
                )
            }
        )
        for item in assessments_for(opportunity, (0.75, 0.70))
    )
    book = build_ranking_book(
        "ranking_nonpositive_alpha_fixture",
        (opportunity,),
        {opportunity.opportunity_id: assessments},
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )

    assert book.items == ()
    assert book.gates[0].status == "rejected"
    assert "nonpositive_uncertainty_adjusted_alpha" in book.gates[0].reason_codes


def test_ranking_exposes_conservative_independent_edge() -> None:
    opportunity = fixture_opportunity()
    book = build_ranking_book(
        "ranking_conservative_edge_fixture",
        (opportunity,),
        {opportunity.opportunity_id: assessments_for(opportunity, (0.78, 0.65))},
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )

    assert book.items[0].components["conservative_variant_probability_lift"] == 0.15
    assert book.items[0].components["variant_edge_strength"] == 0.6


def test_ranking_rejects_when_no_independent_security_view_is_ready() -> None:
    opportunity = fixture_opportunity()
    assessments = tuple(
        PrivateAssessment.model_validate(
            {
                **item.model_dump(mode="json"),
                "recommendation": "wait",
                "underwriting": {
                    **item.underwriting.model_dump(mode="json"),
                    "decision": {
                        **item.underwriting.decision.model_dump(mode="json"),
                        "security_thesis_readiness": "conditional",
                    },
                },
            }
        )
        for item in assessments_for(opportunity)
    )

    book = build_ranking_book(
        "ranking_security_readiness_fixture",
        (opportunity,),
        {opportunity.opportunity_id: assessments},
        discussions={},
        known_at=opportunity.known_at + timedelta(minutes=2),
    )

    assert book.items == ()
    assert book.gates[0].status == "rejected"
    assert book.gates[0].reason_codes == ("independent_security_readiness_unavailable",)
