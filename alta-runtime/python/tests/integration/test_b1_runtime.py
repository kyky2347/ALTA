import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.contracts import Event
from alta_asterism.database import Database
from alta_asterism.migrations import CURRENT_TABLES, LATEST_REVISION
from alta_asterism.version import __version__


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b1_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b1_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_empty_database_upgrade_down_up_and_closed_environment(
    empty_database: str,
) -> None:
    database = Database(empty_database)
    assert database.current() == "base"
    result = subprocess.run(
        [sys.executable, "-m", "alta_asterism", "migrate", "upgrade"],
        env={
            **os.environ,
            "DATABASE_URL": empty_database,
            "REDIS_URL": "redis://127.0.0.1:1/0",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {"revision": LATEST_REVISION}
    assert database.upgrade() == LATEST_REVISION
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT table_schema || '.' || table_name FROM information_schema.tables
            WHERE table_schema IN ('ops','research') ORDER BY 1"""
        ).fetchall()
        assert {row[0] for row in rows} == set(CURRENT_TABLES)
        with pytest.raises(psycopg.errors.InvalidTextRepresentation):
            connection.execute(
                """INSERT INTO ops.job
                (id, environment, version, known_at, kind, status)
                VALUES ('job_live', 'live', 1, now(), 'fixture', 'queued')"""
            )
        connection.rollback()
    assert database.downgrade() == "base"
    assert database.current() == "base"
    assert database.upgrade() == LATEST_REVISION


def free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return value.getsockname()[1]


def request_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as result:
        return json.load(result)


def wait_until(operation, timeout: float = 10):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return operation()
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"operation did not become ready: {last_error}")


def read_state(file: Path) -> dict:
    return json.loads(file.read_text())


def test_supervisor_restart_summary_and_sse_reconnect(
    empty_database: str, tmp_path: Path
) -> None:
    database = Database(empty_database)
    database.upgrade()
    known_at = datetime(2026, 8, 23, tzinfo=UTC)
    first_cursor = database.append_event(
        Event(
            id="event_1",
            environment="replay",
            version=1,
            known_at=known_at,
            aggregate_type="run",
            aggregate_id="run_1",
            event_type="run.created",
        )
    )
    port = free_port()
    state_file = tmp_path / "supervisor.json"
    env = {
        **os.environ,
        "DATABASE_URL": empty_database,
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "ALTA_ENVIRONMENT": "replay",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "alta_asterism",
            "supervisor",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--state-file",
            str(state_file),
            "--max-restarts",
            "2",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert wait_until(lambda: request_json(port, "/health/ready")) == {
            "ready": True
        }
        assert request_json(port, "/health/live")["status"] == "live"
        summary = request_json(port, "/api/v1/system/summary")
        assert summary["meta"]["environment"] == "replay"
        assert summary["meta"]["version"] == __version__
        assert datetime.fromisoformat(summary["meta"]["knownAt"]).tzinfo is not None
        assert summary["data"]["counts"]["event"] == 1
        ledger = request_json(port, "/api/v1/events?cursor=0&limit=10")
        assert ledger["data"]["events"][0]["eventId"] == "event_1"
        assert ledger["data"]["events"][0]["cursor"] == first_cursor
        assert ledger["meta"]["nextCursor"] == first_cursor
        evaluation = request_json(port, "/api/v1/evaluation/summary")
        assert evaluation["data"]["performance"]["readiness"] == "not_started"
        assert "Alpha is unproven" in evaluation["data"]["warning"]

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/stream?cursor=0", timeout=2
        ) as response:
            first_stream = response.read().decode()
        assert f"id: {first_cursor}" in first_stream
        assert "event_1" in first_stream

        second_cursor = database.append_event(
            Event(
                id="event_2",
                environment="replay",
                version=1,
                known_at=known_at,
                aggregate_type="run",
                aggregate_id="run_1",
                event_type="run.ready",
            )
        )
        older = request_json(port, f"/api/v1/events?before={second_cursor}&limit=10")
        assert [event["eventId"] for event in older["data"]["events"]] == ["event_1"]
        reconnect = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/stream",
            headers={"Last-Event-ID": str(first_cursor)},
        )
        with urllib.request.urlopen(reconnect, timeout=2) as response:
            second_stream = response.read().decode()
        assert f"id: {second_cursor}" in second_stream
        assert "event_2" in second_stream
        assert "event_1" not in second_stream

        first_child = wait_until(lambda: read_state(state_file))["childPid"]
        os.kill(first_child, signal.SIGTERM)
        second_child = wait_until(
            lambda: (
                state["childPid"]
                if (state := read_state(state_file))["childPid"] != first_child
                else (_ for _ in ()).throw(OSError("not restarted"))
            )
        )
        assert second_child != first_child
        assert wait_until(lambda: request_json(port, "/health/ready"))["ready"]
        assert (
            request_json(port, "/api/v1/system/summary")["data"]["counts"]["event"] == 2
        )
    finally:
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()
        assert process.returncode == 0, stderr
        assert read_state(state_file)["state"] == "stopped"
