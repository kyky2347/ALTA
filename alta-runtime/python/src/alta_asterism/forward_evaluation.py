from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .alpha_feedback import (
    ALPHA_FEEDBACK_MODE,
    MIN_MIND_BENCHMARKED_POSITIONS,
    MIN_SLICE_BENCHMARKED_POSITIONS,
)
from .alpha_governance import AlphaCapitalGovernancePolicy
from .agentic_deliberation import AgenticDeliberator
from .agentic_expression import AgenticExpressionFlow
from .agentic_position import POSITION_MONITOR_PROMPT_VERSION
from .b5_runtime import _append_event, _contract_event
from .contracts import Environment, Settings
from .database import Database
from .expression import ExpressionPolicy, contract_hash
from .implementation import PortfolioRiskPolicy
from .ranking import BOOK_NAME, RANKING_POLICY_VERSION
from .research_diligence import RESEARCH_QUALITY_VERSION
from .scouts import SCOUT_PROMPT_VERSION, SCOUT_TOOL_CATALOG_VERSION
from .shadow import MonitorPolicy, ShadowFillPolicy
from .trader_mind import (
    PRODUCTION_ACTIVE_RESEARCH_REQUIRED,
    TRADER_MIND_MEMORY_MODE,
)
from .underwriting import UNDERWRITING_POLICY_VERSION
from .version import __version__

EVALUATION_PROTOCOL_VERSION = "forward-shadow-v1"
MAX_COHORT_CYCLES = 10_000
MAX_CONFIGURATION_VARIANTS = 20


@dataclass(frozen=True)
class _EvaluationRows:
    bound: tuple[tuple, ...]
    terminals: tuple[tuple, ...]
    sources: tuple[tuple, ...]
    runs: tuple[tuple, ...]
    open_gates: tuple[tuple, ...]
    positions: tuple[tuple, ...]
    performance: tuple[tuple, ...]
    snapshots: tuple[dict[str, Any], ...]
    position_ids: tuple[str, ...]
    truncated: bool


@dataclass(frozen=True)
class IncompleteEvaluationCycle:
    """One durable cycle binding without a final pipeline outcome."""

    cycle_id: str
    known_at: datetime
    configuration_hash: str | None
    retry_failures: int


def _ratio(numerator: int, denominator: int) -> str | None:
    if denominator == 0:
        return None
    return str(Decimal(numerator) / Decimal(denominator))


