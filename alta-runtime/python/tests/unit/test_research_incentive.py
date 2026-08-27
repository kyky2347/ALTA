from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alta_asterism.alpha_feedback import (
    AlphaOutcomeObservation,
    build_alpha_feedback,
)
from alta_asterism.research_incentive import build_research_incentives
from alta_asterism.scout_batch import incentive_adjusted_budget
from alta_asterism.scouts import FrozenScoutInput, RunBudget

SCOUT_ID = "change_event_scout"


def feedback_with_alpha(value: Decimal, count: int = 30):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    observations = tuple(
        AlphaOutcomeObservation(
            position_id=f"position_{index:03d}",
            scout_id=SCOUT_ID,
            alpha_archetype="revision inflection",
            research_route=("alta_web_research", "alta_finance_data"),
            known_at=start + timedelta(hours=index),
            net_return_bps=value,
            realized_alpha_bps=value,
        )
        for index in range(count)
    )
    return build_alpha_feedback(observations)[0]


def test_prospective_contract_promises_no_immediate_budget() -> None:
    incentive = build_research_incentives((), scout_ids=(SCOUT_ID,))[0]

    assert incentive.state == "prospective"
    assert incentive.bonus_tool_calls == 0
    assert incentive.bonus_total_tokens == 0
    assert "Candidate count" in incentive.directive


def test_immature_feedback_stays_hidden_and_unrewarded() -> None:
    feedback = feedback_with_alpha(Decimal("100"), count=29)
    incentive = build_research_incentives((feedback,), scout_ids=(SCOUT_ID,))[0]

    assert incentive.state == "calibrating"
    assert incentive.alpha_lower_confidence_bps is None
    assert incentive.bonus_tool_calls == 0


def test_positive_conservative_alpha_earns_bounded_research_budget() -> None:
    feedback = feedback_with_alpha(Decimal("25"))
    incentive = build_research_incentives((feedback,), scout_ids=(SCOUT_ID,))[0]
    frozen = FrozenScoutInput(
        wake_id="wake_reward_fixture",
        environment="shadow",
        known_at=feedback.known_at + timedelta(seconds=1),
        universe=("SPY",),
        evidence=(),
        alpha_feedback=(feedback,),
        research_incentives=(incentive,),
        expectation_posture="unavailable",
    )
    budget = incentive_adjusted_budget(
        RunBudget(
            max_tool_calls=6,
            max_total_tokens=60_000,
            max_output_bytes=12_000,
            require_active_research=True,
        ),
        frozen,
    )

    assert incentive.state == "earned"
    assert incentive.alpha_lower_confidence_bps == Decimal("25")
    assert budget.max_tool_calls == 7
    assert budget.max_total_tokens == 68_000
    assert budget.require_active_research is True


def test_non_positive_conservative_alpha_enters_recovery_without_bonus() -> None:
    feedback = feedback_with_alpha(Decimal("-1"))
    incentive = build_research_incentives((feedback,), scout_ids=(SCOUT_ID,))[0]

    assert incentive.state == "recovery"
    assert incentive.bonus_tool_calls == 0
    assert incentive.bonus_total_tokens == 0
    assert "Change the entity" in incentive.directive
