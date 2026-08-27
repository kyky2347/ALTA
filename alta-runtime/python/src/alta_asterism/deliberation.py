from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .foundry import OpportunityDraft
from .underwriting import ScenarioUnderwriting

ASSESSOR_SEATS = ("thesis_assessor", "disconfirming_assessor")
FORECAST_SCENARIO_TOLERANCE = Decimal("0.25")


def require_consistent_forecast_probability(
    forecast_probability: float,
    underwriting: ScenarioUnderwriting,
) -> None:
    """Keep the headline forecast anchored to its scenario distribution."""
    if (
        abs(
            Decimal(str(forecast_probability)) - underwriting.positive_alpha_probability
        )
        > FORECAST_SCENARIO_TOLERANCE
    ):
        raise ValueError(
            "forecast probability conflicts with the scenario distribution"
        )


class PrivateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_id: str
    opportunity_id: str
    run_id: str
    assessor: Literal["thesis_assessor", "disconfirming_assessor"]
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    forecast_probability: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    variant_wedge_quality: float = Field(ge=0, le=1)
    strongest_support: str = Field(min_length=1, max_length=2_000)
    strongest_disconfirmation: str = Field(min_length=1, max_length=2_000)
    first_rejection: str = Field(min_length=1, max_length=2_000)
    missing_evidence: tuple[str, ...] = Field(default=(), max_length=20)
    recommendation: Literal["research", "wait", "reject", "advance"]
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=4_000)
    underwriting: ScenarioUnderwriting
    locked_at: datetime
    prompt_version: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_lock_and_evidence(self) -> "PrivateAssessment":
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("private assessment locked_at must be timezone-aware")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("private assessment evidence_ids must be unique")
        if not set(self.underwriting.evidence_ids).issubset(self.evidence_ids):
            raise ValueError("scenario underwriting cites evidence outside assessment")
        require_consistent_forecast_probability(
            self.forecast_probability, self.underwriting
        )
        decision = self.underwriting.decision
        if (
            decision is not None
            and self.recommendation == "advance"
            and (
                decision.security_thesis_readiness != "ready"
                or decision.company_thesis_status in ("broken", "impaired")
            )
        ):
            raise ValueError(
                "advance requires a ready security thesis and a viable company thesis"
            )
        return self

    @property
    def verdict(self) -> Literal["advance", "hold", "reject"]:
        if self.recommendation == "advance":
            return "advance"
        if self.recommendation == "reject":
            return "reject"
        return "hold"

    @property
    def score(self) -> float:
        return round(
            (
                self.forecast_probability
                + self.evidence_quality
                + self.variant_wedge_quality
                + self.confidence
            )
            / 4,
            12,
        )


def validate_private_pair(
    opportunity: OpportunityDraft,
    assessments: tuple[PrivateAssessment, ...],
) -> tuple[PrivateAssessment, PrivateAssessment]:
    ordered = tuple(sorted(assessments, key=lambda item: item.assessor))
    if len(ordered) != 2 or {item.assessor for item in ordered} != set(ASSESSOR_SEATS):
        raise ValueError("exactly two independent B4 private assessments are required")
    if any(
        item.opportunity_id != opportunity.opportunity_id
        or item.snapshot_hash != opportunity.snapshot_hash
        or not set(item.evidence_ids).issubset(opportunity.evidence_ids)
        for item in ordered
    ):
        raise ValueError(
            "private assessments must share the frozen opportunity snapshot"
        )
    return ordered


def assessment_disagreement(assessments: tuple[PrivateAssessment, ...]) -> float:
    if len(assessments) != 2:
        raise ValueError("disagreement requires two private assessments")
    return abs(
        assessments[0].forecast_probability - assessments[1].forecast_probability
    )


class DiscussionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top_k: Literal[5] = 5
    max_candidates: Literal[5] = 5
    disagreement_threshold: float = Field(default=0.25, ge=0, le=1)
    max_rounds: int = Field(default=2, ge=1, le=3)
    min_probability_change: float = Field(default=0.05, ge=0, le=1)


class DiscussionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    preliminary_position: int = Field(ge=1, le=20)
    disagreement: float = Field(ge=0, le=1)


def select_discussion_candidates(
    candidates: tuple[DiscussionCandidate, ...], policy: DiscussionPolicy
) -> tuple[str, ...]:
    eligible = tuple(
        item
        for item in candidates
        if item.preliminary_position <= policy.top_k
        or item.disagreement >= policy.disagreement_threshold
    )
    ordered = sorted(
        eligible,
        key=lambda item: (
            item.disagreement < policy.disagreement_threshold,
            -item.disagreement,
            item.preliminary_position,
            item.opportunity_id,
        ),
    )
    return tuple(item.opportunity_id for item in ordered[: policy.max_candidates])


class BeliefUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessor: Literal["thesis_assessor", "disconfirming_assessor"]
    before_probability: float = Field(ge=0, le=1)
    after_probability: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(min_length=1, max_length=2_000)


class DiscussionRound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    round_number: int = Field(ge=1, le=3)
    summary: str = Field(min_length=1, max_length=2_000)
    testable_claims: tuple[str, ...] = Field(default=(), max_length=5)
    belief_updates: tuple[BeliefUpdate, ...] = Field(default=(), max_length=2)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20)
    hard_falsifier_triggered: bool = False
    awaiting_future_fact: bool = False


class DiscussionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    eligible: bool
    rounds: tuple[DiscussionRound, ...]
    stop_reason: Literal[
        "ineligible",
        "no_information_gain",
        "hard_falsifier",
        "awaiting_future_fact",
        "max_rounds",
    ]
    final_probabilities: dict[str, float]


def run_short_discussion(
    opportunity: OpportunityDraft,
    assessments: tuple[PrivateAssessment, ...],
    preliminary_position: int,
    rounds: tuple[DiscussionRound, ...],
    policy: DiscussionPolicy,
) -> DiscussionOutcome:
    locked = validate_private_pair(opportunity, assessments)
    disagreement = assessment_disagreement(locked)
    probabilities = {item.assessor: item.forecast_probability for item in locked}
    if (
        preliminary_position > policy.top_k
        and disagreement < policy.disagreement_threshold
    ):
        return DiscussionOutcome(
            opportunity_id=opportunity.opportunity_id,
            eligible=False,
            rounds=(),
            stop_reason="ineligible",
            final_probabilities=probabilities,
        )

    if not rounds:
        return DiscussionOutcome(
            opportunity_id=opportunity.opportunity_id,
            eligible=True,
            rounds=(),
            stop_reason="no_information_gain",
            final_probabilities=probabilities,
        )

    consumed: list[DiscussionRound] = []
    claims: set[str] = set()
    for expected_round, item in enumerate(rounds[: policy.max_rounds], start=1):
        if item.round_number != expected_round:
            raise ValueError("discussion rounds must be contiguous and start at one")
        referenced = set(item.evidence_ids)
        referenced.update(
            evidence_id
            for update in item.belief_updates
            for evidence_id in update.evidence_ids
        )
        if not referenced.issubset(opportunity.evidence_ids):
            raise ValueError("discussion can only reference frozen evidence")

        new_claims = set(item.testable_claims).difference(claims)
        claims.update(item.testable_claims)
        effective_update = False
        seen_assessors: set[str] = set()
        for update in item.belief_updates:
            if update.assessor in seen_assessors:
                raise ValueError("a discussion round can update each assessor once")
            seen_assessors.add(update.assessor)
            if update.before_probability != probabilities[update.assessor]:
                raise ValueError(
                    "belief update is not anchored to the prior probability"
                )
            material_change = (
                abs(update.after_probability - update.before_probability)
                >= policy.min_probability_change
            )
            if material_change and not update.evidence_ids:
                raise ValueError(
                    "material belief updates require frozen evidence provenance"
                )
            effective_update = effective_update or material_change
            probabilities[update.assessor] = update.after_probability
        consumed.append(item)
        if item.hard_falsifier_triggered:
            return DiscussionOutcome(
                opportunity_id=opportunity.opportunity_id,
                eligible=True,
                rounds=tuple(consumed),
                stop_reason="hard_falsifier",
                final_probabilities=probabilities,
            )
        if item.awaiting_future_fact:
            return DiscussionOutcome(
                opportunity_id=opportunity.opportunity_id,
                eligible=True,
                rounds=tuple(consumed),
                stop_reason="awaiting_future_fact",
                final_probabilities=probabilities,
            )
        if not new_claims and not effective_update:
            return DiscussionOutcome(
                opportunity_id=opportunity.opportunity_id,
                eligible=True,
                rounds=tuple(consumed),
                stop_reason="no_information_gain",
                final_probabilities=probabilities,
            )
    return DiscussionOutcome(
        opportunity_id=opportunity.opportunity_id,
        eligible=True,
        rounds=tuple(consumed),
        stop_reason="max_rounds",
        final_probabilities=probabilities,
    )