def _decimal_mean(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(sum(values, Decimal(0)) / Decimal(len(values)))


def _performance_readiness(
    *,
    measurements: int,
    benchmarked: int,
    missing_measurements: int,
    minimum_closed_positions: int,
    configuration_stable: bool,
) -> str:
    if not configuration_stable:
        return "configuration_drift"
    if measurements < minimum_closed_positions:
        return "collecting"
    if missing_measurements or benchmarked != measurements:
        return "data_quality_blocked"
    return "ready_for_review"


def evaluation_configuration(settings: Settings) -> dict[str, Any]:
    """Returns the bounded, non-secret configuration relevant to forward results."""
    return {
        "protocolVersion": EVALUATION_PROTOCOL_VERSION,
        "releaseVersion": __version__,
        "cohortId": settings.evaluation_cohort_id,
        "universe": list(settings.universe),
        "scouts": {
            "provider": settings.agent_provider,
            "model": settings.agent_model,
            "reasoningEffort": settings.agent_reasoning_effort,
            "concurrency": settings.scout_concurrency,
            "promptVersion": SCOUT_PROMPT_VERSION,
            "toolCatalogVersion": SCOUT_TOOL_CATALOG_VERSION,
            "activeResearchRequired": PRODUCTION_ACTIVE_RESEARCH_REQUIRED,
            "priorMindMemory": TRADER_MIND_MEMORY_MODE,
            "alphaFeedback": {
                "mode": ALPHA_FEEDBACK_MODE,
                "minimumMindBenchmarkedPositions": MIN_MIND_BENCHMARKED_POSITIONS,
                "minimumSliceBenchmarkedPositions": MIN_SLICE_BENCHMARKED_POSITIONS,
                "automaticPolicyChanges": False,
            },
        },
        "roleModels": settings.safe_dump()["role_models"],
        "rolePrompts": {
            "deliberation": AgenticDeliberator.PROMPT_VERSION,
            "expression": AgenticExpressionFlow.PROMPT_VERSION,
            "expressionAudit": AgenticExpressionFlow.AUDIT_PROMPT_VERSION,
            "positionMonitor": POSITION_MONITOR_PROMPT_VERSION,
        },
        "policies": {
            "rankingBook": BOOK_NAME,
            "ranking": RANKING_POLICY_VERSION,
            "researchQuality": RESEARCH_QUALITY_VERSION,
            "underwriting": UNDERWRITING_POLICY_VERSION,
            "alphaCapitalGovernance": AlphaCapitalGovernancePolicy().version,
            "expression": ExpressionPolicy().version,
            "portfolioRisk": PortfolioRiskPolicy().version,
            "shadowFill": ShadowFillPolicy().version,
            "monitor": MonitorPolicy().version,
        },
        "sources": {
            "finlightConfigured": settings.finlight_api_key is not None,
            "massiveEnabled": settings.massive_enabled,
            "massiveConfigured": settings.massive_api_key is not None,
            "massiveDiscoveryEnabled": settings.massive_discovery_enabled,
            "massiveMaxRequestsPerCycle": settings.massive_max_requests_per_cycle,
        },
        "limits": {
            "agentDeadlineSeconds": settings.agent_deadline_seconds,
            "reasoningAgentDeadlineSeconds": (
                settings.reasoning_agent_deadline_seconds
            ),
            "autonomousIntervalSeconds": settings.autonomous_interval_seconds,
            "autonomousFollowUpIntervalSeconds": (
                settings.autonomous_follow_up_interval_seconds
            ),
            "autonomousPositionIntervalSeconds": (
                settings.autonomous_position_interval_seconds
            ),
            "shadowMaxPositionNotional": str(settings.shadow_max_position_notional),
        },
        "capitalMode": (
            "tiger_paper_mirror" if settings.tiger_paper_enabled else "disabled"
        ),
    }


class ForwardEvaluationLedger:
    """Binds each autonomous cycle to one immutable evaluation configuration."""

    def __init__(self, database: Database, settings: Settings) -> None:
        if settings.environment is not Environment.SHADOW:
            raise ValueError("forward evaluation requires environment=shadow")
        self.database = database
        self.settings = settings

    def bind_cycle(self, cycle_id: str, known_at) -> str:
        configuration = evaluation_configuration(self.settings)
        configuration_hash = contract_hash(configuration)
        payload = {
            "cycle_id": cycle_id,
            "cohort_id": self.settings.evaluation_cohort_id,
            "protocol_version": EVALUATION_PROTOCOL_VERSION,
            "configuration_hash": configuration_hash,
            "configuration": configuration,
        }
        with self.database.connect() as connection:
            existing = connection.execute(
                """SELECT payload FROM ops.event WHERE environment = %s
                AND aggregate_id = %s AND event_type = 'evaluation.cycle.bound'
                ORDER BY sequence LIMIT 1""",
                (self.settings.environment.value, cycle_id),
            ).fetchone()
            if existing is not None:
                if existing[0] != payload:
                    raise ValueError(
                        "autonomous cycle is already bound to a different evaluation"
                    )
                return configuration_hash
            _append_event(
                connection,
                _contract_event(
                    event_type="evaluation.cycle.bound",
                    aggregate_type="evaluation_cycle",
                    aggregate_id=cycle_id,
                    environment=Environment.SHADOW,
                    known_at=known_at,
                    payload=payload,
                    correlation_id=self.settings.evaluation_cohort_id,
                ),
            )
        return configuration_hash

    def incomplete_cycles(self) -> tuple[IncompleteEvaluationCycle, ...]:
        """Return unfinished cycles in creation order for startup reconciliation.

        A failure with ``retry_scheduled=true`` is an attempt failure, not a
        final cycle outcome.  Completed cycles and fail-closed failures are
        excluded so a restarted autonomous process cannot accidentally create
        a second cycle while durable work is still resumable.
        """

        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT bound.aggregate_id, bound.known_at,
                bound.payload->>'configuration_hash',
                count(retry.sequence)::integer
                FROM ops.event bound
                LEFT JOIN ops.event retry
                  ON retry.environment = bound.environment
                 AND retry.aggregate_id = bound.aggregate_id
                 AND retry.event_type = 'mvp.pipeline.failed'
                 AND retry.payload->>'retry_scheduled' = 'true'
                WHERE bound.environment = %s
                  AND bound.event_type = 'evaluation.cycle.bound'
                  AND NOT EXISTS (
                    SELECT 1 FROM ops.event terminal
                    WHERE terminal.environment = bound.environment
                      AND terminal.aggregate_id = bound.aggregate_id
                      AND (
                        terminal.event_type = 'mvp.pipeline.completed'
                        OR (
                          terminal.event_type = 'mvp.pipeline.failed'
                          AND COALESCE(
                            terminal.payload->>'retry_scheduled', 'false'
                          ) <> 'true'
                        )
                      )
                  )
                GROUP BY bound.sequence, bound.aggregate_id, bound.known_at,
                         bound.payload->>'configuration_hash'
                ORDER BY bound.sequence""",
                (self.settings.environment.value,),
            ).fetchall()
        return tuple(
            IncompleteEvaluationCycle(
                cycle_id=row[0],
                known_at=row[1],
                configuration_hash=row[2],
                retry_failures=row[3],
            )
            for row in rows
        )


class ForwardEvaluationReader:
    """Projects bounded cohort health without changing research or capital policy."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def summary(
        self, environment: str, cohort_id: str, minimum_closed_positions: int
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = self._load_rows(connection, environment, cohort_id)
        if rows is None:
            return self._empty(cohort_id, minimum_closed_positions)

        configuration = self._configuration_projection(rows.bound, rows.truncated)
        terminal_types = Counter(row[1] for row in rows.terminals)
        closed_count = sum(status == "closed" for _, status in rows.positions)
        performance = self._performance(
            rows.performance,
            open_positions=sum(status == "open" for _, status in rows.positions),
            missing_measurements=max(closed_count - len(rows.performance), 0),
            minimum_closed_positions=minimum_closed_positions,
            configuration_stable=configuration["configurationStable"],
        )
        cycle_projection = self._cycle_projection(rows.snapshots)
        open_gates = dict(rows.open_gates)
        return {
            "protocolVersion": EVALUATION_PROTOCOL_VERSION,
            "cohortId": cohort_id,
            "firstBoundAt": rows.bound[0][1],
            "lastBoundAt": rows.bound[-1][1],
            "boundCycles": len(rows.bound),
            "completedCycles": terminal_types["mvp.pipeline.completed"],
            "failedCycles": terminal_types["mvp.pipeline.failed"],
            "incompleteCycles": len(rows.bound) - len(rows.terminals),
            **cycle_projection,
            "shadowOpenCycles": len(rows.position_ids),
            "openOutcomes": {
                "noFill": open_gates.get("shadow.open.no_fill", 0),
                "rejected": open_gates.get("shadow.open.rejected", 0),
            },
            **configuration,
            "sources": self._source_projection(rows.sources),
            "agents": self._agent_projection(rows.runs, rows.snapshots),
            "performance": performance,
            "warning": "Alpha is unproven; this cohort is forward research evidence only.",
        }

    @staticmethod
    def _load_rows(
        connection, environment: str, cohort_id: str
    ) -> _EvaluationRows | None:
        bound_rows = connection.execute(
            """SELECT aggregate_id, known_at, payload FROM ops.event
            WHERE environment = %s AND event_type = 'evaluation.cycle.bound'
            AND payload->>'cohort_id' = %s
            ORDER BY sequence DESC LIMIT %s""",
            (environment, cohort_id, MAX_COHORT_CYCLES + 1),
        ).fetchall()
        truncated = len(bound_rows) > MAX_COHORT_CYCLES
        bound = tuple(reversed(bound_rows[:MAX_COHORT_CYCLES]))
        cycle_ids = [row[0] for row in bound]
        if not cycle_ids:
            return None
        terminals = tuple(
            connection.execute(
                """SELECT DISTINCT ON (aggregate_id) aggregate_id, event_type, payload
                FROM ops.event WHERE environment = %s AND aggregate_id = ANY(%s)
                AND (
                  event_type = 'mvp.pipeline.completed'
                  OR (
                    event_type = 'mvp.pipeline.failed'
                    AND COALESCE(payload->>'retry_scheduled', 'false') <> 'true'
                  )
                )
                ORDER BY aggregate_id, sequence DESC""",
                (environment, cycle_ids),
            ).fetchall()
        )
        sources = tuple(
            connection.execute(
                """SELECT payload->>'posture', count(*) FROM ops.event
                WHERE environment = %s AND event_type = 'source.posture'
                AND payload->>'cycle_id' = ANY(%s)
                GROUP BY payload->>'posture'""",
                (environment, cycle_ids),
            ).fetchall()
        )
        runs = tuple(
            connection.execute(
                """SELECT role, status, model_provider, model_id, prompt_version,
                tool_catalog_version, count(*) FROM research.run
                WHERE environment = %s AND cycle_id = ANY(%s)
                GROUP BY role, status, model_provider, model_id, prompt_version,
                tool_catalog_version ORDER BY role, status, model_provider, model_id""",
                (environment, cycle_ids),
            ).fetchall()
        )
        open_gates = tuple(
            connection.execute(
                """SELECT event_type, count(*) FROM ops.event
                WHERE environment = %s
                AND event_type IN ('shadow.open.no_fill','shadow.open.rejected')
                AND payload->>'cycle_id' = ANY(%s) GROUP BY event_type""",
                (environment, cycle_ids),
            ).fetchall()
        )
        snapshots = tuple(
            row[2].get("snapshot", {})
            for row in terminals
            if row[1] == "mvp.pipeline.completed"
        )
        position_ids = tuple(
            snapshot["shadow_position_id"]
            for snapshot in snapshots
            if snapshot.get("shadow_position_id")
        )
        positions = (
            tuple(
                connection.execute(
                    """SELECT id, status FROM research.shadow_position
                    WHERE environment = %s AND id = ANY(%s)""",
                    (environment, list(position_ids)),
                ).fetchall()
            )
            if position_ids
            else ()
        )
        performance = (
            tuple(
                connection.execute(
                    """SELECT aggregate_id, payload, known_at FROM ops.event
                    WHERE environment = %s
                    AND event_type = 'position.performance.measured'
                    AND aggregate_id = ANY(%s) ORDER BY sequence""",
                    (environment, list(position_ids)),
                ).fetchall()
            )
            if position_ids
            else ()
        )
        return _EvaluationRows(
            bound=bound,
            terminals=terminals,
            sources=sources,
            runs=runs,
            open_gates=open_gates,
            positions=positions,
            performance=performance,
            snapshots=snapshots,
            position_ids=position_ids,
            truncated=truncated,
        )

    @staticmethod
    def _configuration_projection(
        bound_rows: tuple[tuple, ...], truncated: bool
    ) -> dict[str, Any]:
        variants = Counter(row[2]["configuration_hash"] for row in bound_rows)
        configurations = {
            row[2]["configuration_hash"]: row[2]["configuration"] for row in bound_rows
        }
        return {
            "configurationStable": len(variants) == 1 and not truncated,
            "configurationVariantCount": len(variants),
            "configurationVariants": [
                {
                    "hash": value,
                    "cycles": count,
                    "configuration": configurations[value],
                }
                for value, count in variants.most_common(MAX_CONFIGURATION_VARIANTS)
            ],
            "windowTruncated": truncated,
        }

    @staticmethod
    def _cycle_projection(snapshots: tuple[dict[str, Any], ...]) -> dict[str, int]:
        return {
            "idleCycles": sum(item.get("status") == "MVP_IDLE" for item in snapshots),
            "waitCycles": sum(
                item.get("status") != "MVP_IDLE"
                and bool(item.get("expression_attempts"))
                and all(attempt[2] == "wait" for attempt in item["expression_attempts"])
                for item in snapshots
            ),
            "candidateCycles": sum(
                bool(item.get("candidate_ids")) for item in snapshots
            ),
            "novelOpportunityCycles": sum(
                bool(item.get("opportunities")) for item in snapshots
            ),
            "instrumentAttemptCycles": sum(
                any(
                    attempt[2] != "wait"
                    for attempt in item.get("expression_attempts", [])
                )
                for item in snapshots
            ),
        }

    @staticmethod
    def _source_projection(source_rows: tuple[tuple, ...]) -> dict[str, Any]:
        postures = {str(posture): count for posture, count in source_rows}
        total = sum(postures.values())
        return {
            "observations": total,
            "healthyRate": _ratio(postures.get("healthy", 0), total),
            "postures": postures,
        }

    @staticmethod
    def _agent_projection(
        run_rows: tuple[tuple, ...], snapshots: tuple[dict[str, Any], ...]
    ) -> dict[str, Any]:
        statuses = Counter()
        routes = []
        for role, status, provider, model, prompt, tools, count in run_rows:
            statuses[status] += count
            routes.append(
                {
                    "role": role,
                    "status": status,
                    "provider": provider,
                    "model": model,
                    "promptVersion": prompt,
                    "toolCatalogVersion": tools,
                    "count": count,
                }
            )
        scout_statuses = Counter(
            status
            for snapshot in snapshots
            for status in snapshot.get("scout_statuses", {}).values()
        )
        invoked = sum(statuses.values())
        return {
            "invokedRuns": invoked,
            "completionRate": _ratio(statuses.get("succeeded", 0), invoked),
            "statuses": dict(statuses),
            "scoutStatuses": dict(scout_statuses),
            "routes": routes,
        }

    @staticmethod
    def _performance(
        rows,
        *,
        open_positions: int,
        missing_measurements: int,
        minimum_closed_positions: int,
        configuration_stable: bool,
    ) -> dict[str, Any]:
        returns = [Decimal(row[1]["net_return_bps"]) for row in rows]
        alphas = [
            Decimal(row[1]["realized_alpha_bps"])
            for row in rows
            if row[1].get("realized_alpha_bps") is not None
        ]
        pnl = [Decimal(row[1]["net_pnl"]) for row in rows]
        return {
            "readiness": _performance_readiness(
                measurements=len(rows),
                benchmarked=len(alphas),
                missing_measurements=missing_measurements,
                minimum_closed_positions=minimum_closed_positions,
                configuration_stable=configuration_stable,
            ),
            "minimumClosedPositions": minimum_closed_positions,
            "closedPositions": len(rows),
            "openPositions": open_positions,
            "missingPerformanceMeasurements": missing_measurements,
            "benchmarkedClosedPositions": len(alphas),
            "benchmarkCoverageRate": _ratio(len(alphas), len(rows)),
            "positiveReturnRate": _ratio(
                sum(value > 0 for value in returns), len(returns)
            ),
            "meanNetReturnBps": _decimal_mean(returns),
            "meanRealizedAlphaBps": _decimal_mean(alphas),
            "cumulativeNetPnl": str(sum(pnl, Decimal(0))),
            "lastMeasuredAt": rows[-1][2] if rows else None,
        }

    @staticmethod
    def _empty(cohort_id: str, minimum_closed_positions: int) -> dict[str, Any]:
        return {
            "protocolVersion": EVALUATION_PROTOCOL_VERSION,
            "cohortId": cohort_id,
            "boundCycles": 0,
            "configurationStable": None,
            "performance": {
                "readiness": "not_started",
                "minimumClosedPositions": minimum_closed_positions,
                "closedPositions": 0,
            },
            "warning": "No autonomous cycles are bound; Alpha is unproven.",
        }
