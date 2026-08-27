from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract

_BPS_QUANTUM = Decimal("0.0001")


class AlphaClock(FrozenContract):
    """Point-in-time decay record for an underwritten opportunity edge."""

    version: Literal["alta-alpha-clock-v1"] = "alta-alpha-clock-v1"
    method: Literal["linear_remaining_horizon_proxy"] = "linear_remaining_horizon_proxy"
    known_at: datetime
    evidence_freshness_at: datetime
    horizon_days: int = Field(ge=1, le=365)
    age_seconds: int = Field(ge=0)
    remaining_seconds: int = Field(ge=0)
    retention_fraction: Decimal = Field(ge=0, le=1)
    stage: Literal["forming", "active", "expiring", "expired"]
    raw_expected_net_alpha_bps: Decimal
    time_adjusted_expected_net_alpha_bps: Decimal
    catalyst_clarity: Decimal = Field(ge=0, le=1)
    next_pricing_facts: tuple[str, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_clock(self) -> "AlphaClock":
        for value, name in (
            (self.known_at, "alpha clock known_at"),
            (self.evidence_freshness_at, "alpha clock evidence_freshness_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.evidence_freshness_at > self.known_at:
            raise ValueError("alpha clock cannot use future evidence")
        if self.age_seconds + self.remaining_seconds != self.horizon_days * 86_400:
            raise ValueError("alpha clock horizon decomposition is inconsistent")
        expected = (self.raw_expected_net_alpha_bps * self.retention_fraction).quantize(
            _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
        )
        if self.time_adjusted_expected_net_alpha_bps != expected:
            raise ValueError("time-adjusted Alpha does not match the frozen clock")
        return self


def build_alpha_clock(
    *,
    known_at: datetime,
    evidence_freshness_at: datetime,
    horizon_days: int,
    raw_expected_net_alpha_bps: Decimal,
    catalyst_clarity: Decimal,
    next_pricing_facts: tuple[str, ...],
) -> AlphaClock:
    """Conservatively reduces unearned edge as its evidence horizon elapses."""

    if horizon_days < 1 or horizon_days > 365:
        raise ValueError("alpha horizon must be between 1 and 365 days")
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("alpha clock known_at must be timezone-aware")
    if (
        evidence_freshness_at.tzinfo is None
        or evidence_freshness_at.utcoffset() is None
    ):
        raise ValueError("alpha evidence freshness must be timezone-aware")
    if evidence_freshness_at > known_at:
        raise ValueError("alpha clock cannot use future evidence")

    horizon = timedelta(days=horizon_days)
    total_seconds = int(horizon.total_seconds())
    age_seconds = min(
        total_seconds,
        max(0, int((known_at - evidence_freshness_at).total_seconds())),
    )
    remaining_seconds = total_seconds - age_seconds
    retention = Decimal(remaining_seconds) / Decimal(total_seconds)
    if retention == 0:
        stage = "expired"
    elif retention <= Decimal("0.20"):
        stage = "expiring"
    elif retention <= Decimal("0.67"):
        stage = "active"
    else:
        stage = "forming"
    adjusted = (raw_expected_net_alpha_bps * retention).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    return AlphaClock(
        known_at=known_at,
        evidence_freshness_at=evidence_freshness_at,
        horizon_days=horizon_days,
        age_seconds=age_seconds,
        remaining_seconds=remaining_seconds,
        retention_fraction=retention,
        stage=stage,
        raw_expected_net_alpha_bps=raw_expected_net_alpha_bps,
        time_adjusted_expected_net_alpha_bps=adjusted,
        catalyst_clarity=catalyst_clarity,
        next_pricing_facts=tuple(dict.fromkeys(next_pricing_facts))[:4],
    )
