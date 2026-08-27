from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, model_validator

from .alpha_feedback import AlphaContributor
from .contracts import Environment
from .expression import (
    HASH_PATTERN,
    MONEY_QUANTUM,
    FrozenContract,
    QuoteSnapshot,
    VersionBinding,
    _aware,
    contract_hash,
)
from .implementation import TradeImplementationPlan
from .investment_thesis import MAX_THESIS_PILLARS, ThesisPillar


def _require_shadow(binding: VersionBinding) -> None:
    if binding.environment != Environment.SHADOW:
        raise ValueError("Shadow contracts require environment=shadow")


class ShadowFillPolicy(FrozenContract):
    version: Literal["b8-shadow-fill-v2"] = "b8-shadow-fill-v2"
    frozen_latency_ms: int = Field(default=500, ge=0, le=60_000)
    max_price_age_seconds: int = Field(default=60, ge=1, le=3_600)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0)
    option_slippage_bps: Decimal = Field(default=Decimal("50"), ge=0)
    commission_bps: Decimal = Field(default=Decimal("1"), ge=0)
    minimum_commission: Decimal = Field(default=Decimal("0.01"), ge=0)
    option_commission_per_contract: Decimal = Field(default=Decimal("0.65"), ge=0)


class ShadowIntent(FrozenContract):
    intent_id: str = Field(min_length=3, max_length=128)
    position_id: str = Field(min_length=3, max_length=128)
    action: Literal["open", "close"]
    expression_id: str = Field(min_length=3, max_length=128)
    expression_version: int = Field(ge=1)
    expression_hash: str = Field(pattern=HASH_PATTERN)
    binding: VersionBinding
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.:-]{0,31}$")
    quantity: Decimal = Field(gt=0)
    committed_at: datetime
    policy_version: str
    limit_price: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_time(self) -> "ShadowIntent":
        _aware(self.committed_at, "intent committed_at")
        _require_shadow(self.binding)
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


class ShadowFill(FrozenContract):
    fill_id: str = Field(min_length=3, max_length=128)
    intent_id: str
    position_id: str
    action: Literal["open", "close"]
    binding: VersionBinding
    status: Literal["filled", "no_fill"]
    reason_code: str
    known_at: datetime
    quote: QuoteSnapshot
    quantity: Decimal = Field(gt=0)
    fill_price: Decimal | None = Field(default=None, gt=0)
    commission: Decimal | None = Field(default=None, ge=0)
    fill_model_version: str

    @model_validator(mode="after")
    def validate_fill(self) -> "ShadowFill":
        _aware(self.known_at, "fill known_at")
        _require_shadow(self.binding)
        has_values = self.fill_price is not None and self.commission is not None
        if (self.status == "filled") != has_values:
            raise ValueError("filled status and price/commission must agree")
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


def evaluate_shadow_fill(
    intent: ShadowIntent, quote: QuoteSnapshot, policy: ShadowFillPolicy
) -> ShadowFill:
    if intent.policy_version != policy.version:
        raise ValueError("intent is bound to a different fill policy")
    if quote.symbol != intent.symbol:
        raise ValueError("fill quote symbol does not match intent")
    eligible_at = intent.committed_at + timedelta(milliseconds=policy.frozen_latency_ms)
    reason: str | None = None
    if quote.known_at <= eligible_at:
        reason = "quote_not_after_frozen_latency"
    elif quote.as_of <= intent.committed_at:
        reason = "quote_not_forward_of_intent"
    elif (quote.known_at - quote.as_of).total_seconds() > policy.max_price_age_seconds:
        reason = "price_stale"

    fill_id = f"fill_{contract_hash([intent.intent_id, quote.content_hash])[:32]}"
    if reason is not None:
        return ShadowFill(
            fill_id=fill_id,
            intent_id=intent.intent_id,
            position_id=intent.position_id,
            action=intent.action,
            binding=intent.binding,
            status="no_fill",
            reason_code=reason,
            known_at=quote.known_at,
            quote=quote,
            quantity=intent.quantity,
            fill_model_version=policy.version,
        )

    slippage_bps = (
        policy.option_slippage_bps
        if intent.symbol.startswith("O:")
        else policy.slippage_bps
    )
    slippage = slippage_bps / Decimal(10_000)
    reference = quote.ask if intent.action == "open" else quote.bid
    multiplier = (
        Decimal(1) + slippage if intent.action == "open" else Decimal(1) - slippage
    )
    fill_price = (reference * multiplier).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    if intent.limit_price is not None and (
        (intent.action == "open" and fill_price > intent.limit_price)
        or (intent.action == "close" and fill_price < intent.limit_price)
    ):
        return ShadowFill(
            fill_id=fill_id,
            intent_id=intent.intent_id,
            position_id=intent.position_id,
            action=intent.action,
            binding=intent.binding,
            status="no_fill",
            reason_code="guarded_limit_not_market",
            known_at=quote.known_at,
            quote=quote,
            quantity=intent.quantity,
            fill_model_version=policy.version,
        )
    notional = (fill_price * intent.quantity).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    commission = (
        max(
            intent.quantity / Decimal(100) * policy.option_commission_per_contract,
            policy.minimum_commission,
        )
        if intent.symbol.startswith("O:")
        else max(
            (notional * policy.commission_bps / Decimal(10_000)).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            ),
            policy.minimum_commission,
        )
    )
    return ShadowFill(
        fill_id=fill_id,
        intent_id=intent.intent_id,
        position_id=intent.position_id,
        action=intent.action,
        binding=intent.binding,
        status="filled",
        reason_code="conservative_quote_fill",
        known_at=quote.known_at,
        quote=quote,
        quantity=intent.quantity,
        fill_price=fill_price,
        commission=commission,
        fill_model_version=policy.version,
    )


