from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .deliberation import (
    DiscussionOutcome,
    PrivateAssessment,
    assessment_disagreement,
    validate_private_pair,
)
from .foundry import OpportunityDraft, canonical_hash
from .research_diligence import (
    RESEARCH_DECISION_HURDLE,
    research_quality_components,
)
from .underwriting import consensus_decision, consensus_underwriting

BOOK_NAME = "opportunity_1_90d"
RANKING_POLICY_VERSION = "alta-ranking-decision-edge-v3"
HORIZON_MIN_DAYS = 1
HORIZON_MAX_DAYS = 90


class RankingGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    status: Literal["ranked", "degraded", "rejected"]
    reason_codes: tuple[str, ...] = ()


class RankedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rank_id: str
    opportunity_id: str
    position: int = Field(ge=1, le=20)
    score: float = Field(ge=0, le=1)
    components: dict[str, float]
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RankingBook(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ranking_run_id: str
    book: Literal["opportunity_1_90d"] = BOOK_NAME
    horizon_min_days: Literal[1] = HORIZON_MIN_DAYS
    horizon_max_days: Literal[90] = HORIZON_MAX_DAYS
    known_at: datetime
    items: tuple[RankedItem, ...]
    gates: tuple[RankingGate, ...]

    @model_validator(mode="after")
    def known_at_is_timezone_aware(self) -> "RankingBook":
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("ranking book known_at must be timezone-aware")
        return self


def _degraded_reasons(opportunity: OpportunityDraft) -> tuple[str, ...]:
    reasons = [
        f"{field}_missing"
        for field in (
            "observed_change",
            "mechanism",
            "expectation",
            "variant_wedge",
            "why_now",
            "first_rejection",
            "prediction",
            "freshness_at",
        )
        if getattr(opportunity, field) in (None, "")
    ]
    if opportunity.direction is None:
        reasons.append("direction_missing")
    if opportunity.investability in (None, "unknown"):
        reasons.append("investability_missing")
    return tuple(reasons)


def _independent_probability_lifts(
    assessments: tuple[PrivateAssessment, PrivateAssessment],
) -> tuple[Decimal, ...]:
    decisions = tuple(item.underwriting.decision for item in assessments)
    if any(item is None for item in decisions):
        return ()
    return tuple(
        Decimal(str(item.inside_view_probability))
        - Decimal(str(item.base_rate_probability))
        for item in decisions
        if item is not None
    )


def _assessment_rejections(
    opportunity: OpportunityDraft,
    assessments: tuple[PrivateAssessment, ...] | None,
) -> tuple[str, ...]:
    if assessments is None:
        return ("private_assessments_missing",)
    try:
        locked = validate_private_pair(opportunity, assessments)
    except ValueError:
        return ("private_assessments_invalid",)
    decision = consensus_decision((locked[0].underwriting, locked[1].underwriting))
    if decision.reason_codes:
        return decision.reason_codes
    reasons = []
    probability_lifts = _independent_probability_lifts(locked)
    if len(probability_lifts) != 2 or min(probability_lifts) <= 0:
        reasons.append("independent_variant_edge_absent")
    underwriting = consensus_underwriting(
        (locked[0].underwriting, locked[1].underwriting)
    )
    if underwriting["uncertainty_adjusted_expected_alpha_bps"] <= 0:
        reasons.append("nonpositive_uncertainty_adjusted_alpha")
    return tuple(reasons)


def _research_rejections(opportunity: OpportunityDraft) -> tuple[str, ...]:
    diligence = opportunity.research_diligence
    if diligence is None or diligence.posture == "no_op":
        return ("research_diligence_missing",)
    quality = research_quality_components(diligence)["research_quality"]
    if quality < RESEARCH_DECISION_HURDLE:
        return ("research_quality_below_decision_hurdle",)
    return ()


def pre_assessment_rejections(opportunity: OpportunityDraft) -> tuple[str, ...]:
    """Return deterministic blockers before spending tokens on private debate."""

    reasons: list[str] = []
    if not HORIZON_MIN_DAYS <= opportunity.horizon_days <= HORIZON_MAX_DAYS:
        reasons.append("outside_1_90_day_horizon")
    if not opportunity.evidence_ids:
        reasons.append("evidence_missing")
    if not opportunity.falsifier:
        reasons.append("falsifier_missing")
    if opportunity.expectation_posture == "unavailable":
        reasons.append("expectation_posture_unavailable")
    reasons.extend(_degraded_reasons(opportunity))
    reasons.extend(_research_rejections(opportunity))
    return tuple(sorted(set(reasons)))


def _gate(
    opportunity: OpportunityDraft,
    assessments: tuple[PrivateAssessment, ...] | None,
) -> RankingGate:
    pre_assessment = pre_assessment_rejections(opportunity)
    rejected: list[str] = [
        reason
        for reason in pre_assessment
        if reason not in _degraded_reasons(opportunity)
    ]
    degraded: list[str] = list(_degraded_reasons(opportunity))
    rejected.extend(_assessment_rejections(opportunity, assessments))
    if rejected:
        return RankingGate(
            opportunity_id=opportunity.opportunity_id,
            status="rejected",
            reason_codes=tuple(sorted(set(rejected + degraded))),
        )
    if degraded:
        return RankingGate(
            opportunity_id=opportunity.opportunity_id,
            status="degraded",
            reason_codes=tuple(sorted(set(degraded))),
        )
    return RankingGate(opportunity_id=opportunity.opportunity_id, status="ranked")


def _rounded(value: Decimal) -> float:
    bounded = max(Decimal(0), min(Decimal(1), value))
    return float(bounded.quantize(Decimal("0.000000000001"), ROUND_HALF_EVEN))


def _score(
    opportunity: OpportunityDraft,
    assessments: tuple[PrivateAssessment, ...],
    discussion: DiscussionOutcome | None,
    known_at: datetime,
) -> tuple[float, dict[str, float]]:
    locked = validate_private_pair(opportunity, assessments)
    private_probability = sum(
        Decimal(str(item.forecast_probability)) for item in locked
    ) / Decimal(2)
    effective_probability = private_probability
    if discussion is not None:
        if discussion.opportunity_id != opportunity.opportunity_id:
            raise ValueError("discussion outcome targets a different opportunity")
        if discussion.stop_reason == "hard_falsifier":
            effective_probability = Decimal(0)
        elif discussion.final_probabilities:
            effective_probability = sum(
                Decimal(str(value)) for value in discussion.final_probabilities.values()
            ) / Decimal(len(discussion.final_probabilities))
    evidence_quality = sum(
        Decimal(str(item.evidence_quality)) for item in locked
    ) / Decimal(2)
    wedge_quality = sum(
        Decimal(str(item.variant_wedge_quality)) for item in locked
    ) / Decimal(2)
    underwriting = consensus_underwriting(
        (locked[0].underwriting, locked[1].underwriting)
    )
    research_quality = research_quality_components(opportunity.research_diligence)
    decision = consensus_decision((locked[0].underwriting, locked[1].underwriting))
    age_days = max(Decimal(0), Decimal(str((known_at - opportunity.freshness_at).days)))
    decision_horizon = min(opportunity.horizon_days, decision.edge_half_life_days)
    freshness = max(Decimal(0), Decimal(1) - age_days / Decimal(decision_horizon))
    investability = (
        Decimal(1) if opportunity.investability == "ready" else Decimal("0.6")
    )
    expectation = (
        Decimal(1) if opportunity.expectation_posture == "available" else Decimal("0.7")
    )
    disagreement = Decimal(str(assessment_disagreement(locked)))
    decision_readiness = Decimal(1) if decision.status == "ready" else Decimal("0.75")
    base_rate = sum(
        (Decimal(str(value)) for value in decision.base_rate_probability_range),
        Decimal(0),
    ) / Decimal(2)
    inside_view = sum(
        (Decimal(str(value)) for value in decision.inside_view_probability_range),
        Decimal(0),
    ) / Decimal(2)
    independent_probability_lifts = _independent_probability_lifts(locked)
    conservative_probability_lift = min(independent_probability_lifts)
    variant_edge_strength = min(
        Decimal(1), conservative_probability_lift / Decimal("0.25")
    )
    components = {
        "effective_probability": _rounded(effective_probability),
        "evidence_quality": _rounded(evidence_quality),
        "variant_wedge_quality": _rounded(wedge_quality),
        "freshness": _rounded(freshness),
        "investability": _rounded(investability),
        "expectation_posture": _rounded(expectation),
        "private_disagreement": _rounded(disagreement),
        "consensus_expected_alpha_bps": float(
            underwriting["consensus_expected_alpha_bps"].quantize(Decimal("0.01"))
        ),
        "conservative_expected_alpha_bps": float(
            underwriting["conservative_expected_alpha_bps"].quantize(Decimal("0.01"))
        ),
        "forecast_dispersion_bps": float(
            underwriting["forecast_dispersion_bps"].quantize(Decimal("0.01"))
        ),
        "forecast_uncertainty_reserve_bps": float(
            underwriting["forecast_uncertainty_reserve_bps"].quantize(Decimal("0.01"))
        ),
        "uncertainty_adjusted_expected_alpha_bps": float(
            underwriting["uncertainty_adjusted_expected_alpha_bps"].quantize(
                Decimal("0.01")
            )
        ),
        "expected_alpha_score": _rounded(underwriting["expected_alpha_score"]),
        "downside_resilience": _rounded(underwriting["downside_resilience"]),
        "payoff_asymmetry": _rounded(underwriting["payoff_asymmetry"]),
        "catalyst_clarity": _rounded(underwriting["catalyst_clarity"]),
        "crowding_risk": _rounded(underwriting["crowding_risk"]),
        "liquidity_risk": _rounded(underwriting["liquidity_risk"]),
        "scenario_disagreement": _rounded(underwriting["scenario_disagreement"]),
        "decision_readiness": _rounded(decision_readiness),
        "edge_half_life_days": float(decision.edge_half_life_days),
        "base_rate_probability": _rounded(base_rate),
        "inside_view_probability": _rounded(inside_view),
        "variant_probability_lift": float(
            (inside_view - base_rate).quantize(Decimal("0.000000000001"))
        ),
        "conservative_variant_probability_lift": float(
            conservative_probability_lift.quantize(Decimal("0.000000000001"))
        ),
        "variant_edge_strength": _rounded(variant_edge_strength),
        "research_quality": _rounded(research_quality["research_quality"]),
        "research_source_breadth": _rounded(research_quality["source_breadth"]),
        "research_route_diversity": _rounded(research_quality["route_diversity"]),
        "research_non_news_depth": _rounded(research_quality["non_news_depth"]),
    }
    score = (
        variant_edge_strength * Decimal("0.05")
        + evidence_quality * Decimal("0.15")
        + wedge_quality * Decimal("0.15")
        + underwriting["expected_alpha_score"] * Decimal("0.20")
        + underwriting["payoff_asymmetry"] * Decimal("0.10")
        + underwriting["catalyst_clarity"] * Decimal("0.10")
        + underwriting["downside_resilience"] * Decimal("0.05")
        + freshness * Decimal("0.05")
        + investability * Decimal("0.05")
        + decision_readiness * Decimal("0.05")
        + research_quality["research_quality"] * Decimal("0.10")
        - disagreement * Decimal("0.05")
        - underwriting["scenario_disagreement"] * Decimal("0.05")
        - underwriting["crowding_risk"] * Decimal("0.05")
        - underwriting["liquidity_risk"] * Decimal("0.05")
    )
    return _rounded(score), components


def build_ranking_book(
    ranking_run_id: str,
    opportunities: tuple[OpportunityDraft, ...],
    assessments: dict[str, tuple[PrivateAssessment, ...]],
    discussions: dict[str, DiscussionOutcome],
    known_at: datetime,
) -> RankingBook:
    if not 1 <= len(opportunities) <= 20:
        raise ValueError("B4 ranking input must contain 1 to 20 opportunities")
    gates = tuple(
        _gate(opportunity, assessments.get(opportunity.opportunity_id))
        for opportunity in sorted(opportunities, key=lambda item: item.opportunity_id)
    )
    gate_by_id = {item.opportunity_id: item for item in gates}
    scored = []
    for opportunity in opportunities:
        if gate_by_id[opportunity.opportunity_id].status != "ranked":
            continue
        score, components = _score(
            opportunity,
            assessments[opportunity.opportunity_id],
            discussions.get(opportunity.opportunity_id),
            known_at,
        )
        scored.append((opportunity, score, components))
    scored.sort(key=lambda item: (-item[1], item[0].opportunity_id))
    items = tuple(
        RankedItem(
            rank_id="rank_"
            + canonical_hash([ranking_run_id, opportunity.opportunity_id])[:32],
            opportunity_id=opportunity.opportunity_id,
            position=position,
            score=score,
            components=components,
            snapshot_hash=opportunity.snapshot_hash,
        )
        for position, (opportunity, score, components) in enumerate(scored, start=1)
    )
    return RankingBook(
        ranking_run_id=ranking_run_id,
        known_at=known_at,
        items=items,
        gates=gates,
    )
