import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .alpha_feedback import load_alpha_contributors
from .agent_context import bounded_text, evidence_context, fit_frozen_items
from .agentic_roles import StructuredRoleRunner, canonical_hash
from .b5_runtime import B5Runtime, _append_event, _contract_event
from .capital_allocation import (
    CapitalAllocationDecision,
    IncumbentAlpha,
    allocate_capital,
)
from .contracts import Environment
from .database import Database
from .expression import ExpressionProposal
from .foundry import OpportunityDraft
from .implementation import TradeImplementationPlan
from .market_data import MassiveMarketData
from .paper_execution import (
    PaperExecutionError,
    PaperExecutionResult,
    TigerPaperExecutor,
)
from .portfolio_construction import PortfolioConstructor
from .position_performance import PositionPerformanceRecorder
from .shadow import (
    LedgerTransaction,
    MonitorObservation,
    MonitorPolicy,
    PositionThesis,
    ShadowFillPolicy,
    ShadowIntent,
    close_ledger_transaction,
    evaluate_shadow_fill,
    monitor_position,
    open_ledger_transaction,
)

POSITION_MONITOR_PROMPT_VERSION = "position-monitor-v2"


class PillarMonitorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pillar_id: str = Field(pattern=r"^pillar_[a-f0-9]{32}$")
    status: Literal["confirming", "weakening", "invalidated", "unresolved"]
    rationale: str = Field(min_length=1, max_length=600)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=8)


class PositionMonitorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position_id: str = Field(min_length=3, max_length=128)
    falsifier_triggered: bool
    rationale: str = Field(min_length=1, max_length=1_000)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=8)
    pillar_reviews: tuple[PillarMonitorDecision, ...] = Field(default=(), max_length=4)


class PortfolioMonitorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decisions: tuple[PositionMonitorDecision, ...] = Field(max_length=8)


def valid_monitor_bindings(
    decisions: tuple[PositionMonitorDecision, ...],
    pillar_ids: dict[str, set[str]],
    relevant_evidence_ids: set[str],
) -> bool:
    """Rejects partial, duplicated, or invented thesis reviews fail closed."""

    if len(decisions) != len(pillar_ids):
        return False
    if {item.position_id for item in decisions} != set(pillar_ids):
        return False
    for decision in decisions:
        if len(set(decision.evidence_ids)) != len(decision.evidence_ids):
            return False
        if not set(decision.evidence_ids).issubset(relevant_evidence_ids):
            return False
        expected_pillars = pillar_ids[decision.position_id]
        reviewed_pillars = [item.pillar_id for item in decision.pillar_reviews]
        if len(reviewed_pillars) != len(set(reviewed_pillars)):
            return False
        if set(reviewed_pillars) != expected_pillars:
            return False
        review_evidence: set[str] = set()
        for review in decision.pillar_reviews:
            if len(set(review.evidence_ids)) != len(review.evidence_ids):
                return False
            if not set(review.evidence_ids).issubset(relevant_evidence_ids):
                return False
            if review.status == "invalidated" and not review.evidence_ids:
                return False
            review_evidence.update(review.evidence_ids)
        if not review_evidence.issubset(decision.evidence_ids):
            return False
        if expected_pillars and decision.falsifier_triggered != any(
            review.status == "invalidated" for review in decision.pillar_reviews
        ):
            return False
    return True


