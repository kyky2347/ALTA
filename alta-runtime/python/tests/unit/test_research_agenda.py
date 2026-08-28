from datetime import UTC, datetime, timedelta

from alta_asterism.research_agenda import (
    OpenResearchQuestion,
    ResearchQueueInput,
    build_open_research_questions,
    build_opportunity_drive,
    build_research_queue,
)


def test_research_agenda_is_prioritized_deduplicated_and_bounded() -> None:
    questions = build_open_research_questions(
        opportunity_id="opportunity_fixture",
        next_test=" Verify the estimate revision in the next filing. ",
        first_rejection="The signal may already be priced.",
        assessor_questions=(
            (
                "thesis_assessor",
                "Check whether management guidance confirms the mechanism.",
            ),
            (
                "disconfirming_assessor",
                "Verify the estimate revision in the next filing.",
            ),
            (
                "disconfirming_assessor",
                "Test whether a rival supply explanation fits better.",
            ),
        ),
    )

    assert [item.origin for item in questions] == [
        "scout_next_test",
        "disconfirming_assessor",
    ]
    assert questions[1].prompt.startswith("Test whether a rival")
    assert len({item.question_id for item in questions}) == 2
    assert questions == build_open_research_questions(
        opportunity_id="opportunity_fixture",
        next_test=" Verify the estimate revision in the next filing. ",
        first_rejection="The signal may already be priced.",
        assessor_questions=(
            (
                "thesis_assessor",
                "Check whether management guidance confirms the mechanism.",
            ),
            (
                "disconfirming_assessor",
                "Verify the estimate revision in the next filing.",
            ),
            (
                "disconfirming_assessor",
                "Test whether a rival supply explanation fits better.",
            ),
        ),
    )


def test_thesis_pillar_becomes_an_exact_follow_up_question() -> None:
    questions = build_open_research_questions(
        opportunity_id="opportunity_fixture",
        next_test=None,
        first_rejection="The market already discounts the change.",
        thesis_questions=("Verify the next operating update against the frozen path.",),
    )

    assert questions[0].origin == "thesis_pillar"
    assert questions[0].prompt.startswith("Verify the next operating")


def test_opportunity_drive_balances_follow_up_and_independent_exploration() -> None:
    scout_ids = ("mind_a", "mind_b", "mind_c", "mind_d")
    wake_at = datetime(2026, 8, 27, 12, tzinfo=UTC)
    queue = build_research_queue(
        wake_at=wake_at,
        opportunities=(
            ResearchQueueInput(
                opportunity_id="opportunity_a",
                status="forming",
                known_at=wake_at - timedelta(days=2),
                horizon_days=10,
                research_questions=(
                    OpenResearchQuestion(
                        question_id="a" * 16,
                        origin="disconfirming_assessor",
                        prompt="Test the strongest rival explanation.",
                    ),
                ),
            ),
            ResearchQueueInput(
                opportunity_id="opportunity_b",
                status="ranked",
                known_at=wake_at - timedelta(days=1),
                horizon_days=30,
                research_questions=(
                    OpenResearchQuestion(
                        question_id="b" * 16,
                        origin="thesis_pillar",
                        prompt="Verify the causal operating milestone.",
                    ),
                ),
            ),
        ),
    )
    drive = build_opportunity_drive(
        cycle_id="live-20260827-120000-000000",
        idle_streak=3,
        research_queue=queue,
        scout_ids=scout_ids,
    )

    assert drive.posture == "resolve_backlog"
    assert drive.route_change_required is True
    assert len(drive.follow_up_scout_ids) == 2
    assert len(drive.research_assignments) == 2
    assert len({item.question_id for item in drive.research_assignments}) == 2
    for assignment in drive.research_assignments:
        scoped = drive.for_scout(assignment.scout_id)
        assert scoped.assigned_research == assignment
    assert (
        len(
            [
                scout_id
                for scout_id in scout_ids
                if drive.for_scout(scout_id).assigned_mode == "follow_up"
            ]
        )
        == 2
    )
    assert (
        len(
            [
                scout_id
                for scout_id in scout_ids
                if drive.for_scout(scout_id).assigned_mode == "explore"
            ]
        )
        == 2
    )
    assert drive == build_opportunity_drive(
        cycle_id="live-20260827-120000-000000",
        idle_streak=3,
        research_queue=queue,
        scout_ids=scout_ids,
    )


def test_opportunity_drive_changes_route_after_repeated_empty_cycles() -> None:
    drive = build_opportunity_drive(
        cycle_id="live-empty",
        idle_streak=99,
        research_queue=(),
        scout_ids=("mind_a", "mind_b", "mind_c", "mind_d"),
    )

    assert drive.posture == "expand_search"
    assert drive.idle_streak == 12
    assert drive.route_change_required is True
    assert drive.follow_up_scout_ids == ()


def test_research_queue_prioritizes_decision_gaps_and_excludes_expired_work() -> None:
    wake_at = datetime(2026, 8, 27, 12, tzinfo=UTC)
    queue = build_research_queue(
        wake_at=wake_at,
        opportunities=(
            ResearchQueueInput(
                opportunity_id="opportunity_live",
                status="forming",
                known_at=wake_at - timedelta(days=8),
                horizon_days=10,
                research_questions=(
                    OpenResearchQuestion(
                        question_id="a" * 16,
                        origin="scout_next_test",
                        prompt="Check the next operating disclosure.",
                    ),
                    OpenResearchQuestion(
                        question_id="b" * 16,
                        origin="disconfirming_assessor",
                        prompt="Test whether the rival supply mechanism fits better.",
                    ),
                ),
            ),
            ResearchQueueInput(
                opportunity_id="opportunity_expired",
                status="ranked",
                known_at=wake_at - timedelta(days=31),
                horizon_days=30,
                research_questions=(
                    OpenResearchQuestion(
                        question_id="c" * 16,
                        origin="disconfirming_assessor",
                        prompt="This question is past its decision horizon.",
                    ),
                ),
            ),
            ResearchQueueInput(
                opportunity_id="opportunity_shadow",
                status="shadow",
                known_at=wake_at - timedelta(days=1),
                horizon_days=30,
                research_questions=(
                    OpenResearchQuestion(
                        question_id="d" * 16,
                        origin="disconfirming_assessor",
                        prompt="The position monitor owns this question.",
                    ),
                ),
            ),
        ),
    )

    assert [item.opportunity_id for item in queue] == [
        "opportunity_live",
        "opportunity_live",
    ]
    assert queue[0].question_id == "b" * 16
    assert queue[0].priority_score > queue[1].priority_score
    assert queue[0].reason_codes == (
        "forming",
        "disconfirming",
        "urgent",
    )
