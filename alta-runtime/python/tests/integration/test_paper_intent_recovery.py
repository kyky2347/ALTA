import os
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.database import Database
from alta_asterism.paper_execution import PaperExecutionResult
from alta_asterism.paper_intent import PaperIntentError, PaperIntentStore


def _database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def paper_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_paper_{uuid4().hex[:12]}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield _database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.mark.parametrize(
    "operation,expected_before",
    [("open", Decimal(0)), ("close", Decimal(1))],
)
def test_prepared_intent_restart_is_abandoned_without_dispatch(
    paper_database: str, operation: str, expected_before: Decimal
) -> None:
    database = Database(paper_database)
    database.upgrade()
    first = PaperIntentStore(database, "a" * 64)
    durable = first.prepare(
        cycle_id=f"cycle_{operation}",
        position_id=f"position_{operation}",
        expression_id=f"expression_{operation}",
        operation=operation,
        symbol="SPY",
        limit_price=Decimal("500"),
        local_commit={"kill_point": "after_prepare"},
    )
    assert durable.expected_position_before == expected_before

    restarted = PaperIntentStore(database, "a" * 64)
    unresolved = restarted.unresolved()
    assert [item.state for item in unresolved] == ["prepared"]
    restarted.abandon_prepared(unresolved[0].intent_id)
    assert restarted.unresolved() == ()


@pytest.mark.parametrize(
    "operation,status,action,position_before,position_after",
    [
        ("open", "filled", "BUY", "0", "1"),
        ("close", "already_flat", "SELL", "1", "0"),
    ],
)
def test_broker_first_restart_reaches_one_atomic_local_commit_state(
    paper_database: str,
    operation: str,
    status: str,
    action: str,
    position_before: str,
    position_after: str,
) -> None:
    database = Database(paper_database)
    database.upgrade()
    store = PaperIntentStore(database, "b" * 64)
    durable = store.prepare(
        cycle_id=f"cycle_{operation}",
        position_id=f"position_{operation}",
        expression_id=f"expression_{operation}",
        operation=operation,
        symbol="SPY",
        limit_price=Decimal("500"),
        local_commit={"kill_point": "after_broker"},
    )
    store.mark_dispatching(durable.intent_id)

    restarted = PaperIntentStore(database, "b" * 64)
    dispatching = restarted.unresolved()[0]
    result = PaperExecutionResult(
        status=status,
        action=action,
        symbol="SPY",
        quantity="1" if status == "filled" else "0",
        position_before=position_before,
        position_after=position_after,
        average_fill_price="500" if status == "filled" else None,
        broker_order_hash="c" * 64 if status == "filled" else None,
    )
    filled = restarted.record_result(dispatching.intent_id, result)
    assert filled.state == "broker_filled"
    with database.connect() as connection:
        PaperIntentStore.commit_local(connection, filled.intent_id)
    assert restarted.unresolved() == ()
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM ops.paper_intent WHERE id = %s",
                (filled.intent_id,),
            ).fetchone()[0]
            == "local_committed"
        )


def test_close_only_drain_is_durable_until_broker_and_local_are_flat(
    paper_database: str,
) -> None:
    database = Database(paper_database)
    database.upgrade()
    store = PaperIntentStore(database, "d" * 64)
    drain = store.ensure_drain(7)
    store.mark_drain_draining(drain.drain_id)

    with pytest.raises(PaperIntentError, match="broker flat"):
        store.complete_drain(drain.drain_id, {"positionCount": 1, "openOrderCount": 0})
    restarted = PaperIntentStore(database, "d" * 64)
    assert restarted.ensure_drain(7).state == "draining"
    restarted.complete_drain(drain.drain_id, {"positionCount": 0, "openOrderCount": 0})
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM ops.paper_drain WHERE id = %s", (drain.drain_id,)
            ).fetchone()[0]
            == "completed"
        )
