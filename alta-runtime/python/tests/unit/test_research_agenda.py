from alta_asterism.research_agenda import (
    build_open_research_questions,
    build_opportunity_drive,
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
    drive = build_opportunity_drive(
        cycle_id="live-20260827-120000-000000",
        idle_streak=3,
        priority_opportunity_ids=("opportunity_a", "opportunity_b"),
        scout_ids=scout_ids,
    )

    assert drive.posture == "resolve_backlog"
    assert drive.route_change_required is True
    assert len(drive.follow_up_scout_ids) == 2
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
        priority_opportunity_ids=("opportunity_a", "opportunity_b"),
        scout_ids=scout_ids,
    )


def test_opportunity_drive_changes_route_after_repeated_empty_cycles() -> None:
    drive = build_opportunity_drive(
        cycle_id="live-empty",
        idle_streak=99,
        priority_opportunity_ids=(),
        scout_ids=("mind_a", "mind_b", "mind_c", "mind_d"),
    )

    assert drive.posture == "expand_search"
    assert drive.idle_streak == 12
    assert drive.route_change_required is True
    assert drive.follow_up_scout_ids == ()
