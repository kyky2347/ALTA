from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .database import Database


RESEARCH_OPERATIONS_VERSION = "alta-research-operations-v4"
RESEARCH_OPERATIONS_RUNS_PER_MIND = 5
REQUIRED_EVIDENCE_ROLES = frozenset(
    {"primary_fact", "mechanism", "market_context", "counterevidence"}
)


def _safe_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _domain(locator: object) -> str | None:
    if not isinstance(locator, str):
        return None
    parsed = urlsplit(locator)
    hostname = parsed.hostname
    return hostname.casefold() if hostname else None


def _source_family(tool_name: object) -> str:
    name = str(tool_name or "")
    if name == "alta_finance_data":
        return "market_data"
    if name == "alta_social_search":
        return "social"
    if name in {"alta_web_research", "alta_web_search"}:
        return "discovery"
    if name in {
        "alta_web_fetch",
        "alta_web_batch_fetch",
        "alta_web_crawl",
        "alta_web_feed",
        "alta_web_archive",
        "alta_academic_search",
    }:
        return "primary_web"
    return "other"


def _token_total(usage: object) -> int:
    payload = _safe_dict(usage)
    total = payload.get("total_tokens") or payload.get("totalTokens")
    if isinstance(total, int) and total >= 0:
        return total
    values = (
        payload.get("input_tokens"),
        payload.get("output_tokens"),
        payload.get("inputTokens"),
        payload.get("outputTokens"),
    )
    return sum(value for value in values if isinstance(value, int) and value >= 0)


def _run_metrics(row: dict[str, Any]) -> dict[str, Any]:
    provenance = _safe_list(row.get("toolProvenance"))
    completed_calls = 0
    failed_calls = 0
    domains: set[str] = set()
    source_families: set[str] = set()
    for raw_tool in provenance:
        tool = _safe_dict(raw_tool)
        status = str(tool.get("status") or "").casefold()
        if status in {"completed", "succeeded"}:
            completed_calls += 1
        else:
            failed_calls += 1
        source_families.add(_source_family(tool.get("tool_name")))
        for locator in _safe_list(tool.get("source_locators")):
            if hostname := _domain(locator):
                domains.add(hostname)

    artifact = _safe_dict(row.get("artifact"))
    output = _safe_dict(artifact.get("output"))
    diligence = _safe_dict(artifact.get("research_diligence"))
    evidence_roles = {
        str(role)
        for role in _safe_list(diligence.get("evidence_roles"))
        if str(role) in REQUIRED_EVIDENCE_ROLES
    }
    evidence_origins = {
        str(origin)
        for origin in _safe_list(diligence.get("independent_evidence_origins"))
        if isinstance(origin, str) and len(origin) == 64
    }
    posture = str(diligence.get("posture") or "unassessed")
    attempt_count = max(int(row.get("attemptCount") or 1), 1)
    status = str(row.get("status") or "")
    error_code = str(row.get("errorCode") or "")
    assigned_mode = str(row.get("assignedMode") or "explore")
    output_research_mode = str(output.get("research_mode") or "")
    follow_up_assigned = assigned_mode == "follow_up"
    follow_up_executed = (
        follow_up_assigned
        and status == "succeeded"
        and output_research_mode == "follow_up"
    )
    return {
        **row,
        "completedToolCalls": completed_calls,
        "failedToolCalls": failed_calls,
        "sourceDomains": domains,
        "sourceFamilies": source_families,
        "evidenceRoles": evidence_roles,
        "evidenceOrigins": evidence_origins,
        "citedSourceCount": int(diligence.get("cited_source_count") or 0),
        "sourceRoleCollisions": int(diligence.get("source_role_collisions") or 0),
        "researchPosture": posture,
        "tokenTotal": _token_total(row.get("actualUsage")),
        "attemptCount": attempt_count,
        "retried": attempt_count > 1,
        "retryRecovered": attempt_count > 1 and status == "succeeded",
        "contractRejected": status == "failed" and error_code == "invalid_output",
        "deadlineFailed": status == "failed" and error_code == "deadline_exceeded",
        "assignedMode": assigned_mode,
        "outputResearchMode": output_research_mode,
        "followUpAssigned": follow_up_assigned,
        "followUpExecuted": follow_up_executed,
        "followUpNoOp": follow_up_executed and row.get("outputKind") == "no_op",
    }


