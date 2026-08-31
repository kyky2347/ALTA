from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .expression_base import FrozenContract
from .underwriting_calibration import (
    AlphaPerformanceObservation,
    summarize_alpha_evidence,
)


@dataclass(frozen=True)
class CapitalPerformanceObservation:
    position_id: str
    known_at: datetime
    net_pnl: Decimal
    realized_alpha_bps: Decimal


@dataclass(frozen=True)
class _GovernanceMetrics:
    recent_mean_alpha_bps: Decimal | None
    confidence95_lower_alpha_bps: Decimal | None
    confidence95_upper_alpha_bps: Decimal | None
    selection_adjusted_lower_alpha_bps: Decimal | None
    selection_critical_z: Decimal | None
    max_drawdown_nav_bps: Decimal
    evidence_posture: str


class AlphaCapitalGovernancePolicy(FrozenContract):
    """Conservative rolling policy for long-lived autonomous Shadow capital."""

    version: Literal["alta-alpha-capital-governance-v1"] = (
        "alta-alpha-capital-governance-v1"
    )
    window_size: int = Field(default=30, ge=10, le=250)
    minimum_evidence_sample: int = Field(default=30, ge=10, le=250)
    probation_sample: int = Field(default=10, ge=5, le=100)
    max_drawdown_nav_bps: Decimal = Field(default=Decimal("100"), gt=0)
    collecting_multiplier: Decimal = Field(default=Decimal("0.50"), gt=0, le=1)
    probation_multiplier: Decimal = Field(default=Decimal("0.50"), gt=0, le=1)
    capital_preservation_multiplier: Decimal = Field(
        default=Decimal("0.10"), gt=0, le=1
    )

    @model_validator(mode="after")
    def validate_policy(self) -> "AlphaCapitalGovernancePolicy":
        if self.minimum_evidence_sample > self.window_size:
            raise ValueError("evidence sample cannot exceed the rolling window")
        if self.probation_sample > self.minimum_evidence_sample:
            raise ValueError("probation sample cannot exceed the evidence sample")
        if self.capital_preservation_multiplier > self.probation_multiplier:
            raise ValueError("capital preservation cannot exceed probation capital")
        return self


class AlphaCapitalGovernance(FrozenContract):
    """Frozen capital posture derived only from prior cost-adjusted outcomes."""

    policy_version: str = Field(min_length=3, max_length=64)
    source_portfolio_policy_version: str = Field(min_length=3, max_length=64)
    posture: Literal["unscoped", "collecting", "normal", "probation", "preservation"]
    capital_multiplier: Decimal = Field(gt=0, le=1)
    sample_size: int = Field(ge=0)
    window_size: int = Field(ge=0)
    recent_mean_alpha_bps: Decimal | None = None
    confidence95_lower_alpha_bps: Decimal | None = None
    confidence95_upper_alpha_bps: Decimal | None = None
    research_trials: int = Field(default=0, ge=0)
    selection_adjusted_lower_alpha_bps: Decimal | None = None
    selection_critical_z: Decimal | None = Field(default=None, gt=0)
    max_drawdown_nav_bps: Decimal = Field(ge=0)
    evidence_posture: str = Field(min_length=1, max_length=96)
    observed_through: datetime | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)

    @classmethod
    def unscoped(cls, source_portfolio_policy_version: str) -> "AlphaCapitalGovernance":
        return cls(
            policy_version="alta-alpha-capital-governance-v1",
            source_portfolio_policy_version=source_portfolio_policy_version,
            posture="unscoped",
            capital_multiplier=Decimal(1),
            sample_size=0,
            window_size=0,
            max_drawdown_nav_bps=Decimal(0),
            evidence_posture="not_loaded",
            reason_codes=("governance_not_loaded",),
        )


def _maximum_drawdown(pnl: tuple[Decimal, ...]) -> Decimal:
    cumulative = Decimal(0)
    high_water = Decimal(0)
    maximum = Decimal(0)
    for value in pnl:
        cumulative += value
        high_water = max(high_water, cumulative)
        maximum = max(maximum, high_water - cumulative)
    return maximum


def _validated_window(
    observations: tuple[CapitalPerformanceObservation, ...],
    *,
    policy: AlphaCapitalGovernancePolicy,
    total_sample_size: int | None,
) -> tuple[
    tuple[CapitalPerformanceObservation, ...],
    tuple[CapitalPerformanceObservation, ...],
]:
    if len({item.position_id for item in observations}) != len(observations):
        raise ValueError("capital governance observations must be unique by position")
    if total_sample_size is not None and total_sample_size < len(observations):
        raise ValueError("total sample cannot be smaller than the supplied window")
    if any(
        item.known_at.tzinfo is None or item.known_at.utcoffset() is None
        for item in observations
    ):
        raise ValueError("capital governance observations must be timezone-aware")
    ordered = tuple(
        sorted(observations, key=lambda item: (item.known_at, item.position_id))
    )
    return ordered, ordered[-policy.window_size :]


