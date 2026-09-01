import hashlib
import json
import re
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox

from .ingest import redact
from .scouts import (
    ScoutRunSpec,
    ToolProvenance,
)

RESEARCH_BUDGET_EXEMPT_CONTROL_TOOLS = frozenset(
    {"list_mcp_resources", "list_mcp_resource_templates"}
)
MAX_DISCOVERED_EVIDENCE = 40


class ScoutDeadlineExceeded(Exception):
    pass


class ScoutBudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class ModelTurn:
    final_response: str
    thread_id: str
    turn_id: str
    total_tokens: int | None
    tools: tuple[ToolProvenance, ...]
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int | None = None
    discovered_evidence: tuple["ToolEvidenceDiscovery", ...] = ()
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ToolEvidenceDiscovery:
    tool_call_id: str
    tool_name: str
    source_locator: str
    content: dict[str, Any]
    content_hash: str
    origin_fingerprint: str = ""


class MindClient(Protocol):
    def run(
        self, spec: ScoutRunSpec, prompt: str, schema: dict[str, Any]
    ) -> ModelTurn: ...


def budget_charge_tokens(turn: ModelTurn) -> int | None:
    """Charges new context/output while retaining full provider usage for audit."""
    if turn.total_tokens is None:
        return None
    cached = turn.usage.get("cached_input_tokens", 0)
    return max(0, turn.total_tokens - cached)


def budget_charge_tool_calls(turn: ModelTurn) -> int:
    """Count completed research calls; the gateway caps all admitted attempts."""
    return sum(
        item.status == "completed"
        and item.tool_name not in RESEARCH_BUDGET_EXEMPT_CONTROL_TOOLS
        for item in turn.tools
    )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical_tool_locator(candidate: str) -> str | None:
    trimmed = candidate.rstrip(".,;:!?)\"']}>")
    unredacted = urlsplit(trimmed)
    if (unredacted.username, unredacted.password) != (None, None):
        return None
    parsed = urlsplit(redact(trimmed))
    if not parsed.hostname or (parsed.username, parsed.password) != (None, None):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


_SOURCE_LOCATOR_KEYS = frozenset(
    {
        "canonicalurl",
        "href",
        "link",
        "original",
        "snapshoturl",
        "sourceurl",
        "uri",
        "url",
    }
)

_EVIDENCE_RECORD_COLLECTION_KEYS = frozenset(
    {
        "captures",
        "fallbackresults",
        "filings",
        "items",
        "pages",
        "results",
        "sources",
    }
)

_NON_EVIDENCE_LOCATOR_KEYS = frozenset(
    {
        "favicon",
        "faviconurl",
        "image",
        "imageurl",
        "images",
        "links",
        "logo",
        "logourl",
        "socialimage",
        "thumbnail",
        "thumbnailurl",
    }
)


def _source_locators(value: Any) -> tuple[str, ...]:
    found: list[str] = []
    _collect_explicit_locators(value, found)
    if not found:
        _collect_text_locators(value, found)
    return tuple(found)


def _normalized_locator_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _append_source_urls(value: str, found: list[str]) -> None:
    for match in re.finditer(r"https://[^\s\"'<>\\]+", value):
        if len(found) >= 10:
            return
        locator = _canonical_tool_locator(match.group(0))
        if locator is not None and locator not in found:
            found.append(locator)


def _direct_source_locator_values(value: dict[Any, Any]) -> tuple[str, ...]:
    return tuple(
        child
        for child_key, child in value.items()
        if _normalized_locator_key(str(child_key)) in _SOURCE_LOCATOR_KEYS
        and isinstance(child, str)
    )


def _collect_explicit_mapping(value: dict[Any, Any], found: list[str]) -> None:
    direct = _direct_source_locator_values(value)
    if not direct:
        for child_key, child in value.items():
            _collect_explicit_locators(child, found, key=str(child_key))
        return
    before_nested = len(found)
    for child_key, child in value.items():
        if _normalized_locator_key(str(child_key)) in _EVIDENCE_RECORD_COLLECTION_KEYS:
            _collect_explicit_locators(child, found, key=str(child_key))
    if len(found) == before_nested:
        for child in direct:
            _append_source_urls(child, found)


def _collect_explicit_locators(
    value: Any, found: list[str], *, key: str | None = None
) -> None:
    if len(found) >= 10 or _normalized_locator_key(key) in _NON_EVIDENCE_LOCATOR_KEYS:
        return
    if isinstance(value, dict):
        _collect_explicit_mapping(value, found)
    elif isinstance(value, list):
        for child in value:
            _collect_explicit_locators(child, found, key=key)


