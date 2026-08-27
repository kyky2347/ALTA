from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from .agentic_deliberation import AgenticDeliberator
from .agentic_roles import StructuredRoleUnavailable
from .agentic_roles import StructuredRoleRunner
from .b4_runtime import DeliberationRepository, FoundryRepository
from .contracts import Environment
from .database import Database
from .deliberation import (
    DiscussionPolicy,
    DiscussionRound,
    PrivateAssessment,
    run_short_discussion,
)
from .expression import contract_hash
from .foundry import CandidateDraft, OpportunityDraft, deduplicate
from .mind_worker import MindClient
from .opportunity_registry import OpportunityRegistry
from .ranking import RankingBook, build_ranking_book
from .ranking_store import RankingRepository
from .research_diligence import ResearchDiligence
from .scout_batch import MindWorker
from .scout_repository import ScoutRepository
from .scouts import CandidateOutput, FrozenScoutInput, RunBudget
from .underwriting import DecisionIntelligence, ScenarioCase, ScenarioUnderwriting


@dataclass(frozen=True)
class ResearchRuntimeConfig:
    model_provider: str = "fixture"
    model_id: str = "fixture-model"
    max_tool_calls: int = 3
    max_total_tokens: int = 1_000
    max_output_bytes: int = 8_192
    deadline_seconds: float = 5
    max_concurrency: int = 1
    use_wall_clock: bool = False
    require_active_research: bool = False


