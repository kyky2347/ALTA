from datetime import UTC, datetime, timedelta

from alta_asterism.research_operations import project_research_operations


def run_row(
    *,
    role: str,
    status: str = "succeeded",
    output_kind: str = "candidate",
    posture: str = "cross_checked",
    attempt_count: int = 1,
    error_code: str | None = None,
    assigned_mode: str = "explore",
    output_research_mode: str = "explore",
) -> dict[str, object]:
    return {
        "id": f"run_{role}_{status}",
        "role": role,
        "status": status,
        "errorCode": error_code or ("provider_timeout" if status == "failed" else None),
        "attemptCount": attempt_count,
        "knownAt": datetime(2026, 8, 30, 12, tzinfo=UTC),
        "toolProvenance": [
            {
                "tool_name": "alta_web_batch_fetch",
                "status": "completed",
                "source_locators": [
                    "https://filing.example/a",
                    "https://operations.example/b",
                ],
            },
            {
                "tool_name": "alta_finance_data",
                "status": "completed",
                "source_locators": ["https://market.example/c"],
            },
        ],
        "actualUsage": {"input_tokens": 100, "output_tokens": 40},
        "latencyMs": 1200,
        "outputKind": output_kind,
        "assignedMode": assigned_mode,
        "artifact": {
            "output": {"research_mode": output_research_mode},
            "research_diligence": {
                "posture": posture,
                "evidence_roles": [
                    "primary_fact",
                    "mechanism",
                    "market_context",
                    "counterevidence",
                ],
                "independent_evidence_origins": ["a" * 64, "b" * 64, "c" * 64],
                "cited_source_count": 4,
                "source_role_collisions": 1,
            },
        },
    }


def test_projection_exposes_bounded_process_evidence_without_queries() -> None:
    scout_ids = ("change_event_scout", "expectations_gap_scout")
    first = run_row(role=scout_ids[0])
    older = {
        **run_row(role=scout_ids[0], output_kind="no_op", posture="screen_grade"),
        "id": "run_older",
        "knownAt": datetime(2026, 8, 30, 11, tzinfo=UTC),
    }

    projected = project_research_operations((first, older), scout_ids)

    assert projected["posture"] == "cross_checked"
    assert projected["windowRuns"] == 2
    assert projected["completedToolCalls"] == 4
    assert projected["uniqueSourceDomains"] == 3
    assert projected["independentEvidenceOrigins"] == 3
    assert projected["citedSources"] == 8
    assert projected["sourceRoleCollisions"] == 2
    assert projected["crossCheckedRuns"] == 1
    assert projected["screenGradeRuns"] == 1
    assert projected["totalTokens"] == 280
    assert projected["minds"][0]["posture"] == "cross_checked"
    assert projected["minds"][0]["evidenceRoles"] == [
        "counterevidence",
        "market_context",
        "mechanism",
        "primary_fact",
    ]
    assert projected["minds"][1]["posture"] == "waiting"
    assert "query" not in str(projected).casefold()


def test_projection_degrades_on_saved_failure_and_preserves_latest_error() -> None:
    scout_ids = ("change_event_scout",)
    failed = {
        **run_row(role=scout_ids[0], status="failed", output_kind="no_op"),
        "toolProvenance": [
            {
                "tool_name": "alta_web_research",
                "status": "failed",
                "source_locators": [],
            }
        ],
        "knownAt": datetime(2026, 8, 30, 12, tzinfo=UTC) + timedelta(minutes=1),
    }

    projected = project_research_operations((failed,), scout_ids)

    assert projected["posture"] == "degraded"
    assert projected["failedRuns"] == 1
    assert projected["failedToolCalls"] == 1
    assert projected["minds"][0]["latestErrorCode"] == "provider_timeout"


def test_projection_separates_recovered_retries_from_contract_rejections() -> None:
    scout_ids = ("change_event_scout",)
    recovered = run_row(role=scout_ids[0], attempt_count=2)
    rejected = {
        **run_row(
            role=scout_ids[0],
            status="failed",
            attempt_count=3,
            error_code="invalid_output",
        ),
        "id": "run_contract_rejected",
        "knownAt": datetime(2026, 8, 30, 11, tzinfo=UTC),
    }

    projected = project_research_operations((recovered, rejected), scout_ids)

    assert projected["retriedRuns"] == 2
    assert projected["retryRecoveredRuns"] == 1
    assert projected["contractRejectedRuns"] == 1
    assert projected["deadlineFailedRuns"] == 0
    assert projected["minds"][0]["latestAttemptCount"] == 2


def test_projection_separates_follow_up_assignment_execution_and_no_op() -> None:
    scout_ids = ("change_event_scout",)
    completed_no_op = run_row(
        role=scout_ids[0],
        output_kind="no_op",
        assigned_mode="follow_up",
        output_research_mode="follow_up",
    )
    failed = {
        **run_row(
            role=scout_ids[0],
            status="failed",
            assigned_mode="follow_up",
            output_research_mode="",
        ),
        "id": "run_failed_follow_up",
        "knownAt": datetime(2026, 8, 30, 11, tzinfo=UTC),
    }

    projected = project_research_operations((completed_no_op, failed), scout_ids)

    assert projected["version"] == "alta-research-operations-v4"
    assert projected["followUpAssignedRuns"] == 2
    assert projected["followUpExecutedRuns"] == 1
    assert projected["followUpNoOpRuns"] == 1
    assert projected["minds"][0]["followUpAssignedRuns"] == 2
    assert projected["minds"][0]["followUpExecutedRuns"] == 1
