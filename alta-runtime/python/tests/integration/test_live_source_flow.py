import hashlib
import os
import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from alta_asterism.database import Database
from alta_asterism.agentic_deliberation import PrivateAssessmentPayload
from alta_asterism.agentic_roles import StructuredRoleRunner
from alta_asterism.autonomous import AutonomousOwnerBusy, AutonomousRunner
from alta_asterism.contracts import Event, Settings
from alta_asterism.context_budget import (
    MAX_FROZEN_SCOUT_INPUT_BYTES,
    canonical_json_bytes,
)
from alta_asterism.cycle_recovery import FrozenCycleSnapshotError
from alta_asterism.live_source_flow import DatabaseSourceFlow, IngestingSourceFlow
from alta_asterism.mind_worker import ModelTurn, ScoutDeadlineExceeded
from alta_asterism.mvp_fixture import MvpFixture
from alta_asterism.mvp_orchestrator import MvpOrchestrator
from alta_asterism.scout_repository import ScoutRepository
from alta_asterism.scouts import (
    SCOUTS,
    RunBudget,
    fit_frozen_input_for_scout,
    make_run_spec,
)


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def live_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_live_{uuid4().hex[:12]}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_database_source_flow_normalizes_raw_and_enforces_point_in_time(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)
    with database.connect() as connection:
        for raw_id, known_at, title in (
            ("raw_known", wake_at - timedelta(minutes=2), "Known filing changed"),
            ("raw_future", wake_at + timedelta(minutes=2), "Future leak"),
            (
                "raw_shadow_fixture",
                wake_at - timedelta(minutes=1),
                "Fixture must not enter a live wake",
            ),
        ):
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body) VALUES (%s,'shadow',1,%s,'finlight',%s,%s,%s)""",
                (
                    raw_id,
                    known_at,
                    raw_id,
                    (
                        "a"
                        if raw_id == "raw_known"
                        else ("b" if raw_id == "raw_future" else "c")
                    )
                    * 64,
                    Jsonb(
                        {
                            "title": title,
                            "fixture": raw_id == "raw_shadow_fixture",
                            "source_url": (
                                "https://fixture.invalid/filing?api_key=secret"
                            ),
                            "origin_fingerprint": "d" * 64,
                        }
                    ),
                ),
            )

    flow = DatabaseSourceFlow(database, ("AAPL", "SPY"))
    frozen, postures = flow.schedule_and_wake("cycle_live_001", wake_at, {})
    recovered, _ = flow.schedule_and_wake("cycle_live_001", wake_at, {})
    repeated, _ = flow.schedule_and_wake("cycle_live_002", wake_at, {})

    assert frozen.universe == ("AAPL", "SPY")
    assert [item.raw_id for item in frozen.evidence] == ["raw_known"]
    assert frozen.evidence[0].source_locator == "https://fixture.invalid/filing"
    assert frozen.evidence[0].origin_fingerprint == "d" * 64
    assert frozen.expectation_posture == "available"
    assert frozen.portfolio_research_mandate is not None
    assert frozen.portfolio_research_mandate.posture == "empty_book"
    assert frozen.research_attention_portfolio is not None
    assert frozen.research_attention_portfolio.posture == "insufficient_sample"
    assert len(frozen.research_attention_portfolio.assignments) == len(SCOUTS)
    assert frozen.opportunity_continuity is not None
    assert frozen.opportunity_continuity.posture == "empty"
    assert frozen.opportunity_continuity.scanned_active == 0
    assert postures == {"finlight": "healthy"}
    assert recovered.evidence == frozen.evidence
    assert repeated.evidence == frozen.evidence
    with database.connect() as connection:
        assert (
            connection.execute("SELECT count(*) FROM research.evidence").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM ops.event WHERE aggregate_id = 'cycle_live_001'"
            ).fetchone()[0]
            == 2
        )


def test_database_source_flow_allows_autonomous_search_without_seed_evidence(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    flow = DatabaseSourceFlow(database, ("SPY",))

    frozen, postures = flow.schedule_and_wake(
        "cycle_empty_001", datetime(2026, 8, 23, 15, tzinfo=UTC), {}
    )

    assert frozen.evidence == ()
    assert frozen.expectation_posture == "unavailable"
    assert postures == {"durable_database": "degraded"}


def test_database_source_flow_freezes_and_validates_market_research_agenda(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 24, 15, tzinfo=UTC)
    closes = {
        "SPY": (100, 100, 101, 101, 102, 103),
        "AAPL": (100, 100, 100, 100, 101, 112),
    }
    with database.connect() as connection:
        for symbol, values in closes.items():
            for index, close in enumerate(values):
                source_key = f"daily:{symbol}:{index}"
                session = wake_at.date() - timedelta(days=6 - index)
                connection.execute(
                    """INSERT INTO research.raw
                    (id, environment, version, known_at, source, source_key,
                     content_hash, body)
                    VALUES (%s,'shadow',1,%s,'massive',%s,%s,%s)""",
                    (
                        f"raw_market_agenda_{symbol}_{index}",
                        wake_at - timedelta(hours=1),
                        source_key,
                        hashlib.sha256(source_key.encode()).hexdigest(),
                        Jsonb(
                            {
                                "semanticTimes": {
                                    "eventAt": datetime.combine(
                                        session,
                                        datetime.min.time(),
                                        tzinfo=UTC,
                                    ).isoformat()
                                },
                                "payload": {
                                    "symbol": symbol,
                                    "aggregate": {
                                        "open": close,
                                        "high": close * 1.01,
                                        "low": close * 0.99,
                                        "close": close,
                                        "volume": (
                                            3_000_000
                                            if symbol == "AAPL" and index == 5
                                            else 1_000_000
                                        ),
                                    },
                                },
                            }
                        ),
                    ),
                )

    frozen, _ = DatabaseSourceFlow(database, ("SPY", "AAPL")).schedule_and_wake(
        "cycle_market_agenda_001", wake_at, {}
    )

    assert frozen.market_research_agenda is not None
    assert frozen.market_research_agenda.posture == "screen_ready"
    assert frozen.market_research_agenda.seeds
    scoped = frozen.for_scout(
        "market_dislocation_scout", ("massive_bar", "relative_market_move")
    )
    assert len(scoped.market_research_agenda.seeds) == 1
    repository = ScoutRepository(database)
    repository.validate_frozen_input(scoped)
    original_seed = scoped.market_research_agenda.seeds[0]
    tampered = scoped.model_copy(
        update={
            "market_research_agenda": scoped.market_research_agenda.model_copy(
                update={
                    "seeds": (
                        original_seed.model_copy(
                            update={"priority_score": Decimal("0")}
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="market research seed"):
        repository.validate_frozen_input(tampered)


def test_database_source_flow_changes_research_route_after_idle_streak(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)
    for index in range(3):
        database.append_event(
            Event(
                id=f"event_idle_drive_{index}",
                environment="shadow",
                version=1,
                known_at=wake_at - timedelta(minutes=3 - index),
                aggregate_type="mvp_pipeline",
                aggregate_id=f"live-20260823-145{index}00-000000",
                event_type="mvp.pipeline.completed",
                payload={"snapshot": {"status": "MVP_IDLE"}},
            )
        )

    frozen, _ = DatabaseSourceFlow(database, ("SPY",)).schedule_and_wake(
        "live-20260823-150000-000000", wake_at, {}
    )

    assert frozen.opportunity_drive.posture == "expand_search"
    assert frozen.opportunity_drive.idle_streak == 3
    assert frozen.opportunity_drive.route_change_required is True
    assert len(frozen.research_incentives) == len(SCOUTS)
    assert all(item.state == "prospective" for item in frozen.research_incentives)
    assert all(item.bonus_tool_calls == 0 for item in frozen.research_incentives)
    assert all(
        frozen.for_scout(
            scout.scout_id, scout.primary_sources
        ).opportunity_drive.assigned_mode
        == "explore"
        for scout in SCOUTS
    )


def test_database_source_flow_freezes_prior_trader_mind_experience_as_non_evidence(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)
    with database.connect() as connection:
        for index, scout in enumerate(SCOUTS, start=1):
            connection.execute(
                """INSERT INTO research.mind_state
                (id, environment, version, known_at, scout_id, turn_count,
                 context_tokens, started_at, rolling_summary, model_provider,
                 model_id, prompt_version, tool_catalog_version)
                VALUES (%s,'shadow',%s,%s,%s,%s,100,%s,%s,'deepseek',
                        'deepseek-v4-flash','alpha-trader-v2',
                        'alta-active-research-v2')""",
                (
                    f"mind_fixture_{index}",
                    index,
                    wake_at - timedelta(minutes=10),
                    scout.scout_id,
                    index,
                    wake_at - timedelta(hours=1),
                    json.dumps(
                        {
                            "outcome": "no_op",
                            "finding": f"Prior route {index} lacked proof.",
                        },
                        separators=(",", ":"),
                    ),
                ),
            )

    frozen, _ = DatabaseSourceFlow(database, ("SPY",)).schedule_and_wake(
        "cycle_mind_memory_001", wake_at, {}
    )

    assert len(frozen.trader_mind_memories) == len(SCOUTS)
    scoped = frozen.for_scout(SCOUTS[0].scout_id, SCOUTS[0].primary_sources)
    assert [item.scout_id for item in scoped.trader_mind_memories] == [
        SCOUTS[0].scout_id
    ]
    assert scoped.evidence == ()
    ScoutRepository(database).validate_frozen_input(scoped)
    tampered = scoped.model_copy(
        update={
            "trader_mind_memories": (
                scoped.trader_mind_memories[0].model_copy(
                    update={"summary": "Unpersisted memory"}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="does not match PostgreSQL"):
        ScoutRepository(database).validate_frozen_input(tampered)


def test_database_source_flow_sheds_accumulated_context_to_preserve_live_wake(
    live_database: str,
) -> None:
    """A long-lived database must not make the next autonomous wake impossible."""

    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 25, 15, tzinfo=UTC)
    with database.connect() as connection:
        for index in range(12):
            raw_id = f"raw_context_pressure_{index:02d}"
            content_hash = hashlib.sha256(raw_id.encode()).hexdigest()
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body)
                VALUES (%s,'shadow',1,%s,'finlight',%s,%s,%s)""",
                (
                    raw_id,
                    wake_at - timedelta(minutes=index + 1),
                    raw_id,
                    content_hash,
                    Jsonb({"title": f"{index:02d} " + "e" * 470}),
                ),
            )
        for index, scout in enumerate(SCOUTS, start=1):
            connection.execute(
                """INSERT INTO research.mind_state
                (id, environment, version, known_at, scout_id, turn_count,
                 context_tokens, started_at, rolling_summary, model_provider,
                 model_id, prompt_version, tool_catalog_version)
                VALUES (%s,'shadow',%s,%s,%s,%s,100,%s,%s,'deepseek',
                        'deepseek-v4-flash','alpha-trader-v2',
                        'alta-active-research-v2')""",
                (
                    f"mind_context_pressure_{index}",
                    index,
                    wake_at - timedelta(minutes=20),
                    scout.scout_id,
                    index,
                    wake_at - timedelta(hours=1),
                    "m" * 1_200,
                ),
            )

    frozen, _ = DatabaseSourceFlow(
        database,
        ("SPY", "AAPL"),
        max_evidence=12,
    ).schedule_and_wake("cycle_context_pressure_001", wake_at, {})

    encoded = canonical_json_bytes(frozen.model_dump(mode="json"))
    assert len(encoded) <= MAX_FROZEN_SCOUT_INPUT_BYTES
    assert frozen.evidence
    assert len(frozen.evidence) == 12
    assert frozen.trader_mind_memories == ()
    ScoutRepository(database).validate_frozen_input(frozen)