class LedgerLine(FrozenContract):
    account: Literal["cash", "position", "expense", "realized_pnl"]
    debit: Decimal = Field(default=Decimal(0), ge=0)
    credit: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def validate_one_sided(self) -> "LedgerLine":
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("ledger line must have exactly one non-zero side")
        return self


class LedgerTransaction(FrozenContract):
    transaction_id: str = Field(min_length=3, max_length=128)
    position_id: str
    fill_id: str
    action: Literal["open", "close"]
    binding: VersionBinding
    known_at: datetime
    currency: Literal["USD"] = "USD"
    quantity_delta: Decimal
    lines: tuple[LedgerLine, ...] = Field(min_length=3, max_length=4)
    ledger_version: Literal["b5-shadow-ledger-v1"] = "b5-shadow-ledger-v1"

    @model_validator(mode="after")
    def validate_balanced(self) -> "LedgerTransaction":
        _aware(self.known_at, "ledger known_at")
        _require_shadow(self.binding)
        debits = sum((line.debit for line in self.lines), Decimal(0))
        credits = sum((line.credit for line in self.lines), Decimal(0))
        if debits != credits:
            raise ValueError("ledger transaction is not balanced")
        if self.action == "open" and self.quantity_delta <= 0:
            raise ValueError("open transaction must add quantity")
        if self.action == "close" and self.quantity_delta >= 0:
            raise ValueError("close transaction must remove quantity")
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


def open_ledger_transaction(fill: ShadowFill) -> LedgerTransaction:
    if fill.status != "filled" or fill.action != "open":
        raise ValueError("open ledger requires a filled open")
    if fill.fill_price is None or fill.commission is None:
        raise ValueError("filled open is missing price or commission")
    notional = (fill.fill_price * fill.quantity).quantize(MONEY_QUANTUM)
    total = notional + fill.commission
    return LedgerTransaction(
        transaction_id=f"ledger_{contract_hash([fill.fill_id, 'open'])[:32]}",
        position_id=fill.position_id,
        fill_id=fill.fill_id,
        action="open",
        binding=fill.binding,
        known_at=fill.known_at,
        quantity_delta=fill.quantity,
        lines=(
            LedgerLine(account="position", debit=notional),
            LedgerLine(account="expense", debit=fill.commission),
            LedgerLine(account="cash", credit=total),
        ),
    )


def close_ledger_transaction(
    fill: ShadowFill, *, position_cost_basis: Decimal
) -> LedgerTransaction:
    if fill.status != "filled" or fill.action != "close":
        raise ValueError("close ledger requires a filled close")
    if fill.fill_price is None or fill.commission is None:
        raise ValueError("filled close is missing price or commission")
    proceeds = (fill.fill_price * fill.quantity).quantize(MONEY_QUANTUM)
    cash = proceeds - fill.commission
    if cash <= 0 or position_cost_basis <= 0:
        raise ValueError("close ledger values must be positive")
    lines = [
        LedgerLine(account="cash", debit=cash),
        LedgerLine(account="expense", debit=fill.commission),
        LedgerLine(account="position", credit=position_cost_basis),
    ]
    imbalance = cash + fill.commission - position_cost_basis
    if imbalance > 0:
        lines.append(LedgerLine(account="realized_pnl", credit=imbalance))
    elif imbalance < 0:
        lines.append(LedgerLine(account="realized_pnl", debit=-imbalance))
    return LedgerTransaction(
        transaction_id=f"ledger_{contract_hash([fill.fill_id, 'close'])[:32]}",
        position_id=fill.position_id,
        fill_id=fill.fill_id,
        action="close",
        binding=fill.binding,
        known_at=fill.known_at,
        quantity_delta=-fill.quantity,
        lines=tuple(lines),
    )


