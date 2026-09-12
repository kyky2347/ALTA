import hashlib
import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from .mind_worker import (
    MindClient,
    ModelTurn,
    ScoutBudgetExceeded,
    ScoutDeadlineExceeded,
    RESEARCH_BUDGET_EXEMPT_CONTROL_TOOLS,
    budget_charge_tool_calls,
    budget_charge_tokens,
)
from .scout_repository import ScoutRepository, ScoutRunOutcome
from .scout_feedback import ActiveResearchRequired, build_scout_retry_feedback
from .scout_limits import MAX_SCOUT_TOKEN_BUDGET
from .scouts import (
    ACTIVE_RESEARCH_TOOLS,
    SCOUTS,
    FrozenScoutInput,
    RunBudget,
    ScoutConfig,
    ScoutRunSpec,
    build_prompt,
    fit_frozen_input_for_scout,
    make_run_spec,
    output_schema,
    parse_output,
)

SCOUT_CONTROL_TOOLS = RESEARCH_BUDGET_EXEMPT_CONTROL_TOOLS


def tools_within_scout_territory(
    turn: ModelTurn, allowed_tools: tuple[str, ...]
) -> bool:
    allowed = set(allowed_tools) | SCOUT_CONTROL_TOOLS
    return all(tool.tool_name in allowed for tool in turn.tools)


def active_research_attempted(turn: ModelTurn, allowed_tools: tuple[str, ...]) -> bool:
    active = ACTIVE_RESEARCH_TOOLS.intersection(allowed_tools)
    return any(tool.tool_name in active for tool in turn.tools)


def incentive_adjusted_budget(
    base: RunBudget, frozen_input: FrozenScoutInput
) -> RunBudget:
    """Apply only the frozen, maturity-gated research bonus within hard caps."""

    if len(frozen_input.research_incentives) != 1:
        return base
    incentive = frozen_input.research_incentives[0]
    if incentive.state != "earned":
        return base
    return base.model_copy(
        update={
            "max_tool_calls": min(12, base.max_tool_calls + incentive.bonus_tool_calls),
            "max_total_tokens": min(
                MAX_SCOUT_TOKEN_BUDGET,
                base.max_total_tokens + incentive.bonus_total_tokens,
            ),
        }
    )


