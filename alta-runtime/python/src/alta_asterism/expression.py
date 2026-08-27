from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Environment
from .expression_base import FrozenContract, contract_hash
from .implementation import TradeImplementationPlan

HASH_PATTERN = r"^[a-f0-9]{64}$"
MONEY_QUANTUM = Decimal("0.000001")
BPS_QUANTUM = Decimal("0.0001")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class EvidenceVersion(FrozenContract):
    evidence_id: str = Field(min_length=3, max_length=128)
    version: int = Field(ge=1)
    known_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> "EvidenceVersion":
        _aware(self.known_at, "evidence known_at")
        return self


class VersionBinding(FrozenContract):
    environment: Environment
    opportunity_id: str = Field(min_length=3, max_length=128)
    opportunity_version: int = Field(ge=1)
    opportunity_snapshot_hash: str = Field(pattern=HASH_PATTERN)
    evidence: tuple[EvidenceVersion, ...] = Field(min_length=1, max_length=20)
    evidence_set_hash: str = Field(pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_evidence_set(self) -> "VersionBinding":
        identities = [(item.evidence_id, item.version) for item in self.evidence]
        if identities != sorted(identities) or len(set(identities)) != len(identities):
            raise ValueError("evidence versions must be unique and sorted")
        expected = contract_hash(
            [item.model_dump(mode="json") for item in self.evidence]
        )
        if self.evidence_set_hash != expected:
            raise ValueError("evidence_set_hash does not match evidence versions")
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


class QuoteSnapshot(FrozenContract):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.:-]{0,31}$")
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    currency: Literal["USD"] = "USD"
    as_of: datetime
    known_at: datetime
    raw_id: str = Field(min_length=3, max_length=128)
    raw_version: int = Field(ge=1)
    content_hash: str = Field(pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_quote(self) -> "QuoteSnapshot":
        _aware(self.as_of, "quote as_of")
        _aware(self.known_at, "quote known_at")
        if self.ask < self.bid:
            raise ValueError("quote ask cannot be below bid")
        if self.as_of > self.known_at:
            raise ValueError("quote as_of cannot exceed known_at")
        return self


class ExpressionProposal(FrozenContract):
    expression_id: str = Field(min_length=3, max_length=128)
    version: int = Field(default=1, ge=1)
    binding: VersionBinding
    kind: Literal["stock", "etf", "option", "wait"]
    symbol: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9.:-]{0,31}$")
    side: Literal["long"] | None = None
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    rationale: str = Field(min_length=1, max_length=4_000)
    decision_known_at: datetime
    quote: QuoteSnapshot | None = None
    implementation_plan: TradeImplementationPlan | None = None
    thesis_pillar_ids: tuple[str, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_shape(self) -> "ExpressionProposal":
        _aware(self.decision_known_at, "expression decision_known_at")
        if self.binding.environment == Environment.PAPER:
            raise ValueError("B5 research expressions cannot use the Paper environment")
        if len(set(self.thesis_pillar_ids)) != len(self.thesis_pillar_ids):
            raise ValueError("expression thesis pillar IDs must be unique")
        if self.kind == "wait":
            if (
                any((self.symbol, self.side, self.quote, self.thesis_pillar_ids))
                or self.quantity != 0
            ):
                raise ValueError(
                    "Wait cannot carry an instrument, side, quantity, quote, or pillar"
                )
        elif self.symbol is None or self.side != "long" or self.quantity <= 0:
            raise ValueError(
                "Instrument expression requires a symbol, long side, and positive quantity"
            )
        elif self.quote is None or self.quote.symbol != self.symbol:
            raise ValueError(
                "Instrument expression requires a quote for the exact symbol"
            )
        elif self.implementation_plan is not None and (
            self.implementation_plan.status != "ready"
            or self.implementation_plan.target_quantity != self.quantity
        ):
            raise ValueError(
                "instrument expression does not match its implementation plan"
            )
        return self

    def hash(self) -> str:
        return contract_hash(self.model_dump(mode="json"))


class ExpressionPolicy(FrozenContract):
    version: Literal["b8-expression-v2"] = "b8-expression-v2"
    max_price_age_seconds: int = Field(default=60, ge=1, le=3_600)
    max_spread_bps: Decimal = Field(default=Decimal("40"), ge=0)
    max_all_in_cost_bps: Decimal = Field(default=Decimal("55"), ge=0)
    max_option_spread_bps: Decimal = Field(default=Decimal("1200"), ge=0)
    max_option_all_in_cost_bps: Decimal = Field(default=Decimal("1300"), ge=0)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0)
    option_slippage_bps: Decimal = Field(default=Decimal("50"), ge=0)
    commission_bps: Decimal = Field(default=Decimal("1"), ge=0)
    minimum_commission: Decimal = Field(default=Decimal("0.01"), ge=0)
    option_commission_per_contract: Decimal = Field(default=Decimal("0.65"), ge=0)


