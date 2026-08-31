from decimal import Decimal
from statistics import NormalDist
from typing import Literal

from pydantic import Field

from .expression_base import FrozenContract


class ResearchSelectionEvidence(FrozenContract):
    """Family-wise confidence bound for a searched opportunity population."""

    version: Literal["alta-research-selection-v1"] = "alta-research-selection-v1"
    research_trials: int = Field(ge=0)
    effective_trials: int = Field(ge=1)
    family_wise_error_rate: Decimal = Field(gt=0, lt=1)
    critical_z: Decimal | None = Field(default=None, gt=0)
    adjusted_lower_alpha_bps: Decimal | None = None


def selection_adjusted_alpha_evidence(
    *,
    sample_size: int,
    mean_alpha_bps: Decimal | None,
    standard_error_bps: Decimal | None,
    research_trials: int,
    family_wise_error_rate: Decimal = Decimal("0.05"),
) -> ResearchSelectionEvidence:
    """Apply a conservative Bonferroni bound to the observed research funnel."""

    if sample_size < 0:
        raise ValueError("sample size cannot be negative")
    if research_trials < sample_size:
        raise ValueError("research trials cannot be smaller than the observed sample")
    if not Decimal(0) < family_wise_error_rate < Decimal(1):
        raise ValueError("family-wise error rate must be between zero and one")
    effective_trials = max(1, research_trials)
    if mean_alpha_bps is None or standard_error_bps is None:
        return ResearchSelectionEvidence(
            research_trials=research_trials,
            effective_trials=effective_trials,
            family_wise_error_rate=family_wise_error_rate,
        )
    # Allocate half of the family-wise error budget to the lower tail so one
    # trial reproduces the familiar two-sided 95% lower confidence bound.
    tail_probability = family_wise_error_rate / Decimal(2 * effective_trials)
    critical_z = Decimal(str(NormalDist().inv_cdf(1 - float(tail_probability))))
    adjusted_lower = mean_alpha_bps - critical_z * standard_error_bps
    return ResearchSelectionEvidence(
        research_trials=research_trials,
        effective_trials=effective_trials,
        family_wise_error_rate=family_wise_error_rate,
        critical_z=critical_z,
        adjusted_lower_alpha_bps=adjusted_lower,
    )
