"""One bounded in-context correction; never repair facts or grant admission."""

import copy
import hashlib
import json
from typing import Any

from .freshness import current_signal_window
from .scout_feedback import build_scout_retry_feedback
from .scouts import ScoutRunSpec, parse_output


def finalization_repair(
    spec: ScoutRunSpec,
    response: str,
    schema: dict[str, Any],
    available: set[tuple[str, str]],
    market_context: set[tuple[str, str]],
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    try:
        parse_output(response, spec, available, market_context)
        return None
    except ValueError as error:
        feedback = build_scout_retry_feedback("invalid_output", error)
    corrected_schema = copy.deepcopy(schema)
    locator = corrected_schema["properties"]["tool_evidence_refs"]["items"][
        "properties"
    ]["source_locator"]
    # Dynamic enum is built exclusively from completed, source-scoped evidence.
    # A near match, search-only result, or invented URL is never added to it.
    locator["enum"] = sorted({url for _call, url in available}) or [""]
    prompt = json.dumps(
        {
            "scout_id": spec.scout.scout_id,
            "instruction": (
                "Correct your final JSON using only evidence already retrieved in this "
                "thread. Do not call tools or redo research. Select exact source URLs "
                "from the schema enum; never reconstruct or alter a URL. Return no_op "
                "with the exact frozen lineage if eligible evidence is insufficient. "
                "First check freshness_at against current_signal_window: an older "
                "event cannot pass even if all formatting issues are fixed. Return "
                "no_op unless already-retrieved evidence genuinely revalidates it. "
                "Do not change facts, backdate evidence or weaken the thesis to pass. "
                "Keep prose compact, every pillar within horizon, and total UTF-8 JSON "
                "below max_output_bytes. This is the only finalization correction."
            ),
            "max_output_bytes": spec.budget.max_output_bytes,
            "frozen_wake": spec.frozen_input.known_at.isoformat(),
            "current_signal_window": current_signal_window(spec.frozen_input.known_at),
            "retry_feedback": feedback,
        },
        separators=(",", ":"),
    )
    audit = {
        "draft_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "feedback": feedback,
        "citation_choices": len(locator["enum"]) if available else 0,
    }
    return prompt, corrected_schema, audit
