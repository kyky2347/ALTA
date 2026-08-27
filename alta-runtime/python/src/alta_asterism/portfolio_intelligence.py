from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal

from pydantic import Field, field_validator

from .alpha_isolation import AlphaSource, SystematicExposure
from .expression_base import FrozenContract
from .implementation import PortfolioRiskPolicy, PortfolioState

_BPS = Decimal(10_000)
_BPS_QUANTUM = Decimal("0.01")
_SATURATION_FRACTION = Decimal("0.80")
_RESEARCHABLE_ALPHA_SOURCES: tuple[AlphaSource, ...] = (
    "idiosyncratic",
    "earnings_revision",
    "event",
    "relative_value",
    "market_structure",
    "systematic_factor",
)


class PortfolioResearchMandate(FrozenContract):
    """Frozen book context that guides research without becoming Evidence."""

    version: Literal["alta-portfolio-research-mandate-v1"] = (
        "alta-portfolio-research-mandate-v1"
    )
    known_at: datetime
    posture: Literal["empty_book", "balanced", "concentrated", "risk_constrained"]
    open_positions: int = Field(ge=0, le=8)
    gross_nav_bps: Decimal = Field(ge=0)
    stress_nav_bps: Decimal = Field(ge=0)
    saturated_alpha_sources: tuple[AlphaSource, ...] = Field(default=(), max_length=7)
    saturated_systematic_exposures: tuple[SystematicExposure, ...] = Field(
        default=(), max_length=16
    )
    saturated_catalyst_keys: tuple[str, ...] = Field(default=(), max_length=8)
    diversification_search_targets: tuple[AlphaSource, ...] = Field(
        default=(), max_length=3
    )
    research_objectives: tuple[str, ...] = Field(default=(), max_length=4)

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "portfolio research mandate known_at must be timezone-aware"
            )
        return value


def build_portfolio_research_mandate(
    state: PortfolioState,
    policy: PortfolioRiskPolicy,
    known_at: datetime,
) -> PortfolioResearchMandate:
    """Translates current book constraints into bounded, non-prescriptive research context."""

    source_limit = policy.dollars(policy.max_alpha_source_nav_bps)
    exposure_limit = policy.dollars(policy.max_systematic_exposure_nav_bps)
    catalyst_limit = policy.dollars(policy.max_catalyst_nav_bps)
    stress_limit = policy.dollars(policy.max_portfolio_stress_nav_bps)
    saturated_sources = tuple(
        item.source
        for item in state.alpha_source_buckets
        if item.source != "legacy_unclassified"
        and item.gross_notional >= source_limit * _SATURATION_FRACTION
    )
    saturated_exposures = tuple(
        item.tag
        for item in state.exposure_buckets
        if item.tag not in {"none", "unknown"}
        and item.gross_notional >= exposure_limit * _SATURATION_FRACTION
    )
    saturated_catalysts = tuple(
        item.catalyst_key
        for item in state.catalyst_buckets
        if item.catalyst_key != "legacy-unclassified"
        and item.gross_notional >= catalyst_limit * _SATURATION_FRACTION
    )
    stress_constrained = (
        state.aggregate_stress_loss >= stress_limit * _SATURATION_FRACTION
    )
    gross_by_source = {
        item.source: item.gross_notional for item in state.alpha_source_buckets
    }
    search_targets = ()
    if state.known_open_positions and (
        saturated_sources
        or saturated_exposures
        or saturated_catalysts
        or stress_constrained
    ):
        search_targets = tuple(
            sorted(
                _RESEARCHABLE_ALPHA_SOURCES,
                key=lambda source: (gross_by_source.get(source, Decimal(0)), source),
            )[:3]
        )

    top_source_fraction = Decimal(0)
    if state.gross_notional > 0 and state.alpha_source_buckets:
        top_source_fraction = (
            max(item.gross_notional for item in state.alpha_source_buckets)
            / state.gross_notional
        )
    if state.known_open_positions == 0:
        posture = "empty_book"
    elif (
        saturated_sources
        or saturated_exposures
        or saturated_catalysts
        or stress_constrained
    ):
        posture = "risk_constrained"
    elif top_source_fraction >= Decimal("0.60"):
        posture = "concentrated"
    else:
        posture = "balanced"

    objectives = [
        "Seek a distinct causal payoff, not a cosmetic ticker diversification.",
        "A no-op is preferable to weakening evidence or falsifiability standards.",
    ]
    if search_targets:
        objectives.insert(
            0,
            (
                "Test independent opportunities outside saturated catalyst, "
                "Alpha-source, and factor buckets."
                if saturated_catalysts
                else "Test independent opportunities outside saturated Alpha and factor buckets."
            ),
        )
    if stress_constrained:
        objectives.append(
            "Favor bounded-downside or capital-efficient hypotheses that survive stress.",
        )
    return PortfolioResearchMandate(
        known_at=known_at,
        posture=posture,  # type: ignore[arg-type]
        open_positions=state.known_open_positions,
        gross_nav_bps=_nav_bps(state.gross_notional, policy.reference_nav),
        stress_nav_bps=_nav_bps(state.aggregate_stress_loss, policy.reference_nav),
        saturated_alpha_sources=saturated_sources,
        saturated_systematic_exposures=saturated_exposures,
        saturated_catalyst_keys=saturated_catalysts,
        diversification_search_targets=search_targets,
        research_objectives=tuple(objectives),
    )


def _nav_bps(value: Decimal, reference_nav: Decimal) -> Decimal:
    return (value / reference_nav * _BPS).quantize(
        _BPS_QUANTUM, rounding=ROUND_HALF_EVEN
    )
