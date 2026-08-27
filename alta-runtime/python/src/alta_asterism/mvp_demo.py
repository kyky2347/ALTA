from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .database import Database
from .expression import contract_hash
from .mvp_fixture import FixtureMindClient, MvpFixture
from .mvp_orchestrator import MvpOrchestrator, MvpRunResult


def run_demo(
    database: Database,
    demo_id: str,
    wake_at: datetime,
) -> MvpRunResult:
    fixture = MvpFixture.default()
    client = FixtureMindClient(fixture)
    return MvpOrchestrator(database, fixture, client).run(demo_id, wake_at)


def replay_demo(database: Database, demo_id: str) -> MvpRunResult:
    fixture = MvpFixture.default()
    client = FixtureMindClient(fixture)
    return MvpOrchestrator(database, fixture, client).replay(demo_id)


class SoakResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    status: str
    session_start: datetime
    session_end: datetime
    event_time_duration_seconds: int = Field(ge=23_400)
    cadence_minutes: int = Field(ge=1)
    cycles: int = Field(ge=2)
    failures: tuple[str, ...]
    replay_hashes: tuple[str, ...]
    manual_database_repairs: int = 0


def run_market_session_soak(
    database: Database,
    session_id: str,
    session_start: datetime,
    session_end: datetime,
    cadence_minutes: int,
) -> SoakResult:
    duration = int((session_end - session_start).total_seconds())
    if duration < 23_400:
        raise ValueError("soak must cover at least one 6.5-hour market session")
    if not 1 <= cadence_minutes <= 195:
        raise ValueError("soak cadence must produce at least three scheduled wakes")
    fixture = MvpFixture.default()
    client = FixtureMindClient(fixture)
    orchestrator = MvpOrchestrator(database, fixture, client)
    failures: list[str] = []
    hashes: list[str] = []
    wake_at = session_start
    cycle = 0
    while wake_at <= session_end:
        demo_id = f"{session_id}-{cycle:03d}"
        try:
            hashes.append(orchestrator.run(demo_id, wake_at).replay_hash)
        except Exception as error:
            failures.append(f"{demo_id}:{type(error).__name__}")
        cycle += 1
        wake_at += timedelta(minutes=cadence_minutes)
    result = SoakResult(
        session_id=session_id,
        status="PASS" if not failures else "FAIL",
        session_start=session_start,
        session_end=session_end,
        event_time_duration_seconds=duration,
        cadence_minutes=cadence_minutes,
        cycles=cycle,
        failures=tuple(failures),
        replay_hashes=tuple(hashes),
    )
    with database.connect() as connection:
        _append_event(
            connection,
            _contract_event(
                event_type="mvp.soak.completed",
                aggregate_type="mvp_soak",
                aggregate_id=session_id,
                environment=Environment.SHADOW,
                known_at=session_end + timedelta(seconds=1),
                payload={
                    **result.model_dump(mode="json"),
                    "result_hash": contract_hash(result.model_dump(mode="json")),
                },
                correlation_id=session_id,
            ),
        )
    return result
