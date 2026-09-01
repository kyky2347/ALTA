from datetime import datetime, timedelta
from typing import Literal

from psycopg.types.json import Jsonb

from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .database import Database
from .expression import contract_hash
from .mvp_fixture import FixtureSource, MvpFixture
from .scout_repository import ScoutRepository
from .scouts import EvidenceSnapshot, FrozenScoutInput

SourcePosture = Literal[
    "healthy", "disabled", "stale", "degraded", "rate_limited", "unavailable"
]


class MvpSourceFlow:
    def __init__(self, database: Database, fixture: MvpFixture) -> None:
        self.database = database
        self.fixture = fixture

    def schedule_and_wake(
        self,
        demo_id: str,
        wake_at: datetime,
        overrides: dict[str, SourcePosture],
    ) -> tuple[FrozenScoutInput, dict[str, SourcePosture]]:
        known_sources = {item.source_id for item in self.fixture.sources}
        if not set(overrides).issubset(known_sources):
            raise ValueError("source override names an unknown source")
        massive = next(
            (item for item in self.fixture.sources if item.source_id == "massive"),
            None,
        )
        if (
            massive is not None
            and overrides.get("massive", massive.default_posture) != "disabled"
        ):
            raise ValueError("Massive remains disabled without coordination evidence")
        postures: dict[str, SourcePosture] = {}
        snapshots: list[EvidenceSnapshot] = []
        with self.database.connect() as connection:
            self._record_wake(connection, demo_id, wake_at)
            for source in self.fixture.sources:
                posture = overrides.get(source.source_id, source.default_posture)
                postures[source.source_id] = posture
                self._record_source_posture(
                    connection, demo_id, source, posture, wake_at
                )
                snapshot = self._seed_source(
                    connection, demo_id, source, posture, wake_at
                )
                if snapshot is not None:
                    snapshots.append(snapshot)
        if not snapshots:
            raise ValueError("all fixture sources are unavailable")
        frozen = FrozenScoutInput(
            wake_id=demo_id,
            environment=Environment.SHADOW,
            known_at=wake_at,
            universe=self.fixture.universe,
            evidence=tuple(snapshots),
            expectation_posture="available",
        )
        ScoutRepository(self.database).start_batch(f"batch_{demo_id}", frozen, postures)
        return frozen, postures

    def _record_wake(self, connection, demo_id: str, wake_at: datetime) -> None:
        values = (
            (
                "schedule.wake_due",
                "schedule",
                wake_at - timedelta(seconds=1),
                {"demo_id": demo_id, "scheduled_for": wake_at.isoformat()},
            ),
            (
                "wake.created",
                "wake",
                wake_at,
                {
                    "demo_id": demo_id,
                    "fixture_version": self.fixture.fixture_version,
                },
            ),
        )
        for event_type, aggregate_type, known_at, payload in values:
            _append_event(
                connection,
                _contract_event(
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=demo_id,
                    environment=Environment.SHADOW,
                    known_at=known_at,
                    payload=payload,
                    correlation_id=demo_id,
                ),
            )

    @staticmethod
    def _record_source_posture(
        connection,
        demo_id: str,
        source: FixtureSource,
        posture: SourcePosture,
        wake_at: datetime,
    ) -> None:
        reason = {
            "healthy": "fixture_available",
            "disabled": (
                "massive_policy_disabled"
                if source.source_id == "massive"
                else "source_disabled"
            ),
            "stale": "freshness_expired",
        }[posture]
        _append_event(
            connection,
            _contract_event(
                event_type="source.posture",
                aggregate_type="source",
                aggregate_id=f"{demo_id}:{source.source_id}",
                environment=Environment.SHADOW,
                known_at=wake_at,
                payload={
                    "demo_id": demo_id,
                    "source_id": source.source_id,
                    "posture": posture,
                    "reason": reason,
                },
                correlation_id=demo_id,
            ),
        )

    @staticmethod
    def _seed_source(
        connection,
        demo_id: str,
        source: FixtureSource,
        posture: SourcePosture,
        wake_at: datetime,
    ) -> EvidenceSnapshot | None:
        if posture == "disabled":
            return None
        raw_known_at = wake_at - (
            timedelta(days=1) if posture == "stale" else timedelta(minutes=2)
        )
        evidence_known_at = raw_known_at + timedelta(minutes=1)
        body = {
            "fixture": True,
            "demo_id": demo_id,
            "source_id": source.source_id,
            "summary": source.summary,
        }
        content_hash = contract_hash(body)
        raw_id = f"raw_{contract_hash([demo_id, source.source_id])[:32]}"
        evidence_id = f"evidence_{contract_hash([raw_id, 'evidence'])[:32]}"
        connection.execute(
            """INSERT INTO research.raw
            (id, environment, version, known_at, source, source_key,
             content_hash, body) VALUES (%s,'shadow',1,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING""",
            (
                raw_id,
                raw_known_at,
                source.raw_source,
                f"{demo_id}:{source.source_id}",
                content_hash,
                Jsonb(body),
            ),
        )
        connection.execute(
            """INSERT INTO research.evidence
            (id, environment, version, known_at, raw_id, stance, summary)
            VALUES (%s,'shadow',1,%s,%s,'support',%s)
            ON CONFLICT (id) DO NOTHING""",
            (evidence_id, evidence_known_at, raw_id, source.summary),
        )
        if posture == "stale":
            return None
        return EvidenceSnapshot(
            evidence_id=evidence_id,
            raw_id=raw_id,
            source=source.raw_source,
            territory=source.territory,
            source_locator=f"fixture://{source.source_id}/{demo_id}",
            known_at=evidence_known_at,
            content_hash=content_hash,
            summary=source.summary,
        )
