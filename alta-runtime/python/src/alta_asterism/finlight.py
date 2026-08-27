import hashlib
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

import psycopg

from .database import Database
from .contracts import Environment
from .ingest import Cooldown, RateLimited, RawSink, SourceEnvelope


class FinlightMode(StrEnum):
    WS_REST_GAP = "ws_rest_gap"
    REST_POLLING = "rest_polling"


class FinlightDisconnected(Exception):
    pass


class SourceBusy(Exception):
    pass


class FinlightTransport(Protocol):
    websocket_available: bool

    def stream(self, cursor: str | None) -> Iterable[SourceEnvelope]: ...

    def rest_gap(self, cursor: str | None) -> Iterable[SourceEnvelope]: ...

    def poll_rest(self, cursor: str | None) -> Iterable[SourceEnvelope]: ...


class SourceCursorStore(Protocol):
    def load(self) -> str | None: ...

    def save(self, cursor: str) -> None: ...


class PostgresSourceCursorStore:
    def __init__(
        self,
        database: Database,
        environment: Environment,
        source: str = "finlight",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.database = database
        self.environment = environment
        self.source = source
        self.clock = clock
        self.id = (
            "cursor_"
            + hashlib.sha256(f"{environment.value}\0{source}".encode()).hexdigest()[:32]
        )

    def load(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT cursor FROM ops.source_cursor
                WHERE environment = %s AND source = %s""",
                (self.environment.value, self.source),
            ).fetchone()
        return row[0] if row else None

    def save(self, cursor: str) -> None:
        if not cursor or len(cursor.encode()) > 2_048:
            raise ValueError("source cursor must be non-empty and bounded")
        known_at = self.clock()
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise ValueError("source cursor clock must be timezone-aware")
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO ops.source_cursor
                (id, environment, version, known_at, source, cursor)
                VALUES (%s,%s,1,%s,%s,%s)
                ON CONFLICT (environment, source) DO UPDATE SET
                version = ops.source_cursor.version + 1,
                known_at = EXCLUDED.known_at,
                cursor = EXCLUDED.cursor""",
                (
                    self.id,
                    self.environment.value,
                    known_at,
                    self.source,
                    cursor,
                ),
            )


class PostgresSourceOwner:
    def __init__(self, database: Database, owner_name: str = "finlight") -> None:
        self.database = database
        self.owner_name = owner_name

    @contextmanager
    def acquire(self):
        connection = psycopg.connect(
            self.database.dsn, connect_timeout=3, autocommit=True
        )
        acquired = connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (f"alta-source-owner:{self.owner_name}",),
        ).fetchone()[0]
        if not acquired:
            connection.close()
            raise SourceBusy(f"source owner already held: {self.owner_name}")
        try:
            yield
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (f"alta-source-owner:{self.owner_name}",),
            )
            connection.close()


@dataclass(frozen=True)
class FinlightResult:
    mode: FinlightMode
    realtime_news: bool
    posture: str
    reason: str
    inserted: int = 0
    duplicates: int = 0
    retry_after: float | None = None
    cursor: str | None = None


class FinlightAdapter:
    def __init__(
        self,
        transport: FinlightTransport,
        raw_store: RawSink,
        owner: PostgresSourceOwner,
        cooldown: Cooldown | None = None,
        cursor_store: SourceCursorStore | None = None,
    ) -> None:
        self.transport = transport
        self.raw_store = raw_store
        self.owner = owner
        self.cooldown = cooldown or Cooldown()
        self.cursor_store = cursor_store

    def _save_one(self, envelope: SourceEnvelope) -> bool:
        if envelope.source_id != "finlight":
            raise ValueError("Finlight adapter received a non-Finlight envelope")
        return self.raw_store.save(envelope).inserted

    def _save(self, envelopes: Iterable[SourceEnvelope]) -> Iterable[tuple[bool, str]]:
        for envelope in envelopes:
            was_inserted = self._save_one(envelope)
            yield was_inserted, envelope.source_cursor or envelope.source_record_id

    def run_once(self, cursor: str | None = None) -> FinlightResult:
        if cursor is None and self.cursor_store is not None:
            cursor = self.cursor_store.load()
        mode = (
            FinlightMode.WS_REST_GAP
            if self.transport.websocket_available
            else FinlightMode.REST_POLLING
        )
        remaining = self.cooldown.remaining()
        if remaining > 0:
            return FinlightResult(
                mode=mode,
                realtime_news=mode is FinlightMode.WS_REST_GAP,
                posture="rate_limited",
                reason="retry_after_cooldown",
                retry_after=remaining,
            )
        inserted = 0
        duplicates = 0
        try:
            with self.owner.acquire():
                if mode is FinlightMode.REST_POLLING:
                    for was_inserted, cursor in self._save(
                        self.transport.poll_rest(cursor)
                    ):
                        inserted += int(was_inserted)
                        duplicates += int(not was_inserted)
                        self._persist_cursor(cursor)
                    return FinlightResult(
                        mode=mode,
                        realtime_news=False,
                        posture="degraded",
                        reason="websocket_unavailable_rest_polling",
                        inserted=inserted,
                        duplicates=duplicates,
                        cursor=cursor,
                    )
                try:
                    for was_inserted, cursor in self._save(
                        self.transport.stream(cursor)
                    ):
                        inserted += int(was_inserted)
                        duplicates += int(not was_inserted)
                        self._persist_cursor(cursor)
                    reason = "websocket_active"
                    posture = "healthy"
                except FinlightDisconnected:
                    for was_inserted, cursor in self._save(
                        self.transport.rest_gap(cursor)
                    ):
                        inserted += int(was_inserted)
                        duplicates += int(not was_inserted)
                        self._persist_cursor(cursor)
                    reason = "websocket_disconnected_rest_gap"
                    posture = "degraded"
                return FinlightResult(
                    mode=mode,
                    realtime_news=True,
                    posture=posture,
                    reason=reason,
                    inserted=inserted,
                    duplicates=duplicates,
                    cursor=cursor,
                )
        except SourceBusy:
            return FinlightResult(
                mode=mode,
                realtime_news=mode is FinlightMode.WS_REST_GAP,
                posture="disabled",
                reason="second_owner_rejected",
            )
        except RateLimited as error:
            self.cooldown.record(error.retry_after)
            return FinlightResult(
                mode=mode,
                realtime_news=mode is FinlightMode.WS_REST_GAP,
                posture="rate_limited",
                reason="upstream_429",
                inserted=inserted,
                duplicates=duplicates,
                retry_after=error.retry_after,
                cursor=cursor,
            )

    def _persist_cursor(self, cursor: str) -> None:
        if self.cursor_store is not None:
            self.cursor_store.save(cursor)
