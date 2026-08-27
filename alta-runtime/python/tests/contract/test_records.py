from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alta_asterism.contracts import (
    Assessment,
    Candidate,
    Environment,
    Event,
    Evidence,
    Expression,
    Job,
    Opportunity,
    Rank,
    Raw,
    Run,
    ShadowPosition,
)


def test_w0_records_preserve_environment_version_and_known_at() -> None:
    known_at = datetime(2026, 8, 23, tzinfo=UTC)
    base = {"environment": Environment.REPLAY, "version": 1, "known_at": known_at}
    records = [
        Job(id="job_1", kind="wake", status="queued", **base),
        Run(id="run_1", role="fixture", status="queued", **base),
        Raw(
            id="raw_1",
            source="fixture",
            source_key="one",
            content_hash="a" * 64,
            body={"fixture": True},
            **base,
        ),
        Evidence(
            id="evidence_1",
            raw_id="raw_1",
            stance="support",
            summary="fixture evidence",
            **base,
        ),
        Candidate(
            id="candidate_1",
            run_id="run_1",
            title="Fixture",
            why_now="New fact",
            expectation="Consensus",
            variant_wedge="Difference",
            falsifier="Counter fact",
            horizon_days=10,
            confidence=0.5,
            **base,
        ),
        Opportunity(
            id="opportunity_1",
            candidate_id="candidate_1",
            status="forming",
            title="Fixture",
            thesis="Testable thesis",
            falsifier="Counter fact",
            horizon_days=10,
            **base,
        ),
        Assessment(
            id="assessment_1",
            opportunity_id="opportunity_1",
            run_id="run_1",
            assessor="fixture",
            verdict="hold",
            score=0.5,
            rationale="Insufficient evidence",
            **base,
        ),
        Rank(
            id="rank_1",
            opportunity_id="opportunity_1",
            book="w0",
            position=1,
            score=0.5,
            **base,
        ),
        Expression(
            id="expression_1",
            opportunity_id="opportunity_1",
            opportunity_version=1,
            kind="wait",
            status="validated",
            rationale="Wait for evidence",
            **base,
        ),
        ShadowPosition(
            id="shadow_1",
            expression_id="expression_1",
            symbol="SPY",
            side="long",
            quantity=1,
            status="open",
            **base,
        ),
        Event(
            id="event_1",
            aggregate_type="run",
            aggregate_id="run_1",
            event_type="run.created",
            **base,
        ),
    ]

    assert [(item.environment, item.version, item.known_at) for item in records] == [
        (Environment.REPLAY, 1, known_at)
    ] * 11


def test_contracts_reject_naive_time_and_unbounded_event_payload() -> None:
    with pytest.raises(ValidationError):
        Event(
            id="event_1",
            environment="replay",
            version=1,
            known_at=datetime(2026, 8, 23),
            aggregate_type="run",
            aggregate_id="run_1",
            event_type="run.created",
        )
    with pytest.raises(ValidationError):
        Event(
            id="event_1",
            environment="replay",
            version=1,
            known_at=datetime(2026, 8, 23, tzinfo=UTC),
            aggregate_type="run",
            aggregate_id="run_1",
            event_type="run.created",
            payload={"value": "x" * 17_000},
        )
