import json
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.b5_runtime import _append_event, _contract_event
from alta_asterism.contracts import Environment, Settings
from alta_asterism.database import Database
from alta_asterism.forward_evaluation import (
    ForwardEvaluationLedger,
    ForwardEvaluationReader,
)


def _database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def evaluation_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_evaluation_{uuid4().hex[:12]}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield _database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def _settings(database_url: str, *, universe: str = "SPY,AAPL") -> Settings:
    return Settings(
        DATABASE_URL=database_url,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
        ALTA_EVALUATION_COHORT_ID="forward-fixture",
        ALTA_EVALUATION_MIN_CLOSED_POSITIONS=10,
        ALTA_UNIVERSE=universe,
        FINLIGHT_API_KEY="fixture-finlight-secret",
        MASSIVE_API_KEY="fixture-massive-secret",
    )


def _append_terminal(
    database: Database,
    cycle_id: str,
    known_at: datetime,
    event_type: str,
    payload: dict,
) -> None:
    with database.connect() as connection:
        _append_event(
            connection,
            _contract_event(
                event_type=event_type,
                aggregate_type="mvp_pipeline",
                aggregate_id=cycle_id,
                environment=Environment.SHADOW,
                known_at=known_at,
                payload=payload,
                correlation_id=cycle_id,
            ),
        )


def test_forward_cohort_exposes_drift_coverage_and_cycle_attribution(
    evaluation_database: str,
) -> None:
    database = Database(evaluation_database)
    database.upgrade()
    known_at = datetime(2026, 8, 25, 13, 30, tzinfo=UTC)
    first_cycle = "live-20260825-133000-000001"
    second_cycle = "live-20260825-140000-000002"
    retrying_cycle = "live-20260825-143000-000003"
    first = ForwardEvaluationLedger(database, _settings(evaluation_database))

    first_hash = first.bind_cycle(first_cycle, known_at)
    assert first.bind_cycle(first_cycle, known_at) == first_hash
    changed = ForwardEvaluationLedger(
        database, _settings(evaluation_database, universe="SPY,AAPL,NVDA")
    )
    with pytest.raises(ValueError, match="different evaluation"):
        changed.bind_cycle(first_cycle, known_at)
    assert (
        changed.bind_cycle(second_cycle, known_at + timedelta(minutes=30)) != first_hash
    )
    first.bind_cycle(retrying_cycle, known_at + timedelta(minutes=60))

    snapshot = {
        "status": "MVP_IDLE",
        "scout_statuses": {
            "macro_regime": "succeeded",
            "news_catalyst": "failed",
        },
        "candidate_ids": ["candidate_fixture"],
        "opportunities": [],
        "expression_attempts": [],
        "shadow_position_id": None,
    }
    _append_terminal(
        database,
        first_cycle,
        known_at + timedelta(minutes=1),
        "mvp.pipeline.completed",
        {"snapshot": snapshot, "replay_hash": "0" * 64},
    )
    _append_terminal(
        database,
        second_cycle,
        known_at + timedelta(minutes=31),
        "mvp.pipeline.failed",
        {"cycle_id": second_cycle, "error_type": "FixtureFailure"},
    )
    _append_terminal(
        database,
        retrying_cycle,
        known_at + timedelta(minutes=61),
        "mvp.pipeline.failed",
        {
            "cycle_id": retrying_cycle,
            "error_type": "FixtureTransientFailure",
            "retry_scheduled": True,
        },
    )
    with database.connect() as connection:
        _append_event(
            connection,
            _contract_event(
                event_type="source.posture",
                aggregate_type="source",
                aggregate_id=f"{first_cycle}:fixture",
                environment=Environment.SHADOW,
                known_at=known_at,
                payload={
                    "cycle_id": first_cycle,
                    "source_id": "fixture",
                    "posture": "healthy",
                },
                correlation_id=first_cycle,
            ),
        )
        connection.execute(
            """INSERT INTO research.run
            (id, environment, version, known_at, cycle_id, role, status,
             input_hash, frozen_input, budget, deadline_at, prompt_version,
             tool_catalog_version, model_provider, model_id, trace_id,
             tool_provenance, evidence_ids, attempt_count)
            VALUES ('run_evaluation_fixture','shadow',1,%s,%s,'macro_regime',
            'succeeded',repeat('0',64),'{}'::jsonb,'{}'::jsonb,%s,
            'alpha-trader-v1','alta-gateway-b3-v1','deepseek',
            'deepseek-v4-flash','trace_fixture','[]'::jsonb,'{}'::text[],1)""",
            (known_at, first_cycle, known_at + timedelta(minutes=3)),
        )

    summary = ForwardEvaluationReader(database).summary("shadow", "forward-fixture", 10)
    assert summary["configurationStable"] is False
    assert summary["configurationVariantCount"] == 2
    assert summary["boundCycles"] == 3
    assert summary["completedCycles"] == 1
    assert summary["failedCycles"] == 1
    assert summary["incompleteCycles"] == 1
    assert summary["idleCycles"] == 1
    assert summary["candidateCycles"] == 1
    assert summary["sources"] == {
        "observations": 1,
        "healthyRate": "1",
        "postures": {"healthy": 1},
    }
    assert summary["agents"]["completionRate"] == "1"
    assert summary["agents"]["routes"][0]["role"] == "macro_regime"
    assert summary["performance"]["readiness"] == "configuration_drift"

    with database.connect() as connection:
        payloads = connection.execute(
            """SELECT payload FROM ops.event
            WHERE event_type = 'evaluation.cycle.bound' ORDER BY sequence"""
        ).fetchall()
    published = json.dumps(payloads)
    assert "fixture-finlight-secret" not in published
    assert "fixture-massive-secret" not in published
    assert ".alta/agent-workspace" not in published
    with database.connect() as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """UPDATE ops.event SET payload = '{}'::jsonb
                WHERE event_type = 'evaluation.cycle.bound'"""
            )
