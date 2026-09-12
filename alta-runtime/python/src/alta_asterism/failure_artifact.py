"""Fit untrusted failure diagnostics without relaxing durable database limits."""

from copy import deepcopy
from hashlib import sha256
from typing import Any

from .context_budget import canonical_json_bytes, json_size

MAX_FAILURE_ARTIFACT_BYTES = 16_384


def bounded_failure_artifact(content: dict[str, Any]) -> dict[str, Any]:
    """Prefer full provenance over a preview; explicitly mark any omitted detail.

    The run row independently keeps the validated tool provenance. This is a
    diagnostic artifact for a rejected attempt, never evidence for a Candidate.
    JSON escaping is measured as PostgreSQL measures it, not as raw string bytes.
    """
    if json_size(content) <= MAX_FAILURE_ARTIFACT_BYTES:
        return content
    result = deepcopy(content)
    result["diagnostics_truncated"] = True
    result["original_diagnostics_bytes"] = json_size(content)
    result["original_diagnostics_hash"] = sha256(
        canonical_json_bytes(content)
    ).hexdigest()
    preview = result.get("bounded_final_response") or ""
    result["bounded_final_response"] = ""
    if json_size(result) > MAX_FAILURE_ARTIFACT_BYTES:
        # A nearly full run-provenance budget leaves no room for the enclosing
        # artifact. Keep a verifiable summary instead of rolling back failure
        # recording and crashing the entire research cycle.
        provenance = result.pop("tool_provenance", [])
        result["tool_provenance"] = []
        result["tool_provenance_omitted"] = True
        result["tool_provenance_count"] = len(provenance)
        result["tool_provenance_hash"] = sha256(
            canonical_json_bytes(provenance)
        ).hexdigest()
    low, high = 0, len(preview)
    while low < high:
        middle = (low + high + 1) // 2
        result["bounded_final_response"] = preview[:middle]
        if json_size(result) <= MAX_FAILURE_ARTIFACT_BYTES:
            low = middle
        else:
            high = middle - 1
    result["bounded_final_response"] = preview[:low]
    return result
