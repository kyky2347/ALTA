import os
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.autonomous import (
    AutonomousOwnerBusy,
    AutonomousRunner,
    acquire_autonomous_owner,
    release_autonomous_owner,
)
from alta_asterism.contracts import Settings
from alta_asterism.database import AutonomousFenceLost, Database


def _database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def fencing_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_fence_{uuid4().hex[:12]}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield _database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_autonomous_owner_rejects_second_owner_and_advances_epoch(
    fencing_database: str,
) -> None:
    first_database = Database(fencing_database)
    first_database.upgrade()
    first = acquire_autonomous_owner(first_database)
    try:
        with pytest.raises(AutonomousOwnerBusy):
            acquire_autonomous_owner(Database(fencing_database))
        first_database.assert_autonomous_fence()
        first_epoch = first.epoch
    finally:
        release_autonomous_owner(first)

    second_database = Database(fencing_database)
    second = acquire_autonomous_owner(second_database)
    try:
        assert second.epoch > first_epoch
        second_database.assert_autonomous_fence()
    finally:
        release_autonomous_owner(second)


def test_terminated_owner_session_and_stale_epoch_fail_closed(
    fencing_database: str,
) -> None:
    old_database = Database(fencing_database)
    old_database.upgrade()
    old_owner = acquire_autonomous_owner(old_database)
    old_epoch = old_owner.epoch
    old_token = old_owner.token_digest

    with pytest.raises(AutonomousFenceLost, match="disconnected"):
        with old_database.connect() as old_transaction:
            old_transaction.execute(
                """INSERT INTO ops.job
                (id, environment, version, known_at, kind, status)
                VALUES ('lost-session-write', 'shadow', 1, now(),
                        'fencing-test', 'queued')"""
            )
            with psycopg.connect(fencing_database, autocommit=True) as admin:
                assert admin.execute(
                    "SELECT pg_terminate_backend(%s)", (old_owner.backend_pid,)
                ).fetchone()[0]

    current_database = Database(fencing_database)
    current_owner = acquire_autonomous_owner(current_database)
    stale_database = Database(fencing_database)
    stale_database.activate_autonomous_fence(
        owner_key=old_owner.owner_key,
        epoch=old_epoch,
        token_digest=old_token,
        session_validator=lambda: None,
    )
    try:
        assert current_owner.epoch > old_epoch
        with pytest.raises(AutonomousFenceLost, match="stale or revoked"):
            with stale_database.connect() as connection:
                connection.execute(
                    """INSERT INTO ops.job
                    (id, environment, version, known_at, kind, status)
                    VALUES ('stale-owner-write', 'shadow', 1, now(),
                            'fencing-test', 'queued')"""
                )
        with current_database.connect() as connection:
            assert (
                connection.execute(
                    """SELECT count(*) FROM ops.job
                    WHERE id IN ('lost-session-write', 'stale-owner-write')"""
                ).fetchone()[0]
                == 0
            )
    finally:
        stale_database.clear_autonomous_fence(token_digest=old_token)
        release_autonomous_owner(current_owner)
        release_autonomous_owner(old_owner)


def test_advisory_lock_loss_rejects_next_transaction(fencing_database: str) -> None:
    database = Database(fencing_database)
    database.upgrade()
    owner = acquire_autonomous_owner(database)
    try:
        assert owner.connection.execute(
            "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
            (owner.owner_key,),
        ).fetchone()[0]
        with pytest.raises(AutonomousFenceLost, match="ownership was lost"):
            database.assert_autonomous_fence()
    finally:
        release_autonomous_owner(owner)


def test_release_drains_fenced_transaction_without_deadlock(
    fencing_database: str,
) -> None:
    database = Database(fencing_database)
    database.upgrade()
    owner = acquire_autonomous_owner(database)
    entered = threading.Event()
    allow_exit = threading.Event()
    release_done = threading.Event()
    errors: list[BaseException] = []

    def transaction() -> None:
        try:
            with database.connect() as connection:
                connection.execute("SELECT 1")
                entered.set()
                assert allow_exit.wait(5)
        except BaseException as error:
            errors.append(error)

    def release() -> None:
        try:
            release_autonomous_owner(owner)
        except BaseException as error:
            errors.append(error)
        finally:
            release_done.set()

    transaction_thread = threading.Thread(target=transaction)
    transaction_thread.start()
    assert entered.wait(5)
    release_thread = threading.Thread(target=release)
    release_thread.start()
    time.sleep(0.05)
    assert not release_done.is_set()
    with pytest.raises(AutonomousFenceLost, match="draining"):
        with database.connect():
            pass
    allow_exit.set()
    transaction_thread.join(5)
    release_thread.join(5)

    assert not transaction_thread.is_alive()
    assert not release_thread.is_alive()
    assert release_done.is_set()
    assert errors == []


def test_mutating_cli_entrypoints_share_writer_exclusion_and_confirm_downgrade(
    fencing_database: str,
) -> None:
    database = Database(fencing_database)
    database.upgrade()
    environment = {
        **os.environ,
        "DATABASE_URL": fencing_database,
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "ALTA_ENVIRONMENT": "shadow",
    }
    unconfirmed = subprocess.run(
        [sys.executable, "-m", "alta_asterism", "migrate", "downgrade"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert unconfirmed.returncode != 0
    assert "confirm-destructive-downgrade" in unconfirmed.stderr
    assert database.ready()

    owner = acquire_autonomous_owner(database)
    try:
        commands = (
            ("migrate", "upgrade"),
            ("migrate", "downgrade", "--confirm-destructive-downgrade"),
            ("demo", "--demo-id", "writer-exclusion-demo"),
            ("soak", "--session-id", "writer-exclusion-soak"),
        )
        for command in commands:
            result = subprocess.run(
                [sys.executable, "-m", "alta_asterism", *command],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            assert result.returncode != 0
            assert "another writer owns the database" in result.stderr
    finally:
        release_autonomous_owner(owner)
    assert database.ready()


def test_runner_cancels_after_owner_backend_is_terminated(
    fencing_database: str,
) -> None:
    database = Database(fencing_database)
    database.upgrade()
    states = []

    class TerminatingRuntime:
        def __init__(self, fenced_database: Database) -> None:
            self.database = fenced_database
            self.orchestrator = self

        def run(self, _cycle_id, _wake_at):
            with psycopg.connect(fencing_database, autocommit=True) as admin:
                backend_pid = admin.execute(
                    """SELECT backend_pid FROM ops.autonomous_owner
                    WHERE owner_key = 'alta-autonomous-runner'"""
                ).fetchone()[0]
                assert admin.execute(
                    "SELECT pg_terminate_backend(%s)", (backend_pid,)
                ).fetchone()[0]
            with self.database.connect() as connection:
                connection.execute("SELECT 1")

        def close(self) -> None:
            return None

    settings = Settings(
        DATABASE_URL=fencing_database,
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_ENVIRONMENT="shadow",
    )
    runner = AutonomousRunner(
        database,
        settings,
        runtime_factory=lambda fenced_database, _settings: TerminatingRuntime(
            fenced_database
        ),
        state_callback=lambda status, detail: states.append((status, detail)),
    )

    assert runner.run(threading.Event(), once=True) == 1
    assert states[-1][0] == "failed"
    assert states[-1][1]["cycle_result"] == "owner_lost"
    assert states[-1][1]["failure_type"] == "AutonomousFenceLost"
