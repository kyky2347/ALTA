"""Small, fail-closed contracts. Raw credentials and account IDs never leave here."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Provider = Literal["tiger", "alpaca", "ibkr", "longport", "futu", "schwab"]
Environment = Literal["PAPER", "LIVE"]
Number = Annotated[Decimal, Field(allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class BrokerError(RuntimeError):
    """Only constant error codes cross the operator boundary, never SDK text."""


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Profile(Contract):
    provider: Provider
    environment: Environment
    account: SecretStr
    credentials: dict[str, SecretStr] = Field(repr=False)
    max_order_notional: Positive = Decimal("10000")
    max_gross_notional: Positive = Decimal("25000")
    max_quote_age_seconds: int = Field(default=10, ge=1, le=30)
    max_spread_bps: Positive = Decimal("30")

    @model_validator(mode="after")
    def validate_profile(self):
        import re

        if not re.fullmatch(r"[A-Za-z0-9._-]{3,128}", self.account.get_secret_value()):
            raise ValueError("account_binding_invalid")
        if self.max_order_notional > self.max_gross_notional:
            raise ValueError("order_limit_exceeds_gross_limit")
        if self.provider == "schwab" and self.environment != "LIVE":
            raise ValueError("schwab_paper_unavailable")
        if len(self.credentials) > 12 or any(
            not re.fullmatch(r"[a-z_]{2,40}", key)
            or not 1 <= len(value.get_secret_value()) <= 16000
            for key, value in self.credentials.items()
        ):
            raise ValueError("credentials_invalid")
        return self

    def secret(self, key: str) -> str:
        if key not in self.credentials:
            raise BrokerError("credential_missing")
        return self.credentials[key].get_secret_value()

    @property
    def binding(self) -> str:
        raw = f"{self.provider}:{self.environment}:{self.account.get_secret_value()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def revision(self) -> str:
        raw = self.model_dump(mode="json")
        raw["account"] = self.account.get_secret_value()
        raw["credentials"] = {
            key: value.get_secret_value() for key, value in self.credentials.items()
        }
        import json

        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


class Position(Contract):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9. /_-]{0,39}$")
    quantity: Number
    market_value: Number | None
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Order(Contract):
    order_id: str = Field(min_length=1, max_length=128, repr=False)
    client_id: str = Field(default="", max_length=128)
    symbol: str = Field(min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    quantity: Positive
    filled: Number = Field(ge=0)
    limit_price: Positive | None = None
    average_price: Positive | None = None
    state: Literal["working", "filled", "cancelled", "rejected", "unknown"]

    @model_validator(mode="after")
    def validate_fill(self):
        if self.filled > self.quantity:
            raise ValueError("fill_exceeds_order")
        if self.state == "filled" and (
            self.filled != self.quantity or self.average_price is None
        ):
            raise ValueError("fill_evidence_incomplete")
        return self


class Snapshot(Contract):
    binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    environment: Environment
    verified_at: datetime
    currency: Literal["USD"]
    equity: Number
    cash: Number
    buying_power: Number
    positions: tuple[Position, ...]
    orders: tuple[Order, ...]
    account_verified: bool
    environment_verified: bool
    trading_permitted: bool

    @model_validator(mode="after")
    def validate_snapshot(self):
        if self.verified_at.tzinfo is None:
            raise ValueError("timestamp_requires_timezone")
        if len(self.positions) > 1000 or len(self.orders) > 2000:
            raise ValueError("snapshot_limit_exceeded")
        if len({p.symbol for p in self.positions}) != len(self.positions):
            raise ValueError("duplicate_position")
        return self


class Intent(Contract):
    client_id: str = Field(pattern=r"^alta-[a-f0-9]{32}$")
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,14}$")
    side: Literal["BUY", "SELL"]
    quantity: Positive = Field(max_digits=12, decimal_places=0)
    limit_price: Positive = Field(max_digits=12, decimal_places=2)
    reference_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,128}$")
    # Caller specifies a strict limit, never a market order after an LLM delay.
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at.tzinfo is None:
            raise ValueError("timestamp_requires_timezone")
        return self


class Quote(Contract):
    symbol: str
    bid: Positive
    ask: Positive
    observed_at: datetime
    # Only actual realtime entitlement; delayed/unknown feeds cannot admit risk.
    realtime: bool

    @model_validator(mode="after")
    def validate_quote(self):
        if self.bid > self.ask or self.observed_at.tzinfo is None:
            raise ValueError("quote_invalid")
        return self


class Adapter(Protocol):
    def snapshot(self) -> Snapshot: ...
    def submit(self, intent: Intent) -> Order: ...
    def lookup(self, client_id: str, order_id: str | None) -> Order | None: ...
    def cancel(self, order_id: str) -> None: ...
    def close(self) -> None: ...


def now() -> datetime:
    return datetime.now(UTC)


def require(condition: bool, code: str):
    if not condition:
        raise BrokerError(code)


def dispatch_guard(intent: Intent):
    """The engine shortens this deadline to the dispatch quote's expiry."""
    require(now() < intent.expires_at, "dispatch_deadline_expired")