class PositionThesis(FrozenContract):
    thesis_id: str = Field(min_length=3, max_length=128)
    version: int = Field(default=1, ge=1)
    position_id: str
    expression_id: str
    expression_version: int = Field(ge=1)
    expression_hash: str = Field(pattern=HASH_PATTERN)
    binding: VersionBinding
    known_at: datetime
    entry_expectation: str = Field(min_length=1, max_length=2_000)
    why_now: str = Field(min_length=1, max_length=2_000)
    invalidation_condition: str = Field(min_length=1, max_length=2_000)
    time_exit_at: datetime
    next_catalyst: str = Field(min_length=1, max_length=2_000)
    better_opportunity_min_bps: Decimal = Field(ge=0)
    alpha_contributors: tuple[AlphaContributor, ...] = Field(default=(), max_length=20)
    implementation_plan: TradeImplementationPlan | None = None
    thesis_pillars: tuple[ThesisPillar, ...] = Field(
        default=(), max_length=MAX_THESIS_PILLARS
    )

    @model_validator(mode="after")
    def validate_times(self) -> "PositionThesis":
        _aware(self.known_at, "thesis known_at")
        _aware(self.time_exit_at, "thesis time_exit_at")
        _require_shadow(self.binding)
        if self.time_exit_at <= self.known_at:
            raise ValueError("time exit must follow thesis creation")
        pillar_ids = [item.pillar_id for item in self.thesis_pillars]
        if len(set(pillar_ids)) != len(pillar_ids):
            raise ValueError("position thesis pillar IDs must be unique")
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


class MonitorObservation(FrozenContract):
    observation_id: str = Field(min_length=3, max_length=128)
    position_id: str
    thesis_id: str
    thesis_version: int = Field(ge=1)
    thesis_hash: str = Field(pattern=HASH_PATTERN)
    binding: VersionBinding
    known_at: datetime
    quote: QuoteSnapshot
    falsifier_triggered: bool = False
    better_opportunity_advantage_bps: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_time(self) -> "MonitorObservation":
        _aware(self.known_at, "monitor known_at")
        _require_shadow(self.binding)
        return self


class MonitorPolicy(FrozenContract):
    version: Literal["b5-monitor-v1"] = "b5-monitor-v1"
    max_price_age_seconds: int = Field(default=60, ge=1, le=3_600)


class ExitDecision(FrozenContract):
    decision_id: str = Field(min_length=3, max_length=128)
    position_id: str
    thesis_id: str
    thesis_version: int = Field(ge=1)
    thesis_hash: str = Field(pattern=HASH_PATTERN)
    binding: VersionBinding
    known_at: datetime
    action: Literal["hold", "exit"]
    reason_code: Literal[
        "hold",
        "thesis_invalidated",
        "time_exit",
        "better_opportunity",
        "price_stale",
        "quote_not_known",
    ]
    observation_id: str
    policy_version: str

    @model_validator(mode="after")
    def validate_binding_and_time(self) -> "ExitDecision":
        _aware(self.known_at, "exit decision known_at")
        _require_shadow(self.binding)
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


def monitor_position(
    thesis: PositionThesis,
    observation: MonitorObservation,
    policy: MonitorPolicy,
) -> ExitDecision:
    if observation.position_id != thesis.position_id:
        raise ValueError("monitor observation targets a different position")
    if observation.binding != thesis.binding:
        raise ValueError("monitor observation changed frozen version binding")
    if (
        observation.thesis_id,
        observation.thesis_version,
        observation.thesis_hash,
    ) != (thesis.thesis_id, thesis.version, thesis.hash()):
        raise ValueError("monitor observation changed frozen thesis version")

    action: Literal["hold", "exit"] = "hold"
    reason: Literal[
        "hold",
        "thesis_invalidated",
        "time_exit",
        "better_opportunity",
        "price_stale",
        "quote_not_known",
    ] = "hold"
    if observation.falsifier_triggered:
        action, reason = "exit", "thesis_invalidated"
    elif observation.known_at >= thesis.time_exit_at:
        action, reason = "exit", "time_exit"
    elif (
        observation.better_opportunity_advantage_bps is not None
        and observation.better_opportunity_advantage_bps
        >= thesis.better_opportunity_min_bps
    ):
        action, reason = "exit", "better_opportunity"
    elif observation.quote.known_at > observation.known_at:
        action, reason = "exit", "quote_not_known"
    elif (
        observation.known_at - observation.quote.as_of
    ).total_seconds() > policy.max_price_age_seconds:
        action, reason = "exit", "price_stale"

    decision_id = (
        "exit_"
        + contract_hash([observation.observation_id, action, reason, policy.version])[
            :32
        ]
    )
    return ExitDecision(
        decision_id=decision_id,
        position_id=thesis.position_id,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        thesis_hash=thesis.hash(),
        binding=thesis.binding,
        known_at=observation.known_at,
        action=action,
        reason_code=reason,
        observation_id=observation.observation_id,
        policy_version=policy.version,
    )
