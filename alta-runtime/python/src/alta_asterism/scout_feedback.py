import json

from pydantic import ValidationError


class ActiveResearchRequired(Exception):
    pass


SCOUT_RETRY_ISSUE_LIMIT = 2


def _bounded_issue_part(value: object, maximum: int = 96) -> str:
    normalized = "_".join(str(value).strip().split())
    return normalized[:maximum] or "unknown"


def build_scout_retry_feedback(error_code: str, error: Exception) -> dict[str, object]:
    """Return bounded correction metadata without replaying model output."""

    issues: list[dict[str, str]] = []
    if isinstance(error, ValidationError):
        category = "schema_validation"
        for item in error.errors()[:SCOUT_RETRY_ISSUE_LIMIT]:
            location = ".".join(_bounded_issue_part(part, 32) for part in item["loc"])
            issues.append(
                {
                    "path": location[:64] or "$",
                    "code": _schema_issue_code(item),
                }
            )
    elif isinstance(error, json.JSONDecodeError):
        category = "json_contract"
        issues.append({"path": "$", "code": "invalid_json"})
    elif isinstance(error, ActiveResearchRequired):
        category = "active_research"
        issues.append({"path": "tool_calls", "code": "active_research_required"})
    elif str(error) == "Scout output exceeds max_output_bytes":
        category = "output_budget"
        issues.append({"path": "$", "code": "output_bytes_exceeded"})
    else:
        message = str(error).casefold()
        category = "semantic_contract"
        semantic_codes = (
            ("decision-complete", "decision_fields_incomplete"),
            ("thesis pillar", "thesis_pillar_invalid"),
            ("research attention seat", "attention_seat_violation"),
            ("alpha_archetype", "alpha_archetype_invalid"),
            ("evidence outside", "evidence_scope_violation"),
            ("tool evidence", "tool_evidence_binding_invalid"),
            ("assigned opportunity", "follow_up_parent_invalid"),
            ("assigned research question", "follow_up_question_invalid"),
            ("freshness_at is expired", "freshness_signal_expired"),
            ("freshness_at exceeds", "freshness_after_frozen_wake"),
            ("freshness_at", "freshness_invalid"),
            ("finance market context", "market_context_required"),
            ("expectation posture", "market_context_required"),
        )
        code = next(
            (value for fragment, value in semantic_codes if fragment in message),
            "semantic_contract_invalid",
        )
        issues.append({"path": "$", "code": code})
    feedback: dict[str, object] = {
        "previous_error_code": _bounded_issue_part(error_code, 64),
        "category": category,
        "issues": issues,
    }
    if category == "output_budget":
        feedback["correction"] = (
            "UTF-8 JSON below max_output_bytes. Prose <=320 chars/field; pillars "
            "<=160. Preserve required fields, exact refs, independent evidence "
            "roles and lineage; no_op if it cannot fit. Never truncate citations."
        )
    elif issues[0]["code"] == "freshness_signal_expired":
        feedback["correction"] = (
            "Retrieve a new thesis-changing observable inside the current signal "
            "window, or return no_op. Re-fetching an old filing does not renew it. "
            "Never replace its event time with today's retrieval time."
        )
    elif issues[0]["code"] == "freshness_after_frozen_wake":
        feedback["correction"] = (
            "Use the source event time no later than frozen_input.known_at. "
            "Check the timezone; do not backdate future evidence. Return no_op "
            "if there is no eligible current signal."
        )
    return feedback


def _schema_issue_code(item: dict[str, object]) -> str:
    # Pydantic reports every model-level invariant as "value_error". Only
    # translate our known contract messages, never reflect arbitrary input.
    message = str(item.get("msg", ""))
    invariants = (
        (
            "explore Candidate cannot claim follow-up lineage",
            "explore_lineage_must_be_empty",
        ),
        (
            "explore no-op cannot claim follow-up lineage",
            "explore_lineage_must_be_empty",
        ),
        (
            "thesis pillar cannot resolve after Candidate horizon",
            "pillar_days_must_not_exceed_horizon",
        ),
        (
            "follow_up Candidate requires parent Opportunity and research question",
            "follow_up_requires_exact_assignment",
        ),
        (
            "follow_up no-op requires parent Opportunity and research question",
            "follow_up_requires_exact_assignment",
        ),
    )
    return next(
        (
            code
            for expected, code in invariants
            if message == f"Value error, {expected}"
        ),
        _bounded_issue_part(item.get("type"), 40),
    )