def _collect_text_locators(
    value: Any, found: list[str], *, key: str | None = None
) -> None:
    if len(found) >= 10 or _normalized_locator_key(key) in _NON_EVIDENCE_LOCATOR_KEYS:
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            _collect_text_locators(child, found, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _collect_text_locators(child, found, key=key)
    elif isinstance(value, str):
        _append_source_urls(value, found)


def _utf8_prefix(value: str, maximum_bytes: int) -> str:
    encoded = value.encode()
    if len(encoded) <= maximum_bytes:
        return value
    return encoded[:maximum_bytes].decode(errors="ignore")


def _matching_source_payload(value: Any, locator: str) -> Any | None:
    """Return the smallest structured result node that directly owns a URL."""

    if isinstance(value, dict):
        return _matching_mapping_payload(value, locator)
    if isinstance(value, list):
        return _matching_list_payload(value, locator)
    return None


def _mapping_owns_locator(value: dict[Any, Any], locator: str) -> bool:
    return any(
        _canonical_tool_locator(child) == locator
        for child_key, child in value.items()
        if _normalized_locator_key(str(child_key)) in _SOURCE_LOCATOR_KEYS
        and isinstance(child, str)
    )


def _matching_mapping_payload(value: dict[Any, Any], locator: str) -> Any | None:
    if _mapping_owns_locator(value, locator):
        return value
    for child_key, child in value.items():
        matched = _matching_source_payload(child, locator)
        if matched is None:
            continue
        normalized_key = _normalized_locator_key(str(child_key))
        if normalized_key in {"metadata", "provenance"} or normalized_key.endswith(
            "provenance"
        ):
            return value
        return matched
    return None


def _matching_list_payload(value: list[Any], locator: str) -> Any | None:
    for child in value:
        matched = _matching_source_payload(child, locator)
        if matched is not None:
            return matched
    return None


def _source_scoped_result(value: Any, locator: str) -> Any:
    """Keep durable Evidence attributable to one source, not a call-wide prefix."""

    return _matching_source_payload(value, locator) or value


_ORIGIN_ROUTE_KEYS = _SOURCE_LOCATOR_KEYS | frozenset(
    {
        "alloweddomainmatch",
        "backend",
        "backends",
        "cached",
        "fallback",
        "fallbackchain",
        "failures",
        "metadata",
        "partial",
        "provider",
        "providers",
        "publisher",
        "query",
        "queries",
        "rank",
        "researchqualityscore",
        "researchtermmatches",
        "resultcount",
        "score",
        "searchbackend",
        "source",
        "sources",
        "stale",
    }
)


def _origin_content_projection(value: Any, *, key: str | None = None) -> Any | None:
    """Fingerprint underlying content without treating routes as independent facts.

    The same release can arrive through several tools, URLs, or syndication mirrors.
    Counting those routes as separate origins overstates corroboration.  Retaining
    normalized structured content while dropping retrieval-route metadata is
    deliberately conservative. Object keys and list-record boundaries remain
    intact, while list order and duplicate route records do not affect identity.
    """

    normalized_key = re.sub(r"[^a-z0-9]", "", (key or "").casefold())
    if normalized_key in _ORIGIN_ROUTE_KEYS:
        return None
    if isinstance(value, dict):
        projected = {}
        for child_key, child in value.items():
            child_name = re.sub(r"[^a-z0-9]", "", str(child_key).casefold())
            child_value = _origin_content_projection(child, key=str(child_key))
            if child_name and child_value is not None:
                projected[child_name] = child_value
        return projected or None
    if isinstance(value, list):
        unique = {}
        for child in value:
            child_value = _origin_content_projection(child)
            if child_value is None:
                continue
            encoded = json.dumps(
                child_value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            unique[encoded] = child_value
        return [unique[encoded] for encoded in sorted(unique)] or None
    if isinstance(value, str):
        without_routes = re.sub(r"https?://[^\s\"'<>\\]+", " ", value)
        return " ".join(without_routes.split()).casefold() or None
    if isinstance(value, (int, float, bool)):
        return value
    return None


def _strict_schema_node(value: Any) -> Any:
    if isinstance(value, list):
        return [_strict_schema_node(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if key in {"default", "discriminator"}:
            continue
        normalized_key = "anyOf" if key == "oneOf" else key
        result[normalized_key] = _strict_schema_node(child)
    properties = result.get("properties")
    if result.get("type") == "object" and isinstance(properties, dict):
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def _strict_output_schema(value: dict[str, Any]) -> dict[str, Any]:
    """Makes Pydantic schemas portable to strict structured-output providers."""
    result = _strict_schema_node(value)
    if result.get("type") == "object":
        return result
    definitions = result.pop("$defs", None)
    wrapped = {
        "type": "object",
        "properties": {"output": result},
        "required": ["output"],
        "additionalProperties": False,
    }
    if definitions is not None:
        wrapped["$defs"] = definitions
    return wrapped


def _tool_evidence(items: Sequence[Any]) -> tuple[ToolEvidenceDiscovery, ...]:
    per_call: list[list[ToolEvidenceDiscovery]] = []
    for item in items:
        root = getattr(item, "root", item)
        body = root.model_dump(mode="json", by_alias=True)
        item_type = body.get("type")
        if item_type not in {"mcpToolCall", "dynamicToolCall", "webSearch"}:
            continue
        if str(body.get("status", "completed")) != "completed":
            continue
        tool_call_id = str(body.get("id", "unknown"))
        tool_name = (
            "web_search"
            if item_type == "webSearch"
            else str(body.get("tool", "unknown"))
        )
        redacted_result = redact(body.get("result"))
        result_text = _utf8_prefix(
            json.dumps(
                redacted_result,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            2_000,
        )
        discoveries = []
        for locator in _source_locators(redacted_result):
            source_payload = _source_scoped_result(redacted_result, locator)
            source_text = _utf8_prefix(
                json.dumps(
                    source_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                4_000,
            )
            origin_projection = _origin_content_projection(source_payload)
            origin_fingerprint = _canonical_hash(
                {"content_projection": origin_projection}
                if origin_projection is not None
                else {"source_locator": locator}
            )
            content = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "source_locator": locator,
                "result_text": source_text or result_text,
                "origin_fingerprint": origin_fingerprint,
            }
            discoveries.append(
                ToolEvidenceDiscovery(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    source_locator=locator,
                    content=content,
                    content_hash=_canonical_hash(content),
                    origin_fingerprint=origin_fingerprint,
                )
            )
        if discoveries:
            per_call.append(discoveries)

    # Preserve evidence from every completed research step before taking more
    # URLs from an early broad search. Without round-robin allocation, a first
    # deep-search call could consume the whole evidence window and silently
    # discard later market-context or counterevidence calls.
    result: list[ToolEvidenceDiscovery] = []
    for locator_index in range(10):
        for discoveries in per_call:
            if locator_index < len(discoveries):
                result.append(discoveries[locator_index])
                if len(result) >= MAX_DISCOVERED_EVIDENCE:
                    return tuple(result)
    return tuple(result)


def _tool_provenance(items: Sequence[Any]) -> tuple[ToolProvenance, ...]:
    result: list[ToolProvenance] = []
    for item in items:
        root = getattr(item, "root", item)
        body = root.model_dump(mode="json", by_alias=True)
        item_type = body.get("type")
        if item_type not in {"mcpToolCall", "dynamicToolCall", "webSearch"}:
            continue
        if item_type == "webSearch":
            tool_name = "web_search"
            arguments = {"query": body.get("query")}
        else:
            tool_name = str(body.get("tool", "unknown"))
            arguments = body.get("arguments", {})
        result.append(
            ToolProvenance(
                tool_call_id=str(body.get("id", "unknown")),
                tool_name=tool_name,
                status=str(body.get("status", "completed")),
                arguments_hash=_canonical_hash(redact(arguments)),
                source_locators=_source_locators(body.get("result")),
            )
        )
    return tuple(result)


class SdkAppServerMindClient:
    def __init__(
        self,
        *,
        repo_root: Path,
        provider: str,
        model_id: str,
        agent_cwd: Path,
        reasoning_effort: str = "low",
        launch_command: tuple[str, ...] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        interrupt_grace_seconds: float = 1.0,
    ) -> None:
        command = launch_command or (
            str(repo_root / "alta"),
            provider,
            "app-server",
        )
        safe_launch = (
            sys.executable,
            "-m",
            "alta_asterism.agent_launch",
            "--",
            *command,
        )
        self._clock = clock
        self._model_id = model_id
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("reasoning_effort must be low, medium, or high")
        self._reasoning_effort = reasoning_effort
        self._agent_cwd = agent_cwd
        self._interrupt_grace_seconds = interrupt_grace_seconds
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._codex_config = CodexConfig(
            launch_args_override=safe_launch,
            cwd=str(agent_cwd),
            env={"ALTA_AGENT_SAFE_APP_SERVER": "1"},
            client_name="alta_mind_worker",
            client_title="ALTA Mind Worker",
            experimental_api=False,
        )
        self._codex: Codex | None = None

    def close(self) -> None:
        if self._codex is not None:
            self._codex.close()
            self._codex = None
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _reset_after_stuck_turn(self) -> None:
        if self._codex is not None:
            self._codex.close()
            self._codex = None
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = ThreadPoolExecutor(max_workers=1)

    def __enter__(self) -> "SdkAppServerMindClient":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def run(self, spec: ScoutRunSpec, prompt: str, schema: dict[str, Any]) -> ModelTurn:
        with self._lock:
            started = time.monotonic()
            if self._codex is None:
                self._codex = Codex(self._codex_config)
            thread = self._codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                config={
                    "features.apply_patch_freeform": False,
                    "features.apps": False,
                    "features.multi_agent": False,
                    "features.plugins": False,
                    "features.shell_tool": False,
                    "features.standalone_web_search": False,
                    "features.unified_exec": False,
                    "features.web_search": False,
                    "features.web_search_request": False,
                    "model_reasoning_effort": self._reasoning_effort,
                    "mcp_servers.alta_internet.enabled": bool(spec.scout.allowed_tools),
                    "mcp_servers.alta_internet.enabled_tools": list(
                        spec.scout.allowed_tools
                    ),
                    "mcp_servers.alta_internet.http_headers.X-ALTA-Run-ID": spec.run_id,
                    "mcp_servers.alta_internet.http_headers.X-ALTA-Max-Tool-Calls": str(
                        spec.budget.max_tool_calls
                    ),
                    "orchestrator.skills.enabled": False,
                    "project_doc_max_bytes": 0,
                    "web_search": "disabled",
                },
                cwd=str(self._agent_cwd),
                developer_instructions=(
                    "Operate read-only. Use only the supplied Scout territory. "
                    + (
                        "Before answering, you MUST call at least one enabled ALTA "
                        "active-research tool; do not return a placeholder or no-op "
                        "without making that tool call. "
                        if spec.budget.require_active_research
                        else ""
                    )
                    + "Return only the requested structured output."
                ),
                ephemeral=True,
                model=self._model_id,
                sandbox=Sandbox.read_only,
                service_name="alta_mind_worker",
            )
            schema_requires_envelope = schema.get("type") != "object"
            turn = thread.turn(
                prompt,
                approval_mode=ApprovalMode.deny_all,
                model=self._model_id,
                output_schema=_strict_output_schema(schema),
                sandbox=Sandbox.read_only,
            )

            def await_result(active_turn):
                remaining = (spec.deadline_at - self._clock()).total_seconds()
                if remaining <= 0:
                    active_turn.interrupt()
                    raise ScoutDeadlineExceeded(
                        "Scout deadline elapsed before turn stream"
                    )
                future = self._executor.submit(active_turn.run)
                try:
                    return future.result(timeout=remaining)
                except FutureTimeout as error:
                    active_turn.interrupt()
                    try:
                        future.result(timeout=self._interrupt_grace_seconds)
                    except FutureTimeout:
                        self._reset_after_stuck_turn()
                    except Exception:
                        pass
                    raise ScoutDeadlineExceeded(
                        "Scout turn exceeded its deadline"
                    ) from error

            results = [await_result(turn)]
            if not (results[0].final_response or "").strip():
                recovery_prompt = json.dumps(
                    {
                        "scout_id": spec.scout.scout_id,
                        "instruction": (
                            "Return the final structured object now using only the "
                            "evidence already gathered. Do not call another tool. If "
                            "the evidence is insufficient, return a no_op object."
                        ),
                    },
                    separators=(",", ":"),
                )
                recovery_turn = thread.turn(
                    recovery_prompt,
                    approval_mode=ApprovalMode.deny_all,
                    model=self._model_id,
                    output_schema=_strict_output_schema(schema),
                    sandbox=Sandbox.read_only,
                )
                results.append(await_result(recovery_turn))
            result = results[-1]
            if not (result.final_response or "").strip():
                raise ValueError("App Server turn did not return a final response")
            final_response = result.final_response
            if schema_requires_envelope:
                envelope = json.loads(final_response)
                if isinstance(envelope, dict) and "output" in envelope:
                    final_response = json.dumps(
                        envelope["output"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
            usage_fields = (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            )
            usage_totals = None
            if all(item.usage is not None for item in results):
                usage_totals = {
                    field: sum(getattr(item.usage.total, field) for item in results)
                    for field in usage_fields
                }
            items = tuple(item for child in results for item in child.items)
            return ModelTurn(
                final_response=final_response,
                thread_id=thread.id,
                turn_id=result.id,
                total_tokens=(usage_totals["total_tokens"] if usage_totals else None),
                tools=_tool_provenance(items),
                usage=usage_totals or {},
                latency_ms=max(0, int((time.monotonic() - started) * 1_000)),
                discovered_evidence=_tool_evidence(items),
                completed_at=self._clock(),
            )
