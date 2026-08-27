import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alta_asterism.database import Database
from alta_asterism.contracts import Environment
from alta_asterism.finlight import (
    FinlightAdapter,
    FinlightDisconnected,
    FinlightMode,
    PostgresSourceCursorStore,
    PostgresSourceOwner,
    SourceBusy,
)
from alta_asterism.ingest import RawStore, SourceEnvelope

FIXTURES = Path(__file__).parents[1] / "fixtures"


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_b2_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b2_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b2_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def load_finlight() -> SourceEnvelope:
    return SourceEnvelope.model_validate_json(
        (FIXTURES / "finlight" / "article_ws.json").read_text()
    )


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self.values = iter(values)

    def __call__(self) -> datetime:
        return next(self.values)


def test_raw_store_is_idempotent_preserves_first_known_at_and_redacts(
    empty_b2_database: str,
) -> None:
    database = Database(empty_b2_database)
    database.upgrade()
    first_known = datetime(2026, 8, 23, 13, tzinfo=UTC)
    envelope = load_finlight().model_copy(
        update={
            "source_url": "https://fixture.invalid/item?api_key=REDACTION_CANARY",
            "payload": {
                **load_finlight().payload,
                "authorization": "Bearer REDACTION_CANARY",
            },
        }
    )
    duplicate = envelope.model_copy(
        update={
            "channel": "rest",
            "received_at": envelope.received_at + timedelta(minutes=2),
        }
    )
    store = RawStore(
        database,
        clock=SequenceClock(first_known, first_known + timedelta(minutes=3)),
    )

    first = store.save(envelope)
    repeated = store.save(duplicate)

    assert (first.id, first.content_hash, first.known_at, first.inserted) == (
        repeated.id,
        repeated.content_hash,
        repeated.known_at,
        True,
    )
    assert repeated.inserted is False
    assert first.known_at == first_known
    with database.connect() as connection:
        count, body = connection.execute(
            "SELECT count(*), min(body::text) FROM research.raw"
        ).fetchone()
    assert count == 1
    assert "REDACTION_CANARY" not in body
    assert body.count("[REDACTED]") == 2


def test_raw_store_identity_isolated_by_environment(empty_b2_database: str) -> None:
    database = Database(empty_b2_database)
    database.upgrade()
    envelope = load_finlight()
    known_at = datetime(2026, 8, 23, 13, tzinfo=UTC)

    replay = RawStore(
        database, environment=Environment.REPLAY, clock=lambda: known_at
    ).save(envelope)
    shadow = RawStore(
        database,
        environment=Environment.SHADOW,
        clock=lambda: known_at + timedelta(minutes=1),
    ).save(envelope)

    assert replay.id != shadow.id
    assert replay.known_at != shadow.known_at
    assert replay.inserted is shadow.inserted is True
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT environment::text, id FROM research.raw ORDER BY environment"
        ).fetchall()
    assert rows == [("replay", replay.id), ("shadow", shadow.id)]


def test_finlight_single_owner_disconnect_gap_and_polling_posture(
    empty_b2_database: str,
) -> None:
    database = Database(empty_b2_database)
    database.upgrade()
    first = load_finlight()
    gap_duplicate = first.model_copy(
        update={
            "channel": "rest",
            "received_at": first.received_at + timedelta(seconds=5),
        }
    )
    gap_new = gap_duplicate.model_copy(
        update={
            "source_record_id": "fixture-finlight-002",
            "payload": {**gap_duplicate.payload, "headline": "Gap fixture headline"},
        }
    )

    class DisconnectingTransport:
        websocket_available = True

        def stream(self, cursor):
            yield first
            raise FinlightDisconnected

        def rest_gap(self, cursor):
            assert cursor == first.source_record_id
            return [gap_duplicate, gap_new]

        def poll_rest(self, cursor):
            raise AssertionError("REST polling must not run when WS capability exists")

    known_at = datetime(2026, 8, 23, 13, tzinfo=UTC)
    store = RawStore(database, clock=lambda: known_at)
    owner = PostgresSourceOwner(database)
    adapter = FinlightAdapter(DisconnectingTransport(), store, owner)

    result = adapter.run_once()

    assert result == type(result)(
        mode=FinlightMode.WS_REST_GAP,
        realtime_news=True,
        posture="degraded",
        reason="websocket_disconnected_rest_gap",
        inserted=2,
        duplicates=1,
        cursor="fixture-finlight-002",
    )
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM research.raw WHERE source = 'finlight'"
            ).fetchone()[0]
            == 2
        )

    with owner.acquire():
        with pytest.raises(SourceBusy):
            with PostgresSourceOwner(database).acquire():
                pass
        rejected = adapter.run_once()
    assert (rejected.posture, rejected.reason) == (
        "disabled",
        "second_owner_rejected",
    )

    class PollingTransport:
        websocket_available = False

        def stream(self, cursor):
            raise AssertionError("WS must not run without capability")

        def rest_gap(self, cursor):
            raise AssertionError("gap fetch must not run without a WS disconnect")

        def poll_rest(self, cursor):
            return [
                first.model_copy(
                    update={
                        "source_record_id": "fixture-finlight-003",
                        "channel": "rest",
                    }
                )
            ]

    polling = FinlightAdapter(PollingTransport(), store, owner).run_once()
    assert (
        polling.mode,
        polling.realtime_news,
        polling.posture,
        polling.reason,
    ) == (
        FinlightMode.REST_POLLING,
        False,
        "degraded",
        "websocket_unavailable_rest_polling",
    )


def test_finlight_cursor_survives_adapter_and_process_recreation(
    empty_b2_database: str,
) -> None:
    database = Database(empty_b2_database)
    database.upgrade()
    first = load_finlight().model_copy(update={"channel": "rest"})
    seen: list[str | None] = []

    class Transport:
        websocket_available = False

        def stream(self, cursor):
            raise AssertionError

        def rest_gap(self, cursor):
            raise AssertionError

        def poll_rest(self, cursor):
            seen.append(cursor)
            return [first] if cursor is None else []

    cursor_store = PostgresSourceCursorStore(
        database,
        Environment.SHADOW,
        clock=lambda: datetime(2026, 8, 23, 14, tzinfo=UTC),
    )
    raw_store = RawStore(database, Environment.SHADOW)
    FinlightAdapter(
        Transport(), raw_store, PostgresSourceOwner(database), cursor_store=cursor_store
    ).run_once()
    FinlightAdapter(
        Transport(), raw_store, PostgresSourceOwner(database), cursor_store=cursor_store
    ).run_once()

    assert seen == [None, first.source_record_id]
    assert cursor_store.load() == first.source_record_id


def test_b2_did_not_add_schema_or_network_clients(empty_b2_database: str) -> None:
    database = Database(empty_b2_database)
    database.upgrade()
    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """SELECT table_schema || '.' || table_name
                FROM information_schema.tables
                WHERE table_schema IN ('ops', 'research')"""
            ).fetchall()
        }
    from alta_asterism.migrations import CURRENT_TABLES

    assert tables == set(CURRENT_TABLES)
    package_root = Path(__file__).parents[2] / "src" / "alta_asterism"
    modules = {path.stem for path in package_root.glob("*.py")}
    assert {"scout", "trading", "massive_ws"}.isdisjoint(modules)
    assert "http" not in json.dumps(sorted(modules))
