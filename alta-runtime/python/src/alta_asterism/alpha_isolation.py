from decimal import Decimal
from typing import Literal, cast, get_args

from pydantic import Field, model_validator

from .expression_base import FrozenContract


AlphaSource = Literal[
    "idiosyncratic",
    "earnings_revision",
    "event",
    "relative_value",
    "market_structure",
    "systematic_factor",
    "legacy_unclassified",
]
SystematicExposure = Literal[
    "market_beta",
    "sector",
    "growth_duration",
    "value",
    "momentum",
    "quality",
    "size",
    "volatility",
    "rates",
    "fx",
    "commodity",
    "liquidity",
    "crowding",
    "event_gap",
    "none",
    "unknown",
]
HedgePosture = Literal[
    "unhedged_intentional",
    "size_down",
    "contained_by_option",
    "requires_multi_leg",
    "not_applicable",
]
KNOWN_SYSTEMATIC_EXPOSURES = frozenset(get_args(SystematicExposure))


def normalize_systematic_exposure(value: object) -> SystematicExposure:
    if isinstance(value, str) and value in KNOWN_SYSTEMATIC_EXPOSURES:
        return cast(SystematicExposure, value)
    return "unknown"


class AlphaIsolation(FrozenContract):
    """Auditable split between intended Alpha and systematic risk.

    This is deliberately a conservative sizing input, not an expected-return
    booster. A high score can preserve a risk budget; it cannot manufacture one.
    """

    posture: Literal["legacy", "provisional", "audited"]
    alpha_source: AlphaSource
    systematic_exposures: tuple[SystematicExposure, ...] = Field(
        default=(), max_length=8
    )
    hedge_posture: HedgePosture
    proposer_score: Decimal | None = Field(default=None, ge=0, le=1)
    auditor_score: Decimal | None = Field(default=None, ge=0, le=1)
    conservative_score: Decimal | None = Field(default=None, ge=0, le=1)
    sizing_multiplier: Decimal = Field(default=Decimal(1), gt=0, le=1)
    basis_risk: str = Field(default="", max_length=800)
    exposure_disagreements: tuple[str, ...] = Field(default=(), max_length=8)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_isolation(self) -> "AlphaIsolation":
        if len(set(self.systematic_exposures)) != len(self.systematic_exposures):
            raise ValueError("systematic exposures must be unique")
        if "none" in self.systematic_exposures and len(self.systematic_exposures) != 1:
            raise ValueError("none cannot be combined with systematic exposures")
        if self.posture == "audited" and (
            self.auditor_score is None or self.conservative_score is None
        ):
            raise ValueError("audited Alpha isolation requires both scores")
        return self

    @property
    def binding_exposures(self) -> tuple[SystematicExposure, ...]:
        return tuple(
            item
            for item in self.systematic_exposures
            if item not in {"none", "unknown"}
        )


def provisional_alpha_isolation(
    *,
    alpha_source: AlphaSource,
    systematic_exposures: tuple[SystematicExposure, ...],
    hedge_posture: HedgePosture,
    thesis_purity: float,
    timing_fit: float,
    basis_risk: str,
) -> AlphaIsolation:
    proposer_score = min(Decimal(str(thesis_purity)), Decimal(str(timing_fit)))
    reasons = []
    if alpha_source == "legacy_unclassified" or not systematic_exposures:
        reasons.append("systematic_exposure_unclassified")
    if "unknown" in systematic_exposures:
        reasons.append("systematic_exposure_unclassified")
    if hedge_posture == "requires_multi_leg":
        reasons.append("alpha_requires_unsupported_multi_leg_expression")
    return AlphaIsolation(
        posture="provisional",
        alpha_source=alpha_source,
        systematic_exposures=systematic_exposures,
        hedge_posture=hedge_posture,
        proposer_score=proposer_score,
        conservative_score=proposer_score,
        sizing_multiplier=(
            Decimal("0.5") if proposer_score < Decimal("0.8") else Decimal(1)
        ),
        basis_risk=basis_risk,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def audited_alpha_isolation(
    *,
    alpha_source: AlphaSource,
    proposed_exposures: tuple[SystematicExposure, ...],
    confirmed_exposures: tuple[SystematicExposure, ...],
    proposed_hedge_posture: HedgePosture,
    audited_hedge_posture: HedgePosture,
    thesis_purity: float,
    timing_fit: float,
    thesis_alignment: float,
    implementation_quality: float,
    auditor_score: float,
    basis_risk: str,
    exposure_disagreements: tuple[str, ...],
) -> AlphaIsolation:
    proposer_score = min(Decimal(str(thesis_purity)), Decimal(str(timing_fit)))
    independent_score = min(
        Decimal(str(thesis_alignment)),
        Decimal(str(implementation_quality)),
        Decimal(str(auditor_score)),
    )
    conservative_score = min(proposer_score, independent_score)
    reasons = []
    disagreements = list(exposure_disagreements)
    if set(proposed_exposures) != set(confirmed_exposures):
        disagreements.append("proposer_and_auditor_exposure_sets_differ")
    exposures = tuple(dict.fromkeys((*proposed_exposures, *confirmed_exposures)))
    if alpha_source == "legacy_unclassified" or not exposures or "unknown" in exposures:
        reasons.append("systematic_exposure_unclassified")
    if disagreements:
        reasons.append("systematic_exposure_audit_disagreement")
    hedge_posture = _conservative_hedge_posture(
        proposed_hedge_posture, audited_hedge_posture
    )
    if hedge_posture == "requires_multi_leg":
        reasons.append("alpha_requires_unsupported_multi_leg_expression")
    return AlphaIsolation(
        posture="audited",
        alpha_source=alpha_source,
        systematic_exposures=exposures,
        hedge_posture=hedge_posture,
        proposer_score=proposer_score,
        auditor_score=independent_score,
        conservative_score=conservative_score,
        sizing_multiplier=(
            Decimal("0.5") if conservative_score < Decimal("0.8") else Decimal(1)
        ),
        basis_risk=basis_risk,
        exposure_disagreements=tuple(dict.fromkeys(disagreements)),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def legacy_alpha_isolation() -> AlphaIsolation:
    return AlphaIsolation(
        posture="legacy",
        alpha_source="legacy_unclassified",
        hedge_posture="not_applicable",
    )


def _conservative_hedge_posture(
    proposed: HedgePosture, audited: HedgePosture
) -> HedgePosture:
    order: tuple[HedgePosture, ...] = (
        "not_applicable",
        "unhedged_intentional",
        "contained_by_option",
        "size_down",
        "requires_multi_leg",
    )
    return max((proposed, audited), key=order.index)
