import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, TypeVar

from psycopg.types.json import Jsonb
from pydantic import BaseModel, TypeAdapter, ValidationError

from .agent_context import require_bounded_frozen_input
from .context_budget import MAX_ROLE_PROMPT_BYTES, canonical_json_bytes
from .database import Database
from .mind_worker import (
    MindClient,
    ModelTurn,
    ScoutBudgetExceeded,
    ScoutDeadlineExceeded,
    budget_charge_tokens,
)
from .scouts import RunBudget

OutputT = TypeVar("OutputT", bound=BaseModel)
MAX_ROLE_ATTEMPTS = 2


class StructuredRoleUnavailable(Exception):
    """A bounded judgment role could not produce an admissible output."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class _Role:
    scout_id: str
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RoleSpec:
    run_id: str
    scout: _Role
    budget: RunBudget
    deadline_at: datetime


@dataclass(frozen=True)
class RoleOutput(Generic[OutputT]):
    value: OutputT
    turn: ModelTurn | None
    recovered: bool


def _validate_structured_response(adapter: TypeAdapter[OutputT], text: str) -> OutputT:
    try:
        return adapter.validate_json(text)
    except ValidationError as original_error:
        decoder = json.JSONDecoder()
        candidates: dict[str, OutputT] = {}
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text, index)
                validated = adapter.validate_python(candidate)
            except (json.JSONDecodeError, ValidationError):
                continue
            canonical = json.dumps(
                validated.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            candidates[canonical] = validated
        if len(candidates) != 1:
            raise original_error
        return next(iter(candidates.values()))


class StructuredRoleRunner:
    """Runs non-Scout minds through the same isolated App Server harness."""

    def __init__(
        self,
        database: Database,
        client: MindClient,
        *,
        model_provider: str,
        model_id: str,
        max_total_tokens: int = 4_000,
        max_output_bytes: int = 12_000,
        deadline_seconds: float = 120,
    ) -> None:
        self.database = database
        self.client = client
        self.model_provider = model_provider
        self.model_id = model_id
        self.budget = RunBudget(
            max_tool_calls=0,
            max_total_tokens=max_total_tokens,
            max_output_bytes=max_output_bytes,
        )
        self.deadline_seconds = deadline_seconds

    def run(
        self,
        *,
        cycle_id: str,
        run_id: str,
        role: str,
        prompt: dict[str, Any],
        output_type: type[OutputT],
        frozen_input: dict[str, Any],
        evidence_ids: tuple[str, ...],
        known_at: datetime,
        prompt_version: str,
    ) -> RoleOutput[OutputT]:
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise ValueError("role known_at must be timezone-aware")
        prompt_text = json.dumps(
            prompt, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        if len(prompt_text.encode()) > MAX_ROLE_PROMPT_BYTES:
            raise StructuredRoleUnavailable("prompt_budget")
        try:
            require_bounded_frozen_input(frozen_input)
        except ValueError as error:
            raise StructuredRoleUnavailable("frozen_input_budget") from error
        adapter = TypeAdapter(output_type)
        try:
            existing = self._existing(run_id, cycle_id, adapter)
        except ValidationError as error:
            raise StructuredRoleUnavailable("recovered_output_invalid") from error
        if existing is not None:
            return RoleOutput(value=existing, turn=None, recovered=True)
        input_hash = canonical_hash(frozen_input)
        while True:
            spec = _RoleSpec(
                run_id=run_id,
                scout=_Role(role),
                budget=self.budget,
                deadline_at=datetime.now(UTC)
                + timedelta(seconds=self.deadline_seconds),
            )
            attempt = self._start(
                spec,
                cycle_id=cycle_id,
                role=role,
                frozen_input=frozen_input,
                input_hash=input_hash,
                evidence_ids=evidence_ids,
                known_at=known_at,
                prompt_version=prompt_version,
            )
            turn: ModelTurn | None = None
            try:
                turn = self.client.run(spec, prompt_text, adapter.json_schema())
                self._validate_turn(turn)
                value = _validate_structured_response(adapter, turn.final_response)
                self._complete(spec, value, turn, known_at)
                return RoleOutput(value=value, turn=turn, recovered=False)
            except ValidationError as error:
                self._fail(run_id, type(error).__name__, turn)
                if attempt < MAX_ROLE_ATTEMPTS:
                    continue
                raise StructuredRoleUnavailable("invalid_output") from error
            except ScoutDeadlineExceeded as error:
                self._fail(run_id, type(error).__name__, turn)
                if attempt < MAX_ROLE_ATTEMPTS:
                    continue
                raise StructuredRoleUnavailable(type(error).__name__) from error
            except ScoutBudgetExceeded as error:
                self._fail(run_id, type(error).__name__, turn)
                raise StructuredRoleUnavailable(type(error).__name__) from error
            except Exception as error:
                self._fail(run_id, type(error).__name__, turn)
                raise

    def _existing(
        self, run_id: str, cycle_id: str, adapter: TypeAdapter[OutputT]
    ) -> OutputT | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT r.status, a.content, r.cycle_id,
                r.model_provider, r.model_id
                FROM research.run r
                LEFT JOIN research.run_artifact a ON a.run_id = r.id
                  AND a.artifact_kind = 'role_output'
                WHERE r.id = %s ORDER BY a.version DESC NULLS LAST LIMIT 1""",
                (run_id,),
            ).fetchone()
            if row is not None and row[2] is None:
                connection.execute(
                    """UPDATE research.run SET cycle_id = %s
                    WHERE id = %s AND cycle_id IS NULL""",
                    (cycle_id, run_id),
                )
                row = (*row[:2], cycle_id, *row[3:])
        if row is None:
            return None
        if row[2:] != (cycle_id, self.model_provider, self.model_id):
            raise ValueError("role run cycle or model route changed during recovery")
        if row[0] == "succeeded":
            if row[1] is None:
                raise ValueError("succeeded role run is missing its durable output")
            return adapter.validate_python(row[1]["output"])
        return None

    def _start(
        self,
        spec: _RoleSpec,
        *,
        cycle_id: str,
        role: str,
        frozen_input: dict[str, Any],
        input_hash: str,
        evidence_ids: tuple[str, ...],
        known_at: datetime,
        prompt_version: str,
    ) -> int:
        with self.database.connect() as connection:
            inserted = connection.execute(
                """INSERT INTO research.run
                (id, environment, version, known_at, cycle_id, role, status, input_hash,
                 frozen_input, budget, deadline_at, prompt_version,
                 tool_catalog_version, model_provider, model_id, trace_id,
                 tool_provenance, evidence_ids, attempt_count)
                VALUES (%s,'shadow',1,%s,%s,%s,'running',%s,%s,%s,%s,%s,'none',
                        %s,%s,%s,'[]'::jsonb,%s,1)
                ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    spec.run_id,
                    known_at,
                    cycle_id,
                    role,
                    input_hash,
                    Jsonb(frozen_input),
                    Jsonb(self.budget.model_dump(mode="json")),
                    spec.deadline_at,
                    prompt_version,
                    self.model_provider,
                    self.model_id,
                    f"trace_{spec.run_id[4:]}",
                    list(evidence_ids),
                ),
            ).fetchone()
            if inserted is not None:
                return 1
            row = connection.execute(
                """SELECT environment::text, cycle_id, role, input_hash, status,
                attempt_count, model_provider, model_id
                FROM research.run WHERE id = %s FOR UPDATE""",
                (spec.run_id,),
            ).fetchone()
            if row[:4] != ("shadow", cycle_id, role, input_hash):
                raise ValueError("role run ID already has different frozen input")
            if row[6:] != (self.model_provider, self.model_id):
                raise ValueError("role run ID already has a different model route")
            if row[4] == "succeeded":
                raise ValueError("completed role run was not recovered before start")
            if row[5] >= MAX_ROLE_ATTEMPTS:
                raise ValueError("structured role retry budget is exhausted")
            updated = connection.execute(
                """UPDATE research.run SET status = 'running', error_code = NULL,
                deadline_at = %s, attempt_count = attempt_count + 1
                WHERE id = %s RETURNING attempt_count""",
                (spec.deadline_at, spec.run_id),
            ).fetchone()
            return updated[0]

    def _validate_turn(self, turn: ModelTurn) -> None:
        if turn.tools:
            raise ScoutBudgetExceeded("structured role cannot call tools")
        charged_tokens = budget_charge_tokens(turn)
        if charged_tokens is None:
            raise ScoutBudgetExceeded("structured role token usage is missing")
        if charged_tokens > self.budget.max_total_tokens:
            raise ScoutBudgetExceeded("structured role token budget exceeded")
        if len(turn.final_response.encode()) > self.budget.max_output_bytes:
            raise ScoutBudgetExceeded("structured role output budget exceeded")

    def _complete(
        self,
        spec: _RoleSpec,
        value: OutputT,
        turn: ModelTurn,
        fallback_known_at: datetime,
    ) -> None:
        content = {
            "schema": "alta.role-output.v1",
            "output": value.model_dump(mode="json"),
        }
        known_at = turn.completed_at or fallback_known_at
        content_hash = canonical_hash(content)
        artifact_id = "artifact_" + canonical_hash([spec.run_id, "role_output", 1])[:32]
        with self.database.connect() as connection:
            updated = connection.execute(
                """UPDATE research.run SET status = 'succeeded', error_code = NULL,
                output_kind = 'role_output', thread_id = %s, turn_id = %s,
                actual_usage = %s, latency_ms = %s
                WHERE id = %s AND status = 'running' RETURNING id""",
                (
                    turn.thread_id,
                    turn.turn_id,
                    Jsonb(turn.usage),
                    turn.latency_ms,
                    spec.run_id,
                ),
            ).fetchone()
            if updated is None:
                raise ValueError("structured role completion lost running state")
            connection.execute(
                """INSERT INTO research.run_artifact
                (id, environment, version, known_at, run_id, artifact_kind,
                 schema_version, content, content_hash)
                VALUES (%s,'shadow',1,%s,%s,'role_output','alta.role-output.v1',%s,%s)
                ON CONFLICT (run_id, artifact_kind, version) DO NOTHING""",
                (
                    artifact_id,
                    known_at,
                    spec.run_id,
                    Jsonb(content),
                    content_hash,
                ),
            )

    def _fail(self, run_id: str, error_code: str, turn: ModelTurn | None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE research.run SET status = 'failed', error_code = %s,
                thread_id = %s, turn_id = %s, actual_usage = %s, latency_ms = %s
                WHERE id = %s AND status = 'running'""",
                (
                    error_code[:64],
                    turn.thread_id if turn else None,
                    turn.turn_id if turn else None,
                    Jsonb(turn.usage if turn else {}),
                    turn.latency_ms if turn else None,
                    run_id,
                ),
            )