def project_research_operations(
    rows: Iterable[dict[str, Any]], scout_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Builds a bounded, secret-free view of saved retrieval operations."""

    by_scout: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        role = str(row.get("role") or "")
        if role in scout_ids:
            by_scout[role].append(_run_metrics(row))

    minds: list[dict[str, Any]] = []
    all_domains: set[str] = set()
    all_families: set[str] = set()
    total_runs = completed_calls = failed_calls = 0
    failed_runs = candidate_runs = no_op_runs = 0
    cross_checked_runs = screen_grade_runs = 0
    total_tokens = total_latency = latency_samples = 0
    all_origins: set[str] = set()
    cited_sources = source_role_collisions = 0
    retried_runs = retry_recovered_runs = contract_rejected_runs = 0
    deadline_failed_runs = 0
    follow_up_assigned_runs = follow_up_executed_runs = follow_up_no_op_runs = 0

    for scout_id in scout_ids:
        scout_rows = by_scout.get(scout_id, [])
        scout_domains: set[str] = set()
        scout_families: set[str] = set()
        scout_roles: set[str] = set()
        scout_origins: set[str] = set()
        scout_completed = scout_failed_calls = scout_failed_runs = 0
        scout_candidates = scout_no_ops = scout_cross_checked = scout_screen_grade = 0
        scout_tokens = scout_latency = scout_latency_samples = 0
        scout_cited_sources = scout_role_collisions = 0
        scout_retried = scout_retry_recovered = scout_contract_rejected = 0
        scout_deadline_failed = 0
        scout_follow_up_assigned = scout_follow_up_executed = 0
        scout_follow_up_no_op = 0
        for row in scout_rows:
            scout_domains.update(row["sourceDomains"])
            scout_families.update(row["sourceFamilies"])
            scout_roles.update(row["evidenceRoles"])
            scout_origins.update(row["evidenceOrigins"])
            scout_cited_sources += row["citedSourceCount"]
            scout_role_collisions += row["sourceRoleCollisions"]
            scout_retried += int(row["retried"])
            scout_retry_recovered += int(row["retryRecovered"])
            scout_contract_rejected += int(row["contractRejected"])
            scout_deadline_failed += int(row["deadlineFailed"])
            scout_follow_up_assigned += int(row["followUpAssigned"])
            scout_follow_up_executed += int(row["followUpExecuted"])
            scout_follow_up_no_op += int(row["followUpNoOp"])
            scout_completed += row["completedToolCalls"]
            scout_failed_calls += row["failedToolCalls"]
            scout_failed_runs += int(row.get("status") == "failed")
            scout_candidates += int(row.get("outputKind") == "candidate")
            scout_no_ops += int(row.get("outputKind") == "no_op")
            scout_cross_checked += int(row["researchPosture"] == "cross_checked")
            scout_screen_grade += int(row["researchPosture"] == "screen_grade")
            scout_tokens += row["tokenTotal"]
            latency = row.get("latencyMs")
            if isinstance(latency, int) and latency >= 0:
                scout_latency += latency
                scout_latency_samples += 1

        latest = scout_rows[0] if scout_rows else {}
        if not scout_rows:
            posture = "waiting"
        elif str(latest.get("status")) in {"failed", "cancelled"}:
            posture = "degraded"
        elif latest.get("researchPosture") == "cross_checked":
            posture = "cross_checked"
        elif latest.get("researchPosture") == "screen_grade":
            posture = "screen_grade"
        else:
            posture = "active"
        minds.append(
            {
                "scoutId": scout_id,
                "posture": posture,
                "lastRunAt": latest.get("knownAt"),
                "latestStatus": latest.get("status"),
                "latestErrorCode": latest.get("errorCode"),
                "windowRuns": len(scout_rows),
                "candidateRuns": scout_candidates,
                "noOpRuns": scout_no_ops,
                "failedRuns": scout_failed_runs,
                "completedToolCalls": scout_completed,
                "failedToolCalls": scout_failed_calls,
                "uniqueSourceDomains": len(scout_domains),
                "independentEvidenceOrigins": len(scout_origins),
                "citedSources": scout_cited_sources,
                "sourceRoleCollisions": scout_role_collisions,
                "sourceFamilies": sorted(scout_families),
                "evidenceRoles": sorted(scout_roles),
                "crossCheckedRuns": scout_cross_checked,
                "screenGradeRuns": scout_screen_grade,
                "retriedRuns": scout_retried,
                "retryRecoveredRuns": scout_retry_recovered,
                "contractRejectedRuns": scout_contract_rejected,
                "deadlineFailedRuns": scout_deadline_failed,
                "followUpAssignedRuns": scout_follow_up_assigned,
                "followUpExecutedRuns": scout_follow_up_executed,
                "followUpNoOpRuns": scout_follow_up_no_op,
                "latestAttemptCount": int(latest.get("attemptCount") or 0),
                "totalTokens": scout_tokens,
                "averageLatencyMs": (
                    round(scout_latency / scout_latency_samples)
                    if scout_latency_samples
                    else None
                ),
            }
        )
        all_domains.update(scout_domains)
        all_families.update(scout_families)
        all_origins.update(scout_origins)
        total_runs += len(scout_rows)
        completed_calls += scout_completed
        failed_calls += scout_failed_calls
        failed_runs += scout_failed_runs
        candidate_runs += scout_candidates
        no_op_runs += scout_no_ops
        cross_checked_runs += scout_cross_checked
        screen_grade_runs += scout_screen_grade
        total_tokens += scout_tokens
        cited_sources += scout_cited_sources
        source_role_collisions += scout_role_collisions
        retried_runs += scout_retried
        retry_recovered_runs += scout_retry_recovered
        contract_rejected_runs += scout_contract_rejected
        deadline_failed_runs += scout_deadline_failed
        follow_up_assigned_runs += scout_follow_up_assigned
        follow_up_executed_runs += scout_follow_up_executed
        follow_up_no_op_runs += scout_follow_up_no_op
        total_latency += scout_latency
        latency_samples += scout_latency_samples

    if total_runs == 0:
        posture = "waiting"
    elif failed_runs or failed_calls:
        posture = "degraded"
    elif cross_checked_runs:
        posture = "cross_checked"
    else:
        posture = "active"
    return {
        "version": RESEARCH_OPERATIONS_VERSION,
        "posture": posture,
        "windowRuns": total_runs,
        "candidateRuns": candidate_runs,
        "noOpRuns": no_op_runs,
        "failedRuns": failed_runs,
        "completedToolCalls": completed_calls,
        "failedToolCalls": failed_calls,
        "uniqueSourceDomains": len(all_domains),
        "independentEvidenceOrigins": len(all_origins),
        "citedSources": cited_sources,
        "sourceRoleCollisions": source_role_collisions,
        "sourceFamilies": sorted(all_families),
        "crossCheckedRuns": cross_checked_runs,
        "screenGradeRuns": screen_grade_runs,
        "retriedRuns": retried_runs,
        "retryRecoveredRuns": retry_recovered_runs,
        "contractRejectedRuns": contract_rejected_runs,
        "deadlineFailedRuns": deadline_failed_runs,
        "followUpAssignedRuns": follow_up_assigned_runs,
        "followUpExecutedRuns": follow_up_executed_runs,
        "followUpNoOpRuns": follow_up_no_op_runs,
        "totalTokens": total_tokens,
        "averageLatencyMs": (
            round(total_latency / latency_samples) if latency_samples else None
        ),
        "minds": minds,
        "disclosure": (
            "Saved tool provenance and diligence outcomes only; queries, arguments, "
            "credentials, source text, and private reasoning are not exposed."
        ),
    }


def load_research_operations(
    database: Database,
    environment: str,
    scout_ids: tuple[str, ...],
    per_scout: int = RESEARCH_OPERATIONS_RUNS_PER_MIND,
) -> dict[str, Any]:
    bounded = min(max(per_scout, 1), 10)
    with database.connect() as connection:
        rows = connection.execute(
            """WITH ranked AS (
                SELECT r.id, r.role, r.status, r.error_code, r.known_at,
                r.tool_provenance, r.actual_usage, r.latency_ms, r.output_kind,
                r.attempt_count, artifact.content,
                r.frozen_input->'input'->'opportunity_drive'->>'assigned_mode'
                  AS assigned_mode,
                row_number() OVER (
                    PARTITION BY r.role ORDER BY r.created_at DESC, r.id DESC
                ) AS row_number
                FROM research.run r
                LEFT JOIN LATERAL (
                    SELECT a.content FROM research.run_artifact a
                    WHERE a.run_id = r.id AND a.environment = r.environment
                      AND a.artifact_kind = 'scout_output'
                    ORDER BY a.version DESC LIMIT 1
                ) artifact ON true
                WHERE r.environment = %s AND r.role = ANY(%s)
                  AND r.cycle_id LIKE 'live-%%'
            )
            SELECT id, role, status, error_code, known_at, tool_provenance,
            actual_usage, latency_ms, output_kind, attempt_count, content,
            assigned_mode
            FROM ranked WHERE row_number <= %s
            ORDER BY role, known_at DESC, id DESC""",
            (environment, list(scout_ids), bounded),
        ).fetchall()
    payload_rows = (
        {
            "id": row[0],
            "role": row[1],
            "status": row[2],
            "errorCode": row[3],
            "knownAt": row[4],
            "toolProvenance": row[5],
            "actualUsage": row[6],
            "latencyMs": row[7],
            "outputKind": row[8],
            "attemptCount": row[9],
            "artifact": row[10],
            "assignedMode": row[11],
        }
        for row in rows
    )
    return project_research_operations(payload_rows, scout_ids)