class AgenticPositionBook:
    """Owns the Shadow position lifecycle after an expression is validated."""

    def __init__(
        self,
        database: Database,
        runner: StructuredRoleRunner,
        runtime: B5Runtime,
        market_data: MassiveMarketData | None,
        *,
        max_open_positions: int,
        paper_executor: TigerPaperExecutor | None = None,
        acceptance_hold_seconds: int | None = None,
        portfolio_constructor: PortfolioConstructor | None = None,
    ) -> None:
        if not 1 <= max_open_positions <= 8:
            raise ValueError("max_open_positions must be between 1 and 8")
        self.database = database
        self.runner = runner
        self.runtime = runtime
        self.market_data = market_data
        self.max_open_positions = max_open_positions
        self.paper_executor = paper_executor
        self.acceptance_hold_seconds = acceptance_hold_seconds
        self.portfolio_constructor = portfolio_constructor
        self.performance = PositionPerformanceRecorder(database, market_data)

    def open_shadow(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        proposal: ExpressionProposal,
    ) -> tuple[PositionThesis, LedgerTransaction] | None:
        if proposal.kind == "wait":
            return None
        existing = self._existing_position(proposal.expression_id)
        if existing is not None:
            return existing
        if self.market_data is None:
            return None
        context = self._rationale_context(proposal.rationale)
        with self.database.connect() as connection:
            open_rows = connection.execute(
                """SELECT p.id, p.symbol, p.quantity, p.position_thesis,
                p.entry_price, p.entry_commission, e.kind, e.rationale
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.environment = 'shadow' AND p.status = 'open'
                ORDER BY p.opened_at, p.id"""
            ).fetchall()
            alpha_contributors = load_alpha_contributors(
                connection, opportunity.member_candidate_ids
            )
        if not alpha_contributors:
            self._gate_event(
                cycle_id,
                proposal,
                "shadow.open.rejected",
                "alpha_contributor_snapshot_unavailable",
            )
            return None
        available_pillars = {
            item.pillar_id: item for item in opportunity.thesis_pillars
        }
        if not set(proposal.thesis_pillar_ids).issubset(available_pillars):
            self._gate_event(
                cycle_id,
                proposal,
                "shadow.open.rejected",
                "thesis_pillar_binding_invalid",
            )
            return None
        if opportunity.thesis_pillars and not proposal.thesis_pillar_ids:
            self._gate_event(
                cycle_id,
                proposal,
                "shadow.open.rejected",
                "thesis_pillar_binding_missing",
            )
            return None
        selected_pillars = tuple(
            available_pillars[pillar_id] for pillar_id in proposal.thesis_pillar_ids
        )
        if not self._admit_entry(cycle_id, proposal, context, open_rows):
            return None
        committed_at = datetime.now(UTC)
        fill_policy = ShadowFillPolicy()
        execution = (
            proposal.implementation_plan.execution_plan
            if proposal.implementation_plan is not None
            else None
        )
        position_id = (
            "shadow_" + canonical_hash([cycle_id, proposal.expression_id])[:32]
        )
        intent = ShadowIntent(
            intent_id="intent_" + canonical_hash([cycle_id, "open-v2"])[:32],
            position_id=position_id,
            action="open",
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=proposal.hash(),
            binding=proposal.binding,
            symbol=proposal.symbol or "",
            quantity=proposal.quantity,
            committed_at=committed_at,
            policy_version=fill_policy.version,
            limit_price=(
                execution.entry_limit_price if execution is not None else None
            ),
        )
        quote = self.market_data.forward_quote(
            proposal.kind,
            intent.symbol,
            committed_at=intent.committed_at,
            frozen_latency_ms=fill_policy.frozen_latency_ms,
            underlying_symbol=context.get("underlying_symbol"),
        )
        if quote is None:
            self._gate_event(
                cycle_id, proposal, "shadow.open.no_fill", "forward_quote_unavailable"
            )
            return None
        fill = evaluate_shadow_fill(intent, quote, fill_policy)
        if fill.status != "filled":
            self._gate_event(
                cycle_id, proposal, "shadow.open.no_fill", fill.reason_code
            )
            return None
        paper_result = None
        if self.paper_executor is not None:
            if proposal.kind not in ("stock", "etf"):
                self._gate_event(
                    cycle_id,
                    proposal,
                    "paper.open.rejected",
                    "paper_equity_only",
                )
                return None
            try:
                paper_result = self.paper_executor.open(
                    intent.symbol,
                    quote.ask,
                    cycle_id,
                    limit_offset_bps=(
                        execution.entry_limit_offset_bps
                        if execution is not None
                        else Decimal(25)
                    ),
                    absolute_limit_price=(
                        execution.entry_limit_price if execution is not None else None
                    ),
                )
            except Exception as error:
                self._gate_event(
                    cycle_id,
                    proposal,
                    "paper.open.rejected",
                    f"paper_executor:{type(error).__name__}",
                )
                return None
            self._paper_event(cycle_id, position_id, paper_result)
            if paper_result.status != "filled":
                return None
        ledger = open_ledger_transaction(fill)
        thesis = PositionThesis(
            thesis_id="thesis_" + canonical_hash([cycle_id, position_id])[:32],
            position_id=position_id,
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=proposal.hash(),
            binding=proposal.binding,
            known_at=fill.known_at,
            entry_expectation=(
                opportunity.expectation or opportunity.prediction or opportunity.thesis
            ),
            why_now=opportunity.why_now or opportunity.thesis,
            invalidation_condition=(
                opportunity.falsifier
                or "Opportunity evidence no longer supports the mechanism."
            ),
            time_exit_at=(
                fill.known_at + timedelta(seconds=self.acceptance_hold_seconds)
                if self.acceptance_hold_seconds is not None
                else fill.known_at
                + timedelta(
                    seconds=(
                        proposal.implementation_plan.alpha_clock.remaining_seconds
                        if proposal.implementation_plan is not None
                        and proposal.implementation_plan.alpha_clock is not None
                        else opportunity.horizon_days * 86_400
                    )
                )
            ),
            next_catalyst=(
                opportunity.first_rejection or "Next versioned evidence update."
            ),
            better_opportunity_min_bps=Decimal("75"),
            alpha_contributors=alpha_contributors,
            implementation_plan=proposal.implementation_plan,
            thesis_pillars=selected_pillars,
        )
        try:
            self.runtime.shadow.open(intent, fill, ledger, thesis)
        except Exception:
            if self.paper_executor is not None and paper_result is not None:
                cleanup = self.paper_executor.flatten(
                    intent.symbol, quote.bid, cycle_id
                )
                self._paper_event(cycle_id, position_id, cleanup)
            raise
        self.performance.record_benchmark(position_id, proposal.expression_id)
        return thesis, ledger

    def _admit_entry(
        self,
        cycle_id: str,
        proposal: ExpressionProposal,
        context: dict,
        open_rows: list[tuple],
    ) -> bool:
        duplicate_exposure = any(
            row[1] == proposal.symbol
            or (
                context.get("underlying_symbol")
                and self._rationale_context(row[7]).get("underlying_symbol")
                == context.get("underlying_symbol")
            )
            for row in open_rows
        )
        if duplicate_exposure:
            reason = "duplicate_underlying_exposure"
            self._gate_event(cycle_id, proposal, "shadow.open.rejected", reason)
            return False
        if (
            proposal.implementation_plan is not None
            and self.portfolio_constructor is None
        ):
            self._gate_event(
                cycle_id,
                proposal,
                "shadow.open.rejected",
                "portfolio_constructor_unavailable",
            )
            return False
        allocation = self.assess_capital(
            proposal.implementation_plan, datetime.now(UTC)
        )
        self.record_capital_decision(cycle_id, proposal.expression_id, allocation)
        if allocation.status == "wait":
            self._gate_event(
                cycle_id,
                proposal,
                "shadow.open.rejected",
                "capital_allocation:" + allocation.reason_code,
            )
            return False
        if allocation.status == "rotate":
            pre_rotation_reasons = self.portfolio_constructor.revalidate(
                proposal.implementation_plan,
                prospective_rotation=True,
            )
            if pre_rotation_reasons:
                self._gate_event(
                    cycle_id,
                    proposal,
                    "shadow.open.rejected",
                    ",".join(pre_rotation_reasons),
                )
                return False
            if not self.execute_rotation(cycle_id, allocation):
                self._gate_event(
                    cycle_id,
                    proposal,
                    "shadow.open.rejected",
                    "capital_rotation_not_filled",
                )
                return False
        if proposal.implementation_plan is not None:
            plan_reasons = self.portfolio_constructor.revalidate(
                proposal.implementation_plan
            )
            if plan_reasons:
                self._gate_event(
                    cycle_id,
                    proposal,
                    "shadow.open.rejected",
                    ",".join(plan_reasons),
                )
                return False
        return True

    def assess_capital(
        self,
        plan: TradeImplementationPlan | None,
        known_at: datetime,
    ) -> CapitalAllocationDecision:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, position_thesis
                FROM research.shadow_position
                WHERE environment = 'shadow' AND status = 'open'
                ORDER BY opened_at, id"""
            ).fetchall()
        incumbents = []
        for position_id, raw_thesis in rows:
            thesis = PositionThesis.model_validate(raw_thesis)
            implementation = thesis.implementation_plan
            expected_alpha = None
            if implementation is not None:
                expected_alpha = (
                    implementation.alpha_clock.time_adjusted_expected_net_alpha_bps
                    if implementation.alpha_clock is not None
                    else implementation.expected_net_alpha_bps
                )
            incumbents.append(
                IncumbentAlpha(
                    position_id=position_id,
                    entered_at=thesis.known_at,
                    time_exit_at=thesis.time_exit_at,
                    expected_net_alpha_bps_at_entry=expected_alpha,
                    replacement_hurdle_bps=thesis.better_opportunity_min_bps,
                )
            )
        return allocate_capital(
            plan=plan,
            incumbents=tuple(incumbents),
            max_open_positions=self.max_open_positions,
            known_at=known_at,
        )

    def record_capital_decision(
        self,
        cycle_id: str,
        expression_id: str,
        decision: CapitalAllocationDecision,
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="capital.allocation.evaluated",
                    aggregate_type="expression",
                    aggregate_id=expression_id,
                    environment=Environment.SHADOW,
                    known_at=decision.known_at,
                    payload=decision.model_dump(mode="json"),
                    correlation_id=cycle_id,
                ),
            )

    def execute_rotation(
        self,
        cycle_id: str,
        allocation: CapitalAllocationDecision,
    ) -> bool:
        if allocation.status != "rotate" or allocation.incumbent_position_id is None:
            raise ValueError("capital rotation requires an admitted replacement")
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.id, p.symbol, p.quantity, p.position_thesis,
                p.entry_price, p.entry_commission, e.kind, e.rationale, p.status
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.id = %s AND p.environment = 'shadow'""",
                (allocation.incumbent_position_id,),
            ).fetchone()
        if row is None:
            return False
        if row[8] == "closed":
            return True
        return self._rotate_out(cycle_id, row, allocation)

    def _rotate_out(
        self,
        cycle_id: str,
        row: tuple,
        allocation: CapitalAllocationDecision,
    ) -> bool:
        thesis = PositionThesis.model_validate(row[3])
        context = self._rationale_context(row[7])
        quote = self.market_data.quote(
            row[6], row[1], underlying_symbol=context.get("underlying_symbol")
        )
        if quote is None or allocation.advantage_bps is None:
            return False
        observed_at = max(datetime.now(UTC), quote.known_at)
        observation = MonitorObservation(
            observation_id="observation_"
            + canonical_hash(
                [cycle_id, row[0], quote.content_hash, "capital-rotation-v1"]
            )[:32],
            position_id=row[0],
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            thesis_hash=thesis.hash(),
            binding=thesis.binding,
            known_at=observed_at,
            quote=quote,
            better_opportunity_advantage_bps=allocation.advantage_bps,
        )
        decision = monitor_position(thesis, observation, MonitorPolicy())
        self.runtime.shadow.record_monitor(observation, decision)
        if decision.reason_code != "better_opportunity":
            return False
        return self._close_position(
            cycle_id,
            thesis,
            row[1],
            Decimal(row[2]),
            row[6],
            context,
            decision,
            Decimal(row[4]),
            Decimal(row[5]),
        )

    def _existing_position(
        self, expression_id: str
    ) -> tuple[PositionThesis, LedgerTransaction] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT id, position_thesis
                FROM research.shadow_position
                WHERE expression_id = %s AND environment = 'shadow'""",
                (expression_id,),
            ).fetchone()
        if row is None:
            return None
        thesis = PositionThesis.model_validate(row[1])
        ledgers = self.runtime.shadow.ledger(row[0])
        opening = next((item for item in ledgers if item.action == "open"), None)
        if opening is None:
            raise ValueError("existing Shadow position has no opening ledger")
        return thesis, opening

    def monitor_existing(self, cycle_id: str, frozen_input) -> tuple[str, ...]:
        if self.market_data is None:
            return ()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT p.id, p.symbol, p.quantity, p.position_thesis,
                p.entry_price, p.entry_commission, e.kind, e.rationale
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.environment = 'shadow' AND p.status = 'open'
                ORDER BY p.opened_at, p.id"""
            ).fetchall()
        falsifier_flags = self._falsifier_flags(cycle_id, rows, frozen_input)
        monitored: list[str] = []
        for row in rows:
            thesis = PositionThesis.model_validate(row[3])
            context = self._rationale_context(row[7])
            quote = self.market_data.quote(
                row[6], row[1], underlying_symbol=context.get("underlying_symbol")
            )
            if quote is None:
                continue
            observation = MonitorObservation(
                observation_id="observation_"
                + canonical_hash([cycle_id, row[0], quote.content_hash])[:32],
                position_id=row[0],
                thesis_id=thesis.thesis_id,
                thesis_version=thesis.version,
                thesis_hash=thesis.hash(),
                binding=thesis.binding,
                known_at=datetime.now(UTC),
                quote=quote,
                falsifier_triggered=falsifier_flags.get(row[0], False),
            )
            decision = monitor_position(thesis, observation, MonitorPolicy())
            self.runtime.shadow.record_monitor(observation, decision)
            monitored.append(row[0])
            if decision.action != "exit":
                continue
            if decision.reason_code in ("price_stale", "quote_not_known"):
                self._position_event(
                    cycle_id,
                    thesis,
                    "position.exit.deferred",
                    decision.reason_code,
                )
                continue
            self._close_position(
                cycle_id,
                thesis,
                row[1],
                Decimal(row[2]),
                row[6],
                context,
                decision,
                Decimal(row[4]),
                Decimal(row[5]),
            )
        return tuple(monitored)

    def ensure_cycle_paper_flat(self, cycle_id: str) -> tuple[str, ...]:
        """Idempotently flattens every Paper position opened by one acceptance cycle."""
        if self.paper_executor is None:
            return ()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT aggregate_id
                FROM ops.event
                WHERE environment = 'shadow'
                  AND correlation_id = %s
                  AND event_type = 'paper.order.filled'
                  AND payload->>'action' = 'BUY'
                ORDER BY aggregate_id""",
                (cycle_id,),
            ).fetchall()
        flattened = []
        for (position_id,) in rows:
            self._ensure_paper_flat(cycle_id, position_id)
            flattened.append(position_id)
        return tuple(flattened)

    def _ensure_paper_flat(self, cycle_id: str, position_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.symbol, p.entry_price, e.kind, e.rationale
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.id = %s AND p.environment = 'shadow'""",
                (position_id,),
            ).fetchone()
            paper_row = connection.execute(
                """SELECT payload FROM ops.event
                WHERE aggregate_id = %s
                  AND correlation_id = %s
                  AND event_type IN (
                    'paper.order.filled',
                    'paper.position.verified_flat',
                    'paper.order.no_fill'
                  )
                ORDER BY sequence DESC LIMIT 1""",
                (position_id, cycle_id),
            ).fetchone()
            paper_open_row = connection.execute(
                """SELECT payload FROM ops.event
                WHERE aggregate_id = %s
                  AND correlation_id = %s
                  AND event_type = 'paper.order.filled'
                  AND payload->>'action' = 'BUY'
                ORDER BY sequence DESC LIMIT 1""",
                (position_id, cycle_id),
            ).fetchone()
        if paper_row is None:
            raise PaperExecutionError("Paper safety event binding is missing")
        paper_payload = paper_row[0]
        if Decimal(paper_payload["position_after"]) == 0:
            return
        if row is None:
            symbol = paper_payload["symbol"]
            entry_price = paper_payload.get("average_fill_price")
            if entry_price is None and paper_open_row is not None:
                entry_price = paper_open_row[0].get("average_fill_price")
            kind = "stock"
            context = {}
            if entry_price is None:
                raise PaperExecutionError("Paper safety price binding is missing")
        else:
            symbol, entry_price, kind, rationale = row
            context = self._rationale_context(rationale)
        quote = (
            self.market_data.quote(
                kind,
                symbol,
                underlying_symbol=context.get("underlying_symbol"),
            )
            if self.market_data is not None
            else None
        )
        reference_bid = (
            quote.bid
            if quote is not None
            else max(Decimal(entry_price) * Decimal("0.50"), Decimal("0.01"))
        )
        result = self.paper_executor.flatten(symbol, reference_bid, cycle_id)
        self._paper_event(cycle_id, position_id, result)
        if (
            result.status not in ("filled", "already_flat")
            or Decimal(result.position_after) != 0
        ):
            raise PaperExecutionError(
                "Paper safety flatten did not prove a flat position"
            )

    def _falsifier_flags(
        self, cycle_id: str, rows: list[tuple], frozen_input
    ) -> dict[str, bool]:
        if not rows or not frozen_input.evidence:
            return {}
        positions = []
        earliest_position_at = None
        for row in rows:
            thesis = PositionThesis.model_validate(row[3])
            earliest_position_at = min(
                earliest_position_at or thesis.known_at, thesis.known_at
            )
            positions.append(
                {
                    "position_id": row[0],
                    "symbol": row[1],
                    "position_known_at": thesis.known_at.isoformat(),
                    "entry_expectation": bounded_text(thesis.entry_expectation, 120),
                    "invalidation_condition": bounded_text(
                        thesis.invalidation_condition, 120
                    ),
                    "why_now": bounded_text(thesis.why_now, 120),
                    "thesis_pillars": [
                        {
                            "pillar_id": item.pillar_id,
                            "statement": bounded_text(item.statement, 120),
                            "observable": bounded_text(item.observable, 120),
                            "confirmation_condition": bounded_text(
                                item.confirmation_condition, 120
                            ),
                            "invalidation_condition": bounded_text(
                                item.invalidation_condition, 120
                            ),
                            "due_at": item.due_at.isoformat(),
                        }
                        for item in thesis.thesis_pillars
                    ],
                }
            )
        ordered_evidence = sorted(
            (
                item
                for item in frozen_input.evidence
                if earliest_position_at is not None
                and item.known_at > earliest_position_at
            ),
            key=lambda item: (item.known_at, item.evidence_id),
            reverse=True,
        )
        if not ordered_evidence:
            return {}
        frozen = fit_frozen_items(
            {"positions": positions},
            "new_evidence",
            [evidence_context(item, summary_bytes=160) for item in ordered_evidence],
        )
        relevant_evidence_ids = {item["evidence_id"] for item in frozen["new_evidence"]}
        if not relevant_evidence_ids:
            return {}
        try:
            result = self.runner.run(
                cycle_id=cycle_id,
                run_id="run_"
                + canonical_hash([cycle_id, POSITION_MONITOR_PROMPT_VERSION])[:32],
                role="position_monitor_agent",
                prompt={
                    "contract": "alta.portfolio-monitor.v2",
                    "mission": (
                        "For each position, append a point-in-time review of every "
                        "frozen thesis pillar and decide only whether new frozen "
                        "evidence explicitly satisfies an invalidation condition."
                    ),
                    "untrusted_frozen_input": frozen,
                    "rules": [
                        "Do not reinterpret ordinary volatility as invalidation.",
                        "Ignore evidence that is not newer than a position_known_at.",
                        "Trigger only from supplied new evidence and cite its evidence_id.",
                        "Never rewrite a pillar. Mark it confirming, weakening, invalidated, or unresolved against its exact observable and frozen conditions.",
                        "For a position with thesis_pillars, return exactly one pillar_review for every supplied pillar_id. An invalidated review requires cited new Evidence and falsifier_triggered must then be true.",
                        "Price action alone is not thesis proof. A passed due_at without the required observable is unresolved or weakening, not automatically invalidated.",
                        "Do not recommend a new trade or use unstated information.",
                    ],
                },
                output_type=PortfolioMonitorOutput,
                frozen_input=frozen,
                evidence_ids=tuple(sorted(relevant_evidence_ids)),
                known_at=datetime.now(UTC),
                prompt_version=POSITION_MONITOR_PROMPT_VERSION,
            )
        except Exception as error:
            self._monitor_degraded_event(cycle_id, type(error).__name__)
            return {}
        pillar_ids = {
            item["position_id"]: {
                pillar["pillar_id"] for pillar in item["thesis_pillars"]
            }
            for item in positions
        }
        decisions = result.value.decisions
        if not valid_monitor_bindings(decisions, pillar_ids, relevant_evidence_ids):
            self._monitor_degraded_event(cycle_id, "invalid_monitor_binding")
            return {}
        for decision in decisions:
            self._thesis_review_event(cycle_id, decision)
        return {item.position_id: item.falsifier_triggered for item in decisions}

    def _thesis_review_event(
        self, cycle_id: str, decision: PositionMonitorDecision
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="position.thesis.reviewed",
                    aggregate_type="shadow_position",
                    aggregate_id=decision.position_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload={
                        "cycle_id": cycle_id,
                        "review": decision.model_dump(mode="json"),
                        "original_thesis_mutated": False,
                    },
                    correlation_id=cycle_id,
                ),
            )

    def _monitor_degraded_event(self, cycle_id: str, reason: str) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="position.monitor_agent.degraded",
                    aggregate_type="mvp_pipeline",
                    aggregate_id=cycle_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload={"cycle_id": cycle_id, "reason": reason[:64]},
                    correlation_id=cycle_id,
                ),
            )

    def _close_position(
        self,
        cycle_id: str,
        thesis: PositionThesis,
        symbol: str,
        quantity: Decimal,
        kind: Literal["stock", "etf", "option"],
        context: dict,
        decision,
        entry_price: Decimal,
        entry_commission: Decimal,
    ) -> bool:
        fill_policy = ShadowFillPolicy()
        intent = ShadowIntent(
            intent_id="intent_"
            + canonical_hash([cycle_id, thesis.position_id, "close-v2"])[:32],
            position_id=thesis.position_id,
            action="close",
            expression_id=thesis.expression_id,
            expression_version=thesis.expression_version,
            expression_hash=thesis.expression_hash,
            binding=thesis.binding,
            symbol=symbol,
            quantity=quantity,
            committed_at=datetime.now(UTC),
            policy_version=fill_policy.version,
        )
        quote = self.market_data.forward_quote(
            kind,
            symbol,
            committed_at=intent.committed_at,
            frozen_latency_ms=fill_policy.frozen_latency_ms,
            underlying_symbol=context.get("underlying_symbol"),
        )
        if quote is None:
            self._position_event(
                cycle_id,
                thesis,
                "shadow.exit.no_fill",
                "forward_quote_unavailable",
            )
            return False
        fill = evaluate_shadow_fill(intent, quote, fill_policy)
        if fill.status != "filled":
            self._position_event(
                cycle_id,
                thesis,
                "shadow.exit.no_fill",
                fill.reason_code,
            )
            return False
        if self.paper_executor is not None:
            try:
                execution = (
                    thesis.implementation_plan.execution_plan
                    if thesis.implementation_plan is not None
                    else None
                )
                paper_result = self.paper_executor.close(
                    symbol,
                    quote.bid,
                    cycle_id,
                    limit_offset_bps=(
                        execution.exit_limit_offset_bps
                        if execution is not None
                        else Decimal(25)
                    ),
                )
            except Exception as error:
                self._position_event(
                    cycle_id,
                    thesis,
                    "paper.exit.deferred",
                    f"paper_executor:{type(error).__name__}",
                )
                return False
            self._paper_event(cycle_id, thesis.position_id, paper_result)
            if paper_result.status not in ("filled", "already_flat"):
                return False
        cost_basis = entry_price * quantity
        ledger = close_ledger_transaction(fill, position_cost_basis=cost_basis)
        self.runtime.shadow.close(intent, fill, ledger, decision)
        self.performance.record_result(
            thesis,
            entry_price,
            entry_commission,
            fill.fill_price or Decimal(0),
            fill.commission or Decimal(0),
            quantity,
        )
        return True

    def _paper_event(
        self,
        cycle_id: str,
        position_id: str,
        result: PaperExecutionResult,
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type=(
                        "paper.order.filled"
                        if result.status == "filled"
                        else (
                            "paper.position.verified_flat"
                            if result.status == "already_flat"
                            else "paper.order.no_fill"
                        )
                    ),
                    aggregate_type="shadow_position",
                    aggregate_id=position_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload={
                        "cycle_id": cycle_id,
                        "broker": "tiger_paper",
                        **result.model_dump(mode="json"),
                    },
                    correlation_id=cycle_id,
                ),
            )

    def _gate_event(
        self,
        cycle_id: str,
        proposal: ExpressionProposal,
        event_type: str,
        reason: str,
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type=event_type,
                    aggregate_type="shadow_position",
                    aggregate_id=proposal.expression_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload={"cycle_id": cycle_id, "reason": reason},
                    correlation_id=proposal.binding.opportunity_id,
                ),
            )

    def _position_event(
        self,
        cycle_id: str,
        thesis: PositionThesis,
        event_type: str,
        reason: str,
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type=event_type,
                    aggregate_type="shadow_position",
                    aggregate_id=thesis.position_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload={"cycle_id": cycle_id, "reason": reason},
                    correlation_id=thesis.binding.opportunity_id,
                ),
            )

    @staticmethod
    def _rationale_context(rationale: str) -> dict:
        try:
            value = json.loads(rationale)
        except (TypeError, ValueError):
            return {}
        instrument = value.get("market_instrument", {})
        return instrument if isinstance(instrument, dict) else {}
