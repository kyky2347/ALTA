from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from alta_asterism.cycle_recovery import (
    FrozenCycleSnapshotError,
    frozen_wake_hash,
    recover_frozen_wake,
)
from alta_asterism.opportunity_memory import PriorOpportunitySnapshot
from alta_asterism.research_agenda import (
    OpenResearchQuestion,
    ResearchQueueInput,
    build_opportunity_drive,
    build_research_queue,
    research_question_id,
)
from alta_asterism.scouts import SCOUTS, FrozenScoutInput


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, run_rows, snapshot_rows=()):
        self.run_rows = run_rows
        self.snapshot_rows = snapshot_rows

    def execute(self, query, _params):
        if "FROM research.scout_batch_snapshot" in query:
            return _Rows(self.snapshot_rows)
        if "SELECT r.role, r.frozen_input" in query:
            return _Rows(self.run_rows)
        return _Rows([("durable_database", "healthy")])


class _Database:
    def __init__(self, run_rows, snapshot_rows=()):
        self.connection = _Connection(run_rows, snapshot_rows)

    def connect(self):
        return nullcontext(self.connection)


def test_recovery_restores_global_research_director_from_scoped_snapshots() -> None:
    wake_at = datetime(2026, 8, 28, 12, tzinfo=UTC)
    questions = tuple(
        OpenResearchQuestion(
            question_id=research_question_id(
                "opportunity_recovery",
                origin,
                prompt,
            ),
            origin=origin,
            prompt=prompt,
        )
        for origin, prompt in (
            (
                "disconfirming_assessor",
                "Test whether the rival mechanism explains the observation.",
            ),
            (
                "thesis_pillar",
                "Verify the operating milestone before the decision horizon.",
            ),
        )
    )
    prior = PriorOpportunitySnapshot(
        opportunity_id="opportunity_recovery",
        version=2,
        known_at=wake_at - timedelta(days=1),
        title="Recoverable research parent",
        direction="positive",
        status="forming",
        horizon_days=14,
        summary="A bounded Opportunity with two distinct open questions.",
        snapshot_hash="a" * 64,
        research_questions=questions,
    )
    queue = build_research_queue(
        wake_at=wake_at,
        opportunities=(
            ResearchQueueInput(
                opportunity_id=prior.opportunity_id,
                status=prior.status,
                known_at=prior.known_at,
                horizon_days=prior.horizon_days,
                research_questions=prior.research_questions,
            ),
        ),
    )
    drive = build_opportunity_drive(
        cycle_id="cycle_recovery",
        idle_streak=0,
        research_queue=queue,
        scout_ids=tuple(item.scout_id for item in SCOUTS),
    )
    frozen = FrozenScoutInput(
        wake_id="cycle_recovery",
        environment="shadow",
        known_at=wake_at,
        universe=("SPY",),
        evidence=(),
        prior_opportunities=(prior,),
        opportunity_drive=drive,
        expectation_posture="unavailable",
    )
    run_rows = [
        (
            scout.scout_id,
            {
                "input": frozen.for_scout(
                    scout.scout_id, scout.primary_sources
                ).model_dump(mode="json")
            },
        )
        for scout in SCOUTS
    ]

    recovered = recover_frozen_wake(_Database(run_rows), "cycle_recovery")

    assert recovered is not None
    recovered_frozen, postures = recovered
    assert recovered_frozen.opportunity_drive.assigned_mode == "explore"
    assert recovered_frozen.opportunity_drive.assigned_research is None
    assert recovered_frozen.opportunity_drive.research_queue == drive.research_queue
    assert recovered_frozen.opportunity_drive.research_assignments == (
        drive.research_assignments
    )
    assert postures == {"durable_database": "healthy"}
    for assignment in drive.research_assignments:
        scoped = recovered_frozen.opportunity_drive.for_scout(assignment.scout_id)
        assert scoped.assigned_research == assignment

    with pytest.raises(FrozenCycleSnapshotError, match="no global recovery anchor"):
        recover_frozen_wake(_Database(run_rows[:-1]), "cycle_recovery")

    anchored_postures = {"durable_database": "healthy"}
    anchored = recover_frozen_wake(
        _Database(
            run_rows[:-1],
            (
                (
                    "shadow",
                    wake_at,
                    frozen.model_dump(mode="json"),
                    anchored_postures,
                    frozen_wake_hash(frozen, anchored_postures),
                ),
            ),
        ),
        "cycle_recovery",
    )
    assert anchored == (frozen, anchored_postures)