def test_frozen_mind_memory_remains_valid_after_the_current_mind_evolves(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)
    scout = SCOUTS[0]
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO research.mind_state
            (id, environment, version, known_at, scout_id, turn_count,
             context_tokens, started_at, rolling_summary, model_provider,
             model_id, prompt_version, tool_catalog_version)
            VALUES ('mind_history_fixture','shadow',1,%s,%s,1,100,%s,
                    '{"outcome":"no_op"}','deepseek','deepseek-v4-flash',
                    'alpha-trader-v2','alta-active-research-v2')""",
            (
                wake_at - timedelta(minutes=10),
                scout.scout_id,
                wake_at - timedelta(hours=1),
            ),
        )
    frozen, postures = DatabaseSourceFlow(database, ("SPY",)).schedule_and_wake(
        "cycle_mind_history_001", wake_at, {}
    )
    scoped = frozen.for_scout(scout.scout_id, scout.primary_sources)
    repository = ScoutRepository(database)
    job_id = repository.start_batch(f"batch_{frozen.wake_id}", frozen, postures)
    spec = make_run_spec(
        run_id="run_mind_history_fixture",
        trace_id="trace_mind_history_fixture",
        scout=scout,
        frozen_input=scoped,
        budget=RunBudget(
            max_tool_calls=1, max_total_tokens=1_000, max_output_bytes=1_000
        ),
        deadline_at=wake_at + timedelta(minutes=5),
        model_provider="deepseek",
        model_id="deepseek-v4-flash",
    )
    assert repository.start_run(job_id, spec) is True
    with database.connect() as connection:
        connection.execute(
            """UPDATE research.mind_state SET version=2, known_at=%s,
            turn_count=2, rolling_summary='{"outcome":"candidate"}'
            WHERE id='mind_history_fixture'""",
            (wake_at + timedelta(seconds=1),),
        )

    repository.validate_frozen_input(scoped)
    assert repository.reconcile_expired_activity(wake_at + timedelta(minutes=6)) == (
        1,
        1,
    )
    with database.connect() as connection:
        assert connection.execute(
            """SELECT r.status, r.error_code, j.status
            FROM research.run r JOIN ops.job j ON j.id=r.job_id
            WHERE r.id='run_mind_history_fixture'"""
        ).fetchone() == ("failed", "recovery_deadline_expired", "failed")


class FailingMassiveAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, _dataset, _symbols):
        self.calls += 1
        raise RuntimeError("credential-like connector detail must stay redacted")


def test_massive_transport_failure_degrades_source_without_aborting_cycle(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    adapter = FailingMassiveAdapter()
    flow = IngestingSourceFlow(
        DatabaseSourceFlow(database, ("SPY",)),
        massive_adapter=adapter,
        massive_discovery_enabled=True,
    )
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)

    frozen, postures = flow.schedule_and_wake("cycle_degraded_001", wake_at, {})
    recovered, recovered_postures = flow.schedule_and_wake(
        "cycle_degraded_001", wake_at, {}
    )

    assert frozen.wake_id == "cycle_degraded_001"
    assert postures == {
        "durable_database": "degraded",
        "finlight_transport": "disabled",
        "massive_transport": "degraded",
    }
    assert recovered == frozen
    assert recovered_postures == postures
    assert adapter.calls == 1
    with database.connect() as connection:
        payload = connection.execute(
            """SELECT payload FROM ops.event
            WHERE aggregate_id = 'cycle_degraded_001:massive_transport'
              AND event_type = 'source.posture'"""
        ).fetchone()[0]
    assert payload["reason"] == "connector_error:RuntimeError"
    assert "credential-like" not in json.dumps(payload)

    _, backed_off = flow.schedule_and_wake(
        "cycle_degraded_002", wake_at + timedelta(seconds=30), {}
    )
    assert backed_off["massive_transport"] == "degraded"
    assert adapter.calls == 1
    with database.connect() as connection:
        second_payload = connection.execute(
            """SELECT payload FROM ops.event
            WHERE aggregate_id = 'cycle_degraded_002:massive_transport'
              AND event_type = 'source.posture'"""
        ).fetchone()[0]
    assert second_payload["reason"] == "connector_backoff:30s"


class FakeRoleClient:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, spec, _prompt: str, _schema: dict) -> ModelTurn:
        self.calls += 1
        return ModelTurn(
            final_response=json.dumps(
                {
                    "forecast_probability": 0.61,
                    "evidence_quality": 0.72,
                    "variant_wedge_quality": 0.55,
                    "strongest_support": "The frozen fact supports the mechanism.",
                    "strongest_disconfirmation": "The propagation may already be priced.",
                    "first_rejection": "Reject on the next contrary update.",
                    "missing_evidence": ["next primary update"],
                    "recommendation": "research",
                    "confidence": 0.58,
                    "evidence_ids": ["evidence_fixture"],
                    "rationale": "Independent bounded assessment.",
                    "underwriting": {
                        "benchmark_symbol": "SPY",
                        "bull": {
                            "probability": 0.2,
                            "relative_alpha_bps": 700,
                            "trigger": "Bull trigger.",
                            "evidence_ids": ["evidence_fixture"],
                        },
                        "base": {
                            "probability": 0.41,
                            "relative_alpha_bps": 150,
                            "trigger": "Base trigger.",
                            "evidence_ids": ["evidence_fixture"],
                        },
                        "bear": {
                            "probability": 0.39,
                            "relative_alpha_bps": -500,
                            "trigger": "Bear trigger.",
                            "evidence_ids": ["evidence_fixture"],
                        },
                        "catalyst_clarity": 0.6,
                        "crowding_risk": 0.3,
                        "liquidity_risk": 0.2,
                        "next_pricing_fact": "The next primary update.",
                        "decision": {
                            "what_is_priced_in": "A normal update is priced in.",
                            "variant_view": "The frozen fact supports a faster path.",
                            "reference_class": "Comparable revision events.",
                            "base_rate_probability": 0.5,
                            "inside_view_probability": 0.61,
                            "must_be_true": [
                                "The next observation confirms the mechanism."
                            ],
                            "company_thesis_status": "intact",
                            "security_thesis_readiness": "ready",
                            "edge_half_life_days": 14,
                            "dominant_uncertainty": "Persistence of the change.",
                            "action_trigger": "Re-underwrite at the next update.",
                        },
                    },
                }
            ),
            thread_id="thread_role_fixture",
            turn_id="turn_role_fixture",
            total_tokens=200,
            tools=(),
            usage={"total_tokens": 200},
            latency_ms=12,
            completed_at=datetime(2026, 8, 23, 15, 1, tzinfo=UTC),
        )


class EmptyScoutClient:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, spec, _prompt: str, _schema: dict) -> ModelTurn:
        self.calls += 1
        return ModelTurn(
            final_response=json.dumps(
                {
                    "kind": "no_op",
                    "reason": "No bounded Opportunity is supported.",
                    "evidence_ids": [],
                }
            ),
            thread_id=f"thread_{spec.scout.scout_id}",
            turn_id=f"turn_{spec.scout.scout_id}",
            total_tokens=100,
            tools=(),
            usage={"total_tokens": 100},
            latency_ms=4,
            completed_at=datetime(2026, 8, 23, 15, 1, tzinfo=UTC),
        )


class FailingScoutClient:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _spec, _prompt: str, _schema: dict) -> ModelTurn:
        self.calls += 1
        raise RuntimeError("fixture provider unavailable")


def test_structured_role_output_is_durable_and_recovered_without_model_call(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    client = FakeRoleClient()
    runner = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-role-model",
    )
    arguments = {
        "cycle_id": "role-fixture-cycle",
        "run_id": "run_role_fixture",
        "role": "thesis_assessor",
        "prompt": {"mission": "assess"},
        "output_type": PrivateAssessmentPayload,
        "frozen_input": {"opportunity_id": "opportunity_fixture"},
        "evidence_ids": ("evidence_fixture",),
        "known_at": datetime(2026, 8, 23, 15, tzinfo=UTC),
        "prompt_version": "fixture-role-v1",
    }

    first = runner.run(**arguments)
    with database.connect() as connection:
        connection.execute(
            "UPDATE research.run SET cycle_id = NULL WHERE id = 'run_role_fixture'"
        )
    recovered = runner.run(**arguments)

    assert first.value == recovered.value
    assert first.recovered is False and recovered.recovered is True
    assert client.calls == 1
    with database.connect() as connection:
        row = connection.execute(
            """SELECT r.cycle_id, r.status, r.attempt_count, r.actual_usage, a.content
            FROM research.run r JOIN research.run_artifact a ON a.run_id = r.id
            WHERE r.id = 'run_role_fixture'"""
        ).fetchone()
    assert row[0:4] == (
        "role-fixture-cycle",
        "succeeded",
        1,
        {"total_tokens": 200},
    )
    assert row[4]["output"]["forecast_probability"] == 0.61


def test_structured_role_retries_one_invalid_provider_contract(
    live_database: str,
) -> None:
    class InvalidThenValidClient:
        def __init__(self) -> None:
            self.calls = 0
            self.valid = FakeRoleClient()

        def run(self, spec, prompt: str, schema: dict) -> ModelTurn:
            self.calls += 1
            if self.calls == 1:
                return ModelTurn(
                    final_response="{}",
                    thread_id="thread_role_invalid",
                    turn_id="turn_role_invalid",
                    total_tokens=20,
                    tools=(),
                    usage={"total_tokens": 20},
                    latency_ms=2,
                    completed_at=datetime(2026, 8, 23, 15, 1, tzinfo=UTC),
                )
            return self.valid.run(spec, prompt, schema)

    database = Database(live_database)
    database.upgrade()
    client = InvalidThenValidClient()
    runner = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-role-model",
    )

    result = runner.run(
        cycle_id="role-retry-cycle",
        run_id="run_role_retry_fixture",
        role="thesis_assessor",
        prompt={"mission": "retry one invalid provider contract"},
        output_type=PrivateAssessmentPayload,
        frozen_input={"opportunity_id": "opportunity_fixture"},
        evidence_ids=("evidence_fixture",),
        known_at=datetime(2026, 8, 23, 15, tzinfo=UTC),
        prompt_version="fixture-role-v1",
    )

    assert result.value.forecast_probability == 0.61
    assert client.calls == 2
    with database.connect() as connection:
        assert connection.execute(
            """SELECT status, attempt_count FROM research.run
            WHERE id = 'run_role_retry_fixture'"""
        ).fetchone() == ("succeeded", 2)


def test_structured_role_retries_one_transient_deadline(
    live_database: str,
) -> None:
    class DeadlineThenValidClient:
        def __init__(self) -> None:
            self.calls = 0
            self.valid = FakeRoleClient()

        def run(self, spec, prompt: str, schema: dict) -> ModelTurn:
            self.calls += 1
            if self.calls == 1:
                raise ScoutDeadlineExceeded("fixture transient deadline")
            return self.valid.run(spec, prompt, schema)

    database = Database(live_database)
    database.upgrade()
    client = DeadlineThenValidClient()
    runner = StructuredRoleRunner(
        database,
        client,
        model_provider="fixture",
        model_id="fixture-role-model",
    )

    result = runner.run(
        cycle_id="role-deadline-retry-cycle",
        run_id="run_role_deadline_retry_fixture",
        role="thesis_assessor",
        prompt={"mission": "retry one transient provider deadline"},
        output_type=PrivateAssessmentPayload,
        frozen_input={"opportunity_id": "opportunity_fixture"},
        evidence_ids=("evidence_fixture",),
        known_at=datetime(2026, 8, 23, 15, tzinfo=UTC),
        prompt_version="fixture-role-v1",
    )

    assert result.value.forecast_probability == 0.61
    assert client.calls == 2
    with database.connect() as connection:
        assert connection.execute(
            """SELECT status, attempt_count FROM research.run
            WHERE id = 'run_role_deadline_retry_fixture'"""
        ).fetchone() == ("succeeded", 2)


def test_structured_role_bound_fits_the_postgres_audit_constraint(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    runner = StructuredRoleRunner(
        database,
        FakeRoleClient(),
        model_provider="fixture",
        model_id="fixture-role-model",
    )

    runner.run(
        cycle_id="role-context-cycle",
        run_id="run_role_large_context",
        role="thesis_assessor",
        prompt={"mission": "verify the frozen-input database boundary"},
        output_type=PrivateAssessmentPayload,
        frozen_input={"payload": "x" * 7_000},
        evidence_ids=("evidence_fixture",),
        known_at=datetime(2026, 8, 23, 15, tzinfo=UTC),
        prompt_version="fixture-role-v1",
    )

    with database.connect() as connection:
        row = connection.execute(
            """SELECT status, octet_length(frozen_input::text)
            FROM research.run WHERE id = 'run_role_large_context'"""
        ).fetchone()
    assert row[0] == "succeeded"
    assert row[1] <= 8_192


def test_autonomous_cycle_with_no_opportunity_completes_idle_and_replays(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    client = EmptyScoutClient()
    orchestrator = MvpOrchestrator(
        database,
        MvpFixture.default(),
        client,
        source_flow=DatabaseSourceFlow(database, ("SPY",)),
    )
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)

    result = orchestrator.run("cycle_idle_001", wake_at)
    replayed = orchestrator.run("cycle_idle_001", wake_at)

    assert result.status == "MVP_IDLE"
    assert result.top_opportunity_id is None
    assert result.expression_id is None
    assert replayed.replayed is True
    assert replayed.replay_hash == result.replay_hash
    assert client.calls == 4
    assert database.mvp_status("shadow")["status"] == "MVP_IDLE"
    with database.connect() as connection:
        skipped = connection.execute(
            """SELECT count(*) FROM ops.event
            WHERE aggregate_id = 'cycle_idle_001'
              AND event_type = 'mvp.stage.skipped'"""
        ).fetchone()[0]
    assert skipped == 5


def test_all_failed_scout_job_cannot_complete_the_pipeline(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    cycle_id = "cycle_all_scouts_failed"
    client = FailingScoutClient()
    orchestrator = MvpOrchestrator(
        database,
        MvpFixture.default(),
        client,
        source_flow=DatabaseSourceFlow(database, ("SPY",)),
    )

    with pytest.raises(RuntimeError, match="without a usable role outcome"):
        orchestrator.run(cycle_id, datetime(2026, 8, 23, 15, tzinfo=UTC))

    assert client.calls == len(SCOUTS) * 3
    with database.connect() as connection:
        job = connection.execute(
            """SELECT status, attempt_count FROM ops.job
            WHERE subject_id = %s AND kind = 'scout_batch'""",
            (cycle_id,),
        ).fetchone()
        runs = connection.execute(
            """SELECT status, attempt_count FROM research.run
            WHERE cycle_id = %s ORDER BY role""",
            (cycle_id,),
        ).fetchall()
        completed = connection.execute(
            """SELECT count(*) FROM ops.event
            WHERE aggregate_id = %s AND event_type = 'mvp.pipeline.completed'""",
            (cycle_id,),
        ).fetchone()[0]
    assert job == ("failed", 1)
    assert runs == [("failed", 3)] * len(SCOUTS)
    assert completed == 0


def test_partial_scout_snapshot_recovers_at_same_frozen_wake(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    cycle_id = "cycle_partial_scout_recovery"
    wake_at = datetime(2026, 8, 23, 15, tzinfo=UTC)
    source = DatabaseSourceFlow(database, ("SPY",))
    frozen, postures = source.schedule_and_wake(cycle_id, wake_at, {})
    repository = ScoutRepository(database)
    job_id = repository.start_batch(f"batch_{cycle_id}", frozen, postures)
    scout = SCOUTS[0]
    budget = RunBudget(
        max_tool_calls=3,
        max_total_tokens=1_000,
        max_output_bytes=8_192,
    )
    digest = hashlib.sha256(f"batch_{cycle_id}\0{scout.scout_id}".encode()).hexdigest()
    partial_spec = make_run_spec(
        run_id=f"run_{digest[:32]}",
        trace_id=f"trace_{digest[32:]}",
        scout=scout,
        frozen_input=fit_frozen_input_for_scout(frozen, scout, budget),
        budget=budget,
        deadline_at=wake_at + timedelta(seconds=5),
        model_provider="fixture",
        model_id="fixture-model",
    )
    assert repository.start_run(job_id, partial_spec) is True
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO research.raw
            (id, environment, version, known_at, source, source_key,
             content_hash, body)
            VALUES ('raw_late_backfill','shadow',1,%s,'finlight',
                    'late-backfill',%s,%s)""",
            (
                wake_at - timedelta(minutes=1),
                hashlib.sha256(b"late-backfill").hexdigest(),
                Jsonb(
                    {
                        "title": "Late backfill must not change a frozen wake",
                        "source_url": "https://example.invalid/late-backfill",
                    }
                ),
            ),
        )

    class SourceMustNotRun:
        def schedule_and_wake(self, *_args, **_kwargs):
            raise AssertionError("partial recovery re-queried mutable source state")

    client = EmptyScoutClient()
    result = MvpOrchestrator(
        database,
        MvpFixture.default(),
        client,
        source_flow=SourceMustNotRun(),
    ).run(cycle_id, wake_at)

    assert result.status == "MVP_IDLE"
    assert client.calls == len(SCOUTS) - 1
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT role, input_hash, status, error_code
            FROM research.run WHERE cycle_id = %s ORDER BY role""",
            (cycle_id,),
        ).fetchall()
        late_evidence = connection.execute(
            "SELECT count(*) FROM research.evidence WHERE raw_id = 'raw_late_backfill'"
        ).fetchone()[0]
    assert len(rows) == len(SCOUTS)
    recovered = next(row for row in rows if row[0] == scout.scout_id)
    assert recovered == (
        scout.scout_id,
        partial_spec.input_hash,
        "failed",
        "recovery_incomplete",
    )
    assert all(
        row[2:] == ("succeeded", None) for row in rows if row[0] != scout.scout_id
    )
    assert late_evidence == 0


def test_pre_scout_crash_recovers_anchored_wake_without_late_backfill(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    cycle_id = "cycle_pre_scout_anchor_recovery"
    wake_at = datetime(2026, 8, 23, 15, 30, tzinfo=UTC)
    frozen, postures = DatabaseSourceFlow(database, ("SPY",)).schedule_and_wake(
        cycle_id, wake_at, {}
    )
    with database.connect() as connection:
        anchor = connection.execute(
            """SELECT frozen_input, source_postures
            FROM research.scout_batch_snapshot WHERE cycle_id = %s""",
            (cycle_id,),
        ).fetchone()
        connection.execute(
            """INSERT INTO research.raw
            (id, environment, version, known_at, source, source_key,
             content_hash, body)
            VALUES ('raw_pre_scout_late','shadow',1,%s,'finlight',
                    'pre-scout-late',%s,%s)""",
            (
                wake_at - timedelta(minutes=1),
                hashlib.sha256(b"pre-scout-late").hexdigest(),
                Jsonb(
                    {
                        "title": "A late backfill after the durable wake anchor",
                        "source_url": "https://example.invalid/pre-scout-late",
                    }
                ),
            ),
        )
    assert anchor == (frozen.model_dump(mode="json"), postures)

    class SourceMustNotRun:
        def schedule_and_wake(self, *_args, **_kwargs):
            raise AssertionError("anchored recovery re-queried mutable source state")

    client = EmptyScoutClient()
    result = MvpOrchestrator(
        database,
        MvpFixture.default(),
        client,
        source_flow=SourceMustNotRun(),
    ).run(cycle_id, wake_at)

    assert result.status == "MVP_IDLE"
    assert client.calls == len(SCOUTS)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM research.evidence WHERE raw_id = 'raw_pre_scout_late'"
            ).fetchone()[0]
            == 0
        )


class FakeAutonomousRuntime:
    def __init__(self, _database: Database, _settings: Settings, *, fail: bool) -> None:
        self.fail = fail
        self.orchestrator = self

    def run(self, _cycle_id: str, _wake_at: datetime) -> None:
        if self.fail:
            raise RuntimeError("secret-like detail must not reach the event")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class StoppingAutonomousRuntime:
    def __init__(self, stop: threading.Event) -> None:
        self.stop = stop
        self.orchestrator = self
        self.closed = False

    def run(self, _cycle_id: str, _wake_at: datetime) -> None:
        self.stop.set()
        raise RuntimeError("provider interrupted by planned shutdown")

    def close(self) -> None:
        self.closed = True


def test_autonomous_runner_treats_planned_interrupt_as_cancellation(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    settings = Settings(
        DATABASE_URL=live_database,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
    )
    stop = threading.Event()
    states: list[tuple[str, dict]] = []
    runtime = StoppingAutonomousRuntime(stop)
    runner = AutonomousRunner(
        database,
        settings,
        runtime_factory=lambda _db, _config: runtime,
        state_callback=lambda status, detail: states.append((status, detail)),
    )

    assert runner.run(stop, once=True) == 0
    assert runtime.closed is True
    assert states[-1][0] == "stopping"
    assert states[-1][1]["cycle_result"] == "cancelled"
    assert states[-1][1]["consecutive_failures"] == 0
    with database.connect() as connection:
        failures = connection.execute(
            """SELECT count(*) FROM ops.event
            WHERE event_type = 'mvp.pipeline.failed'"""
        ).fetchone()[0]
    assert failures == 0


def test_autonomous_runner_is_single_owner_and_records_redacted_failure(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    settings = Settings(
        DATABASE_URL=live_database,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
    )
    failing = AutonomousRunner(
        database,
        settings,
        runtime_factory=lambda db, config: FakeAutonomousRuntime(db, config, fail=True),
    )

    assert failing.run(threading.Event(), once=True) == 1
    with database.connect() as connection:
        failure = connection.execute(
            """SELECT payload FROM ops.event
            WHERE event_type = 'mvp.pipeline.failed'"""
        ).fetchone()[0]
    assert failure["error_type"] == "RuntimeError"
    assert failure["retry_scheduled"] is False
    assert "secret-like" not in json.dumps(failure)

    owner = psycopg.connect(live_database, autocommit=True)
    owner.execute(
        "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
        ("alta-autonomous-runner",),
    )
    try:
        with pytest.raises(AutonomousOwnerBusy):
            failing.run(threading.Event(), once=True)
    finally:
        owner.execute(
            "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
            ("alta-autonomous-runner",),
        )
        owner.close()


def test_autonomous_cadence_prioritizes_monitoring_then_follow_up() -> None:
    select = AutonomousRunner.select_cycle_interval
    known_at = datetime(2026, 8, 30, 15, tzinfo=UTC)

    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=True,
        unresolved_opportunity=True,
    ) == (300, "open_position")
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=True,
    ) == (900, "opportunity_backlog")
    assert select(
        base_seconds=600,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=False,
    ) == (600, "base_research")
    # A newly formed/refreshed researchable Opportunity did not exist in the
    # last frozen continuity queue, but should receive one prompt follow-up.
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=False,
        new_researchable_opportunity=True,
    ) == (900, "opportunity_backlog")
    # Closed, rejected, and stale Opportunities are filtered before selection;
    # no durable priority work means the base discovery cadence.
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=False,
        known_at=known_at,
    ) == (1_800, "base_research")
    # Deferred-only research must not masquerade as a permanent backlog. Wake
    # exactly for a near due time, but otherwise preserve base discovery.
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=False,
        known_at=known_at,
        next_research_due_at=known_at + timedelta(minutes=5),
    ) == (300, "opportunity_due")
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=False,
        unresolved_opportunity=False,
        known_at=known_at,
        next_research_due_at=known_at + timedelta(hours=6),
    ) == (1_800, "base_research")
    # Monitoring remains the highest priority even when research is due now.
    assert select(
        base_seconds=1_800,
        follow_up_seconds=900,
        position_seconds=300,
        open_position=True,
        unresolved_opportunity=False,
        known_at=known_at,
        next_research_due_at=known_at - timedelta(seconds=1),
        new_researchable_opportunity=True,
    ) == (300, "open_position")


def test_autonomous_cadence_uses_durable_due_queue_and_new_researchable_work(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    known_at = datetime.now(UTC)
    continuity_at = known_at - timedelta(hours=1)
    evidence_id = "evidence_cadence_state"
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO research.run
            (id, environment, version, known_at, role, status, input_hash,
             frozen_input, budget, deadline_at, prompt_version,
             tool_catalog_version, model_provider, model_id, trace_id,
             tool_provenance, evidence_ids, cycle_id)
            VALUES ('run_cadence_state','shadow',1,%s,'change_event_scout',
                    'succeeded',%s,%s,%s,%s,'cadence-test-v1','none',
                    'deterministic','fixture','trace_cadence_state',
                    '[]'::jsonb,'{}'::text[],'live-cadence-state')""",
            (
                continuity_at,
                hashlib.sha256(b"run_cadence_state").hexdigest(),
                Jsonb(
                    {
                        "input": {
                            "opportunity_continuity": {
                                "known_at": continuity_at.isoformat(),
                                "next_research_due_at": (
                                    known_at + timedelta(hours=6)
                                ).isoformat(),
                            },
                            "opportunity_drive": {
                                "research_queue": [
                                    {"opportunity_id": "opportunity_closed"},
                                    {"opportunity_id": "opportunity_stale"},
                                ]
                            },
                        }
                    }
                ),
                Jsonb({"max_tool_calls": 0}),
                known_at + timedelta(minutes=5),
            ),
        )
        connection.execute(
            """INSERT INTO research.raw
            (id, environment, version, known_at, source, source_key,
             content_hash, body)
            VALUES ('raw_cadence_state','shadow',1,%s,'sec_companyfacts',
                    'cadence-state',%s,%s)""",
            (
                continuity_at - timedelta(minutes=2),
                hashlib.sha256(b"raw_cadence_state").hexdigest(),
                Jsonb({"source_url": "https://data.sec.gov/cadence-state"}),
            ),
        )
        connection.execute(
            """INSERT INTO research.evidence
            (id, environment, version, known_at, raw_id, stance, summary)
            VALUES (%s,'shadow',1,%s,'raw_cadence_state','unknown',
                    'Durable non-fixture cadence evidence.')""",
            (evidence_id, continuity_at - timedelta(minutes=1)),
        )

        def add_opportunity(
            target_connection,
            opportunity_id: str,
            status: str,
            opportunity_known_at: datetime,
            horizon_days: int,
        ) -> None:
            candidate_id = "candidate_" + opportunity_id.removeprefix("opportunity_")
            digest = hashlib.sha256(opportunity_id.encode()).hexdigest()
            target_connection.execute(
                """INSERT INTO research.candidate
                (id, environment, version, known_at, run_id, title, why_now,
                 expectation, variant_wedge, falsifier, horizon_days,
                 confidence, evidence_ids)
                VALUES (%s,'shadow',1,%s,'run_cadence_state',%s,
                        'A bounded cadence fixture.','A prior expectation.',
                        'A measurable wedge.','Reject on failed evidence.',
                        %s,0.5,%s)""",
                (
                    candidate_id,
                    opportunity_known_at,
                    opportunity_id,
                    horizon_days,
                    [evidence_id],
                ),
            )
            target_connection.execute(
                """INSERT INTO research.opportunity
                (id, environment, version, known_at, candidate_id, status,
                 title, thesis, falsifier, horizon_days, member_candidate_ids,
                 exact_key, structural_key, snapshot_hash, foundry_state,
                 merge_revision, direction, expectation_posture, investability,
                 evidence_ids, completeness, identity_version)
                VALUES (%s,'shadow',1,%s,%s,%s,%s,'A testable thesis.',
                        'Reject on failed evidence.',%s,%s,%s,%s,%s,'active',1,
                        'positive','available','ready',%s,'complete',2)""",
                (
                    opportunity_id,
                    opportunity_known_at,
                    candidate_id,
                    status,
                    opportunity_id,
                    horizon_days,
                    [candidate_id],
                    digest,
                    hashlib.sha256((opportunity_id + ":s").encode()).hexdigest(),
                    hashlib.sha256((opportunity_id + ":v").encode()).hexdigest(),
                    [evidence_id],
                ),
            )

        add_opportunity(
            connection,
            "opportunity_closed",
            "closed",
            continuity_at - timedelta(hours=1),
            30,
        )
        add_opportunity(
            connection,
            "opportunity_stale",
            "forming",
            continuity_at - timedelta(days=2),
            1,
        )
        add_opportunity(
            connection,
            "opportunity_deferred",
            "forming",
            continuity_at - timedelta(hours=1),
            30,
        )

    runner = AutonomousRunner(
        database,
        Settings(
            DATABASE_URL=live_database,
            REDIS_URL="redis://127.0.0.1:1/0",
            ALTA_ENVIRONMENT="shadow",
        ),
    )

    # A terminal/stale durable queue plus only far-future deferred work stays
    # on base discovery cadence.
    assert runner._next_cycle_interval() == (1_800, "base_research")

    with database.connect() as connection:
        connection.execute(
            """UPDATE research.run SET frozen_input = jsonb_set(
              frozen_input,
              '{input,opportunity_drive,research_queue}',
              '[{"opportunity_id":"opportunity_deferred"}]'::jsonb
            ) WHERE id = 'run_cadence_state'"""
        )
    assert runner._next_cycle_interval() == (900, "opportunity_backlog")

    with database.connect() as connection:
        connection.execute(
            """UPDATE research.run SET frozen_input = jsonb_set(
              frozen_input,
              '{input,opportunity_drive,research_queue}',
              '[]'::jsonb
            ) WHERE id = 'run_cadence_state'"""
        )
    assert runner._next_cycle_interval() == (1_800, "base_research")

    with database.connect() as connection:
        add_opportunity(
            connection,
            "opportunity_new",
            "forming",
            known_at - timedelta(minutes=30),
            30,
        )

    assert runner._next_cycle_interval() == (900, "opportunity_backlog")
    with database.connect() as connection:
        connection.execute(
            """UPDATE research.opportunity SET status = 'rejected'
            WHERE id = 'opportunity_new'"""
        )
    assert runner._next_cycle_interval() == (1_800, "base_research")


