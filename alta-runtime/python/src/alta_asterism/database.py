import json
from decimal import Decimal
from typing import Any

from .alpha_feedback import AlphaFeedbackProjector
import psycopg
from psycopg.types.json import Jsonb

from .contracts import Event
from .alpha_governance import (
    AlphaCapitalGovernance,
    AlphaCapitalGovernancePolicy,
    CapitalPerformanceObservation,
    evaluate_alpha_capital_governance,
)
from .foundry import CandidateDraft, materialized_thesis_pillars
from .migrations import CURRENT_TABLES, LATEST_REVISION, MIGRATIONS
from .research_agenda import build_open_research_questions
from .research_diligence import ResearchDiligence, strongest_diligence
from .investment_thesis import pillar_research_question
from .underwriting_calibration import (
    AlphaPerformanceObservation,
    CalibrationObservation,
    frozen_expected_net_alpha_bps,
    summarize_alpha_evidence,
    summarize_underwriting_calibration,
)


def _mean_decimal(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(sum(values, Decimal(0)) / Decimal(len(values)))


def _positive_rate(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(Decimal(sum(value > 0 for value in values)) / Decimal(len(values)))


def _calibration_observations(
    implementation_rows: list[tuple],
    realized_by_position: dict[str, Decimal],
) -> tuple[CalibrationObservation, ...]:
    observations = []
    for position_id, expression_kind, position_thesis in implementation_rows:
        if expression_kind != "stock" or position_id not in realized_by_position:
            continue
        expected_alpha = frozen_expected_net_alpha_bps(position_thesis)
        if expected_alpha is not None:
            observations.append(
                CalibrationObservation(
                    position_id=position_id,
                    expected_alpha_bps=expected_alpha,
                    realized_alpha_bps=realized_by_position[position_id],
                )
            )
    return tuple(observations)


def _capital_governance_payload(value: AlphaCapitalGovernance) -> dict[str, Any]:
    return {
        "policyVersion": value.policy_version,
        "sourcePortfolioPolicyVersion": value.source_portfolio_policy_version,
        "posture": value.posture,
        "capitalMultiplier": str(value.capital_multiplier),
        "sampleSize": value.sample_size,
        "windowSize": value.window_size,
        "recentMeanAlphaBps": (
            str(value.recent_mean_alpha_bps)
            if value.recent_mean_alpha_bps is not None
            else None
        ),
        "confidence95UpperAlphaBps": (
            str(value.confidence95_upper_alpha_bps)
            if value.confidence95_upper_alpha_bps is not None
            else None
        ),
        "maxDrawdownNavBps": str(value.max_drawdown_nav_bps),
        "evidencePosture": value.evidence_posture,
        "observedThrough": value.observed_through,
        "reasonCodes": list(value.reason_codes),
    }


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
                "components": item[5],
                "gateStatus": item[6],
                "reasonCodes": item[7],
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
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=3)

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
                """SELECT id, opportunity_id, book, position, score, known_at
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

    def runtime_detail(self, environment: str) -> dict[str, Any]:
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
            "alpha": self.alpha_summary(environment),
            "alphaFeedback": AlphaFeedbackProjector(self).public_summary(environment),
        }

    def alpha_summary(self, environment: str) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT aggregate_id, payload, known_at FROM (
                    SELECT DISTINCT ON (aggregate_id)
                        aggregate_id, payload, known_at, sequence
                    FROM ops.event
                    WHERE environment = %s
                      AND event_type = 'position.performance.measured'
                    ORDER BY aggregate_id, sequence DESC
                ) latest ORDER BY sequence""",
                (environment,),
            ).fetchall()
            open_positions = connection.execute(
                """SELECT count(*) FROM research.shadow_position
                WHERE environment = %s AND status = 'open'""",
                (environment,),
            ).fetchone()[0]
            position_ids = [row[0] for row in rows]
            implementation_rows = (
                connection.execute(
                    """SELECT p.id, e.kind, p.position_thesis
                    FROM research.shadow_position p
                    JOIN research.expression e ON e.id = p.expression_id
                    WHERE p.id = ANY(%s) AND p.environment = %s
                    ORDER BY p.id""",
                    (position_ids, environment),
                ).fetchall()
                if position_ids
                else []
            )
        returns = [Decimal(row[1]["net_return_bps"]) for row in rows]
        alphas = [
            Decimal(row[1]["realized_alpha_bps"])
            for row in rows
            if row[1].get("realized_alpha_bps") is not None
        ]
        pnl = [Decimal(row[1]["net_pnl"]) for row in rows]
        realized_by_position = {
            row[0]: Decimal(row[1]["realized_alpha_bps"])
            for row in rows
            if row[1].get("realized_alpha_bps") is not None
        }
        alpha_evidence = summarize_alpha_evidence(
            tuple(
                AlphaPerformanceObservation(
                    position_id=row[0],
                    realized_alpha_bps=Decimal(row[1]["realized_alpha_bps"]),
                )
                for row in rows
                if row[1].get("realized_alpha_bps") is not None
            )
        )
        from .implementation import PortfolioRiskPolicy

        portfolio_policy = PortfolioRiskPolicy()
        capital_governance = self.alpha_capital_governance(
            environment,
            reference_nav=portfolio_policy.reference_nav,
            source_portfolio_policy_version=portfolio_policy.version,
        )
        return {
            "measurement": "realized_shadow_cost_adjusted",
            "closedPositions": len(rows),
            "openPositions": open_positions,
            "positiveReturnRate": _positive_rate(returns),
            "meanNetReturnBps": _mean_decimal(returns),
            "meanRealizedAlphaBps": _mean_decimal(alphas),
            "cumulativeNetPnl": str(sum(pnl, Decimal(0))),
            "lastMeasuredAt": rows[-1][2] if rows else None,
            "alphaEvidence": alpha_evidence,
            "capitalGovernance": _capital_governance_payload(capital_governance),
            "underwritingCalibration": summarize_underwriting_calibration(
                _calibration_observations(implementation_rows, realized_by_position)
            ),
            "warning": alpha_evidence["warning"],
        }

    def alpha_capital_governance(
        self,
        environment: str,
        *,
        reference_nav: Decimal,
        source_portfolio_policy_version: str,
        policy: AlphaCapitalGovernancePolicy | None = None,
    ) -> AlphaCapitalGovernance:
        policy = policy or AlphaCapitalGovernancePolicy()
        with self.connect() as connection:
            rows = connection.execute(
                """WITH latest AS (
                    SELECT DISTINCT ON (aggregate_id)
                        aggregate_id, payload, known_at, sequence
                    FROM ops.event
                    WHERE environment = %s
                      AND event_type = 'position.performance.measured'
                      AND payload->>'cost_adjusted' = 'true'
                      AND payload->>'realized_alpha_bps' IS NOT NULL
                    ORDER BY aggregate_id, sequence DESC
                )
                SELECT latest.aggregate_id, latest.known_at, latest.payload,
                       count(*) OVER () AS total_sample_size
                FROM latest
                JOIN research.shadow_position position
                  ON position.id = latest.aggregate_id
                 AND position.environment = %s
                WHERE position.position_thesis->'implementation_plan'
                      ->>'policy_version' = %s
                ORDER BY latest.sequence DESC
                LIMIT %s""",
                (
                    environment,
                    environment,
                    source_portfolio_policy_version,
                    policy.window_size,
                ),
            ).fetchall()
        observations = tuple(
            CapitalPerformanceObservation(
                position_id=row[0],
                known_at=row[1],
                net_pnl=Decimal(row[2]["net_pnl"]),
                realized_alpha_bps=Decimal(row[2]["realized_alpha_bps"]),
            )
            for row in reversed(rows)
        )
        return evaluate_alpha_capital_governance(
            observations,
            reference_nav=reference_nav,
            source_portfolio_policy_version=source_portfolio_policy_version,
            policy=policy,
            total_sample_size=int(rows[0][3]) if rows else 0,
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
                (SELECT jsonb_agg(c.foundry_snapshot ORDER BY c.id)
                 FROM research.candidate c
                 WHERE c.id = ANY(research.opportunity.member_candidate_ids)
                   AND c.foundry_snapshot IS NOT NULL)
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
                """SELECT id, book, position, score, known_at, components,
                gate_status, reason_codes FROM research.rank
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


def event_json(event: dict[str, Any]) -> str:
    return json.dumps(
        {
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
