from datetime import UTC, datetime, timedelta

from alta_asterism.agentic_position import (
    PillarMonitorDecision,
    PositionMonitorDecision,
    position_next_catalyst,
    valid_monitor_bindings,
)
from alta_asterism.investment_thesis import ThesisPillar

PILLAR_ID = "pillar_" + "a" * 32


def decision(*, status: str, falsifier_triggered: bool) -> PositionMonitorDecision:
    return PositionMonitorDecision(
        position_id="position_fixture",
        falsifier_triggered=falsifier_triggered,
        rationale="Review only the frozen claim against new Evidence.",
        evidence_ids=("evidence_new",),
        pillar_reviews=(
            PillarMonitorDecision(
                pillar_id=PILLAR_ID,
                status=status,
                rationale="The new observation satisfies the frozen condition.",
                evidence_ids=("evidence_new",),
            ),
        ),
    )


def test_monitor_review_requires_complete_point_in_time_binding() -> None:
    expected = {"position_fixture": {PILLAR_ID}}
    evidence = {"evidence_new"}

    assert valid_monitor_bindings(
        (decision(status="confirming", falsifier_triggered=False),),
        expected,
        evidence,
    )
    assert valid_monitor_bindings(
        (decision(status="invalidated", falsifier_triggered=True),),
        expected,
        evidence,
    )
    assert not valid_monitor_bindings(
        (decision(status="invalidated", falsifier_triggered=False),),
        expected,
        evidence,
    )
    assert not valid_monitor_bindings(
        (decision(status="confirming", falsifier_triggered=False),),
        expected,
        {"different_evidence"},
    )


def test_position_catalyst_uses_earliest_frozen_observable_then_prediction() -> None:
    known_at = datetime(2026, 8, 27, 12, tzinfo=UTC)

    def pillar(identity: str, days: int, observable: str) -> ThesisPillar:
        return ThesisPillar(
            pillar_id="pillar_" + identity * 32,
            source_candidate_ids=(f"candidate_{identity}",),
            statement=f"Frozen claim {identity}.",
            observable=observable,
            confirmation_condition=f"Claim {identity} confirms.",
            invalidation_condition=f"Claim {identity} fails.",
            known_at=known_at,
            expected_by_days=days,
            due_at=known_at + timedelta(days=days),
            evidence_ids=(f"evidence_{identity}",),
        )

    later = pillar("b", 12, "Later operating disclosure")
    earlier = pillar("a", 3, "Earlier regulatory decision")

    assert (
        position_next_catalyst((later, earlier), "Fallback prediction")
        == "Earlier regulatory decision"
    )
    assert position_next_catalyst((), "  Versioned KPI update  ") == (
        "Versioned KPI update"
    )
    assert position_next_catalyst((), None) == "Next versioned evidence update."