class ExpressionValidation(FrozenContract):
    expression_id: str
    expression_version: int = Field(ge=1)
    expression_hash: str = Field(pattern=HASH_PATTERN)
    binding: VersionBinding
    status: Literal["validated", "rejected"]
    reason_codes: tuple[str, ...]
    known_at: datetime
    policy_version: str
    spread_bps: Decimal | None = None
    estimated_cost_bps: Decimal | None = None
    entry_price: Decimal | None = None
    estimated_commission: Decimal | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "ExpressionValidation":
        _aware(self.known_at, "validation known_at")
        if self.status == "rejected" and not self.reason_codes:
            raise ValueError("rejected validation requires a reason")
        return self


def _bps(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator * Decimal(10_000)).quantize(
        BPS_QUANTUM, rounding=ROUND_HALF_UP
    )


def validate_expression(
    proposal: ExpressionProposal, policy: ExpressionPolicy
) -> ExpressionValidation:
    expression_hash = proposal.hash()
    if proposal.kind == "wait":
        return ExpressionValidation(
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=expression_hash,
            binding=proposal.binding,
            status="validated",
            reason_codes=("wait_selected",),
            known_at=proposal.decision_known_at,
            policy_version=policy.version,
        )

    quote = proposal.quote
    if quote is None:
        raise ValueError("instrument expression is missing its quote")
    reasons: list[str] = []
    if quote.known_at > proposal.decision_known_at:
        reasons.append("quote_not_known_at_decision")
    age_seconds = (proposal.decision_known_at - quote.as_of).total_seconds()
    if age_seconds < 0:
        reasons.append("quote_as_of_in_future")
    elif age_seconds > policy.max_price_age_seconds:
        reasons.append("price_stale")

    midpoint = (quote.bid + quote.ask) / Decimal(2)
    spread_bps = _bps(quote.ask - quote.bid, midpoint)
    max_spread_bps = (
        policy.max_option_spread_bps
        if proposal.kind == "option"
        else policy.max_spread_bps
    )
    if spread_bps > max_spread_bps:
        reasons.append("spread_too_wide")

    notional = (quote.ask * proposal.quantity).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    variable_commission = (notional * policy.commission_bps / Decimal(10_000)).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    commission = (
        max(
            proposal.quantity / Decimal(100) * policy.option_commission_per_contract,
            policy.minimum_commission,
        )
        if proposal.kind == "option"
        else max(variable_commission, policy.minimum_commission)
    )
    commission_bps = _bps(commission, notional)
    slippage_bps = (
        policy.option_slippage_bps if proposal.kind == "option" else policy.slippage_bps
    )
    estimated_cost_bps = (spread_bps + slippage_bps + commission_bps).quantize(
        BPS_QUANTUM, rounding=ROUND_HALF_UP
    )
    max_all_in_cost_bps = (
        policy.max_option_all_in_cost_bps
        if proposal.kind == "option"
        else policy.max_all_in_cost_bps
    )
    if estimated_cost_bps > max_all_in_cost_bps:
        reasons.append("estimated_cost_too_high")

    return ExpressionValidation(
        expression_id=proposal.expression_id,
        expression_version=proposal.version,
        expression_hash=expression_hash,
        binding=proposal.binding,
        status="rejected" if reasons else "validated",
        reason_codes=tuple(reasons),
        known_at=proposal.decision_known_at,
        policy_version=policy.version,
        spread_bps=spread_bps,
        estimated_cost_bps=estimated_cost_bps,
        entry_price=quote.ask,
        estimated_commission=commission,
    )
