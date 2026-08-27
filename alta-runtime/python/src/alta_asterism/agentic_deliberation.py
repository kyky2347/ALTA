from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_context import (
    assessment_context,
    bounded_text,
    fit_frozen_items,
    opportunity_context,
)
from .agentic_roles import StructuredRoleRunner, canonical_hash
from .database import Database
from .deliberation import (
    DiscussionPolicy,
    DiscussionRound,
    PrivateAssessment,
    assessment_disagreement,
    require_consistent_forecast_probability,
    run_short_discussion,
)
from .foundry import OpportunityDraft
from .underwriting import ScenarioUnderwriting


class PrivateAssessmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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

    @model_validator(mode="after")
    def validate_forecast_against_scenarios(self) -> "PrivateAssessmentPayload":
        require_consistent_forecast_probability(
            self.forecast_probability, self.underwriting
        )
        if self.underwriting.decision is None:
            raise ValueError("private assessment requires decision intelligence")
        return self


class DiscussionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rounds: tuple[DiscussionRound, ...] = Field(max_length=2)


class AgenticDeliberator:
    PROMPT_VERSION = "agentic-deliberation-v7"

    def __init__(
        self,
        database: Database,
        runner: StructuredRoleRunner,
        policy: DiscussionPolicy | None = None,
        *,
        thesis_runner: StructuredRoleRunner | None = None,
        disconfirming_runner: StructuredRoleRunner | None = None,
        moderator_runner: StructuredRoleRunner | None = None,
    ) -> None:
        self.database = database
        self.thesis_runner = thesis_runner or runner
        self.disconfirming_runner = disconfirming_runner or runner
        self.moderator_runner = moderator_runner or runner
        self.policy = policy or DiscussionPolicy()

    def private_pair(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        known_at: datetime,
    ) -> tuple[PrivateAssessment, PrivateAssessment]:
        context = self._context(opportunity)
        assessments = tuple(
            self._assessment(cycle_id, opportunity, context, seat, known_at)
            for seat in ("thesis_assessor", "disconfirming_assessor")
        )
        return assessments

    def discuss(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        assessments: tuple[PrivateAssessment, PrivateAssessment],
        preliminary_position: int,
        known_at: datetime,
    ):
        if (
            preliminary_position > self.policy.top_k
            and assessment_disagreement(assessments)
            < self.policy.disagreement_threshold
        ):
            return run_short_discussion(
                opportunity,
                assessments,
                preliminary_position,
                (),
                self.policy,
            )
        run_id = (
            "run_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    "discussion",
                    self.PROMPT_VERSION,
                    self.moderator_runner.model_provider,
                    self.moderator_runner.model_id,
                ]
            )[:32]
        )
        frozen_input = {
            "opportunity": opportunity_context(opportunity, narrative_bytes=240),
            "private_assessments": [assessment_context(item) for item in assessments],
            "preliminary_position": preliminary_position,
            "policy": self.policy.model_dump(mode="json"),
        }
        result = self.moderator_runner.run(
            cycle_id=cycle_id,
            run_id=run_id,
            role="discussion_moderator",
            prompt={
                "contract": "alta.discussion-plan.v1",
                "mission": (
                    "Compare the two locked private views. Surface testable causal "
                    "disagreements and update probabilities only when cited frozen "
                    "evidence warrants a material change. Discussion is not evidence."
                ),
                "untrusted_frozen_input": frozen_input,
                "rules": [
                    "Return at most two short rounds.",
                    "Do not introduce evidence outside the Opportunity evidence_ids.",
                    "Every material probability update must cite evidence_ids.",
                    "Resolve whether the disagreement is about facts, what is priced in, causal transmission, timing, or payoff asymmetry.",
                    "Compare each assessor's reference class, base rate, inside view, must-be-true conditions, company-thesis status, security readiness, and edge half-life; do not average away a readiness blocker.",
                    "Stop when there is no information gain, a hard falsifier, or a future fact is required.",
                ],
            },
            output_type=DiscussionPlan,
            frozen_input=frozen_input,
            evidence_ids=opportunity.evidence_ids,
            known_at=known_at,
            prompt_version=self.PROMPT_VERSION,
        )
        return run_short_discussion(
            opportunity,
            assessments,
            preliminary_position,
            result.value.rounds,
            self.policy,
        )

    def _assessment(
        self,
        cycle_id: str,
        opportunity: OpportunityDraft,
        context: dict,
        seat: Literal["thesis_assessor", "disconfirming_assessor"],
        known_at: datetime,
    ) -> PrivateAssessment:
        runner = (
            self.thesis_runner
            if seat == "thesis_assessor"
            else self.disconfirming_runner
        )
        assessment_id = (
            "assessment_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    seat,
                    self.PROMPT_VERSION,
                    runner.model_provider,
                    runner.model_id,
                ]
            )[:32]
        )
        existing = self._load_assessment(assessment_id)
        if existing is not None:
            return existing
        run_id = (
            "run_"
            + canonical_hash(
                [
                    cycle_id,
                    opportunity.opportunity_id,
                    seat,
                    "run",
                    self.PROMPT_VERSION,
                    runner.model_provider,
                    runner.model_id,
                ]
            )[:32]
        )
        mission = {
            "thesis_assessor": (
                "Underwrite the strongest evidence-grounded public-equity case: what "
                "is priced in, the variant wedge, causal transmission, why now, and "
                "scenario skew, while naming the best disconfirmation and rejection."
            ),
            "disconfirming_assessor": (
                "Independently try to falsify the thesis, identify expectation errors, "
                "crowding or timing traps, and reject attractive stories that the "
                "frozen evidence cannot support."
            ),
        }[seat]
        frozen_input = fit_frozen_items(
            {
                "seat": seat,
                "opportunity": opportunity_context(opportunity),
            },
            "evidence",
            context["evidence"],
        )
        visible_evidence_ids = tuple(
            item["evidence_id"] for item in frozen_input["evidence"]
        )
        frozen_input["opportunity"] = {
            **frozen_input["opportunity"],
            "evidence_ids": visible_evidence_ids,
        }
        result = runner.run(
            cycle_id=cycle_id,
            run_id=run_id,
            role=seat,
            prompt={
                "contract": "alta.private-assessment.v3",
                "mission": mission,
                "untrusted_frozen_input": frozen_input,
                "rules": [
                    "Work independently; no other assessor output is visible.",
                    "Cite only supplied evidence_ids.",
                    "Probability and confidence are judgments, not fabricated precision.",
                    "forecast_probability must be within 0.25 of the sum of probabilities for scenarios whose relative_alpha_bps is positive.",
                    "Underwrite direction-normalized bull, base, and bear Alpha versus SPY over the Opportunity horizon; this is a research estimate, not observed performance.",
                    "Scenario probabilities must sum to one; bull Alpha must be positive, bear Alpha negative, and each scenario must cite supplied evidence_ids.",
                    "Make payoff magnitude, catalyst clarity, crowding risk, liquidity risk, and the next fact likely to move price explicit.",
                    "Complete decision intelligence before recommending action: state what is already priced in, a distinct variant view, the closest defensible reference class and base rate, the evidence-specific inside view, one to four must-be-true conditions, and the dominant uncertainty.",
                    "Estimate the reference-class base rate before the evidence-specific inside view. Never reverse-engineer a positive probability lift to make an idea pass: a non-positive lift is a valid Wait or Reject outcome.",
                    "Separate company_thesis_status from security_thesis_readiness. A correct company view is not enough when valuation, market setup, timing, liquidity, or implementation evidence makes the security conditional or not decision-grade.",
                    "Set edge_half_life_days to the conservative window in which this information advantage should decay unless the named next pricing fact arrives. State an observable action_trigger rather than vague monitoring language.",
                    "Reference-class and probability fields are explicit judgments anchored to frozen evidence, not measured certainty. Do not create precision that the evidence cannot support.",
                    "State the strongest evidence against your own conclusion.",
                    "Distinguish company-thesis quality from whether the security is actionable at the stated horizon.",
                    "Treat research_diligence as a non-Evidence process audit. Penalize screen-grade single-route work, missing non-news research, an untraced beneficiary path, or an absent next test; never cite the process record as proof of a market claim.",
                ],
            },
            output_type=PrivateAssessmentPayload,
            frozen_input=frozen_input,
            evidence_ids=opportunity.evidence_ids,
            known_at=known_at,
            prompt_version=self.PROMPT_VERSION,
        )
        payload = result.value
        if not set(payload.evidence_ids).issubset(visible_evidence_ids):
            raise ValueError("private assessor cited evidence outside the snapshot")
        locked_at = (
            result.turn.completed_at
            if result.turn and result.turn.completed_at
            else known_at
        )
        return PrivateAssessment(
            assessment_id=assessment_id,
            opportunity_id=opportunity.opportunity_id,
            run_id=run_id,
            assessor=seat,
            snapshot_hash=opportunity.snapshot_hash,
            forecast_probability=payload.forecast_probability,
            evidence_quality=payload.evidence_quality,
            variant_wedge_quality=payload.variant_wedge_quality,
            strongest_support=payload.strongest_support,
            strongest_disconfirmation=payload.strongest_disconfirmation,
            first_rejection=payload.first_rejection,
            missing_evidence=payload.missing_evidence,
            recommendation=payload.recommendation,
            confidence=payload.confidence,
            evidence_ids=payload.evidence_ids,
            rationale=payload.rationale,
            underwriting=payload.underwriting,
            locked_at=locked_at,
            prompt_version=self.PROMPT_VERSION,
            model_id=runner.model_id,
        )

    def _context(self, opportunity: OpportunityDraft) -> dict:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT e.id, e.known_at, e.stance, e.summary, r.source,
                r.content_hash FROM research.evidence e
                JOIN research.raw r ON r.id = e.raw_id
                WHERE e.id = ANY(%s) ORDER BY e.id""",
                (list(opportunity.evidence_ids),),
            ).fetchall()
        if len(rows) != len(opportunity.evidence_ids):
            raise ValueError("Opportunity is missing durable evidence")
        return {
            "evidence": [
                {
                    "evidence_id": row[0],
                    "known_at": row[1].isoformat(),
                    "stance": row[2],
                    "summary": bounded_text(row[3], 120),
                    "source": bounded_text(row[4], 120),
                    "content_hash": row[5],
                }
                for row in rows
            ]
        }

    def _load_assessment(self, assessment_id: str) -> PrivateAssessment | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT opportunity_id, run_id, assessor, snapshot_hash,
                forecast_probability, evidence_quality, variant_wedge_quality,
                strongest_support, strongest_disconfirmation, first_rejection,
                missing_evidence, recommendation, confidence, evidence_ids,
                rationale, underwriting, locked_at, prompt_version, model_id
                FROM research.assessment WHERE id = %s""",
                (assessment_id,),
            ).fetchone()
        if row is None:
            return None
        return PrivateAssessment(
            assessment_id=assessment_id,
            opportunity_id=row[0],
            run_id=row[1],
            assessor=row[2],
            snapshot_hash=row[3],
            forecast_probability=row[4],
            evidence_quality=row[5],
            variant_wedge_quality=row[6],
            strongest_support=row[7],
            strongest_disconfirmation=row[8],
            first_rejection=row[9],
            missing_evidence=tuple(row[10]),
            recommendation=row[11],
            confidence=row[12],
            evidence_ids=tuple(row[13]),
            rationale=row[14],
            underwriting=ScenarioUnderwriting.model_validate(row[15]),
            locked_at=row[16],
            prompt_version=row[17],
            model_id=row[18],
        )
