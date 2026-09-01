import hashlib
import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg

from .b5_runtime import _append_event, _contract_event
from .autonomous_owner import (
    AutonomousOwnerBusy,
    acquire_autonomous_owner,
    release_autonomous_owner,
)
from .contracts import Environment, Settings
from .cycle_recovery import FrozenCycleSnapshotError
from .database import AutonomousFenceLost, Database
from .forward_evaluation import ForwardEvaluationLedger
from .live_runtime import LiveRuntime
from .paper_execution import PaperCapitalCircuitOpen
from .scout_repository import ScoutRepository

__all__ = [
    "AutonomousOwnerBusy",
    "AutonomousRunner",
    "acquire_autonomous_owner",
    "release_autonomous_owner",
]


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
        owner = acquire_autonomous_owner(self.database)
        failures = 0
        runtime = None
        cycle_id: str | None = None
        wake_at: datetime | None = None
        try:
            ScoutRepository(self.database).reconcile_expired_activity(datetime.now(UTC))
            while not stop.is_set():
                self.database.assert_autonomous_fence()
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
                except AutonomousFenceLost:
                    raise
                except PaperCapitalCircuitOpen as error:
                    failures += 1
                    failure_recorded = True
                    try:
                        self._record_failure(
                            cycle_id,
                            wake_at,
                            error,
                            failures,
                            retry_scheduled=False,
                        )
                    except Exception:
                        failure_recorded = False
                    self._notify(
                        "failed",
                        cycle_id=cycle_id,
                        cycle_completed_at=datetime.now(UTC).isoformat(),
                        cycle_result="capital_circuit_open",
                        failure_type=type(error).__name__,
                        consecutive_failures=failures,
                        failure_recorded=failure_recorded,
                    )
                    return 1
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
                    terminal_snapshot_error = isinstance(
                        error, FrozenCycleSnapshotError
                    )
                    failure_recorded = True
                    try:
                        self._record_failure(
                            cycle_id,
                            wake_at,
                            error,
                            failures,
                            retry_scheduled=not once and not terminal_snapshot_error,
                        )
                    except Exception:
                        failure_recorded = False
                    snapshot_terminalized = True
                    if terminal_snapshot_error:
                        try:
                            ScoutRepository(self.database).terminalize_snapshot_cycle(
                                cycle_id
                            )
                        except Exception:
                            snapshot_terminalized = False
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
                    if not snapshot_terminalized:
                        self._notify(
                            "failed",
                            cycle_id=cycle_id,
                            cycle_completed_at=datetime.now(UTC).isoformat(),
                            cycle_result="snapshot_terminalization_failed",
                            failure_type=type(error).__name__,
                            consecutive_failures=failures,
                            failure_recorded=failure_recorded,
                        )
                        return 1
                    if once:
                        self._notify(
                            "failed",
                            cycle_id=cycle_id,
                            cycle_completed_at=datetime.now(UTC).isoformat(),
                            cycle_result=(
                                "quarantined" if terminal_snapshot_error else "failed"
                            ),
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
                        "cycle_result": (
                            "quarantined" if terminal_snapshot_error else "failed"
                        ),
                        "failure_type": type(error).__name__,
                        "consecutive_failures": failures,
                        "failure_recorded": failure_recorded,
                        "next_cycle_at": retry_at.isoformat(),
                        "retry_in_seconds": retry_seconds,
                        "replacement_cycle_scheduled": terminal_snapshot_error,
                    }
                    self._notify("degraded", **retry_detail)
                    if terminal_snapshot_error:
                        cycle_id = None
                        wake_at = None
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
        except AutonomousFenceLost:
            self._notify(
                "failed",
                cycle_id=cycle_id,
                cycle_completed_at=datetime.now(UTC).isoformat(),
                cycle_result="owner_lost",
                failure_type="AutonomousFenceLost",
                consecutive_failures=failures,
                failure_recorded=False,
            )
            return 1
        finally:
            runtime_closed = self._close_runtime(runtime)
            release_autonomous_owner(owner)
            if not runtime_closed:
                raise RuntimeError("autonomous runtime did not close cleanly")

    def _next_cycle_interval(self) -> tuple[int, str]:
        """Choose bounded cadence from durable work, never from model conviction."""

        known_at = datetime.now(UTC)
        try:
            with self.database.connect() as connection:
                state = connection.execute(
                    """WITH latest_continuity AS (
                      SELECT run.cycle_id,
                        (run.frozen_input->'input'->'opportunity_continuity'
                          ->>'known_at')::timestamptz AS known_at,
                        nullif(
                          run.frozen_input->'input'->'opportunity_continuity'
                            ->>'next_research_due_at',
                          ''
                        )::timestamptz AS next_research_due_at
                      FROM research.run run
                      WHERE run.environment = 'shadow'
                        AND run.cycle_id LIKE 'live-%%'
                        AND jsonb_typeof(
                          run.frozen_input->'input'->'opportunity_continuity'
                        ) = 'object'
                      ORDER BY
                        (run.frozen_input->'input'->'opportunity_continuity'
                          ->>'known_at')::timestamptz DESC,
                        run.created_at DESC,
                        run.id DESC
                      LIMIT 1
                    ), continuity AS (
                      SELECT cycle_id, known_at, next_research_due_at
                      FROM latest_continuity
                      UNION ALL
                      SELECT NULL::text, NULL::timestamptz, NULL::timestamptz
                      WHERE NOT EXISTS (SELECT 1 FROM latest_continuity)
                    ), priority_ids AS (
                      SELECT DISTINCT queue_item->>'opportunity_id' AS opportunity_id
                      FROM latest_continuity latest
                      JOIN research.run run
                        ON run.environment = 'shadow'
                       AND run.cycle_id = latest.cycle_id
                      CROSS JOIN LATERAL jsonb_array_elements(
                        CASE WHEN jsonb_typeof(
                          run.frozen_input->'input'->'opportunity_drive'
                            ->'research_queue'
                        ) = 'array'
                        THEN run.frozen_input->'input'->'opportunity_drive'
                          ->'research_queue'
                        ELSE '[]'::jsonb END
                      ) AS queue_item
                      WHERE jsonb_typeof(queue_item) = 'object'
                        AND queue_item ? 'opportunity_id'
                    ), opportunity_state AS (
                      SELECT opportunity.id, opportunity.status,
                        opportunity.foundry_state, opportunity.known_at,
                        coalesce(
                          deadline.decision_deadline_at,
                          opportunity.known_at
                            + make_interval(days => opportunity.horizon_days)
                        ) AS decision_deadline_at
                      FROM research.opportunity opportunity
                      LEFT JOIN LATERAL (
                        SELECT min((pillar->>'due_at')::timestamptz)
                          AS decision_deadline_at
                        FROM research.candidate candidate,
                          LATERAL jsonb_array_elements(
                            coalesce(
                              candidate.foundry_snapshot->'thesis_pillars',
                              '[]'::jsonb
                            )
                          ) pillar
                        WHERE candidate.id = ANY(opportunity.member_candidate_ids)
                          AND pillar->>'due_at' ~
                            '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
                      ) deadline ON true
                      WHERE opportunity.environment = 'shadow'
                        AND opportunity.known_at <= %s
                        AND cardinality(opportunity.evidence_ids) > 0
                        AND NOT EXISTS (
                          SELECT 1
                          FROM unnest(opportunity.evidence_ids)
                            AS remembered(evidence_id)
                          JOIN research.evidence evidence
                            ON evidence.id = remembered.evidence_id
                          JOIN research.raw raw ON raw.id = evidence.raw_id
                          WHERE lower(raw.source) LIKE '%%fixture%%'
                             OR coalesce(raw.body->>'fixture','false') = 'true'
                        )
                    ), researchable AS (
                      SELECT state.*
                      FROM opportunity_state state
                      WHERE state.foundry_state = 'active'
                        AND state.status IN ('forming', 'ranked')
                        AND state.decision_deadline_at > %s
                    )
                    SELECT
                      EXISTS (
                        SELECT 1 FROM research.shadow_position position
                        WHERE position.environment = 'shadow'
                          AND position.status = 'open'
                      ),
                      EXISTS (
                        SELECT 1 FROM researchable item
                        JOIN priority_ids priority
                          ON priority.opportunity_id = item.id
                      ),
                      continuity.next_research_due_at,
                      EXISTS (SELECT 1 FROM researchable),
                      EXISTS (
                        SELECT 1 FROM researchable item
                        WHERE continuity.known_at IS NULL
                           OR item.known_at > continuity.known_at
                      )
                    FROM continuity""",
                    (known_at, known_at),
                ).fetchone()
        except psycopg.Error:
            return self.settings.autonomous_interval_seconds, "base_fallback"
        if state is None:
            return self.settings.autonomous_interval_seconds, "base_fallback"
        (
            open_position,
            priority_queue_pending,
            next_research_due_at,
            researchable_opportunity,
            new_researchable_opportunity,
        ) = state
        return self.select_cycle_interval(
            base_seconds=self.settings.autonomous_interval_seconds,
            follow_up_seconds=self.settings.autonomous_follow_up_interval_seconds,
            position_seconds=self.settings.autonomous_position_interval_seconds,
            open_position=bool(open_position),
            unresolved_opportunity=bool(priority_queue_pending),
            new_researchable_opportunity=bool(new_researchable_opportunity),
            known_at=known_at,
            next_research_due_at=(
                next_research_due_at if researchable_opportunity else None
            ),
        )

    @staticmethod
    def select_cycle_interval(
        *,
        base_seconds: int,
        follow_up_seconds: int,
        position_seconds: int,
        open_position: bool,
        unresolved_opportunity: bool,
        known_at: datetime | None = None,
        next_research_due_at: datetime | None = None,
        new_researchable_opportunity: bool = False,
    ) -> tuple[int, str]:
        if open_position:
            return min(base_seconds, position_seconds), "open_position"
        if unresolved_opportunity or new_researchable_opportunity:
            return min(base_seconds, follow_up_seconds), "opportunity_backlog"
        if next_research_due_at is not None:
            if known_at is None:
                raise ValueError("deferred Opportunity cadence requires known_at")
            for value in (known_at, next_research_due_at):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError("Opportunity cadence timestamps must be aware")
            seconds_until_due = math.ceil(
                (next_research_due_at - known_at).total_seconds()
            )
            if seconds_until_due <= 0:
                return min(base_seconds, follow_up_seconds), "opportunity_backlog"
            if seconds_until_due < base_seconds:
                return max(1, seconds_until_due), "opportunity_due"
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
