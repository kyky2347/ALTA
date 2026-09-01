import json
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

from .alpha_governance import (
    AlphaCapitalGovernance,
    AlphaCapitalGovernancePolicy,
)
from .alpha_feedback import AlphaFeedbackProjector
from .alpha_reporting import (
    alpha_capital_governance as load_alpha_capital_governance,
    alpha_summary as build_alpha_summary,
    execution_cost_governance as load_execution_cost_governance,
    forecast_calibration_governance as load_forecast_calibration_governance,
)
from .contracts import Event
from .foundry import CandidateDraft, materialized_thesis_pillars
from .forecast_calibration import (
    ForecastCalibrationGovernance,
    ForecastCalibrationPolicy,
)
from .execution_quality import ExecutionCostGovernance, ExecutionCostPolicy
from .investment_thesis import pillar_research_question
from .implementation import PortfolioRiskPolicy
from .migrations import CURRENT_TABLES, LATEST_REVISION, MIGRATIONS
from .opportunity_continuity import load_latest_opportunity_continuity
from .research_agenda import build_open_research_questions
from .research_diligence import ResearchDiligence, strongest_diligence
from .research_operations import load_research_operations
from .research_attention import ResearchAttentionProjector
from .trader_mind import SCOUTS


class AutonomousFenceLost(RuntimeError):
    """The process no longer owns the durable autonomous writer epoch."""


@dataclass(frozen=True)
class _AutonomousFence:
    owner_key: str
    epoch: int
    token_digest: str
    session_validator: Callable[[], None]


OPPORTUNITY_DETAIL_KEYS = (
    "id",
    "version",
    "knownAt",
    "status",
    "title",
    "thesis",
    "falsifier",
    "horizonDays",
    "snapshotHash",
    "observedChange",
    "mechanism",
    "direction",
    "expectation",
    "expectationPosture",
    "variantWedge",
    "whyNow",
    "firstRejection",
    "prediction",
    "investability",
    "freshnessAt",
    "evidenceIds",
    "completeness",
    "memberCandidateIds",
    "entityKey",
    "eventKey",
    "catalystKey",
    "identityVersion",
    "foundryState",
    "mergeParentId",
    "mergeRevision",
)
ASSESSMENT_DETAIL_KEYS = (
    "id",
    "runId",
    "assessor",
    "verdict",
    "score",
    "rationale",
    "forecastProbability",
    "evidenceQuality",
    "variantWedgeQuality",
    "strongestSupport",
    "strongestDisconfirmation",
    "firstRejection",
    "missingEvidence",
    "recommendation",
    "confidence",
    "evidenceIds",
    "lockedAt",
    "promptVersion",
    "modelId",
    "underwriting",
)


