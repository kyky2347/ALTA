from alta_asterism.agentic_position import (
    PillarMonitorDecision,
    PositionMonitorDecision,
    valid_monitor_bindings,
)

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
