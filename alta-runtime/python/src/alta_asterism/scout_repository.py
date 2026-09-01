import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from .alpha_feedback import AlphaFeedbackProjector
from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .cycle_recovery import FrozenCycleSnapshotError, frozen_wake_hash
from .database import Database
from .ingest import redact
from .mind_worker import (
    ModelTurn,
    ScoutDeadlineExceeded,
    _canonical_hash,
    _utf8_prefix,
)
from .market_research_projection import MarketResearchAgendaProjector
from .research_diligence import build_research_diligence
from .research_agenda import ResearchQueueInput, build_research_queue
from .research_incentive import build_research_incentives
from .research_attention import (
    ResearchAttentionProjector,
    apply_research_attention_to_market_agenda,
)
from .scouts import (
    CandidateOutput,
    FrozenScoutInput,
    SCOUTS,
    SCOUT_OUTPUT_ADAPTER,
    ScoutOutput,
    ScoutRunSpec,
)
from .trader_mind import TraderMindMemory, bounded_mind_summary, experience_summary

# App Server structured streams can fail validation before a ModelTurn exists.
# Three total attempts keep recovery bounded while tolerating two identical,
# pre-output transport/schema failures observed under concurrent Scout load.
MAX_SCOUT_ATTEMPTS = 3


@dataclass(frozen=True)
class ScoutRunOutcome:
    run_id: str
    scout_id: str
    status: str
    output: ScoutOutput | None
    error_code: str | None


def _frozen_summary(value: str) -> str:
    normalized = " ".join(value.split())
    return _utf8_prefix(normalized, 480).rstrip()


class ScoutRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def validate_frozen_input(self, frozen_input: FrozenScoutInput) -> None:
        """Validate every role-scoped snapshot against its durable sources."""
        self._validate_canonical_contract(frozen_input)
        expected = {item.evidence_id: item for item in frozen_input.evidence}
        expected_minds = {
            item.scout_id: item for item in frozen_input.trader_mind_memories
        }
        rows, mind_rows, historical_rows = self._load_frozen_rows(
            frozen_input, expected, expected_minds
        )
        self._validate_evidence(frozen_input, expected, rows)
        self._validate_minds(expected_minds, mind_rows, historical_rows)
        self._validate_feedback_and_incentives(frozen_input)
        self._validate_market_agenda(frozen_input)
        self._validate_attention(frozen_input)

    @staticmethod
    def _validate_canonical_contract(frozen_input: FrozenScoutInput) -> None:
        # model_copy is used while fitting role-scoped snapshots; rebuild the
        # contract here so no unchecked update can cross persistence.
        validated = FrozenScoutInput.model_validate(
            frozen_input.model_dump(mode="python")
        )
        if validated != frozen_input:
            raise ValueError("frozen Scout input failed canonical validation")
        expected_queue = build_research_queue(
            wake_at=frozen_input.known_at,
            opportunities=tuple(
                ResearchQueueInput(
                    opportunity_id=item.opportunity_id,
                    status=item.status,
                    known_at=item.known_at,
                    horizon_days=item.horizon_days,
                    decision_deadline_at=item.decision_deadline_at,
                    research_questions=item.research_questions,
                )
                for item in frozen_input.prior_opportunities
            ),
        )
        if frozen_input.opportunity_drive.research_queue != expected_queue:
            raise ValueError(
                "durable research director queue does not match registry memory"
            )

    def _load_frozen_rows(self, frozen_input, expected, expected_minds):
        with self.database.connect() as connection:
            rows = (
                connection.execute(
                    """SELECT e.id, e.raw_id, r.source, r.content_hash, e.known_at,
                    e.summary, CASE
                    WHEN r.body->>'origin_fingerprint' ~ '^[a-f0-9]{64}$'
                    THEN r.body->>'origin_fingerprint' END
                    FROM research.evidence e
                    JOIN research.raw r ON r.id = e.raw_id
                    WHERE e.id = ANY(%s)""",
                    (list(expected),),
                ).fetchall()
                if expected
                else []
            )
            mind_rows = (
                connection.execute(
                    """SELECT scout_id, version, known_at, turn_count, rolling_summary
                    FROM research.mind_state
                    WHERE environment = %s AND scout_id = ANY(%s)""",
                    (frozen_input.environment.value, list(expected_minds)),
                ).fetchall()
                if expected_minds
                else []
            )
            historical_rows = (
                connection.execute(
                    """SELECT frozen_input->'input'->'trader_mind_memories'
                    FROM research.run
                    WHERE environment = %s AND cycle_id = %s
                      AND frozen_input ? 'input'""",
                    (frozen_input.environment.value, frozen_input.wake_id),
                ).fetchall()
                if expected_minds
                else []
            )
        return rows, mind_rows, historical_rows

    @staticmethod
    def _validate_evidence(frozen_input, expected, rows) -> None:
        actual = {
            row[0]: (
                row[1],
                row[2],
                row[3],
                row[4],
                _frozen_summary(row[5]),
                row[6],
            )
            for row in rows
        }
        for evidence_id, item in expected.items():
            durable = (
                item.raw_id,
                item.source,
                item.content_hash,
                item.known_at,
                item.summary,
                item.origin_fingerprint,
            )
            if actual.get(evidence_id) != durable:
                raise ValueError("frozen evidence snapshot does not match PostgreSQL")
            if item.known_at > frozen_input.known_at:
                raise ValueError("frozen evidence is newer than run known_at")

    @staticmethod
    def _validate_minds(expected_minds, mind_rows, historical_rows) -> None:
        current = {
            row[0]: (row[1], row[2], row[3], bounded_mind_summary(row[4]))
            for row in mind_rows
        }
        historical: dict[str, TraderMindMemory] = {}
        for row in historical_rows:
            for value in row[0] or []:
                memory = TraderMindMemory.model_validate(value)
                existing = historical.get(memory.scout_id)
                if existing is not None and existing != memory:
                    raise ValueError(
                        "durable Scout snapshots disagree on Trader Mind memory"
                    )
                historical[memory.scout_id] = memory
        for scout_id, item in expected_minds.items():
            expected = (item.version, item.known_at, item.turn_count, item.summary)
            if current.get(scout_id) != expected and historical.get(scout_id) != item:
                raise ValueError("frozen Trader Mind memory does not match PostgreSQL")

    def _validate_feedback_and_incentives(self, frozen_input: FrozenScoutInput) -> None:
        expected_feedback = {
            item.scout_id: item for item in frozen_input.alpha_feedback
        }
        expected_incentives = {
            item.scout_id: item for item in frozen_input.research_incentives
        }
        if not expected_feedback and not expected_incentives:
            return
        projected = AlphaFeedbackProjector(self.database).at(
            frozen_input.environment, frozen_input.known_at
        )
        actual_feedback = {item.scout_id: item for item in projected}
        if any(
            actual_feedback.get(scout_id) != item
            for scout_id, item in expected_feedback.items()
        ):
            raise ValueError(
                "frozen Trader Mind Alpha feedback does not match PostgreSQL"
            )
        scout_ids = tuple(expected_incentives)
        actual_incentives = {
            item.scout_id: item
            for item in build_research_incentives(
                tuple(
                    actual_feedback[scout_id]
                    for scout_id in scout_ids
                    if scout_id in actual_feedback
                ),
                scout_ids=scout_ids,
            )
        }
        if any(
            actual_incentives.get(scout_id) != item
            for scout_id, item in expected_incentives.items()
        ):
            raise ValueError(
                "frozen Trader Mind research incentive does not match outcomes"
            )

    def _validate_market_agenda(self, frozen_input: FrozenScoutInput) -> None:
        expected = frozen_input.market_research_agenda
        if expected is None:
            return
        projected = MarketResearchAgendaProjector(self.database).at(
            frozen_input.environment,
            frozen_input.universe,
            frozen_input.known_at,
        )
        if expected.model_copy(update={"seeds": ()}) != projected.model_copy(
            update={"seeds": ()}
        ):
            raise ValueError("frozen market research agenda does not match PostgreSQL")
        projected_seeds = {item.seed_id: item for item in projected.seeds}
        if any(projected_seeds.get(item.seed_id) != item for item in expected.seeds):
            raise ValueError("frozen market research seed does not match PostgreSQL")

    def _validate_attention(self, frozen_input: FrozenScoutInput) -> None:
        expected = frozen_input.research_attention_portfolio
        if expected is None:
            return
        projected = ResearchAttentionProjector(self.database).at(
            frozen_input.environment.value,
            frozen_input.universe,
            tuple(item.scout_id for item in expected.assignments),
            frozen_input.known_at,
            {item.scout_id: item.alpha_archetypes for item in SCOUTS},
        )
        if projected != expected:
            raise ValueError(
                "frozen research attention portfolio does not match PostgreSQL"
            )
        agenda = frozen_input.market_research_agenda
        if (
            agenda is not None
            and apply_research_attention_to_market_agenda(agenda, expected) != agenda
        ):
            raise ValueError(
                "frozen market research agenda conflicts with attention seats"
            )

    def reconcile_expired_activity(self, known_at: datetime) -> tuple[int, int]:
        """Fail abandoned Scout work after the scheduler acquires sole ownership."""
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise ValueError("reconciliation known_at must be timezone-aware")
        with self.database.connect() as connection:
            run_ids = [
                row[0]
                for row in connection.execute(
                    """SELECT r.id FROM research.run r
                    JOIN ops.job j ON j.id = r.job_id
                    WHERE r.environment = 'shadow' AND r.status = 'running'
                      AND r.deadline_at < %s AND j.kind = 'scout_batch'
                    ORDER BY r.id""",
                    (known_at,),
                ).fetchall()
            ]
        for run_id in run_ids:
            self.fail(
                run_id,
                "recovery_deadline_expired",
                error=ScoutDeadlineExceeded(
                    "abandoned Scout deadline expired before scheduler recovery"
                ),
            )
        with self.database.connect() as connection:
            jobs = connection.execute(
                """UPDATE ops.job j SET status = 'failed'
                WHERE j.environment = 'shadow' AND j.kind = 'scout_batch'
                  AND j.status = 'running'
                  AND NOT EXISTS (
                    SELECT 1 FROM research.run r
                    WHERE r.job_id = j.id AND r.status = 'running'
                  ) RETURNING j.id"""
            ).fetchall()
        return len(run_ids), len(jobs)

    def cancel_cycle(
        self,
        cycle_id: str,
        *,
        environment: str = "shadow",
        error_code: str = "operator_shutdown",
    ) -> tuple[int, int]:
        """Cancel only in-flight work for one frozen cycle.

        Planned service shutdown is an operational cancellation, not an App
        Server failure.  The cycle identity keeps this transition from touching
        unrelated replay or manual work.
        """

        with self.database.connect() as connection:
            rows = connection.execute(
                """UPDATE research.run SET status = 'cancelled', error_code = %s
                WHERE environment = %s AND cycle_id = %s AND status = 'running'
                RETURNING job_id""",
                (error_code[:64], environment, cycle_id),
            ).fetchall()
            job_ids = sorted({row[0] for row in rows if row[0] is not None})
            jobs = (
                connection.execute(
                    """UPDATE ops.job SET status = 'cancelled'
                    WHERE id = ANY(%s) AND status = 'running' RETURNING id""",
                    (job_ids,),
                ).fetchall()
                if job_ids
                else []
            )
        return len(rows), len(jobs)

    def start_batch(
        self,
        batch_id: str,
        frozen_input: FrozenScoutInput,
        source_postures: dict[str, str],
    ) -> str:
        if not source_postures or any(
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(posture, str)
            or not posture
            for source_id, posture in source_postures.items()
        ):
            raise ValueError("Scout batch requires non-empty source postures")
        normalized_postures = dict(sorted(source_postures.items()))
        job_id = "job_" + hashlib.sha256(batch_id.encode()).hexdigest()[:32]
        snapshot_id = (
            "scout_wake_"
            + hashlib.sha256(frozen_input.wake_id.encode()).hexdigest()[:32]
        )
        snapshot_hash = frozen_wake_hash(frozen_input, normalized_postures)
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO ops.job
                (id, environment, version, known_at, kind, status, subject_id)
                VALUES (%s,%s,1,%s,'scout_batch','running',%s)
                ON CONFLICT (id) DO NOTHING""",
                (
                    job_id,
                    frozen_input.environment.value,
                    frozen_input.known_at,
                    frozen_input.wake_id,
                ),
            )
            job = connection.execute(
                """SELECT environment::text, known_at, kind, status, subject_id,
                attempt_count FROM ops.job WHERE id = %s""",
                (job_id,),
            ).fetchone()
            expected_job = (
                frozen_input.environment.value,
                frozen_input.known_at,
                "scout_batch",
                frozen_input.wake_id,
            )
            if job is None or (job[0], job[1], job[2], job[4]) != expected_job:
                raise FrozenCycleSnapshotError(
                    "Scout batch job identity conflicts with its frozen wake"
                )
            connection.execute(
                """INSERT INTO research.scout_batch_snapshot
                (id, environment, version, known_at, job_id, cycle_id,
                 snapshot_hash, frozen_input, source_postures)
                VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING""",
                (
                    snapshot_id,
                    frozen_input.environment.value,
                    frozen_input.known_at,
                    job_id,
                    frozen_input.wake_id,
                    snapshot_hash,
                    Jsonb(frozen_input.model_dump(mode="json")),
                    Jsonb(normalized_postures),
                ),
            )
            snapshot = connection.execute(
                """SELECT environment::text, known_at, job_id, cycle_id,
                snapshot_hash, frozen_input, source_postures
                FROM research.scout_batch_snapshot WHERE id = %s""",
                (snapshot_id,),
            ).fetchone()
            expected_snapshot = (
                frozen_input.environment.value,
                frozen_input.known_at,
                job_id,
                frozen_input.wake_id,
                snapshot_hash,
            )
            if snapshot is None or snapshot[:5] != expected_snapshot:
                raise FrozenCycleSnapshotError(
                    "Scout batch global frozen snapshot identity conflict"
                )
            if _canonical_hash(snapshot[5]) != _canonical_hash(
                frozen_input.model_dump(mode="json")
            ) or _canonical_hash(snapshot[6]) != _canonical_hash(normalized_postures):
                raise FrozenCycleSnapshotError(
                    "Scout batch global frozen snapshot content conflict"
                )
            if job[3] in {"failed", "cancelled"}:
                reopened = connection.execute(
                    """UPDATE ops.job SET status = 'running',
                    version = version + 1, attempt_count = attempt_count + 1
                    WHERE id = %s AND status = %s
                    RETURNING attempt_count""",
                    (job_id, job[3]),
                ).fetchone()
                if reopened is None:
                    raise FrozenCycleSnapshotError(
                        "Scout batch job changed during recovery"
                    )
                _append_event(
                    connection,
                    _contract_event(
                        event_type="scout.batch.reopened",
                        aggregate_type="scout_batch",
                        aggregate_id=job_id,
                        environment=frozen_input.environment,
                        known_at=frozen_input.known_at,
                        payload={
                            "cycle_id": frozen_input.wake_id,
                            "job_id": job_id,
                            "from_status": job[3],
                            "attempt_count": reopened[0],
                        },
                        correlation_id=frozen_input.wake_id,
                    ),
                )
            elif job[3] not in {"running", "succeeded"}:
                raise FrozenCycleSnapshotError(
                    "Scout batch job has an unrecoverable status"
                )
        return job_id

    def start_run(self, job_id: str, spec: ScoutRunSpec) -> bool:
        return self.start_runs(job_id, (spec,))[0]

    def start_runs(
        self, job_id: str, specs: tuple[ScoutRunSpec, ...]
    ) -> tuple[bool, ...]:
        """Atomically validate/reserve a complete frozen Scout snapshot set."""

        if not specs:
            return ()
        run_ids = tuple(spec.run_id for spec in specs)
        roles = tuple(spec.scout.scout_id for spec in specs)
        if len(set(run_ids)) != len(run_ids) or len(set(roles)) != len(roles):
            raise ValueError("Scout snapshot set contains duplicate identity")
        with self.database.connect() as connection:
            return tuple(self._start_run(connection, job_id, spec) for spec in specs)

    @staticmethod
    def _start_run(connection, job_id: str, spec: ScoutRunSpec) -> bool:
        inserted = connection.execute(
            """INSERT INTO research.run
            (id, environment, version, known_at, job_id, cycle_id, role, status,
             input_hash, frozen_input, budget, deadline_at, prompt_version,
             tool_catalog_version, model_provider, model_id, trace_id,
             tool_provenance, evidence_ids, attempt_count)
            VALUES (%s,%s,1,%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,'[]'::jsonb,%s,1)
            ON CONFLICT (id) DO NOTHING RETURNING id""",
            (
                spec.run_id,
                spec.frozen_input.environment.value,
                spec.frozen_input.known_at,
                job_id,
                spec.frozen_input.wake_id,
                spec.scout.scout_id,
                spec.input_hash,
                Jsonb(spec.persisted_input()),
                Jsonb(spec.budget.model_dump(mode="json")),
                spec.deadline_at,
                spec.prompt_version,
                spec.tool_catalog_version,
                spec.model_provider,
                spec.model_id,
                spec.trace_id,
                [item.evidence_id for item in spec.frozen_input.evidence],
            ),
        ).fetchone()
        if inserted is not None:
            return True
        existing = connection.execute(
            """SELECT environment::text, job_id, cycle_id, role, input_hash, frozen_input,
            budget, prompt_version, tool_catalog_version, model_provider, model_id,
            trace_id, evidence_ids, status, attempt_count
            FROM research.run WHERE id = %s""",
            (spec.run_id,),
        ).fetchone()
        if existing is None:
            raise FrozenCycleSnapshotError(
                "Scout run identity disappeared during snapshot reservation"
            )
        expected = (
            spec.frozen_input.environment.value,
            job_id,
            spec.frozen_input.wake_id,
            spec.scout.scout_id,
            spec.input_hash,
            spec.persisted_input(),
            spec.budget.model_dump(mode="json"),
            spec.prompt_version,
            spec.tool_catalog_version,
            spec.model_provider,
            spec.model_id,
            spec.trace_id,
        )
        identity_checks = {
            "identity": existing[:5] == expected[:5],
            "frozen_input": _canonical_hash(existing[5])
            == _canonical_hash(expected[5]),
            "budget": _canonical_hash(existing[6]) == _canonical_hash(expected[6]),
            "runtime_contract": existing[7:12] == expected[7:12],
        }
        mismatches = [name for name, matches in identity_checks.items() if not matches]
        if mismatches:
            raise FrozenCycleSnapshotError(
                "Scout run ID already has different frozen input fields: "
                + ",".join(mismatches)
            )
        if (
            existing[13] in {"failed", "cancelled"}
            and existing[14] < MAX_SCOUT_ATTEMPTS
        ):
            connection.execute(
                """UPDATE research.run SET status = 'running',
                error_code = NULL, deadline_at = %s,
                tool_provenance = '[]'::jsonb, actual_usage = '{}'::jsonb,
                thread_id = NULL, turn_id = NULL, latency_ms = NULL,
                attempt_count = attempt_count + 1
                WHERE id = %s""",
                (spec.deadline_at, spec.run_id),
            )
            return True
        return False

    def terminalize_snapshot_cycle(
        self,
        cycle_id: str,
        *,
        environment: str = "shadow",
        error_code: str = "frozen_snapshot_inconsistent",
    ) -> tuple[int, int]:
        """Fail closed on a cycle whose immutable Scout set cannot be trusted."""

        with self.database.connect() as connection:
            runs = connection.execute(
                """UPDATE research.run SET status = 'cancelled', error_code = %s
                WHERE environment = %s AND cycle_id = %s
                  AND status IN ('queued','running') RETURNING id""",
                (error_code[:64], environment, cycle_id),
            ).fetchall()
            jobs = connection.execute(
                """UPDATE ops.job SET status = 'failed'
                WHERE environment = %s AND kind = 'scout_batch'
                  AND subject_id = %s AND status IN ('queued','running')
                RETURNING id""",
                (environment, cycle_id),
            ).fetchall()
        return len(runs), len(jobs)

    def existing_outcome(self, spec: ScoutRunSpec) -> ScoutRunOutcome:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT r.status, r.error_code, a.content
                FROM research.run r
                LEFT JOIN research.run_artifact a
                  ON a.run_id = r.id AND a.artifact_kind = 'scout_output'
                WHERE r.id = %s ORDER BY a.version DESC NULLS LAST LIMIT 1""",
                (spec.run_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Scout run disappeared during recovery")
        status, error_code, content = row
        if status == "succeeded":
            if content is None:
                raise ValueError("succeeded Scout run is missing its durable artifact")
            output = SCOUT_OUTPUT_ADAPTER.validate_python(content["output"])
            return ScoutRunOutcome(
                run_id=spec.run_id,
                scout_id=spec.scout.scout_id,
                status="succeeded",
                output=output,
                error_code=None,
            )
        if status == "running":
            self.fail(spec.run_id, "recovery_incomplete")
            error_code = "recovery_incomplete"
        return ScoutRunOutcome(
            run_id=spec.run_id,
            scout_id=spec.scout.scout_id,
            status="failed",
            output=None,
            error_code=error_code or "unknown_failure",
        )

    def complete(
        self, spec: ScoutRunSpec, turn: ModelTurn, output: ScoutOutput
    ) -> None:
        evidence_ids = list(output.evidence_ids)
        provenance = [item.model_dump(mode="json") for item in turn.tools]
        decision_known_at = turn.completed_at or spec.frozen_input.known_at
        diligence = build_research_diligence(
            tools=turn.tools,
            discoveries=turn.discovered_evidence,
            frozen_source_locators=tuple(
                item.source_locator
                for item in spec.frozen_input.evidence
                if item.evidence_id in output.evidence_ids
            ),
            frozen_origin_fingerprints=tuple(
                item.origin_fingerprint
                for item in spec.frozen_input.evidence
                if item.evidence_id in output.evidence_ids
                and item.origin_fingerprint is not None
            ),
            output=output,
        )
        artifact = {
            "schema": "alta.scout-output.v5",
            "output": output.model_dump(mode="json"),
            "research_diligence": diligence.model_dump(mode="json"),
        }
        with self.database.connect() as connection:
            updated = connection.execute(
                """UPDATE research.run SET status = 'succeeded', error_code = NULL,
                tool_provenance = %s, evidence_ids = %s, output_kind = %s,
                thread_id = %s, turn_id = %s, actual_usage = %s, latency_ms = %s
                WHERE id = %s AND status = 'running' RETURNING id""",
                (
                    Jsonb(provenance),
                    evidence_ids,
                    output.kind,
                    turn.thread_id,
                    turn.turn_id,
                    Jsonb(turn.usage),
                    turn.latency_ms,
                    spec.run_id,
                ),
            ).fetchone()
            if updated is None:
                raise ValueError("Scout run completion is not in running state")
            self._insert_artifact(
                connection,
                spec,
                artifact_kind="scout_output",
                schema_version="alta.scout-output.v5",
                content=artifact,
            )
            if isinstance(output, CandidateOutput):
                candidate_id = (
                    "candidate_"
                    + _canonical_hash(
                        {
                            "run_id": spec.run_id,
                            "output": output.model_dump(mode="json"),
                        }
                    )[:32]
                )
                connection.execute(
                    """INSERT INTO research.candidate
                    (id, environment, version, known_at, run_id, alpha_archetype,
                     title, why_now,
                     expectation, variant_wedge, falsifier, horizon_days,
                     confidence, evidence_ids)
                    VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING""",
                    (
                        candidate_id,
                        spec.frozen_input.environment.value,
                        decision_known_at,
                        spec.run_id,
                        output.alpha_archetype,
                        output.title,
                        output.why_now,
                        output.expectation,
                        output.variant_wedge,
                        output.falsifier,
                        output.horizon,
                        output.confidence,
                        evidence_ids,
                    ),
                )
            summary = experience_summary(
                previous_summary=next(
                    (
                        item.summary
                        for item in spec.frozen_input.trader_mind_memories
                        if item.scout_id == spec.scout.scout_id
                    ),
                    None,
                ),
                outcome=output.kind,
                finding=(
                    output.title
                    if isinstance(output, CandidateOutput)
                    else output.reason
                ),
                why_now=(
                    output.why_now if isinstance(output, CandidateOutput) else None
                ),
                first_rejection=(
                    output.first_rejection or output.falsifier
                    if isinstance(output, CandidateOutput)
                    else None
                ),
                completed_tools=tuple(
                    item.tool_name for item in turn.tools if item.status == "completed"
                ),
                collected_sources=len(turn.discovered_evidence),
                research_mode=output.research_mode,
            )
            mind_id = (
                "mind_"
                + _canonical_hash(
                    [spec.frozen_input.environment.value, spec.scout.scout_id]
                )[:32]
            )
            connection.execute(
                """INSERT INTO research.mind_state
                (id, environment, version, known_at, scout_id, thread_id,
                 turn_count, context_tokens, started_at, rolling_summary,
                 evidence_ids, model_provider, model_id, prompt_version,
                 tool_catalog_version)
                VALUES (%s,%s,1,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (environment, scout_id) DO UPDATE SET
                version = research.mind_state.version + 1,
                known_at = EXCLUDED.known_at,
                thread_id = EXCLUDED.thread_id,
                turn_count = research.mind_state.turn_count + 1,
                context_tokens = research.mind_state.context_tokens
                    + EXCLUDED.context_tokens,
                rolling_summary = EXCLUDED.rolling_summary,
                evidence_ids = EXCLUDED.evidence_ids,
                model_provider = EXCLUDED.model_provider,
                model_id = EXCLUDED.model_id,
                prompt_version = EXCLUDED.prompt_version,
                tool_catalog_version = EXCLUDED.tool_catalog_version""",
                (
                    mind_id,
                    spec.frozen_input.environment.value,
                    spec.frozen_input.known_at,
                    spec.scout.scout_id,
                    turn.thread_id,
                    turn.total_tokens or 0,
                    spec.frozen_input.known_at,
                    summary,
                    evidence_ids,
                    spec.model_provider,
                    spec.model_id,
                    spec.prompt_version,
                    spec.tool_catalog_version,
                ),
            )

    def collect_tool_evidence(
        self,
        spec: ScoutRunSpec,
        turn: ModelTurn,
        output: ScoutOutput,
    ) -> ScoutOutput:
        if not isinstance(output, CandidateOutput) or not output.tool_evidence_refs:
            return output
        available = {
            (item.tool_call_id, item.source_locator): item
            for item in turn.discovered_evidence
        }
        known_at = turn.completed_at or spec.frozen_input.known_at
        promoted: list[str] = []
        with self.database.connect() as connection:
            for reference in output.tool_evidence_refs:
                discovery = available.get(
                    (reference.tool_call_id, reference.source_locator)
                )
                if discovery is None:
                    raise ValueError("tool evidence disappeared before collection")
                source = f"agent_tool:{discovery.tool_name}"[:64]
                source_key = (
                    f"{discovery.tool_call_id}:"
                    f"{_canonical_hash(discovery.source_locator)[:32]}"
                )
                raw_id = "raw_" + _canonical_hash(
                    [
                        spec.frozen_input.environment.value,
                        source,
                        source_key,
                        discovery.content_hash,
                    ]
                )
                row = connection.execute(
                    """INSERT INTO research.raw
                    (id, environment, version, known_at, source, source_key,
                     content_hash, body)
                    VALUES (%s,%s,1,%s,%s,%s,%s,%s)
                    ON CONFLICT (environment, source, source_key, content_hash)
                    DO NOTHING RETURNING id""",
                    (
                        raw_id,
                        spec.frozen_input.environment.value,
                        known_at,
                        source,
                        source_key,
                        discovery.content_hash,
                        Jsonb(discovery.content),
                    ),
                ).fetchone()
                if row is None:
                    row = connection.execute(
                        """SELECT id FROM research.raw
                        WHERE environment = %s AND source = %s
                        AND source_key = %s AND content_hash = %s""",
                        (
                            spec.frozen_input.environment.value,
                            source,
                            source_key,
                            discovery.content_hash,
                        ),
                    ).fetchone()
                evidence_id = "evidence_" + _canonical_hash([row[0], "unknown"])[:32]
                summary = _utf8_prefix(
                    (
                        f"Untrusted {discovery.tool_name} result for "
                        f"{discovery.source_locator}: {discovery.content['result_text']}"
                    ),
                    1_800,
                )
                connection.execute(
                    """INSERT INTO research.evidence
                    (id, environment, version, known_at, raw_id, stance, summary,
                     event_time)
                    VALUES (%s,%s,1,%s,%s,'unknown',%s,NULL)
                    ON CONFLICT (id) DO NOTHING""",
                    (
                        evidence_id,
                        spec.frozen_input.environment.value,
                        known_at,
                        row[0],
                        summary,
                    ),
                )
                promoted.append(evidence_id)
        evidence_ids = tuple(dict.fromkeys((*output.evidence_ids, *promoted)))
        if len(evidence_ids) > 20:
            raise ValueError("collected evidence exceeds Candidate limit")
        # Keep the exact, validated tool references in the durable Scout artifact.
        # The promoted evidence IDs are the facts consumed downstream; the refs are
        # retained only so research diligence can prove which completed calls the
        # Candidate actually bound to its thesis.
        return output.model_copy(update={"evidence_ids": evidence_ids})

    def fail(
        self,
        run_id: str,
        error_code: str,
        turn: ModelTurn | None = None,
        error: Exception | None = None,
        *,
        retry_feedback: dict[str, object] | None = None,
    ) -> None:
        provenance = (
            [item.model_dump(mode="json") for item in turn.tools] if turn else []
        )
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT environment::text, known_at, role, attempt_count, status
                FROM research.run WHERE id = %s""",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError("failed Scout run does not exist")
            updated = connection.execute(
                """UPDATE research.run SET status = 'failed', error_code = %s,
                tool_provenance = %s, thread_id = %s, turn_id = %s,
                actual_usage = %s, latency_ms = %s
                WHERE id = %s AND status = 'running' RETURNING id""",
                (
                    error_code,
                    Jsonb(provenance),
                    turn.thread_id if turn else None,
                    turn.turn_id if turn else None,
                    Jsonb(turn.usage if turn else {}),
                    turn.latency_ms if turn else None,
                    run_id,
                ),
            ).fetchone()
            if updated is None:
                if row[4] == "cancelled":
                    return
                raise ValueError("Scout failure is not in running state")
            content = {
                "schema": "alta.scout-failure.v1",
                "error_code": error_code,
                "tool_provenance": provenance,
                "error_type": type(error).__name__ if error else None,
                "error_fingerprint": (
                    _canonical_hash(
                        {
                            "type": type(error).__name__,
                            "message": redact(str(error)),
                        }
                    )
                    if error
                    else None
                ),
                "bounded_final_response": (
                    _utf8_prefix(redact(turn.final_response), 6_000) if turn else None
                ),
                "retry_feedback": retry_feedback,
                "usage": turn.usage if turn else {},
            }
            version = row[3]
            artifact_id = (
                "artifact_" + _canonical_hash([run_id, "failure", version])[:32]
            )
            content_hash = _canonical_hash(content)
            connection.execute(
                """INSERT INTO research.run_artifact
                (id, environment, version, known_at, run_id, artifact_kind,
                 schema_version, content, content_hash)
                VALUES (%s,%s,%s,%s,%s,'failure','alta.scout-failure.v1',%s,%s)
                ON CONFLICT (run_id, artifact_kind, version) DO NOTHING""",
                (
                    artifact_id,
                    row[0],
                    version,
                    row[1],
                    run_id,
                    Jsonb(content),
                    content_hash,
                ),
            )

    @staticmethod
    def _insert_artifact(
        connection,
        spec: ScoutRunSpec,
        *,
        artifact_kind: str,
        schema_version: str,
        content: dict[str, Any],
    ) -> None:
        version = 1
        artifact_id = (
            "artifact_" + _canonical_hash([spec.run_id, artifact_kind, version])[:32]
        )
        content_hash = _canonical_hash(content)
        inserted = connection.execute(
            """INSERT INTO research.run_artifact
            (id, environment, version, known_at, run_id, artifact_kind,
             schema_version, content, content_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (run_id, artifact_kind, version) DO NOTHING
            RETURNING id""",
            (
                artifact_id,
                spec.frozen_input.environment.value,
                version,
                spec.frozen_input.known_at,
                spec.run_id,
                artifact_kind,
                schema_version,
                Jsonb(content),
                content_hash,
            ),
        ).fetchone()
        if inserted is None:
            existing = connection.execute(
                """SELECT content_hash FROM research.run_artifact
                WHERE run_id = %s AND artifact_kind = %s AND version = %s""",
                (spec.run_id, artifact_kind, version),
            ).fetchone()
            if existing != (content_hash,):
                raise ValueError("run artifact identity collision")

    def finish_batch(self, job_id: str, failed: bool) -> None:
        target_status = "failed" if failed else "succeeded"
        with self.database.connect() as connection:
            updated = connection.execute(
                """UPDATE ops.job SET status = %s
                WHERE id = %s AND status = 'running'
                RETURNING environment::text, known_at, subject_id, attempt_count""",
                (target_status, job_id),
            ).fetchone()
            if updated is None:
                existing = connection.execute(
                    "SELECT status FROM ops.job WHERE id = %s", (job_id,)
                ).fetchone()
                if existing == (target_status,) or (
                    target_status == "failed"
                    and existing in {("cancelled",), ("succeeded",)}
                ):
                    return
                if existing != (target_status,):
                    raise FrozenCycleSnapshotError(
                        "Scout batch final status conflicts with durable job state"
                    )
            _append_event(
                connection,
                _contract_event(
                    event_type="scout.batch.finished",
                    aggregate_type="scout_batch",
                    aggregate_id=job_id,
                    environment=Environment(updated[0]),
                    known_at=updated[1],
                    payload={
                        "cycle_id": updated[2],
                        "job_id": job_id,
                        "status": target_status,
                        "attempt_count": updated[3],
                    },
                    correlation_id=updated[2],
                ),
            )
