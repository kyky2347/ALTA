import json
import hashlib
import os
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from alta_asterism.cycle_recovery import FrozenCycleSnapshotError
from alta_asterism.contracts import Environment
from alta_asterism.database import Database
from alta_asterism.live_source_flow import DatabaseSourceFlow
from alta_asterism.mind_worker import (
    MindClient,
    ModelTurn,
    SdkAppServerMindClient,
)
from alta_asterism.mind_pool import MindClientPool
from alta_asterism.scout_batch import MindWorker
from alta_asterism.scout_repository import ScoutRepository
from alta_asterism.scouts import (
    SCOUTS,
    EvidenceSnapshot,
    FrozenScoutInput,
    RunBudget,
    ToolProvenance,
    build_prompt,
    fit_frozen_input_for_scout,
    make_run_spec,
    output_schema,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "app_server"
REPO_ROOT = Path(__file__).parents[4]


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_b3_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b3_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b3_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def seed_frozen_input(database: Database) -> FrozenScoutInput:
    known_at = datetime(2026, 8, 23, 14, tzinfo=UTC)
    fixtures = (
        ("change", "finlight", "finlight_event", "a" * 64),
        ("market", "massive", "massive_bar", "b" * 64),
        ("policy", "official", "official_policy", "c" * 64),
        ("expectation", "primitive", "expectation_primitive", "d" * 64),
    )
    snapshots = []
    with database.connect() as connection:
        for name, source, territory, content_hash in fixtures:
            raw_id = f"raw_{name}"
            evidence_id = f"evidence_{name}"
            summary = f"Synthetic {name} evidence fixture."
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body) VALUES (%s,'replay',1,%s,%s,%s,%s,%s)""",
                (
                    raw_id,
                    known_at - timedelta(minutes=2),
                    source,
                    f"fixture-{name}",
                    content_hash,
                    Jsonb({"fixture": True, "name": name}),
                ),
            )
            connection.execute(
                """INSERT INTO research.evidence
                (id, environment, version, known_at, raw_id, stance, summary)
                VALUES (%s,'replay',1,%s,%s,'support',%s)""",
                (
                    evidence_id,
                    known_at - timedelta(minutes=1),
                    raw_id,
                    summary,
                ),
            )
            snapshots.append(
                EvidenceSnapshot(
                    evidence_id=evidence_id,
                    raw_id=raw_id,
                    source=source,
                    territory=territory,
                    source_locator=f"https://fixture.invalid/{name}",
                    known_at=known_at - timedelta(minutes=1),
                    content_hash=content_hash,
                    summary=summary,
                )
            )
    return FrozenScoutInput(
        wake_id="wake_b3_fixture",
        environment="replay",
        known_at=known_at,
        universe=("DEMO",),
        evidence=tuple(snapshots),
        expectation_posture="unavailable",
    )


def fake_command(
    tmp_path: Path,
    responses: Path | None = None,
    *extra: str,
) -> tuple[tuple[str, ...], Path]:
    log = tmp_path / f"fake-app-server-{uuid4().hex}.jsonl"
    command = (
        sys.executable,
        str(FIXTURES / "fake_app_server.py"),
        "--responses",
        str(responses or FIXTURES / "scout_outputs.json"),
        "--log",
        str(log),
        *extra,
    )
    return command, log


def worker(
    database: Database,
    client: MindClient,
    deadline_seconds: float = 2,
    max_tool_calls: int = 2,
    max_concurrency: int = 1,
    require_active_research: bool = False,
) -> MindWorker:
    return MindWorker(
        repository=ScoutRepository(database),
        client=client,
        model_provider="fixture",
        model_id="fixture-model",
        budget=RunBudget(
            max_tool_calls=max_tool_calls,
            max_total_tokens=1_000,
            max_output_bytes=8_192,
            require_active_research=require_active_research,
        ),
        deadline_seconds=deadline_seconds,
        max_concurrency=max_concurrency,
    )


def client_for(tmp_path: Path, command: tuple[str, ...]) -> SdkAppServerMindClient:
    workspace = tmp_path / "agent-workspace"
    workspace.mkdir(exist_ok=True)
    return SdkAppServerMindClient(
        repo_root=REPO_ROOT,
        provider="fixture",
        model_id="fixture-model",
        agent_cwd=workspace,
        launch_command=command,
        interrupt_grace_seconds=0.5,
    )


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class ParallelNoOpClient:
    def __init__(
        self,
        barrier: threading.Barrier,
        state: dict[str, int],
        state_lock: threading.Lock,
    ) -> None:
        self.barrier = barrier
        self.state = state
        self.state_lock = state_lock
        self.closed = False

    def run(self, spec, _prompt: str, _schema: dict) -> ModelTurn:
        with self.state_lock:
            self.state["active"] += 1
            self.state["max_active"] = max(
                self.state["max_active"], self.state["active"]
            )
        try:
            self.barrier.wait(timeout=1)
            return ModelTurn(
                final_response=json.dumps(
                    {
                        "kind": "no_op",
                        "reason": "Parallel fixture found no supportable candidate.",
                        "evidence_ids": [],
                    }
                ),
                thread_id=f"thread_{spec.scout.scout_id}",
                turn_id=f"turn_{spec.scout.scout_id}",
                total_tokens=100,
                tools=(),
                usage={"total_tokens": 100},
                latency_ms=1,
                completed_at=spec.frozen_input.known_at,
            )
        finally:
            with self.state_lock:
                self.state["active"] -= 1

    def close(self) -> None:
        self.closed = True


class InvalidThenValidClient:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.deadlines: dict[str, list[datetime]] = {}
        self.prompts: dict[str, list[dict[str, object]]] = {}

    def run(self, spec, prompt: str, _schema: dict) -> ModelTurn:
        count = self.calls.get(spec.scout.scout_id, 0) + 1
        self.calls[spec.scout.scout_id] = count
        self.deadlines.setdefault(spec.scout.scout_id, []).append(spec.deadline_at)
        self.prompts.setdefault(spec.scout.scout_id, []).append(json.loads(prompt))
        response = (
            {"kind": "candidate", "title": "Incomplete"}
            if spec.scout.scout_id == "market_dislocation_scout" and count == 1
            else {
                "kind": "no_op",
                "reason": "The bounded fixture does not support a Candidate.",
                "evidence_ids": [],
            }
        )
        return ModelTurn(
            final_response=json.dumps(response),
            thread_id=f"thread_{spec.scout.scout_id}_{count}",
            turn_id=f"turn_{spec.scout.scout_id}_{count}",
            total_tokens=100,
            tools=(),
            usage={"total_tokens": 100},
            latency_ms=1,
            completed_at=spec.frozen_input.known_at,
        )


def test_oversized_failure_diagnostics_do_not_rollback_terminal_status(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen = seed_frozen_input(database)
    repository = ScoutRepository(database)
    job_id = repository.start_batch(
        "batch_large_failure", frozen, {"fixture": "healthy"}
    )
    spec = make_run_spec(
        run_id="run_large_failure",
        trace_id="trace_large_failure",
        scout=SCOUTS[0],
        frozen_input=frozen.for_territories(SCOUTS[0].primary_sources),
        budget=RunBudget(
            max_tool_calls=11, max_total_tokens=98_000, max_output_bytes=8192
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=30),
        model_provider="fixture",
        model_id="fixture-model",
    )
    assert repository.start_run(job_id, spec)
    tools = tuple(
        ToolProvenance(
            tool_call_id=f"call_{index}",
            tool_name="alta_web_fetch",
            status="completed",
            arguments_hash="a" * 64,
            source_locators=("https://example.org/" + str(index) + "x" * 900,),
        )
        for index in range(11)
    )
    turn = ModelTurn(
        final_response='\\"線索' * 2000,
        thread_id="thread_large",
        turn_id="turn_large",
        total_tokens=100,
        tools=tools,
        usage={"total_tokens": 100},
    )
    repository.fail(spec.run_id, "invalid_output", turn, ValueError("invalid output"))
    with database.connect() as connection:
        row = connection.execute(
            """SELECT r.status, r.tool_provenance, a.content,
            octet_length(a.content::text) FROM research.run r
            JOIN research.run_artifact a ON a.run_id=r.id WHERE r.id=%s""",
            (spec.run_id,),
        ).fetchone()
    assert row[0] == "failed"
    assert len(row[1]) == 11
    assert row[2]["tool_provenance"] == row[1]
    assert row[2]["diagnostics_truncated"] is True
    assert row[3] <= 16_384
    database.close()


def test_planned_shutdown_cancels_only_running_cycle_work(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    repository = ScoutRepository(database)
    job_id = repository.start_batch(
        "batch_planned_shutdown", frozen_input, {"fixture": "healthy"}
    )
    spec = make_run_spec(
        run_id="run_planned_shutdown",
        trace_id="trace_planned_shutdown",
        scout=SCOUTS[0],
        frozen_input=frozen_input.for_territories(SCOUTS[0].primary_sources),
        budget=RunBudget(
            max_tool_calls=2,
            max_total_tokens=1_000,
            max_output_bytes=8_192,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=30),
        model_provider="fixture",
        model_id="fixture-model",
    )

    assert repository.start_run(job_id, spec) is True
    assert repository.cancel_cycle(
        frozen_input.wake_id,
        environment="replay",
    ) == (1, 1)

    # A provider thread may finish unwinding after the signal handler has
    # committed cancellation.  That late failure must not overwrite the
    # operator intent or create a misleading failure artifact.
    repository.fail(
        spec.run_id,
        "app_server_error",
        error=RuntimeError("late provider shutdown"),
    )
    repository.finish_batch(job_id, failed=True)

    with database.connect() as connection:
        run = connection.execute(
            "SELECT status, error_code FROM research.run WHERE id = %s",
            (spec.run_id,),
        ).fetchone()
        job_status = connection.execute(
            "SELECT status FROM ops.job WHERE id = %s",
            (job_id,),
        ).fetchone()[0]
        failures = connection.execute(
            """SELECT count(*) FROM research.run_artifact
            WHERE run_id = %s AND artifact_kind = 'failure'""",
            (spec.run_id,),
        ).fetchone()[0]

    assert run == ("cancelled", "operator_shutdown")
    assert job_status == "cancelled"
    assert failures == 0


def test_recovered_snapshot_set_rolls_back_missing_roles_on_hash_mismatch(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    repository = ScoutRepository(database)
    job_id = repository.start_batch(
        "batch_atomic_recovery", frozen_input, {"fixture": "healthy"}
    )
    budget = RunBudget(
        max_tool_calls=2,
        max_total_tokens=1_000,
        max_output_bytes=8_192,
    )
    deadline = datetime.now(UTC) + timedelta(seconds=30)

    def spec_for(scout, source: FrozenScoutInput):
        return make_run_spec(
            run_id=f"run_atomic_recovery_{scout.scout_id}",
            trace_id=f"trace_atomic_recovery_{scout.scout_id}",
            scout=scout,
            frozen_input=fit_frozen_input_for_scout(source, scout, budget),
            budget=budget,
            deadline_at=deadline,
            model_provider="fixture",
            model_id="fixture-model",
        )

    expected = tuple(spec_for(scout, frozen_input) for scout in SCOUTS)
    changed = frozen_input.model_copy(update={"universe": ("CHANGED",)})
    conflicting = spec_for(SCOUTS[-1], changed)
    assert repository.start_run(job_id, conflicting) is True

    with pytest.raises(FrozenCycleSnapshotError):
        repository.start_runs(job_id, expected)

    with database.connect() as connection:
        rows = connection.execute(
            """SELECT id, input_hash FROM research.run
            WHERE job_id = %s ORDER BY id""",
            (job_id,),
        ).fetchall()
    assert rows == [(conflicting.run_id, conflicting.input_hash)]


def test_failed_scout_job_reopens_same_cycle_with_audited_attempt(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    repository = ScoutRepository(database)
    batch_id = "batch_failed_job_recovery"
    postures = {"direct_batch": "healthy"}
    job_id = repository.start_batch(batch_id, frozen_input, postures)
    budget = RunBudget(
        max_tool_calls=2,
        max_total_tokens=1_000,
        max_output_bytes=8_192,
    )
    deadline = datetime.now(UTC) + timedelta(seconds=30)
    specs = tuple(
        make_run_spec(
            run_id=(
                "run_"
                + hashlib.sha256(f"{batch_id}\0{scout.scout_id}".encode()).hexdigest()[
                    :32
                ]
            ),
            trace_id=(
                "trace_"
                + hashlib.sha256(f"{batch_id}\0{scout.scout_id}".encode()).hexdigest()[
                    32:
                ]
            ),
            scout=scout,
            frozen_input=fit_frozen_input_for_scout(frozen_input, scout, budget),
            budget=budget,
            deadline_at=deadline,
            model_provider="fixture",
            model_id="fixture-model",
        )
        for scout in SCOUTS
    )
    assert repository.start_runs(job_id, specs) == (True,) * len(SCOUTS)
    for spec in specs:
        repository.fail(
            spec.run_id,
            "interrupted_fixture",
            error=RuntimeError("simulated process interruption"),
        )
    repository.finish_batch(job_id, failed=True)

    outcomes = worker(database, InvalidThenValidClient()).run_batch(
        batch_id, frozen_input
    )

    assert all(item.status == "succeeded" for item in outcomes)
    with database.connect() as connection:
        job = connection.execute(
            """SELECT status, version, attempt_count FROM ops.job
            WHERE id = %s""",
            (job_id,),
        ).fetchone()
        runs = connection.execute(
            """SELECT status, attempt_count FROM research.run
            WHERE job_id = %s ORDER BY role""",
            (job_id,),
        ).fetchall()
        events = connection.execute(
            """SELECT event_type, payload FROM ops.event
            WHERE aggregate_id = %s AND event_type LIKE 'scout.batch.%%'
            ORDER BY sequence""",
            (job_id,),
        ).fetchall()
    assert job == ("succeeded", 2, 2)
    assert all(status == "succeeded" and attempts >= 2 for status, attempts in runs)
    assert [
        (event_type, payload["attempt_count"]) for event_type, payload in events
    ] == [
        ("scout.batch.finished", 1),
        ("scout.batch.reopened", 2),
        ("scout.batch.finished", 2),
    ]
    assert [payload.get("status") for _event_type, payload in events] == [
        "failed",
        None,
        "succeeded",
    ]


def test_sdk_repairs_a_contract_in_the_same_thread_with_shared_budget(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen = seed_frozen_input(database)
    command, log = fake_command(tmp_path, None, "--invalid-first-finalization")
    spec = make_run_spec(
        run_id="run_finalization_repair",
        trace_id="trace_finalization_repair",
        scout=SCOUTS[0],
        frozen_input=frozen.for_territories(SCOUTS[0].primary_sources),
        budget=RunBudget(
            max_tool_calls=2,
            max_total_tokens=40_000,
            max_output_bytes=8_192,
            require_active_research=True,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=60),
        model_provider="fixture",
        model_id="fixture-model",
    )
    with client_for(tmp_path, command) as client:
        turn = client.run(spec, build_prompt(spec), output_schema(spec))
    starts = [row for row in read_log(log) if row["method"] == "turn/start"]
    assert len(starts) == 2
    assert starts[0]["params"]["threadId"] == starts[1]["params"]["threadId"]
    assert turn.total_tokens == 320
    assert (
        turn.finalization_audit["feedback"]["issues"][0]["code"]
        == "explore_lineage_must_be_empty"
    )
    assert len(turn.finalization_audit["draft_sha256"]) == 64
    assert "unassigned-parent" not in str(turn.finalization_audit)
    assert json.loads(turn.final_response).get("parent_opportunity_id") is None


def test_sdk_requests_one_no_tool_finalization_after_empty_provider_response(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    command, log = fake_command(tmp_path, None, "--empty-first-turn")
    spec = make_run_spec(
        run_id="run_empty_provider_recovery",
        trace_id="trace_empty_provider_recovery",
        scout=SCOUTS[0],
        frozen_input=frozen_input.for_territories(SCOUTS[0].primary_sources),
        budget=RunBudget(
            max_tool_calls=2,
            max_total_tokens=1_000,
            max_output_bytes=8_192,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=2),
        model_provider="fixture",
        model_id="fixture-model",
    )
    with client_for(tmp_path, command) as client:
        turn = client.run(spec, build_prompt(spec), output_schema())

    assert json.loads(turn.final_response)["kind"] == "candidate"
    assert turn.total_tokens == 320
    turns = [item for item in read_log(log) if item["method"] == "turn/start"]
    assert len(turns) == 2
    recovery = json.loads(turns[1]["params"]["input"][0]["text"])
    assert recovery == {
        "scout_id": SCOUTS[0].scout_id,
        "instruction": (
            "Return the final structured object now using only the evidence already "
            "gathered. Do not call another tool. If the evidence is insufficient, "
            "return a no_op object."
        ),
    }


def test_mind_pool_runs_four_scouts_concurrently_and_keeps_stable_order(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    barrier = threading.Barrier(len(SCOUTS))
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()
    clients = tuple(ParallelNoOpClient(barrier, state, state_lock) for _ in SCOUTS)

    with MindClientPool(clients) as client:
        outcomes = worker(database, client, max_concurrency=len(SCOUTS)).run_batch(
            "batch_parallel", frozen_input
        )

    assert state["max_active"] == len(SCOUTS)
    assert [(item.scout_id, item.status) for item in outcomes] == [
        (scout.scout_id, "succeeded") for scout in SCOUTS
    ]
    assert all(client.closed for client in clients)


def test_live_policy_fails_closed_when_trader_minds_skip_active_research(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    barrier = threading.Barrier(len(SCOUTS))
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()
    clients = tuple(ParallelNoOpClient(barrier, state, state_lock) for _ in SCOUTS)

    with MindClientPool(clients) as client:
        outcomes = worker(
            database,
            client,
            max_concurrency=len(SCOUTS),
            require_active_research=True,
        ).run_batch("batch_active_research_required", frozen_input)

    assert all(item.status == "failed" for item in outcomes)
    assert all(item.error_code == "active_research_required" for item in outcomes)


def test_fake_app_server_runs_four_scouts_with_sdk_and_persists_provenance(
    empty_b3_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    command, log = fake_command(tmp_path)
    for key in (
        "MASSIVE_API_KEY",
        "FINLIGHT_API_KEY",
        "TIGER_PRIVATE_KEY",
        "OPENAI_API_KEY",
        "HOST_UNRELATED_SECRET",
    ):
        monkeypatch.setenv(key, "REDACTION_CANARY")
    monkeypatch.setenv("ALTA_GATEWAY_TOKEN", "fixture-local-token")

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client, require_active_research=True).run_batch(
            "batch_fixture", frozen_input
        )

    assert [(item.scout_id, item.status, item.output.kind) for item in outcomes] == [
        ("change_event_scout", "succeeded", "candidate"),
        ("market_dislocation_scout", "succeeded", "candidate"),
        ("causal_policy_scout", "succeeded", "candidate"),
        ("expectation_gap_scout", "succeeded", "no_op"),
    ]
    with database.connect() as connection:
        counts = connection.execute(
            """SELECT
            (SELECT count(*) FROM ops.job),
            (SELECT count(*) FROM research.run),
            (SELECT count(*) FROM research.candidate),
            (SELECT count(*) FROM research.rank),
            (SELECT count(*) FROM research.expression)"""
        ).fetchone()
        runs = connection.execute(
            """SELECT role, input_hash, frozen_input, budget, deadline_at,
            prompt_version, tool_catalog_version, model_provider, model_id,
            trace_id, tool_provenance, evidence_ids, output_kind, thread_id,
            turn_id FROM research.run ORDER BY role"""
        ).fetchall()
        artifacts = connection.execute(
            """SELECT r.role, a.content, a.content_hash, r.actual_usage,
            r.latency_ms, r.attempt_count
            FROM research.run r JOIN research.run_artifact a ON a.run_id = r.id
            WHERE a.artifact_kind = 'scout_output' ORDER BY r.role"""
        ).fetchall()
        minds = connection.execute(
            """SELECT scout_id, turn_count, context_tokens, thread_id,
            rolling_summary FROM research.mind_state ORDER BY scout_id"""
        ).fetchall()
    assert counts == (1, 4, 3, 0, 0)
    assert all(len(row[1]) == 64 and row[4].tzinfo is not None for row in runs)
    assert all(
        row[5:9]
        == (
            "alpha-trader-v30",
            "alta-active-research-v11",
            "fixture",
            "fixture-model",
        )
        for row in runs
    )
    assert all(row[9].startswith("trace_") and row[13] and row[14] for row in runs)
    assert all(len(row[2]["input"]["evidence"]) <= 1 for row in runs)
    change = next(row for row in runs if row[0] == "change_event_scout")
    serialized_provenance = json.dumps(change[10])
    assert "REDACTION_CANARY" not in serialized_provenance
    assert "?" not in serialized_provenance
    assert "https://fixture.invalid/event" in serialized_provenance
    assert change[11] == ["evidence_change"]
    assert change[12] == "candidate"
    assert len(artifacts) == len(minds) == 4
    assert all(len(row[2]) == 64 for row in artifacts)
    assert all(row[3]["total_tokens"] == 160 for row in artifacts)
    assert all(row[4] >= 0 and row[5] == 1 for row in artifacts)
    assert all(row[1]["output"]["kind"] in {"candidate", "no_op"} for row in artifacts)
    assert all(row[1:3] == (1, 160) and row[3] for row in minds)
    mind_memories = {row[0]: json.loads(row[4]) for row in minds}
    assert mind_memories["change_event_scout"]["recent"][-1]["tools"] == [
        "alta_news_search"
    ]
    assert mind_memories["market_dislocation_scout"]["recent"][-1]["tools"] == [
        "alta_finance_data"
    ]
    assert all(item["recent"][-1]["sources"] == 1 for item in mind_memories.values())
    assert all(
        item["schema"] == "alta.trader-mind-memory.v3"
        for item in mind_memories.values()
    )
    no_op = next(row for row in artifacts if row[0] == "expectation_gap_scout")
    assert no_op[1]["output"]["reason"] == (
        "The frozen expectation posture is unavailable, so no gap is asserted."
    )

    requests = read_log(log)
    assert [item["method"] for item in requests].count("initialize") == 1
    thread_starts = [item for item in requests if item["method"] == "thread/start"]
    assert len(thread_starts) == 4
    turns = [item for item in requests if item["method"] == "turn/start"]
    assert len(turns) == 4
    territories = []
    for thread_start, turn in zip(thread_starts, turns, strict=True):
        params = turn["params"]
        prompt = json.loads(params["input"][0]["text"])
        territories.extend(prompt["search_territories"])
        assert params["approvalPolicy"] == "never"
        assert params["sandboxPolicy"] == {
            "type": "readOnly",
            "networkAccess": False,
        }
        config = thread_start["params"]["config"]
        assert (
            config["mcp_servers.alta_internet.enabled_tools"] == prompt["allowed_tools"]
        )
        assert config["mcp_servers.alta_internet.enabled"] is True
        attempt_id = config["mcp_servers.alta_internet.http_headers.X-ALTA-Attempt-ID"]
        assert len(attempt_id) == 64 and all(
            c in "0123456789abcdef" for c in attempt_id
        )
        assert config[
            "mcp_servers.alta_internet.http_headers.X-ALTA-Run-ID"
        ].startswith("run_")
        assert config["web_search"] == "disabled"
        assert config["project_doc_max_bytes"] == 0
        assert all(
            config[key] is False
            for key in (
                "features.apply_patch_freeform",
                "features.apps",
                "features.multi_agent",
                "features.plugins",
                "features.shell_tool",
                "features.standalone_web_search",
                "features.unified_exec",
                "features.web_search",
                "features.web_search_request",
                "orchestrator.skills.enabled",
            )
        )
        schema = params["outputSchema"]
        assert schema["type"] == "object"
        assert schema["required"] == list(schema["properties"])
        assert "anyOf" not in json.dumps(schema)
        assert len(prompt["frozen_input"]["evidence"]) <= 1
    assert len(territories) == len(set(territories)) == 4
    forbidden = {
        "DATABASE_URL",
        "REDIS_URL",
        "MASSIVE_API_KEY",
        "FINLIGHT_API_KEY",
        "TIGER_PRIVATE_KEY",
        "OPENAI_API_KEY",
        "HOST_UNRELATED_SECRET",
    }
    assert all(forbidden.isdisjoint(item["envKeys"]) for item in requests)


def test_invalid_structured_output_fails_one_scout_without_candidate_insert(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    responses = json.loads((FIXTURES / "scout_outputs.json").read_text())
    responses["market_dislocation_scout"]["output"] = {
        "kind": "candidate",
        "title": "Missing required fields",
    }
    response_file = tmp_path / "invalid-responses.json"
    response_file.write_text(json.dumps(responses))
    command, _ = fake_command(tmp_path, response_file)

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client).run_batch("batch_invalid", frozen_input)

    assert [(item.scout_id, item.status, item.error_code) for item in outcomes] == [
        ("change_event_scout", "succeeded", None),
        ("market_dislocation_scout", "failed", "invalid_output"),
        ("causal_policy_scout", "succeeded", None),
        ("expectation_gap_scout", "succeeded", None),
    ]
    with database.connect() as connection:
        assert (
            connection.execute("SELECT count(*) FROM research.candidate").fetchone()[0]
            == 2
        )
        failed_run = connection.execute(
            """SELECT status, error_code, thread_id, turn_id
            FROM research.run WHERE role = 'market_dislocation_scout'"""
        ).fetchone()
        failure_artifacts = connection.execute(
            """SELECT a.content FROM research.run_artifact a
            JOIN research.run r ON r.id = a.run_id
            WHERE r.role = 'market_dislocation_scout'
              AND a.artifact_kind = 'failure' ORDER BY a.version"""
        ).fetchall()
    assert failed_run == (
        "failed",
        "invalid_output",
        "thread_4",
        "turn_4",
    )
    assert len(failure_artifacts) == 3
    assert all(item[0]["error_type"] == "ValidationError" for item in failure_artifacts)
    assert all(len(item[0]["error_fingerprint"]) == 64 for item in failure_artifacts)
    assert all(
        "Missing required fields" in item[0]["bounded_final_response"]
        for item in failure_artifacts
    )
    with database.connect() as connection:
        assert connection.execute(
            """SELECT attempt_count FROM research.run
            WHERE role = 'market_dislocation_scout'"""
        ).fetchone() == (3,)
        assert connection.execute(
            """SELECT array_agg(a.version ORDER BY a.version)
            FROM research.run_artifact a JOIN research.run r ON r.id = a.run_id
            WHERE r.role = 'market_dislocation_scout'
              AND a.artifact_kind = 'failure'"""
        ).fetchone() == ([1, 2, 3],)


def test_invalid_structured_output_gets_one_bounded_fresh_retry(
    empty_b3_database: str,
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    client = InvalidThenValidClient()

    outcomes = worker(database, client).run_batch("batch_invalid_retry", frozen_input)

    assert all(item.status == "succeeded" for item in outcomes)
    assert client.calls["market_dislocation_scout"] == 2
    assert all(
        count == 1
        for scout_id, count in client.calls.items()
        if scout_id != "market_dislocation_scout"
    )
    market_deadlines = client.deadlines["market_dislocation_scout"]
    assert len(market_deadlines) == 2
    assert market_deadlines[1] > market_deadlines[0]
    retry_feedback = client.prompts["market_dislocation_scout"][1]["retry_feedback"]
    assert retry_feedback["category"] == "schema_validation"
    assert retry_feedback["previous_error_code"] == "invalid_output"
    assert retry_feedback["issues"]
    with database.connect() as connection:
        assert connection.execute(
            """SELECT attempt_count FROM research.run
            WHERE role = 'market_dislocation_scout'"""
        ).fetchone() == (2,)
        assert connection.execute(
            """SELECT count(*) FROM research.run_artifact a
            JOIN research.run r ON r.id = a.run_id
            WHERE r.role = 'market_dislocation_scout'
              AND a.artifact_kind = 'failure'"""
        ).fetchone() == (1,)
        failure = connection.execute(
            """SELECT content->'retry_feedback' FROM research.run_artifact a
            JOIN research.run r ON r.id = a.run_id
            WHERE r.role = 'market_dislocation_scout'
              AND a.artifact_kind = 'failure'"""
        ).fetchone()[0]
        assert failure["category"] == "schema_validation"
        assert failure["issues"]


def test_tool_discovery_is_promoted_to_append_only_evidence_before_candidate(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    responses = json.loads((FIXTURES / "scout_outputs.json").read_text())
    output = responses["change_event_scout"]["output"]
    output["evidence_ids"] = []
    output["tool_evidence_refs"] = [
        {
            "tool_call_id": None,
            "source_locator": "https://fixture.invalid/event",
        }
    ]
    response_file = tmp_path / "tool-evidence-responses.json"
    response_file.write_text(json.dumps(responses))
    command, _ = fake_command(tmp_path, response_file)

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client).run_batch(
            "batch_tool_evidence", frozen_input
        )

    assert outcomes[0].status == "succeeded"
    assert outcomes[0].output is not None
    assert len(outcomes[0].output.evidence_ids) == 1
    assert outcomes[0].output.tool_evidence_refs[0].tool_call_id == "tool_change_1"
    assert (
        outcomes[0].output.tool_evidence_refs[0].source_locator
        == "https://fixture.invalid/event"
    )
    with database.connect() as connection:
        row = connection.execute(
            """SELECT c.evidence_ids, r.source, r.body, e.known_at, c.known_at,
            e.summary
            FROM research.candidate c
            JOIN research.evidence e ON e.id = c.evidence_ids[1]
            JOIN research.raw r ON r.id = e.raw_id
            WHERE c.run_id = (SELECT id FROM research.run
                              WHERE role = 'change_event_scout')"""
        ).fetchone()
        artifact = connection.execute(
            """SELECT a.content FROM research.run_artifact a
            JOIN research.run r ON r.id = a.run_id
            WHERE r.role = 'change_event_scout'
              AND a.artifact_kind = 'scout_output'"""
        ).fetchone()[0]
    assert row[0] == list(outcomes[0].output.evidence_ids)
    assert row[1] == "agent_tool:alta_news_search"
    assert row[2]["source_locator"] == "https://fixture.invalid/event"
    assert len(row[2]["origin_fingerprint"]) == 64
    assert set(row[2]["origin_fingerprint"]) <= set("0123456789abcdef")
    assert "REDACTION_CANARY" not in json.dumps(row[2])
    assert row[3].tzinfo is not None and row[4] == row[3]
    assert row[5].startswith(
        "Untrusted alta_news_search result for https://fixture.invalid/event:"
    )
    assert "fixture.invalid/event" in row[5]
    next_cycle, _ = DatabaseSourceFlow(
        database,
        ("SPY",),
        environment=Environment.REPLAY,
    ).schedule_and_wake(
        "cycle_tool_evidence_lineage",
        row[3] + timedelta(seconds=1),
        {},
    )
    frozen_tool_evidence = next(
        item for item in next_cycle.evidence if item.evidence_id == row[0][0]
    )
    assert frozen_tool_evidence.origin_fingerprint == row[2]["origin_fingerprint"]
    assert artifact["output"]["tool_evidence_refs"] == [
        {
            "tool_call_id": "tool_change_1",
            "evidence_role": "primary_fact",
            "source_locator": "https://fixture.invalid/event",
        }
    ]


def test_fake_app_server_deadline_interrupts_one_turn_and_batch_continues(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    command, log = fake_command(
        tmp_path,
        None,
        "--delay-scout",
        "change_event_scout",
        "--delay-seconds",
        "0.3",
    )

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client, deadline_seconds=0.08).run_batch(
            "batch_deadline", frozen_input
        )

    assert outcomes[0].error_code == "deadline_exceeded"
    assert [item.status for item in outcomes[1:]] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert any(item["method"] == "turn/interrupt" for item in read_log(log))
    with database.connect() as connection:
        assert (
            connection.execute(
                """SELECT attempt_count FROM research.run
            WHERE role = 'change_event_scout'"""
            ).fetchone()[0]
            == 3
        )


def test_stuck_turn_resets_app_server_before_next_scout(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    command, log = fake_command(
        tmp_path,
        None,
        "--delay-scout",
        "change_event_scout",
        "--delay-seconds",
        "2",
        "--ignore-interrupt",
    )

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client, deadline_seconds=0.4).run_batch(
            "batch_stuck_turn", frozen_input
        )

    assert outcomes[0].error_code == "deadline_exceeded"
    assert [item.status for item in outcomes[1:]] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert [item["method"] for item in read_log(log)].count("initialize") == 4


def test_tool_budget_rejects_tool_using_scout_but_preserves_other_runs(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    responses = json.loads((FIXTURES / "scout_outputs.json").read_text())
    for scout_id in (
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
    ):
        responses[scout_id]["tools"] = []
    response_path = tmp_path / "one-tool-output.json"
    response_path.write_text(json.dumps(responses))
    command, _ = fake_command(tmp_path, response_path)

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client, max_tool_calls=0).run_batch(
            "batch_budget", frozen_input
        )

    assert outcomes[0].error_code == "budget_exceeded"
    assert [item.status for item in outcomes[1:]] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    with database.connect() as connection:
        failed_run = connection.execute(
            """SELECT status, error_code, tool_provenance, thread_id, turn_id
            FROM research.run WHERE role = 'change_event_scout'"""
        ).fetchone()
    assert failed_run[0:2] == ("failed", "budget_exceeded")
    assert [item["tool_name"] for item in failed_run[2]] == ["alta_news_search"]
    assert failed_run[3:] == ("thread_1", "turn_1")


def test_missing_token_usage_fails_closed_without_stopping_other_scouts(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    command, _ = fake_command(
        tmp_path,
        None,
        "--omit-usage-scout",
        "market_dislocation_scout",
    )

    with client_for(tmp_path, command) as client:
        outcomes = worker(database, client).run_batch(
            "batch_missing_usage", frozen_input
        )

    assert [(item.status, item.error_code) for item in outcomes] == [
        ("succeeded", None),
        ("failed", "budget_exceeded"),
        ("succeeded", None),
        ("succeeded", None),
    ]


def test_completed_batch_recovery_uses_durable_artifacts_without_new_turns(
    empty_b3_database: str, tmp_path: Path
) -> None:
    database = Database(empty_b3_database)
    database.upgrade()
    frozen_input = seed_frozen_input(database)
    first_command, first_log = fake_command(tmp_path)
    with client_for(tmp_path, first_command) as client:
        first = worker(database, client).run_batch("batch_recovery", frozen_input)

    second_command, second_log = fake_command(tmp_path)
    with client_for(tmp_path, second_command) as client:
        recovered = worker(database, client).run_batch("batch_recovery", frozen_input)

    assert recovered == first
    assert [item["method"] for item in read_log(first_log)].count("turn/start") == 4
    assert not second_log.exists()
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT max(attempt_count) FROM research.run"
            ).fetchone()[0]
            == 1
        )
