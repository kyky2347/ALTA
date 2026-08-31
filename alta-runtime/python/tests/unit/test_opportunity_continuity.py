from datetime import UTC, datetime, timedelta

from alta_asterism.opportunity_continuity import build_opportunity_continuity
from alta_asterism.opportunity_memory import PriorOpportunitySnapshot
from alta_asterism.research_agenda import OpenResearchQuestion, research_question_id


WAKE_AT = datetime(2026, 8, 30, 14, tzinfo=UTC)


def opportunity(
    index: int,
    *,
    age_days: int,
    deadline_days: int,
    origin: str = "scout_next_test",
    with_question: bool = True,
) -> PriorOpportunitySnapshot:
    opportunity_id = f"opportunity_{index}"
    prompt = f"Test the durable causal claim for opportunity {index}."
    questions = (
        (
            OpenResearchQuestion(
                question_id=research_question_id(opportunity_id, origin, prompt),
                origin=origin,
                prompt=prompt,
            ),
        )
        if with_question
        else ()
    )
    return PriorOpportunitySnapshot(
        opportunity_id=opportunity_id,
        version=1,
        known_at=WAKE_AT - timedelta(days=age_days),
        title=f"Opportunity {index}",
        entity_key=f"entity-{index}",
        direction="positive",
        status="forming",
        horizon_days=365,
        decision_deadline_at=WAKE_AT + timedelta(days=deadline_days),
        summary="A bounded historical thesis requiring a new independent test.",
        snapshot_hash=f"{index:x}" * 64,
        research_questions=questions,
    )


def test_global_priority_precedes_recent_prompt_window() -> None:
    opportunities = (
        opportunity(1, age_days=1, deadline_days=120, with_question=False),
        opportunity(2, age_days=2, deadline_days=90, with_question=False),
        opportunity(3, age_days=3, deadline_days=60),
        opportunity(4, age_days=4, deadline_days=45),
        opportunity(
            5,
            age_days=30,
            deadline_days=2,
            origin="disconfirming_assessor",
        ),
        opportunity(6, age_days=45, deadline_days=8, origin="thesis_pillar"),
    )

    selection = build_opportunity_continuity(
        wake_at=WAKE_AT,
        opportunities=opportunities,
        registry_active=40,
    )

    assert selection.portfolio.scanned_active == 6
    assert selection.portfolio.registry_active == 40
    assert selection.portfolio.registry_scan_saturated is True
    assert selection.portfolio.frozen_active == 4
    assert selection.portfolio.selection_truncated is True
    assert selection.portfolio.posture == "expiring"
    assert selection.portfolio.priority_opportunity_ids == (
        "opportunity_5",
        "opportunity_6",
    )
    assert selection.portfolio.selected_opportunity_ids[:2] == (
        "opportunity_5",
        "opportunity_6",
    )
    assert selection.research_queue[0].remaining_days == 2


def test_fixed_deadline_does_not_slide_when_opportunity_is_refreshed() -> None:
    refreshed = opportunity(7, age_days=1, deadline_days=-1)

    selection = build_opportunity_continuity(
        wake_at=WAKE_AT,
        opportunities=(refreshed,),
    )

    assert selection.research_queue == ()
    assert selection.portfolio.stale_active == 1
    assert selection.portfolio.posture == "stale"
    assert selection.portfolio.earliest_decision_deadline_at == (
        WAKE_AT - timedelta(days=1)
    )


def test_deferred_questions_remain_visible_without_entering_the_due_queue() -> None:
    next_due = WAKE_AT + timedelta(hours=6)
    selection = build_opportunity_continuity(
        wake_at=WAKE_AT,
        opportunities=(
            opportunity(8, age_days=4, deadline_days=10, with_question=False),
        ),
        deferred_questions=2,
        next_research_due_at=next_due,
    )

    assert selection.portfolio.version == "alta-opportunity-continuity-v2"
    assert selection.portfolio.pending_questions == 0
    assert selection.portfolio.deferred_questions == 2
    assert selection.portfolio.next_research_due_at == next_due
    assert selection.research_queue == ()
    assert selection.portfolio.public_summary()["nextResearchDueAt"] == (
        next_due.isoformat()
    )