class VirtualClock:
    def __init__(self) -> None:
        self.current = 0.0

    def monotonic(self) -> float:
        return self.current

    def wait(self, stop: threading.Event, seconds: float) -> bool:
        self.current += seconds
        return stop.is_set()


class RecoveringAutonomousRuntime:
    def __init__(
        self,
        *,
        fail: bool,
        stop_after_success: threading.Event,
        cycle_ids: list[str],
        closed: list[bool],
    ) -> None:
        self.fail = fail
        self.stop_after_success = stop_after_success
        self.cycle_ids = cycle_ids
        self.closed = closed
        self.orchestrator = self

    def run(self, cycle_id: str, _wake_at: datetime) -> SimpleNamespace:
        self.cycle_ids.append(cycle_id)
        if self.fail:
            raise RuntimeError("provider outage detail must remain redacted")
        self.stop_after_success.set()
        return SimpleNamespace(status="MVP_IDLE")

    def close(self) -> None:
        self.closed.append(True)


class SnapshotConflictThenSuccessRuntime:
    def __init__(
        self,
        database: Database,
        stop: threading.Event,
        cycle_ids: list[str],
    ) -> None:
        self.database = database
        self.stop = stop
        self.cycle_ids = cycle_ids
        self.orchestrator = self

    def run(self, cycle_id: str, wake_at: datetime) -> SimpleNamespace:
        self.cycle_ids.append(cycle_id)
        if len(self.cycle_ids) == 1:
            with self.database.connect() as connection:
                connection.execute(
                    """INSERT INTO ops.job
                    (id, environment, version, known_at, kind, status, subject_id)
                    VALUES ('job_snapshot_conflict','shadow',1,%s,
                            'scout_batch','running',%s)""",
                    (wake_at, cycle_id),
                )
            raise FrozenCycleSnapshotError("durable Scout input hash changed")
        self.stop.set()
        return SimpleNamespace(status="MVP_IDLE")