class MindWorker:
    """Runs one durable, isolated Scout batch with bounded parallelism."""

    def __init__(
        self,
        *,
        repository: ScoutRepository,
        client: MindClient,
        model_provider: str,
        model_id: str,
        model_overrides: dict[str, tuple[str, str]] | None = None,
        budget: RunBudget,
        deadline_seconds: float,
        max_concurrency: int = 1,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if not 1 <= max_concurrency <= len(SCOUTS):
            raise ValueError(f"max_concurrency must be between 1 and {len(SCOUTS)}")
        self.repository = repository
        self.client = client
        self.model_provider = model_provider
        self.model_id = model_id
        self.model_overrides = dict(model_overrides or {})
        self.budget = budget
        self.deadline_seconds = deadline_seconds
        self.max_concurrency = max_concurrency
        self.clock = clock

    def run_batch(
        self,
        batch_id: str,
        frozen_input: FrozenScoutInput,
        *,
        source_postures: dict[str, str] | None = None,
    ) -> tuple[ScoutRunOutcome, ...]:
        self.repository.validate_frozen_input(frozen_input)
        durable_postures = source_postures or {
            "direct_batch": ("healthy" if frozen_input.evidence else "unavailable")
        }
        job_id = self.repository.start_batch(batch_id, frozen_input, durable_postures)
        try:
            started_at = self.clock()
            specs = tuple(
                self._build_run_spec(
                    batch_id,
                    frozen_input,
                    config,
                    started_at
                    + timedelta(
                        seconds=self.deadline_seconds
                        * (index + 1 if self.max_concurrency == 1 else 1)
                    ),
                )
                for index, config in enumerate(SCOUTS)
            )
            # Reservation and validation are one transaction. A recovered
            # partial set either matches every prior frozen role before missing
            # roles are inserted, or commits no new role at all.
            inserted_runs = self.repository.start_runs(job_id, specs)
            if self.max_concurrency == 1:
                completed = []
                for spec, inserted in zip(specs, inserted_runs, strict=True):
                    completed.append(
                        self._run_one(job_id, spec)
                        if inserted
                        else self.repository.existing_outcome(spec)
                    )
            else:
                outcomes: list[ScoutRunOutcome | None] = [None] * len(SCOUTS)
                pending: list[tuple[int, ScoutRunSpec]] = []
                for index, (spec, inserted) in enumerate(
                    zip(specs, inserted_runs, strict=True)
                ):
                    if inserted:
                        pending.append((index, spec))
                    else:
                        outcomes[index] = self.repository.existing_outcome(spec)
                with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
                    futures: dict[Future[ScoutRunOutcome], int] = {
                        executor.submit(self._run_one, job_id, spec): index
                        for index, spec in pending
                    }
                    for future, index in futures.items():
                        outcomes[index] = future.result()
                completed = [item for item in outcomes if item is not None]
        except Exception:
            self.repository.finish_batch(job_id, failed=True)
            raise
        if len(completed) != len(SCOUTS):
            self.repository.finish_batch(job_id, failed=True)
            raise RuntimeError("Scout batch did not produce one outcome per Scout")
        self.repository.finish_batch(
            job_id, failed=all(item.status == "failed" for item in completed)
        )
        return tuple(completed)

    def _build_run_spec(
        self,
        batch_id: str,
        frozen_input: FrozenScoutInput,
        config: ScoutConfig,
        deadline_at: datetime,
    ) -> ScoutRunSpec:
        scoped_input = frozen_input.for_scout(config.scout_id, config.primary_sources)
        scout_budget = incentive_adjusted_budget(self.budget, scoped_input)
        scout_input = fit_frozen_input_for_scout(frozen_input, config, scout_budget)
        if scout_budget != self.budget and not scout_input.research_incentives:
            scout_budget = self.budget
            scout_input = fit_frozen_input_for_scout(frozen_input, config, scout_budget)
        run_digest = hashlib.sha256(
            f"{batch_id}\0{config.scout_id}".encode()
        ).hexdigest()
        return make_run_spec(
            run_id=f"run_{run_digest[:32]}",
            trace_id=f"trace_{run_digest[32:]}",
            scout=config,
            frozen_input=scout_input,
            budget=scout_budget,
            deadline_at=deadline_at,
            model_provider=self.model_overrides.get(
                config.scout_id, (self.model_provider, self.model_id)
            )[0],
            model_id=self.model_overrides.get(
                config.scout_id, (self.model_provider, self.model_id)
            )[1],
        )

    def _run_one(self, job_id: str, spec: ScoutRunSpec) -> ScoutRunOutcome:
        retry_feedback: dict[str, object] | None = None
        while True:
            turn: ModelTurn | None = None
            try:
                turn = self.client.run(
                    spec, build_prompt(spec, retry_feedback), output_schema(spec)
                )
                self._validate_budget(spec, turn)
                available_tool_evidence = {
                    (item.tool_call_id, item.source_locator)
                    for item in turn.discovered_evidence
                }
                market_context_evidence = {
                    (item.tool_call_id, item.source_locator)
                    for item in turn.discovered_evidence
                    if item.tool_name == "alta_finance_data"
                }
                output = parse_output(
                    turn.final_response,
                    spec,
                    available_tool_evidence,
                    market_context_evidence,
                )
                output = self.repository.collect_tool_evidence(spec, turn, output)
                self.repository.complete(spec, turn, output)
                return ScoutRunOutcome(
                    run_id=spec.run_id,
                    scout_id=spec.scout.scout_id,
                    status="succeeded",
                    output=output,
                    error_code=None,
                )
            except ScoutDeadlineExceeded as error:
                outcome = self._failed(spec, "deadline_exceeded", turn, error)
                spec = spec.model_copy(
                    update={"deadline_at": self._next_deadline(spec)}
                )
                if self.repository.start_run(job_id, spec):
                    continue
                return outcome
            except ScoutBudgetExceeded as error:
                return self._failed(spec, "budget_exceeded", turn, error)
            except ActiveResearchRequired as error:
                retry_feedback = build_scout_retry_feedback(
                    "active_research_required", error
                )
                outcome = self._failed(
                    spec,
                    "active_research_required",
                    turn,
                    error,
                    retry_feedback,
                )
                retry_spec = self._retry(job_id, spec)
                if retry_spec is not None:
                    spec = retry_spec
                    continue
                return outcome
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                retry_feedback = build_scout_retry_feedback("invalid_output", error)
                outcome = self._failed(
                    spec, "invalid_output", turn, error, retry_feedback
                )
                retry_spec = self._retry(job_id, spec)
                if retry_spec is not None:
                    spec = retry_spec
                    continue
                return outcome
            except Exception as error:
                outcome = self._failed(spec, "app_server_error", turn, error)
                retry_spec = self._retry(job_id, spec)
                if retry_spec is not None:
                    spec = retry_spec
                    continue
                return outcome

    def _retry(self, job_id: str, spec: ScoutRunSpec) -> ScoutRunSpec | None:
        retry_spec = spec.model_copy(update={"deadline_at": self._next_deadline(spec)})
        return retry_spec if self.repository.start_run(job_id, retry_spec) else None

    def _next_deadline(self, spec: ScoutRunSpec) -> datetime:
        return max(
            self.clock() + timedelta(seconds=self.deadline_seconds),
            spec.deadline_at + timedelta(microseconds=1),
        )

    def _validate_budget(self, spec: ScoutRunSpec, turn: ModelTurn) -> None:
        if budget_charge_tool_calls(turn) > spec.budget.max_tool_calls:
            raise ScoutBudgetExceeded("tool call budget exceeded")
        charged_tokens = budget_charge_tokens(turn)
        if charged_tokens is None:
            raise ScoutBudgetExceeded("token usage missing")
        if charged_tokens > spec.budget.max_total_tokens:
            raise ScoutBudgetExceeded("token budget exceeded")
        if not tools_within_scout_territory(turn, spec.scout.allowed_tools):
            raise ScoutBudgetExceeded("tool outside Scout territory")
        if spec.budget.require_active_research and not active_research_attempted(
            turn, spec.scout.allowed_tools
        ):
            raise ActiveResearchRequired(
                "Trader Mind completed without an active research attempt"
            )

    def _failed(
        self,
        spec: ScoutRunSpec,
        error_code: str,
        turn: ModelTurn | None,
        error: Exception,
        retry_feedback: dict[str, object] | None = None,
    ) -> ScoutRunOutcome:
        self.repository.fail(
            spec.run_id,
            error_code,
            turn,
            error,
            retry_feedback=retry_feedback,
        )
        return ScoutRunOutcome(
            run_id=spec.run_id,
            scout_id=spec.scout.scout_id,
            status="failed",
            output=None,
            error_code=error_code,
        )