def _window_metrics(
    window: tuple[CapitalPerformanceObservation, ...],
    *,
    reference_nav: Decimal,
    policy: AlphaCapitalGovernancePolicy,
    research_trials: int,
) -> _GovernanceMetrics:
    alphas = tuple(item.realized_alpha_bps for item in window)
    recent_mean = sum(alphas, Decimal(0)) / Decimal(len(alphas)) if alphas else None
    drawdown_nav_bps = (
        _maximum_drawdown(tuple(item.net_pnl for item in window))
        / reference_nav
        * Decimal(10_000)
    )
    evidence = summarize_alpha_evidence(
        tuple(
            AlphaPerformanceObservation(item.position_id, item.realized_alpha_bps)
            for item in window
        ),
        minimum_sample=policy.minimum_evidence_sample,
        research_trials=research_trials,
    )
    lower = (
        Decimal(str(evidence["confidence95LowerBps"]))
        if evidence["confidence95LowerBps"] is not None
        else None
    )
    upper = (
        Decimal(str(evidence["confidence95UpperBps"]))
        if evidence["confidence95UpperBps"] is not None
        else None
    )
    selection_lower = (
        Decimal(str(evidence["selectionAdjustedConfidence95LowerBps"]))
        if evidence["selectionAdjustedConfidence95LowerBps"] is not None
        else None
    )
    selection_critical_z = (
        Decimal(str(evidence["selectionCriticalZ"]))
        if evidence["selectionCriticalZ"] is not None
        else None
    )
    return _GovernanceMetrics(
        recent_mean_alpha_bps=recent_mean,
        confidence95_lower_alpha_bps=lower,
        confidence95_upper_alpha_bps=upper,
        selection_adjusted_lower_alpha_bps=selection_lower,
        selection_critical_z=selection_critical_z,
        max_drawdown_nav_bps=drawdown_nav_bps,
        evidence_posture=str(evidence["posture"]),
    )


def _reason_codes(
    metrics: _GovernanceMetrics,
    *,
    sample_size: int,
    policy: AlphaCapitalGovernancePolicy,
) -> list[str]:
    reasons = []
    if metrics.max_drawdown_nav_bps >= policy.max_drawdown_nav_bps:
        reasons.append("rolling_shadow_drawdown_limit")
    if (
        sample_size >= policy.minimum_evidence_sample
        and metrics.confidence95_upper_alpha_bps is not None
        and metrics.confidence95_upper_alpha_bps <= 0
    ):
        reasons.append("negative_alpha_confidence_interval")
    if (
        sample_size >= policy.probation_sample
        and metrics.recent_mean_alpha_bps is not None
        and metrics.recent_mean_alpha_bps < 0
    ):
        reasons.append("recent_mean_alpha_negative")
    if sample_size >= policy.minimum_evidence_sample and (
        metrics.selection_adjusted_lower_alpha_bps is None
        or metrics.selection_adjusted_lower_alpha_bps <= 0
    ):
        reasons.append("selection_adjusted_alpha_not_proven")
    return reasons


def _capital_posture(
    reasons: list[str],
    *,
    sample_size: int,
    policy: AlphaCapitalGovernancePolicy,
) -> tuple[str, Decimal]:
    if {
        "rolling_shadow_drawdown_limit",
        "negative_alpha_confidence_interval",
    }.intersection(reasons):
        return "preservation", policy.capital_preservation_multiplier
    if "recent_mean_alpha_negative" in reasons:
        return "probation", policy.probation_multiplier
    if "selection_adjusted_alpha_not_proven" in reasons:
        return "probation", policy.probation_multiplier
    if sample_size < policy.minimum_evidence_sample:
        reasons.append("forward_alpha_sample_collecting")
        return "collecting", policy.collecting_multiplier
    reasons.append("selection_adjusted_forward_alpha_positive")
    return "normal", Decimal(1)


def evaluate_alpha_capital_governance(
    observations: tuple[CapitalPerformanceObservation, ...],
    *,
    reference_nav: Decimal,
    source_portfolio_policy_version: str,
    policy: AlphaCapitalGovernancePolicy | None = None,
    total_sample_size: int | None = None,
    research_trials: int | None = None,
) -> AlphaCapitalGovernance:
    """Throttle but never lever up from bounded rolling forward Shadow evidence."""

    if reference_nav <= 0:
        raise ValueError("reference NAV must be positive")
    policy = policy or AlphaCapitalGovernancePolicy()
    ordered, window = _validated_window(
        observations,
        policy=policy,
        total_sample_size=total_sample_size,
    )
    total_sample = len(ordered) if total_sample_size is None else total_sample_size
    research_trials = total_sample if research_trials is None else research_trials
    if research_trials < total_sample:
        raise ValueError("research trials cannot be smaller than the total sample")
    metrics = _window_metrics(
        window,
        reference_nav=reference_nav,
        policy=policy,
        research_trials=research_trials,
    )
    reason_codes = _reason_codes(
        metrics,
        sample_size=len(window),
        policy=policy,
    )
    posture, multiplier = _capital_posture(
        reason_codes,
        sample_size=len(window),
        policy=policy,
    )

    return AlphaCapitalGovernance(
        policy_version=policy.version,
        source_portfolio_policy_version=source_portfolio_policy_version,
        posture=posture,
        capital_multiplier=multiplier,
        sample_size=(len(ordered) if total_sample_size is None else total_sample_size),
        window_size=len(window),
        recent_mean_alpha_bps=metrics.recent_mean_alpha_bps,
        confidence95_lower_alpha_bps=metrics.confidence95_lower_alpha_bps,
        confidence95_upper_alpha_bps=metrics.confidence95_upper_alpha_bps,
        research_trials=research_trials,
        selection_adjusted_lower_alpha_bps=(metrics.selection_adjusted_lower_alpha_bps),
        selection_critical_z=metrics.selection_critical_z,
        max_drawdown_nav_bps=metrics.max_drawdown_nav_bps,
        evidence_posture=metrics.evidence_posture,
        observed_through=window[-1].known_at if window else None,
        reason_codes=tuple(reason_codes),
    )