def test_autonomous_runner_quarantines_snapshot_conflict_before_new_cycle(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    settings = Settings(
        DATABASE_URL=live_database,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS=1,
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS=1,
    )
    stop = threading.Event()
    clock = VirtualClock()
    cycle_ids: list[str] = []
    states: list[tuple[str, dict]] = []

    runner = AutonomousRunner(
        database,
        settings,
        runtime_factory=lambda db, _settings: SnapshotConflictThenSuccessRuntime(
            db, stop, cycle_ids
        ),
        state_callback=lambda status, detail: states.append((status, detail)),
        monotonic=clock.monotonic,
        waiter=clock.wait,
    )

    assert runner.run(stop) == 0
    assert len(cycle_ids) == 2
    assert cycle_ids[0] != cycle_ids[1]
    degraded = next(detail for status, detail in states if status == "degraded")
    assert degraded["cycle_result"] == "quarantined"
    assert degraded["replacement_cycle_scheduled"] is True
    with database.connect() as connection:
        job_status = connection.execute(
            "SELECT status FROM ops.job WHERE id = 'job_snapshot_conflict'"
        ).fetchone()[0]
        failure = connection.execute(
            """SELECT payload FROM ops.event
            WHERE event_type = 'mvp.pipeline.failed' ORDER BY sequence"""
        ).fetchone()[0]
    assert job_status == "failed"
    assert failure["retry_scheduled"] is False


def test_autonomous_runner_recovers_after_more_than_three_failures(
    live_database: str,
) -> None:
    database = Database(live_database)
    database.upgrade()
    settings = Settings(
        DATABASE_URL=live_database,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
        ALTA_AUTONOMOUS_INTERVAL_SECONDS=60,
        ALTA_AUTONOMOUS_HEARTBEAT_SECONDS=5,
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS=1,
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS=4,
        ALTA_AUTONOMOUS_CYCLE_TIMEOUT_SECONDS=300,
        ALTA_AGENT_DEADLINE_SECONDS=30,
        ALTA_REASONING_AGENT_DEADLINE_SECONDS=30,
    )
    stop = threading.Event()
    clock = VirtualClock()
    cycle_ids: list[str] = []
    closed: list[bool] = []
    states: list[tuple[str, dict]] = []
    attempts = iter((True, True, True, True, False))

    def runtime_factory(_database: Database, _settings: Settings):
        return RecoveringAutonomousRuntime(
            fail=next(attempts),
            stop_after_success=stop,
            cycle_ids=cycle_ids,
            closed=closed,
        )

    runner = AutonomousRunner(
        database,
        settings,
        runtime_factory=runtime_factory,
        state_callback=lambda status, detail: states.append((status, detail)),
        monotonic=clock.monotonic,
        waiter=clock.wait,
    )

    assert runner.run(stop) == 0
    assert len(cycle_ids) == 5
    assert len(set(cycle_ids)) == 1
    assert len(closed) == 5
    assert [status for status, _detail in states].count("degraded") >= 4
    assert states[-1][0] == "stopping"
    assert states[-1][1]["cycle_result"] == "MVP_IDLE"
    with database.connect() as connection:
        failures = connection.execute(
            """SELECT payload FROM ops.event
            WHERE event_type = 'mvp.pipeline.failed'
            ORDER BY sequence"""
        ).fetchall()
    assert [row[0]["consecutive_failures"] for row in failures] == [1, 2, 3, 4]
    assert all(row[0]["retry_scheduled"] is True for row in failures)
    assert "provider outage" not in json.dumps(failures)