class MvpResearchFlow:
    def __init__(
        self,
        database: Database,
        mind_client: MindClient,
        config: ResearchRuntimeConfig | None = None,
        role_runner: StructuredRoleRunner | None = None,
        deliberator: AgenticDeliberator | None = None,
    ) -> None:
        self.database = database
        self.mind_client = mind_client
        self.config = config or ResearchRuntimeConfig()
        self.agentic_deliberator = deliberator or (
            AgenticDeliberator(database, role_runner) if role_runner else None
        )

    def run_scouts(self, demo_id: str, frozen_input: FrozenScoutInput):
        worker = MindWorker(
            repository=ScoutRepository(self.database),
            client=self.mind_client,
            model_provider=self.config.model_provider,
            model_id=self.config.model_id,
            budget=RunBudget(
                max_tool_calls=self.config.max_tool_calls,
                max_total_tokens=self.config.max_total_tokens,
                max_output_bytes=self.config.max_output_bytes,
                require_active_research=self.config.require_active_research,
            ),
            deadline_seconds=self.config.deadline_seconds,
            max_concurrency=self.config.max_concurrency,
            clock=(
                lambda: datetime.now(UTC)
                if self.config.use_wall_clock
                else frozen_input.known_at
            ),
        )
        return worker.run_batch(f"batch_{demo_id}", frozen_input)

    def materialize_candidates(
        self, demo_id: str, outcomes, wake_at: datetime
    ) -> tuple[tuple[CandidateDraft, ...], tuple[OpportunityDraft, ...]]:
        candidates = self._candidate_drafts(outcomes, wake_at)
        if not candidates:
            return (), ()
        result = deduplicate(demo_id, candidates)
        FoundryRepository(self.database).materialize(result, candidates)
        opportunities = OpportunityRegistry(self.database).resolve(
            demo_id, result.opportunities
        )
        return candidates, opportunities

    def assess_and_debate(
        self,
        demo_id: str,
        opportunities: tuple[OpportunityDraft, ...],
        wake_at: datetime,
    ):
        repository = DeliberationRepository(self.database)
        assessments = {}
        discussions = {}
        for preliminary_position, opportunity in enumerate(
            sorted(opportunities, key=lambda item: item.opportunity_id), start=1
        ):
            try:
                pair = (
                    self.agentic_deliberator.private_pair(
                        demo_id, opportunity, self._stage_time(wake_at, 8)
                    )
                    if self.agentic_deliberator
                    else self._private_pair(demo_id, opportunity, wake_at)
                )
            except StructuredRoleUnavailable:
                # Ranking will durably reject an Opportunity without two valid,
                # independent assessments. One model failure must not stop 24x7.
                continue
            for item in pair:
                if self.agentic_deliberator is None:
                    self._ensure_assessment_run(opportunity, item, wake_at)
                repository.lock_private_assessment(opportunity, item)
            repository.share_private_assessments(
                opportunity, self._stage_time(wake_at, 9)
            )
            try:
                discussion = (
                    self.agentic_deliberator.discuss(
                        demo_id,
                        opportunity,
                        pair,
                        preliminary_position,
                        self._stage_time(wake_at, 10),
                    )
                    if self.agentic_deliberator
                    else run_short_discussion(
                        opportunity,
                        pair,
                        preliminary_position=preliminary_position,
                        rounds=(
                            DiscussionRound(
                                round_number=1,
                                summary=(
                                    "No new fixture evidence; stop without inventing evidence."
                                ),
                                evidence_ids=opportunity.evidence_ids,
                            ),
                        ),
                        policy=DiscussionPolicy(),
                    )
                )
            except StructuredRoleUnavailable:
                # Missing moderated debate is insufficient independent review.
                # Leave this Opportunity out of the rankable assessment map.
                continue
            repository.record_discussion(
                opportunity, discussion, self._stage_time(wake_at, 10)
            )
            assessments[opportunity.opportunity_id] = pair
            discussions[opportunity.opportunity_id] = discussion
        return assessments, discussions

    def rank(
        self,
        demo_id: str,
        opportunities: tuple[OpportunityDraft, ...],
        assessments,
        discussions,
        wake_at: datetime,
    ) -> RankingBook:
        book = build_ranking_book(
            f"ranking_{contract_hash([demo_id, 'opportunity_1_90d'])[:32]}",
            opportunities,
            assessments,
            discussions,
            self._stage_time(wake_at, 12),
        )
        RankingRepository(self.database).persist(book, opportunities)
        return book

    def _stage_time(self, wake_at: datetime, offset_seconds: int) -> datetime:
        if self.config.use_wall_clock:
            return datetime.now(UTC)
        return wake_at + timedelta(seconds=offset_seconds)

    def _candidate_drafts(self, outcomes, wake_at: datetime):
        drafts = []
        with self.database.connect() as connection:
            for outcome in outcomes:
                if not isinstance(outcome.output, CandidateOutput):
                    continue
                row = connection.execute(
                    """SELECT c.id, c.version, c.known_at, r.frozen_input,
                    a.content->'research_diligence'
                    FROM research.candidate c JOIN research.run r ON r.id = c.run_id
                    JOIN research.run_artifact a ON a.run_id = r.id
                      AND a.artifact_kind = 'scout_output'
                    WHERE c.run_id = %s""",
                    (outcome.run_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("successful Scout Candidate was not persisted")
                output = outcome.output
                drafts.append(
                    CandidateDraft(
                        candidate_id=row[0],
                        research_mode=output.research_mode,
                        parent_opportunity_id=output.parent_opportunity_id,
                        research_question=output.research_question,
                        environment=Environment.SHADOW,
                        version=row[1],
                        known_at=row[2],
                        title=output.title,
                        alpha_archetype=output.alpha_archetype,
                        entity_key=(
                            output.entity_key or f"{outcome.scout_id}-{row[0]}"
                        ),
                        event_key=output.event_key or f"event-{outcome.scout_id}",
                        catalyst_key=(
                            output.catalyst_key or f"catalyst-{outcome.scout_id}"
                        ),
                        observed_change=output.observed_change or output.why_now,
                        mechanism=output.mechanism or output.variant_wedge,
                        direction=output.direction or "positive",
                        expectation=output.expectation,
                        expectation_posture=row[3]["input"]["expectation_posture"],
                        variant_wedge=output.variant_wedge,
                        why_now=output.why_now,
                        falsifier=output.falsifier,
                        first_rejection=(output.first_rejection or output.falsifier),
                        prediction=output.prediction or output.expectation,
                        investability=output.investability or "ready",
                        freshness_at=(
                            output.freshness_at
                            or min(wake_at - timedelta(minutes=1), row[2])
                        ),
                        horizon_days=output.horizon,
                        confidence=output.confidence,
                        evidence_ids=output.evidence_ids,
                        beneficiary_path=output.beneficiary_path,
                        disconfirming_evidence=output.disconfirming_evidence,
                        next_test=output.next_test,
                        thesis_pillars=output.thesis_pillars,
                        research_diligence=(
                            ResearchDiligence.model_validate(row[4])
                            if row[4] is not None
                            else None
                        ),
                    )
                )
        return tuple(drafts)

    @staticmethod
    def _private_pair(
        demo_id: str, opportunity: OpportunityDraft, wake_at: datetime
    ) -> tuple[PrivateAssessment, PrivateAssessment]:
        values = (
            ("thesis_assessor", 0.74, 0.80, 0.76, "advance", 0.72),
            ("disconfirming_assessor", 0.65, 0.70, 0.64, "wait", 0.66),
        )
        return tuple(
            PrivateAssessment(
                assessment_id="assessment_"
                + contract_hash([demo_id, opportunity.opportunity_id, seat])[:32],
                opportunity_id=opportunity.opportunity_id,
                run_id="run_"
                + contract_hash([demo_id, opportunity.opportunity_id, seat, "run"])[
                    :32
                ],
                assessor=seat,
                snapshot_hash=opportunity.snapshot_hash,
                forecast_probability=probability,
                evidence_quality=evidence_quality,
                variant_wedge_quality=wedge_quality,
                strongest_support="Frozen fixture evidence supports the mechanism.",
                strongest_disconfirmation=("The next measure may fail the threshold."),
                first_rejection=(
                    opportunity.first_rejection or opportunity.falsifier or "Reject."
                ),
                missing_evidence=("next versioned update",),
                recommendation=recommendation,
                confidence=confidence,
                evidence_ids=opportunity.evidence_ids,
                rationale="Independent deterministic fixture assessment.",
                underwriting=ScenarioUnderwriting(
                    bull=ScenarioCase(
                        probability=0.2,
                        relative_alpha_bps=700,
                        trigger="The frozen catalyst propagates faster than expected.",
                        evidence_ids=opportunity.evidence_ids,
                    ),
                    base=ScenarioCase(
                        probability=round(probability - 0.2, 2),
                        relative_alpha_bps=180,
                        trigger="The frozen mechanism partially reaches the prediction.",
                        evidence_ids=opportunity.evidence_ids,
                    ),
                    bear=ScenarioCase(
                        probability=round(1 - probability, 2),
                        relative_alpha_bps=-500,
                        trigger="The next update confirms the frozen rejection condition.",
                        evidence_ids=opportunity.evidence_ids,
                    ),
                    catalyst_clarity=0.7,
                    crowding_risk=0.3,
                    liquidity_risk=0.2,
                    next_pricing_fact="The next versioned primary update.",
                    decision=DecisionIntelligence(
                        what_is_priced_in=opportunity.expectation,
                        variant_view=opportunity.variant_wedge,
                        reference_class="Comparable expectation-revision events.",
                        base_rate_probability=0.5,
                        inside_view_probability=probability,
                        must_be_true=(
                            opportunity.prediction or opportunity.variant_wedge,
                        ),
                        company_thesis_status=(
                            "intact" if seat == "thesis_assessor" else "watch"
                        ),
                        security_thesis_readiness=(
                            "ready" if seat == "thesis_assessor" else "conditional"
                        ),
                        edge_half_life_days=min(opportunity.horizon_days, 30),
                        dominant_uncertainty=(
                            opportunity.disconfirming_evidence
                            or "The next observation may not confirm the mechanism."
                        ),
                        action_trigger=(
                            opportunity.next_test
                            or "Re-underwrite at the next versioned primary update."
                        ),
                    ),
                ),
                locked_at=wake_at + timedelta(seconds=8),
                prompt_version="b6-private-fixture-v1",
                model_id="deterministic-fixture",
            )
            for (
                seat,
                probability,
                evidence_quality,
                wedge_quality,
                recommendation,
                confidence,
            ) in values
        )

    def _ensure_assessment_run(
        self,
        opportunity: OpportunityDraft,
        assessment: PrivateAssessment,
        wake_at: datetime,
    ) -> None:
        frozen = {
            "opportunity_id": opportunity.opportunity_id,
            "snapshot_hash": opportunity.snapshot_hash,
            "assessor": assessment.assessor,
        }
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO research.run
                (id, environment, version, known_at, role, status, input_hash,
                 frozen_input, budget, deadline_at, prompt_version,
                 tool_catalog_version, model_provider, model_id, trace_id,
                 tool_provenance, evidence_ids, output_kind)
                VALUES (%s,'shadow',1,%s,%s,'succeeded',%s,%s,%s,%s,
                        'b6-private-fixture-v1','none','deterministic','fixture',
                        %s,'[]'::jsonb,%s,'no_op')
                ON CONFLICT (id) DO NOTHING""",
                (
                    assessment.run_id,
                    wake_at + timedelta(seconds=8),
                    assessment.assessor,
                    contract_hash(frozen),
                    Jsonb(frozen),
                    Jsonb({"external_calls": 0}),
                    wake_at + timedelta(seconds=9),
                    f"trace_{assessment.run_id[4:]}",
                    list(opportunity.evidence_ids),
                ),
            )