def _candidate_snapshots(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _candidate_drafts(
    snapshots: tuple[dict[str, Any], ...],
) -> tuple[CandidateDraft, ...]:
    candidates = []
    for item in snapshots:
        try:
            candidates.append(CandidateDraft.model_validate(item))
        except ValueError:
            continue
    return tuple(candidates)


def _snapshot_value(snapshots: tuple[dict[str, Any], ...], field: str) -> Any:
    return next((item[field] for item in snapshots if item.get(field)), None)


def _strongest_snapshot_diligence(
    snapshots: tuple[dict[str, Any], ...],
) -> ResearchDiligence | None:
    diligences = []
    for item in snapshots:
        raw = item.get("research_diligence")
        if not isinstance(raw, dict):
            continue
        try:
            diligences.append(ResearchDiligence.model_validate(raw))
        except ValueError:
            continue
    return strongest_diligence(tuple(diligences))


def _opportunity_detail_payload(
    *,
    opportunity_id: str,
    row: tuple,
    assessments: list[tuple],
    discussions: list[tuple],
    ranks: list[tuple],
    expressions: list[tuple],
) -> dict[str, Any]:
    snapshots = _candidate_snapshots(row[-1])
    thesis_pillars = materialized_thesis_pillars(_candidate_drafts(snapshots))
    lineage = next(
        (item for item in snapshots if item.get("research_mode") == "follow_up"),
        snapshots[0] if snapshots else {},
    )
    strongest = _strongest_snapshot_diligence(snapshots)
    open_questions = build_open_research_questions(
        opportunity_id=opportunity_id,
        next_test=_snapshot_value(snapshots, "next_test"),
        first_rejection=_snapshot_value(snapshots, "first_rejection"),
        assessor_questions=tuple(
            (item[2], question) for item in assessments for question in item[12]
        ),
        thesis_questions=tuple(
            pillar_research_question(pillar) for pillar in thesis_pillars
        )[:2],
    )
    return {
        **dict(zip(OPPORTUNITY_DETAIL_KEYS, row[:-1], strict=True)),
        "researchLineage": {
            "mode": lineage.get("research_mode", "explore"),
            "parentOpportunityId": lineage.get("parent_opportunity_id"),
            "question": lineage.get("research_question"),
        },
        "researchContributors": [
            {
                "candidateId": item.get("candidate_id"),
                "alphaArchetype": item.get("alpha_archetype"),
                "mode": item.get("research_mode", "explore"),
                "parentOpportunityId": item.get("parent_opportunity_id"),
                "question": item.get("research_question"),
            }
            for item in snapshots
        ],
        "openResearchQuestions": [
            item.model_dump(mode="json") for item in open_questions
        ],
        "beneficiaryPath": _snapshot_value(snapshots, "beneficiary_path"),
        "disconfirmingEvidence": _snapshot_value(snapshots, "disconfirming_evidence"),
        "nextTest": _snapshot_value(snapshots, "next_test"),
        "thesisPillars": [pillar.model_dump(mode="json") for pillar in thesis_pillars],
        "researchDiligence": (
            strongest.model_dump(mode="json") if strongest is not None else None
        ),
        "assessments": [
            dict(zip(ASSESSMENT_DETAIL_KEYS, item, strict=True)) for item in assessments
        ],
        "discussions": [
            {
                "id": item[0],
                "eventType": item[1],
                "knownAt": item[2],
                "detail": item[3],
            }
            for item in discussions
        ],
        "ranks": [
            {
                "id": item[0],
                "book": item[1],
                "position": item[2],
                "score": item[3],
                "knownAt": item[4],
                "rankingRunId": item[5],
                "components": item[6],
                "gateStatus": item[7],
                "reasonCodes": item[8],
            }
            for item in ranks
        ],
        "expressions": [
            {
                "id": item[0],
                "kind": item[1],
                "status": item[2],
                "rationale": item[3],
                "knownAt": item[4],
                "validation": item[5],
            }
            for item in expressions
        ],
    }


class Database:
    def __init__(self, dsn: str, *, pool_size: int = 0) -> None:
        if pool_size < 0:
            raise ValueError("database pool size cannot be negative")
        self.dsn = dsn
        self._pool = (
            ConnectionPool(
                conninfo=dsn,
                min_size=0,
                max_size=pool_size,
                timeout=3,
                kwargs={"connect_timeout": 3},
                check=ConnectionPool.check_connection,
            )
            if pool_size
            else None
        )
        self._fence_lock = threading.Lock()
        self._fence_condition = threading.Condition(self._fence_lock)
        self._autonomous_fence: _AutonomousFence | None = None
        self._fenced_transactions = 0
        self._fence_closing = False

    def activate_autonomous_fence(
        self,
        *,
        owner_key: str,
        epoch: int,
        token_digest: str,
        session_validator: Callable[[], None],
    ) -> None:
        """Fence every transaction created by this database instance.

        The durable row is locked for the transaction after its epoch and
        token are validated. A successor therefore cannot publish a new epoch
        in the middle of a transaction that began under the previous owner.
        """

        if not owner_key or len(owner_key) > 128:
            raise ValueError("autonomous owner key is invalid")
        if epoch <= 0:
            raise ValueError("autonomous owner epoch must be positive")
        if re.fullmatch(r"[a-f0-9]{64}", token_digest) is None:
            raise ValueError("autonomous owner token digest is invalid")
        fence = _AutonomousFence(
            owner_key=owner_key,
            epoch=epoch,
            token_digest=token_digest,
            session_validator=session_validator,
        )
        with self._fence_lock:
            if self._autonomous_fence is not None:
                raise RuntimeError("autonomous database fence is already active")
            self._autonomous_fence = fence
            self._fenced_transactions = 0
            self._fence_closing = False

    def drain_autonomous_fence(self, *, token_digest: str) -> None:
        """Stop admission and wait for every fenced transaction to finish.

        Draining before the owner-row update avoids a lock-order cycle between
        transactions holding ``FOR KEY SHARE`` and the owner session revoking
        that row. The fence remains closed until ``clear_autonomous_fence`` so
        no unfenced transaction can enter before durable revocation completes.
        """

        with self._fence_condition:
            current = self._autonomous_fence
            if current is None:
                return
            if current.token_digest != token_digest:
                raise AutonomousFenceLost("autonomous database fence changed owner")
            self._fence_closing = True
            while self._fenced_transactions:
                self._fence_condition.wait()

    def clear_autonomous_fence(self, *, token_digest: str) -> None:
        self.drain_autonomous_fence(token_digest=token_digest)
        with self._fence_condition:
            current = self._autonomous_fence
            if current is None:
                return
            if current.token_digest != token_digest:
                raise AutonomousFenceLost("autonomous database fence changed owner")
            self._autonomous_fence = None
            self._fence_closing = False

    def assert_autonomous_fence(self) -> None:
        """Fail when the active autonomous writer session or epoch was lost."""

        with self.connect() as connection:
            connection.execute("SELECT 1")

    def _fence_snapshot(self) -> _AutonomousFence | None:
        with self._fence_lock:
            return self._autonomous_fence

    def _enter_fenced_transaction(self) -> _AutonomousFence | None:
        with self._fence_condition:
            fence = self._autonomous_fence
            if fence is None:
                return None
            if self._fence_closing:
                raise AutonomousFenceLost("autonomous database fence is draining")
            self._fenced_transactions += 1
            return fence

    def _leave_fenced_transaction(self, fence: _AutonomousFence | None) -> None:
        if fence is None:
            return
        with self._fence_condition:
            self._fenced_transactions -= 1
            if self._fenced_transactions < 0:
                raise RuntimeError("autonomous fence transaction count underflow")
            if self._fenced_transactions == 0:
                self._fence_condition.notify_all()

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        fence = self._enter_fenced_transaction()
        try:
            manager = (
                self._pool.connection()
                if self._pool is not None
                else psycopg.connect(self.dsn, connect_timeout=3)
            )
            with manager as connection:
                if fence is not None:
                    try:
                        fence.session_validator()
                        durable = connection.execute(
                            """SELECT epoch, token_digest
                            FROM ops.autonomous_owner
                            WHERE owner_key = %s
                            FOR KEY SHARE""",
                            (fence.owner_key,),
                        ).fetchone()
                    except AutonomousFenceLost:
                        raise
                    except psycopg.Error as error:
                        raise AutonomousFenceLost(
                            "autonomous owner validation is unavailable"
                        ) from error
                    if durable != (fence.epoch, fence.token_digest):
                        raise AutonomousFenceLost(
                            "autonomous owner epoch is stale or revoked"
                        )
                yield connection
                if fence is not None:
                    # A transaction that outlives the owner session must roll back,
                    # even when no successor has published a newer epoch yet.
                    fence.session_validator()
        finally:
            self._leave_fenced_transaction(fence)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()

    def current(self) -> str:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('alta_meta.schema_migration')")
                if cursor.fetchone()[0] is None:
                    return "base"
                rows = {
                    row[0]
                    for row in cursor.execute(
                        "SELECT revision FROM alta_meta.schema_migration"
                    ).fetchall()
                }
                return next(
                    (
                        migration.REVISION
                        for migration in reversed(MIGRATIONS)
                        if migration.REVISION in rows
                    ),
                    "base",
                )

    def upgrade(self) -> str:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA IF NOT EXISTS alta_meta")
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS alta_meta.schema_migration (
                    revision text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"""
                )
                for migration in MIGRATIONS:
                    cursor.execute(
                        "SELECT 1 FROM alta_meta.schema_migration WHERE revision = %s",
                        (migration.REVISION,),
                    )
                    if cursor.fetchone() is None:
                        migration.upgrade(cursor)
                        cursor.execute(
                            "INSERT INTO alta_meta.schema_migration (revision) VALUES (%s)",
                            (migration.REVISION,),
                        )
        return LATEST_REVISION

    def downgrade(self) -> str:
        if self.current() == "base":
            return "base"
        with self.connect() as connection:
            with connection.cursor() as cursor:
                applied = {
                    row[0]
                    for row in cursor.execute(
                        "SELECT revision FROM alta_meta.schema_migration"
                    ).fetchall()
                }
                for migration in reversed(MIGRATIONS):
                    if migration.REVISION in applied:
                        migration.downgrade(cursor)
                        cursor.execute(
                            "DELETE FROM alta_meta.schema_migration WHERE revision = %s",
                            (migration.REVISION,),
                        )
        return "base"

    def ready(self) -> bool:
        try:
            with self.connect() as connection:
                connection.execute("SELECT 1")
            return self.current() == LATEST_REVISION
        except psycopg.Error:
            return False

    def summary(self, environment: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.connect() as connection:
            for table in CURRENT_TABLES:
                where = " WHERE environment = %s" if environment else ""
                counts[table.split(".")[-1]] = connection.execute(
                    f"SELECT count(*) FROM {table}{where}",
                    (environment,) if environment else (),
                ).fetchone()[0]
        return counts

    def mvp_status(
        self, environment: str = "shadow", limit: int = 20
    ) -> dict[str, Any]:
        bounded_limit = min(max(limit, 1), 100)
        with self.connect() as connection:
            source_rows = connection.execute(
                """SELECT aggregate_id, known_at, payload FROM (
                    SELECT DISTINCT ON (aggregate_id)
                    aggregate_id, known_at, payload, sequence
                    FROM ops.event WHERE event_type = 'source.posture'
                    AND environment = %s
                    ORDER BY aggregate_id, sequence DESC
                ) AS latest_sources ORDER BY sequence DESC LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            stage_rows = connection.execute(
                """SELECT aggregate_id, known_at, event_type, payload
                FROM ops.event WHERE aggregate_type = 'mvp_pipeline'
                AND environment = %s
                ORDER BY sequence DESC LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            run_rows = connection.execute(
                """SELECT id, cycle_id, role, status, error_code, known_at, model_provider,
                model_id, actual_usage, latency_ms, thread_id FROM research.run
                WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            agent_rows = connection.execute(
                """SELECT id, cycle_id, role, status, error_code, known_at, model_provider,
                model_id, actual_usage, latency_ms, thread_id FROM (
                    SELECT DISTINCT ON (role)
                    id, cycle_id, role, status, error_code, known_at, created_at,
                    model_provider, model_id, actual_usage, latency_ms, thread_id
                    FROM research.run WHERE environment = %s
                    ORDER BY role, created_at DESC, id
                ) AS latest_agents ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            candidate_rows = connection.execute(
                """SELECT id, title, version, known_at, alpha_archetype
                FROM research.candidate
                WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            opportunity_rows = connection.execute(
                """SELECT id, title, status, version, known_at,
                foundry_state, merge_parent_id, merge_revision, identity_version
                FROM research.opportunity WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            rank_rows = connection.execute(
                """SELECT id, opportunity_id, book, position, score, known_at,
                ranking_run_id,
                count(*) OVER (PARTITION BY book, ranking_run_id),
                min(position) OVER (PARTITION BY book, ranking_run_id),
                max(position) OVER (PARTITION BY book, ranking_run_id)
                FROM research.rank WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            expression_rows = connection.execute(
                """SELECT id, opportunity_id, kind, status, version, known_at
                FROM research.expression WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            shadow_rows = connection.execute(
                """SELECT id, expression_id, symbol, status, version, known_at,
                quantity, opened_at, closed_at, entry_price, exit_price,
                entry_commission, exit_commission
                FROM research.shadow_position WHERE environment = %s
                ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            assessment_rows = connection.execute(
                """SELECT id, opportunity_id, assessor, verdict, score,
                recommendation, confidence, known_at, underwriting
                FROM research.assessment
                WHERE environment = %s ORDER BY created_at DESC, id LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            discussion_rows = connection.execute(
                """SELECT id, aggregate_id, event_type, known_at, payload
                FROM ops.event WHERE environment = %s
                AND event_type LIKE 'committee.%%'
                ORDER BY sequence DESC LIMIT %s""",
                (environment, bounded_limit),
            ).fetchall()
            cursor = connection.execute(
                """SELECT COALESCE(max(sequence), 0) FROM ops.event
                WHERE environment = %s""",
                (environment,),
            ).fetchone()[0]
            latest = connection.execute(
                """SELECT aggregate_id, event_type, payload FROM ops.event
                WHERE environment = %s AND aggregate_type = 'mvp_pipeline'
                ORDER BY sequence DESC LIMIT 1""",
                (environment,),
            ).fetchone()
        latest_type = latest[1] if latest else None
        if latest_type == "mvp.pipeline.completed":
            status = latest[2].get("snapshot", {}).get("status", "MVP_RUNNING")
        else:
            status = {
                "mvp.service.recovered": "MVP_RUNNING",
                "mvp.pipeline.failed": "FAILED",
            }.get(latest_type, "RUNNING" if latest else "NOT_COMPLETED")
        return {
            "status": status,
            "environment": environment,
            "currentPipelineId": latest[0] if latest else None,
            "eventCursor": cursor,
            "sources": [
                {
                    "id": row[0],
                    "knownAt": row[1],
                    **row[2],
                }
                for row in source_rows
            ],
            "pipeline": [
                {
                    "id": row[0],
                    "knownAt": row[1],
                    "eventType": row[2],
                    "detail": (
                        {
                            "demo_id": row[0],
                            "replay_hash": row[3]["replay_hash"],
                            "status": row[3]
                            .get("snapshot", {})
                            .get("status", "MVP_RUNNING"),
                        }
                        if row[2] == "mvp.pipeline.completed"
                        else row[3]
                    ),
                }
                for row in stage_rows
            ],
            "runs": [
                {
                    "id": row[0],
                    "cycleId": row[1],
                    "role": row[2],
                    "status": row[3],
                    "errorCode": row[4],
                    "knownAt": row[5],
                    "modelProvider": row[6],
                    "modelId": row[7],
                    "usage": row[8],
                    "latencyMs": row[9],
                    "threadId": row[10],
                }
                for row in run_rows
            ],
            "agents": [
                {
                    "id": row[2],
                    "runId": row[0],
                    "cycleId": row[1],
                    "status": row[3],
                    "errorCode": row[4],
                    "knownAt": row[5],
                    "modelProvider": row[6],
                    "modelId": row[7],
                    "usage": row[8],
                    "latencyMs": row[9],
                    "threadId": row[10],
                }
                for row in agent_rows
            ],
            "candidates": [
                {
                    "id": row[0],
                    "title": row[1],
                    "version": row[2],
                    "knownAt": row[3],
                    "alphaArchetype": row[4],
                }
                for row in candidate_rows
            ],
            "opportunities": [
                {
                    "id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "version": row[3],
                    "knownAt": row[4],
                    "foundryState": row[5],
                    "mergeParentId": row[6],
                    "mergeRevision": row[7],
                    "identityVersion": row[8],
                }
                for row in opportunity_rows
            ],
            "ranks": [
                {
                    "id": row[0],
                    "opportunityId": row[1],
                    "book": row[2],
                    "position": row[3],
                    "score": row[4],
                    "knownAt": row[5],
                    "rankingRunId": row[6],
                    "rankingRunItemCount": row[7],
                    "rankingRunComplete": (
                        row[7] > 0 and row[8] == 1 and row[9] == row[7]
                    ),
                }
                for row in rank_rows
            ],
            "expressions": [
                {
                    "id": row[0],
                    "opportunityId": row[1],
                    "kind": row[2],
                    "status": row[3],
                    "version": row[4],
                    "knownAt": row[5],
                }
                for row in expression_rows
            ],
            "shadowPositions": [
                {
                    "id": row[0],
                    "expressionId": row[1],
                    "symbol": row[2],
                    "status": row[3],
                    "version": row[4],
                    "knownAt": row[5],
                    "quantity": row[6],
                    "openedAt": row[7],
                    "closedAt": row[8],
                    "entryPrice": row[9],
                    "exitPrice": row[10],
                    "entryCommission": row[11],
                    "exitCommission": row[12],
                }
                for row in shadow_rows
            ],
            "assessments": [
                {
                    "id": row[0],
                    "opportunityId": row[1],
                    "assessor": row[2],
                    "verdict": row[3],
                    "score": row[4],
                    "recommendation": row[5],
                    "confidence": row[6],
                    "knownAt": row[7],
                    "underwriting": row[8],
                }
                for row in assessment_rows
            ],
            "discussions": [
                {
                    "id": row[0],
                    "opportunityId": row[1],
                    "eventType": row[2],
                    "knownAt": row[3],
                    "detail": row[4],
                }
                for row in discussion_rows
            ],
        }

    def run_detail(self, run_id: str, environment: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT id, cycle_id, role, status, error_code, known_at, input_hash,
                frozen_input, budget, deadline_at, prompt_version,
                tool_catalog_version, model_provider, model_id, trace_id,
                tool_provenance, evidence_ids, output_kind, thread_id, turn_id,
                actual_usage, latency_ms, attempt_count
                FROM research.run WHERE id = %s AND environment = %s""",
                (run_id, environment),
            ).fetchone()
            if row is None:
                return None
            artifacts = connection.execute(
                """SELECT artifact_kind, version, known_at, schema_version,
                content, content_hash FROM research.run_artifact
                WHERE run_id = %s AND environment = %s
                ORDER BY artifact_kind, version""",
                (run_id, environment),
            ).fetchall()
        keys = (
            "id",
            "cycleId",
            "role",
            "status",
            "errorCode",
            "knownAt",
            "inputHash",
            "frozenInput",
            "budget",
            "deadlineAt",
            "promptVersion",
            "toolCatalogVersion",
            "modelProvider",
            "modelId",
            "traceId",
            "toolProvenance",
            "evidenceIds",
            "outputKind",
            "threadId",
            "turnId",
            "actualUsage",
            "latencyMs",
            "attemptCount",
        )
        return {
            **dict(zip(keys, row, strict=True)),
            "artifacts": [
                {
                    "kind": item[0],
                    "version": item[1],
                    "knownAt": item[2],
                    "schemaVersion": item[3],
                    "content": item[4],
                    "contentHash": item[5],
                }
                for item in artifacts
            ],
        }

    def runtime_detail(
        self,
        environment: str,
        portfolio_policy: PortfolioRiskPolicy | None = None,
        universe: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            minds = connection.execute(
                """SELECT scout_id, version, known_at, thread_id, turn_count,
                context_tokens, rolling_summary, evidence_ids, model_provider,
                model_id, prompt_version, tool_catalog_version
                FROM research.mind_state WHERE environment = %s
                ORDER BY scout_id""",
                (environment,),
            ).fetchall()
            cursors = connection.execute(
                """SELECT source, cursor, version, known_at
                FROM ops.source_cursor WHERE environment = %s ORDER BY source""",
                (environment,),
            ).fetchall()
        return {
            "minds": [
                {
                    "id": row[0],
                    "version": row[1],
                    "knownAt": row[2],
                    "threadId": row[3],
                    "turnCount": row[4],
                    "contextTokens": row[5],
                    "rollingSummary": row[6],
                    "evidenceIds": row[7],
                    "modelProvider": row[8],
                    "modelId": row[9],
                    "promptVersion": row[10],
                    "toolCatalogVersion": row[11],
                }
                for row in minds
            ],
            "sourceCursors": [
                {
                    "source": row[0],
                    "cursor": row[1],
                    "version": row[2],
                    "knownAt": row[3],
                }
                for row in cursors
            ],
            "alpha": self.alpha_summary(environment, portfolio_policy),
            "alphaFeedback": AlphaFeedbackProjector(self).public_summary(environment),
            "researchAttention": (
                ResearchAttentionProjector(self).public_summary(
                    environment,
                    universe,
                    tuple(item.scout_id for item in SCOUTS),
                    {item.scout_id: item.alpha_archetypes for item in SCOUTS},
                )
                if universe
                else None
            ),
            "opportunityContinuity": load_latest_opportunity_continuity(
                self, environment
            ),
            "researchOperations": load_research_operations(
                self,
                environment,
                tuple(item.scout_id for item in SCOUTS),
            ),
        }

    def alpha_summary(
        self,
        environment: str,
        portfolio_policy: PortfolioRiskPolicy | None = None,
    ) -> dict[str, Any]:
        return build_alpha_summary(self, environment, portfolio_policy)

    def alpha_capital_governance(
        self,
        environment: str,
        *,
        reference_nav: Decimal,
        source_portfolio_policy_version: str,
        policy: AlphaCapitalGovernancePolicy | None = None,
    ) -> AlphaCapitalGovernance:
        return load_alpha_capital_governance(
            self,
            environment,
            reference_nav=reference_nav,
            source_portfolio_policy_version=source_portfolio_policy_version,
            policy=policy,
        )

    def forecast_calibration_governance(
        self,
        environment: str,
        *,
        source_portfolio_policy_version: str,
        expression_kind: str = "stock",
        policy: ForecastCalibrationPolicy | None = None,
    ) -> ForecastCalibrationGovernance:
        return load_forecast_calibration_governance(
            self,
            environment,
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            policy=policy,
        )

    def execution_cost_governance(
        self,
        environment: str,
        *,
        source_portfolio_policy_version: str,
        expression_kind: str,
        policy: ExecutionCostPolicy | None = None,
    ) -> ExecutionCostGovernance:
        return load_execution_cost_governance(
            self,
            environment,
            source_portfolio_policy_version=source_portfolio_policy_version,
            expression_kind=expression_kind,
            policy=policy,
        )

    def opportunity_detail(
        self, opportunity_id: str, environment: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT id, version, known_at, status, title, thesis, falsifier,
                horizon_days, snapshot_hash, observed_change, mechanism, direction,
                expectation, expectation_posture, variant_wedge, why_now,
                first_rejection, prediction, investability, freshness_at,
                evidence_ids, completeness, member_candidate_ids,
                entity_key, event_key, catalyst_key, identity_version,
                foundry_state, merge_parent_id, merge_revision,
                (SELECT jsonb_agg(c.foundry_snapshot ORDER BY member.ordinality)
                 FROM unnest(research.opportunity.member_candidate_ids)
                      WITH ORDINALITY AS member(candidate_id, ordinality)
                 JOIN research.candidate c ON c.id = member.candidate_id
                 WHERE c.foundry_snapshot IS NOT NULL)
                FROM research.opportunity WHERE id = %s AND environment = %s""",
                (opportunity_id, environment),
            ).fetchone()
            if row is None:
                return None
            assessments = connection.execute(
                """SELECT id, run_id, assessor, verdict, score, rationale,
                forecast_probability, evidence_quality, variant_wedge_quality,
                strongest_support, strongest_disconfirmation, first_rejection,
                missing_evidence, recommendation, confidence, evidence_ids,
                locked_at, prompt_version, model_id, underwriting
                FROM research.assessment WHERE opportunity_id = %s
                AND environment = %s ORDER BY assessor""",
                (opportunity_id, environment),
            ).fetchall()
            discussions = connection.execute(
                """SELECT id, event_type, known_at, payload FROM ops.event
                WHERE aggregate_id = %s AND environment = %s
                AND event_type LIKE 'committee.%%' ORDER BY sequence""",
                (opportunity_id, environment),
            ).fetchall()
            ranks = connection.execute(
                """SELECT id, book, position, score, known_at, ranking_run_id,
                components, gate_status, reason_codes FROM research.rank
                WHERE opportunity_id = %s AND environment = %s
                ORDER BY known_at DESC, position""",
                (opportunity_id, environment),
            ).fetchall()
            expressions = connection.execute(
                """SELECT id, kind, status, rationale, known_at, validation
                FROM research.expression WHERE opportunity_id = %s
                AND environment = %s ORDER BY known_at DESC""",
                (opportunity_id, environment),
            ).fetchall()
        return _opportunity_detail_payload(
            opportunity_id=opportunity_id,
            row=row,
            assessments=assessments,
            discussions=discussions,
            ranks=ranks,
            expressions=expressions,
        )

    def expression_detail(
        self, expression_id: str, environment: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT id, opportunity_id, version, known_at, kind, status,
                rationale, symbol, side, decision_known_at, quote_snapshot,
                validation, expression_hash, binding_hash, evidence_refs,
                policy_version FROM research.expression
                WHERE id = %s AND environment = %s""",
                (expression_id, environment),
            ).fetchone()
            if row is None:
                return None
            position = connection.execute(
                """SELECT id, symbol, side, quantity, status, opened_at,
                closed_at, entry_price, exit_price, position_thesis, exit_decision
                FROM research.shadow_position WHERE expression_id = %s
                AND environment = %s""",
                (expression_id, environment),
            ).fetchone()
            implementation = connection.execute(
                """SELECT payload->'expression'->'implementation_plan'
                FROM ops.event WHERE aggregate_id = %s AND environment = %s
                AND event_type IN ('expression.validated', 'expression.rejected')
                ORDER BY sequence DESC LIMIT 1""",
                (expression_id, environment),
            ).fetchone()
        keys = (
            "id",
            "opportunityId",
            "version",
            "knownAt",
            "kind",
            "status",
            "rationale",
            "symbol",
            "side",
            "decisionKnownAt",
            "quoteSnapshot",
            "validation",
            "expressionHash",
            "bindingHash",
            "evidenceRefs",
            "policyVersion",
        )
        position_keys = (
            "id",
            "symbol",
            "side",
            "quantity",
            "status",
            "openedAt",
            "closedAt",
            "entryPrice",
            "exitPrice",
            "positionThesis",
            "exitDecision",
        )
        return {
            **dict(zip(keys, row, strict=True)),
            "implementationPlan": (
                implementation[0]
                if implementation is not None and implementation[0] is not None
                else None
            ),
            "shadowPosition": (
                dict(zip(position_keys, position, strict=True)) if position else None
            ),
        }

    def append_event(self, event: Event) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """INSERT INTO ops.event
                (id, environment, version, known_at, aggregate_type, aggregate_id,
                 event_type, payload, correlation_id, causation_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING sequence""",
                (
                    event.id,
                    event.environment.value,
                    event.version,
                    event.known_at,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.event_type,
                    Jsonb(event.payload),
                    event.correlation_id,
                    event.causation_id,
                ),
            ).fetchone()
        return row[0]

    def events_after(
        self, cursor: int, limit: int = 100, environment: str | None = None
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            environment_filter = " AND environment = %s" if environment else ""
            parameters = (
                (cursor, environment, min(max(limit, 1), 100))
                if environment
                else (cursor, min(max(limit, 1), 100))
            )
            rows = connection.execute(
                """SELECT sequence, id, environment::text, version, known_at,
                aggregate_type, aggregate_id, event_type, payload FROM ops.event
                WHERE sequence > %s"""
                + environment_filter
                + " ORDER BY sequence LIMIT %s",
                parameters,
            ).fetchall()
        keys = (
            "cursor",
            "id",
            "environment",
            "version",
            "known_at",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def event_cursor(self, environment: str) -> int:
        """Return the durable change cursor used to invalidate read projections."""
        with self.connect() as connection:
            return connection.execute(
                """SELECT COALESCE(max(sequence), 0) FROM ops.event
                WHERE environment = %s""",
                (environment,),
            ).fetchone()[0]

    def events_before(
        self, cursor: int, limit: int = 100, environment: str | None = None
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            environment_filter = " AND environment = %s" if environment else ""
            parameters = (
                (cursor, environment, min(max(limit, 1), 100))
                if environment
                else (cursor, min(max(limit, 1), 100))
            )
            rows = connection.execute(
                """SELECT sequence, id, environment::text, version, known_at,
                aggregate_type, aggregate_id, event_type, payload FROM ops.event
                WHERE sequence < %s"""
                + environment_filter
                + " ORDER BY sequence DESC LIMIT %s",
                parameters,
            ).fetchall()
        keys = (
            "cursor",
            "id",
            "environment",
            "version",
            "known_at",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
        )
        return [dict(zip(keys, row, strict=True)) for row in reversed(rows)]


def event_json(event: dict[str, Any]) -> str:
    return json.dumps(
        {
            "cursor": event["cursor"],
            "eventId": event["id"],
            "eventType": event["event_type"],
            "aggregateType": event["aggregate_type"],
            "aggregateId": event["aggregate_id"],
            "environment": event["environment"],
            "version": event["version"],
            "knownAt": event["known_at"].isoformat(),
            "payload": event["payload"],
        },
        separators=(",", ":"),
    )
