from copy import deepcopy

from alta_asterism.context_budget import json_size
from alta_asterism.failure_artifact import bounded_failure_artifact


def test_failure_preview_fits_escaped_json_and_preserves_provenance() -> None:
    content = {
        "schema": "alta.scout-failure.v1",
        "tool_provenance": [{"source_locators": ["https://example.org/" + "x" * 950]}]
        * 12,
        "bounded_final_response": '\\"線索' * 1_500,
        "error_code": "invalid_output",
        "retry_feedback": {"category": "semantic_contract"},
    }
    original = deepcopy(content)
    result = bounded_failure_artifact(content)
    assert json_size(original) > 16_384
    assert json_size(result) <= 16_384
    assert result["diagnostics_truncated"] is True
    assert result["tool_provenance"] == original["tool_provenance"]
    assert original["bounded_final_response"].startswith(
        result["bounded_final_response"]
    )
    assert len(result["original_diagnostics_hash"]) == 64
    assert content == original


def test_failure_full_provenance_budget_keeps_explicit_hash_summary() -> None:
    content = {
        "schema": "alta.scout-failure.v1",
        "tool_provenance": [{"source_locators": ["x" * 16_100]}],
        "bounded_final_response": "response" * 800,
        "error_code": "invalid_output",
    }
    result = bounded_failure_artifact(content)
    assert json_size(result) <= 16_384
    assert result["tool_provenance_omitted"] is True
    assert result["tool_provenance_count"] == 1
    assert len(result["tool_provenance_hash"]) == 64
    assert result["error_code"] == "invalid_output"


def test_small_failure_artifact_remains_unchanged() -> None:
    content = {"bounded_final_response": "invalid response", "tool_provenance": []}
    assert bounded_failure_artifact(content) == content
