import hashlib
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg

from .b5_runtime import _append_event, _contract_event
from .contracts import Environment, Settings
from .database import Database
from .forward_evaluation import ForwardEvaluationLedger
from .live_runtime import LiveRuntime
from .scout_repository import ScoutRepository


class AutonomousOwnerBusy(RuntimeError):
    pass


class AutonomousRunner:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        runtime_factory: Callable[[Database, Settings], LiveRuntime] = LiveRuntime,
        state_callback: Callable[[str, dict], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        waiter: Callable[[threading.Event, float], bool] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.runtime_factory = runtime_factory
        self.state_callback = state_callback
        self.monotonic = monotonic
        self.waiter = waiter or (lambda stop, seconds: stop.wait(seconds))
        self.evaluation = ForwardEvaluationLedger(database, settings)

    def run(self, stop: threading.Event, *, once: bool = False) -> int:
        if self.settings.environment is not Environment.SHADOW:
            raise ValueError("autonomous runner requires ALTA_ENVIRONMENT=shadow")
        owner = psycopg.connect(self.database.dsn, connect_timeout=3, autocommit=True)
        acquired = owner.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            ("alta-autonomous-runner",),
        ).fetchone()[0]
        if not acquired:
            owner.close()
            raise AutonomousOwnerBusy("another autonomous runner owns the database")
        failures = 0
        runtime = None
        cycle_id: str | None = None
        wake_at: datetime | None = None
        try:
            ScoutRepository(self.database).reconcile_expired_activity(datetime.now(UTC))
            while not stop.is_set():
                try:
                    owner.execute("SELECT 1")
                except psycopg.Error:
                    self._notify(
                        "failed",
                        cycle_result="owner_lost",
                        failure_type="AutonomousOwnerLost",
                        consecutive_failures=failures,
                    )
                    return 1
                if cycle_id is None or wake_at is None:
                    wake_at = datetime.now(UTC)
                    cycle_id = "live-" + wake_at.strftime("%Y%m%d-%H%M%S-%f")
                self._notify(
                    "running",
                    cycle_id=cycle_id,
                    cycle_started_at=wake_at.isoformat(),
                    cycle_result=None,
                    consecutive_failures=failures,
                )
                try:
                    self.evaluation.bind_cycle(cycle_id, wake_at)
                    if runtime is None:
                        runtime = self.runtime_factory(self.database, self.settings)
                    result = runtime.orchestrator.run(cycle_id, wake_at)
                except Exception as error:
                    if stop.is_set():
                        self._notify(
                            "stopping",
                            cycle_id=cycle_id,
                            cycle_completed_at=datetime.now(UTC).isoformat(),
                            cycle_result="cancelled",
                            failure_type=None,
                            consecutive_failures=failures,
                        )
                        return 0
                    failures += 1
                    failure_recorded = True
                    try:
                        self._record_failure(
                            cycle_id,
                            wake_at,
                            error,
                            failures,
                            retry_scheduled=not once,
                        )
                    except Exception:
                        failure_recorded = False
                    runtime_closed = self._close_runtime(runtime)
                    runtime = None
                    if not runtime_closed:
                        self._notify(
                            "failed",
                            cycle_id=cycle_id,
                            cycle_completed_at=datetime.now(UTC).isoformat(),
                            cycle_result="runtime_close_failed",
                            failure_type="AutonomousRuntimeCloseFailed",
                            consecutive_failures=failures,
                            failure_recorded=failure_recorded,
                        )
                        return 1
                    if once:
                        self._notify(
                            "failed",
                            cycle_id=cycle_id,
                            cycle_completed_at=datetime.now(UTC).isoformat(),
                            cycle_result="failed",
                            failure_type=type(error).__name__,
                            consecutive_failures=failures,
                            failure_recorded=failure_recorded,
                        )
                        return 1
                    retry_seconds = min(
                        self.settings.autonomous_failure_backoff_seconds
                        * 2 ** min(failures - 1, 12),
                        self.settings.autonomous_failure_backoff_max_seconds,
                    )
                    retry_at = datetime.now(UTC) + timedelta(seconds=retry_seconds)
                    retry_detail = {
                        "cycle_id": cycle_id,
                        "cycle_completed_at": datetime.now(UTC).isoformat(),
                        "cycle_result": "failed",
                        "failure_type": type(error).__name__,
                        "consecutive_failures": failures,
                        "failure_recorded": failure_recorded,
                        "next_cycle_at": retry_at.isoformat(),
                        "retry_in_seconds": retry_seconds,
                    }
                    self._notify("degraded", **retry_detail)
                    self._wait_with_heartbeats(
                        stop, retry_seconds, "degraded", retry_detail
                    )
                    continue
                failures = 0
                completed_at = datetime.now(UTC)
                cycle_result = getattr(result, "status", "completed")
                if stop.is_set():
                    # The cycle committed successfully before shutdown won the
                    # race. Preserve that durable result and only stop future
                    # work; cancellation is reserved for interrupted runs.
                    self._notify(
                        "stopping",
                        cycle_id=cycle_id,
                        cycle_completed_at=completed_at.isoformat(),
                        cycle_result=cycle_result,
                        failure_type=None,
                        consecutive_failures=0,
                    )
                    return 0
                if once:
                    self._notify(
                        "stopped",
                        cycle_id=cycle_id,
                        cycle_completed_at=completed_at.isoformat(),
                        cycle_result=cycle_result,
                        consecutive_failures=0,
                    )
                    return 0
                next_interval_seconds, cadence_reason = self._next_cycle_interval()
                next_cycle_at = completed_at + timedelta(seconds=next_interval_seconds)
                waiting_detail = {
                    "cycle_id": cycle_id,
                    "cycle_completed_at": completed_at.isoformat(),
                    "cycle_result": cycle_result,
                    "consecutive_failures": 0,
                    "next_cycle_at": next_cycle_at.isoformat(),
                    "next_interval_seconds": next_interval_seconds,
                    "cadence_reason": cadence_reason,
                    "retry_in_seconds": None,
                }
                self._notify("waiting", **waiting_detail)
                cycle_id = None
                wake_at = None
                self._wait_with_heartbeats(
                    stop,
                    next_interval_seconds,
                    "waiting",
                    waiting_detail,
                )
            return 0
        finally:
            runtime_closed = self._close_runtime(runtime)
            try:
                owner.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    ("alta-autonomous-runner",),
                )
            except psycopg.Error:
                pass
            finally:
                owner.close()
            if not runtime_closed:
                raise RuntimeError("autonomous runtime did not close cleanly")

    def _next_cycle_interval(self) -> tuple[int, str]:
        """Choose bounded cadence from durable work, never from model conviction."""

        try:
            with self.database.connect() as connection:
                open_position = connection.execute(
                    """SELECT EXISTS (
                    SELECT 1 FROM research.shadow_position
                    WHERE environment = 'shadow' AND status = 'open')"""
                ).fetchone()[0]
                unresolved_opportunity = connection.execute(
                    """SELECT EXISTS (
                    SELECT 1 FROM research.opportunity o
                    WHERE o.environment = 'shadow'
                      AND o.foundry_state = 'active'
                      AND cardinality(o.evidence_ids) > 0
                      AND NOT EXISTS (
                        SELECT 1
                        FROM unnest(o.evidence_ids) AS remembered(evidence_id)
                        JOIN research.evidence e ON e.id = remembered.evidence_id
                        JOIN research.raw r ON r.id = e.raw_id
                        WHERE lower(r.source) LIKE '%%fixture%%'
                           OR coalesce(r.body->>'fixture','false') = 'true'
                      ))"""
                ).fetchone()[0]
        except psycopg.Error:
            return self.settings.autonomous_interval_seconds, "base_fallback"
        return self.select_cycle_interval(
            base_seconds=self.settings.autonomous_interval_seconds,
            follow_up_seconds=self.settings.autonomous_follow_up_interval_seconds,
            position_seconds=self.settings.autonomous_position_interval_seconds,
            open_position=bool(open_position),
            unresolved_opportunity=bool(unresolved_opportunity),
        )

    @staticmethod
    def select_cycle_interval(
        *,
        base_seconds: int,
        follow_up_seconds: int,
        position_seconds: int,
        open_position: bool,
        unresolved_opportunity: bool,
    ) -> tuple[int, str]:
        if open_position:
            return min(base_seconds, position_seconds), "open_position"
        if unresolved_opportunity:
            return min(base_seconds, follow_up_seconds), "opportunity_backlog"
        return base_seconds, "base_research"

    def _wait_with_heartbeats(
        self,
        stop: threading.Event,
        seconds: float,
        status: str,
        detail: dict,
    ) -> None:
        deadline = self.monotonic() + seconds
        while not stop.is_set():
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return
            if self.waiter(
                stop, min(remaining, self.settings.autonomous_heartbeat_seconds)
            ):
                return
            self._notify(status, **detail)

    @staticmethod
    def _close_runtime(runtime) -> bool:
        if runtime is None:
            return True
        close = getattr(runtime, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                return False
        return True

    def _notify(self, status: str, **detail) -> None:
        if self.state_callback is not None:
            self.state_callback(
                status,
                {**detail, "heartbeat_at": datetime.now(UTC).isoformat()},
            )

    def _record_failure(
        self,
        cycle_id: str,
        known_at: datetime,
        error: Exception,
        consecutive_failures: int,
        *,
        retry_scheduled: bool,
    ) -> None:
        fingerprint = hashlib.sha256(
            f"{type(error).__module__}.{type(error).__name__}".encode()
        ).hexdigest()
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="mvp.pipeline.failed",
                    aggregate_type="mvp_pipeline",
                    aggregate_id=cycle_id,
                    environment=Environment.SHADOW,
                    known_at=known_at,
                    payload={
                        "cycle_id": cycle_id,
                        "error_type": type(error).__name__,
                        "error_fingerprint": fingerprint,
                        "consecutive_failures": consecutive_failures,
                        "retry_scheduled": retry_scheduled,
                    },
                    correlation_id=cycle_id,
                ),
            )
