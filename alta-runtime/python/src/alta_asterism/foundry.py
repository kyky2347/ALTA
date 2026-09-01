from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import Environment
from .investment_thesis import (
    MAX_THESIS_PILLARS,
    ThesisPillar,
    ThesisPillarDraft,
    materialize_pillar,
)
from .opportunity_identity import (
    canonical_hash,
    exact_identity_key,
    normalize_key,
    structural_identity_key,
)
from .research_diligence import ResearchDiligence
from .research_agenda import ResearchMode

Direction = Literal["positive", "negative", "neutral"]
ExpectationPosture = Literal["available", "proxy_only", "unavailable"]
RelationKind = Literal["duplicate", "merge", "related", "competing"]

COMPLETENESS_FIELDS = (
    "observed_change",
    "mechanism",
    "expectation",
    "variant_wedge",
    "why_now",
    "falsifier",
    "first_rejection",
    "prediction",
    "investability",
    "freshness_at",
)
COMPLETION_FIELDS = (
    "entity_key",
    "event_key",
    "catalyst_key",
    "observed_change",
    "mechanism",
    "direction",
    "expectation",
    "expectation_posture",
    "variant_wedge",
    "why_now",
    "falsifier",
    "first_rejection",
    "prediction",
    "investability",
    "freshness_at",
)


class CandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=3, max_length=128)
    research_mode: ResearchMode = "explore"
    parent_opportunity_id: str | None = Field(
        default=None, min_length=3, max_length=128
    )
    research_question: str | None = Field(default=None, min_length=3, max_length=160)
    environment: Environment
    version: int = Field(ge=1)
    known_at: datetime
    title: str = Field(min_length=1, max_length=256)
    alpha_archetype: str = Field(
        default="legacy_unclassified", min_length=3, max_length=96
    )
    entity_key: str | None = Field(default=None, max_length=128)
    event_key: str | None = Field(default=None, max_length=128)
    catalyst_key: str | None = Field(default=None, max_length=128)
    observed_change: str | None = Field(default=None, max_length=2_000)
    mechanism: str | None = Field(default=None, max_length=2_000)
    direction: Direction | None = None
    expectation: str | None = Field(default=None, max_length=2_000)
    expectation_posture: ExpectationPosture = "unavailable"
    variant_wedge: str | None = Field(default=None, max_length=2_000)
    why_now: str | None = Field(default=None, max_length=2_000)
    falsifier: str | None = Field(default=None, max_length=2_000)
    first_rejection: str | None = Field(default=None, max_length=2_000)
    prediction: str | None = Field(default=None, max_length=2_000)
    investability: Literal["ready", "limited", "unknown"] | None = None
    freshness_at: datetime | None = None
    horizon_days: int = Field(ge=1, le=365)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    beneficiary_path: str | None = Field(default=None, max_length=2_000)
    disconfirming_evidence: str | None = Field(default=None, max_length=2_000)
    next_test: str | None = Field(default=None, max_length=2_000)
    thesis_pillars: tuple[ThesisPillarDraft, ...] = Field(default=(), max_length=3)
    research_diligence: ResearchDiligence | None = None
    completion_provenance: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_point_in_time_and_evidence(self) -> "CandidateDraft":
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("candidate known_at must be timezone-aware")
        if self.freshness_at is not None:
            if (
                self.freshness_at.tzinfo is None
                or self.freshness_at.utcoffset() is None
            ):
                raise ValueError("freshness_at must be timezone-aware")
            if self.freshness_at > self.known_at:
                raise ValueError("freshness_at cannot exceed candidate known_at")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("candidate evidence_ids must be unique")
        if self.research_mode == "follow_up" and (
            self.parent_opportunity_id is None or self.research_question is None
        ):
            raise ValueError(
                "follow_up candidate requires parent Opportunity and research question"
            )
        if self.research_mode == "explore" and (
            self.parent_opportunity_id is not None or self.research_question is not None
        ):
            raise ValueError("explore candidate cannot claim follow-up lineage")
        for field in ("entity_key", "event_key", "catalyst_key", "mechanism"):
            value = getattr(self, field)
            if value is not None and not normalize_key(value):
                raise ValueError(f"{field} must contain a normalized identity token")
        evidence = set(self.evidence_ids)
        if any(
            field not in COMPLETION_FIELDS or not set(ids).issubset(evidence)
            for field, ids in self.completion_provenance.items()
        ):
            raise ValueError(
                "completion provenance must cite frozen candidate evidence"
            )
        if any(
            item.expected_by_days > self.horizon_days for item in self.thesis_pillars
        ):
            raise ValueError("thesis pillar cannot resolve after Candidate horizon")
        return self

    def exact_key(self) -> str | None:
        return exact_identity_key(
            self.entity_key,
            self.event_key,
            self.direction,
            self.horizon_days,
        )

    def structural_key(self) -> str | None:
        return structural_identity_key(
            self.entity_key,
            self.catalyst_key,
            self.direction,
            self.horizon_days,
        )

    def missing_fields(self) -> tuple[str, ...]:
        return tuple(
            field for field in COMPLETENESS_FIELDS if getattr(self, field) in (None, "")
        )


class CompletionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    entity_key: str | None = None
    event_key: str | None = None
    catalyst_key: str | None = None
    observed_change: str | None = None
    mechanism: str | None = None
    direction: Direction | None = None
    expectation: str | None = None
    expectation_posture: ExpectationPosture | None = None
    variant_wedge: str | None = None
    why_now: str | None = None
    falsifier: str | None = None
    first_rejection: str | None = None
    prediction: str | None = None
    investability: Literal["ready", "limited", "unknown"] | None = None
    freshness_at: datetime | None = None
    provenance_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)


def apply_completion(
    candidate: CandidateDraft, patch: CompletionPatch
) -> CandidateDraft:
    if patch.candidate_id != candidate.candidate_id:
        raise ValueError("completion patch targets a different candidate")
    if not set(patch.provenance_evidence_ids).issubset(candidate.evidence_ids):
        raise ValueError("completion patch cites evidence outside the frozen candidate")
    updates: dict[str, Any] = {}
    provenance = dict(candidate.completion_provenance)
    for field in COMPLETION_FIELDS:
        value = getattr(patch, field)
        if value is None:
            continue
        current = getattr(candidate, field)
        is_missing = current in (None, "") or (
            field == "expectation_posture" and current == "unavailable"
        )
        if not is_missing and current != value:
            raise ValueError("completion cannot overwrite a frozen candidate field")
        if is_missing:
            updates[field] = value
            provenance[field] = patch.provenance_evidence_ids
    updates["completion_provenance"] = provenance
    completed = candidate.model_dump()
    completed.update(updates)
    return CandidateDraft.model_validate(completed)


class FoundryRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str
    left_candidate_id: str
    right_candidate_id: str
    kind: RelationKind
    rule: str
    reversible: Literal[True] = True


class OpportunityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    candidate_id: str
    member_candidate_ids: tuple[str, ...]
    research_mode: ResearchMode = "explore"
    parent_opportunity_id: str | None = None
    research_question: str | None = None
    environment: Environment
    version: int
    known_at: datetime
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    exact_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    structural_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str
    thesis: str
    entity_key: str | None
    event_key: str | None
    catalyst_key: str | None
    observed_change: str | None
    mechanism: str | None
    direction: Direction | None
    expectation: str | None
    expectation_posture: ExpectationPosture
    variant_wedge: str | None
    why_now: str | None
    falsifier: str | None
    first_rejection: str | None
    prediction: str | None
    investability: Literal["ready", "limited", "unknown"] | None
    freshness_at: datetime | None
    horizon_days: int
    confidence: float
    evidence_ids: tuple[str, ...]
    audit_evidence_ids: tuple[str, ...] = Field(default=(), max_length=400)
    completeness: Literal["complete", "enriching"]
    beneficiary_path: str | None = None
    disconfirming_evidence: str | None = None
    next_test: str | None = None
    thesis_pillars: tuple[ThesisPillar, ...] = Field(
        default=(), max_length=MAX_THESIS_PILLARS
    )
    research_diligence: ResearchDiligence | None = None

    def missing_fields(self) -> tuple[str, ...]:
        return tuple(
            field for field in COMPLETENESS_FIELDS if getattr(self, field) in (None, "")
        )


class DedupResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: str
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    opportunities: tuple[OpportunityDraft, ...]
    relations: tuple[FoundryRelation, ...]


def _relation(left: CandidateDraft, right: CandidateDraft) -> tuple[str, str] | None:
    left_exact = left.exact_key()
    right_exact = right.exact_key()
    if left_exact is not None and left_exact == right_exact:
        return "duplicate", "exact_identity_v2"
    left_structural = left.structural_key()
    right_structural = right.structural_key()
    if left_structural is not None and left_structural == right_structural:
        return "merge", "structural_identity_v2"
    same_entity = bool(
        left.entity_key
        and right.entity_key
        and normalize_key(left.entity_key) == normalize_key(right.entity_key)
    )
    same_event = bool(
        left.event_key
        and right.event_key
        and normalize_key(left.event_key) == normalize_key(right.event_key)
    )
    if same_entity and same_event and left.direction != right.direction:
        return "competing", "opposite_direction_guard_v1"
    if same_event or (
        same_entity
        and left.mechanism
        and right.mechanism
        and normalize_key(left.mechanism) == normalize_key(right.mechanism)
    ):
        return "related", "shared_event_or_mechanism_v1"
    return None


def deduplicate(batch_id: str, candidates: tuple[CandidateDraft, ...]) -> DedupResult:
    if not 1 <= len(candidates) <= 20:
        raise ValueError("B4 Foundry batch must contain 1 to 20 candidates")
    ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if len({item.candidate_id for item in ordered}) != len(ordered):
        raise ValueError("Foundry candidate IDs must be unique")
    if len({item.environment for item in ordered}) != 1:
        raise ValueError("Foundry candidates cannot cross environments")

    parent = {item.candidate_id: item.candidate_id for item in ordered}

    def root(candidate_id: str) -> str:
        while parent[candidate_id] != candidate_id:
            parent[candidate_id] = parent[parent[candidate_id]]
            candidate_id = parent[candidate_id]
        return candidate_id

    def union(left_id: str, right_id: str) -> None:
        left_root = root(left_id)
        right_root = root(right_id)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    relations: list[FoundryRelation] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            match = _relation(left, right)
            if match is None:
                continue
            kind, rule = match
            relation_id = (
                "relation_"
                + canonical_hash(
                    [batch_id, left.candidate_id, right.candidate_id, kind, rule]
                )[:32]
            )
            relations.append(
                FoundryRelation(
                    relation_id=relation_id,
                    left_candidate_id=left.candidate_id,
                    right_candidate_id=right.candidate_id,
                    kind=kind,
                    rule=rule,
                )
            )
            if kind in {"duplicate", "merge"}:
                union(left.candidate_id, right.candidate_id)

    groups: dict[str, list[CandidateDraft]] = {}
    for item in ordered:
        groups.setdefault(root(item.candidate_id), []).append(item)

    opportunities = tuple(
        _opportunity_from_group(batch_id, tuple(group))
        for _, group in sorted(groups.items())
    )
    snapshot_hash = canonical_hash([item.model_dump(mode="json") for item in ordered])
    return DedupResult(
        batch_id=batch_id,
        snapshot_hash=snapshot_hash,
        opportunities=opportunities,
        relations=tuple(relations),
    )


def _opportunity_from_group(
    batch_id: str, members: tuple[CandidateDraft, ...]
) -> OpportunityDraft:
    ordered = tuple(sorted(members, key=lambda item: item.candidate_id))
    identity_anchor = ordered[0]
    follow_ups = tuple(item for item in ordered if item.research_mode == "follow_up")
    lineage = (
        max(
            follow_ups,
            key=lambda item: (item.known_at, item.version, item.candidate_id),
        )
        if follow_ups
        else identity_anchor
    )
    # A merged Opportunity must remain one coherent claim bundle.  Choosing
    # fields independently across Candidates can synthesize a thesis no Trader
    # Mind actually proposed and for which no single evidence lineage exists.
    # A follow-up owns the refreshed claim; otherwise the deterministic identity
    # anchor owns it.  Other members remain frozen contributors for audit and
    # duplicate/competing analysis, never silent co-authors of the main claim.
    claim_anchor = lineage

    member_ids = tuple(item.candidate_id for item in ordered)
    audit_evidence_ids = tuple(
        dict.fromkeys(
            evidence_id for item in ordered for evidence_id in item.evidence_ids
        )
    )
    evidence_ids = claim_anchor.evidence_ids
    # Decision inputs must remain bound to the selected claim. Contributor
    # evidence is retained separately for Foundry/group audit and may not boost
    # the claim's pillars, diligence score, assessment, ranking, or expression.
    frozen_pillars = materialized_thesis_pillars((claim_anchor,))
    observed_change = claim_anchor.observed_change
    mechanism = claim_anchor.mechanism
    variant_wedge = claim_anchor.variant_wedge
    thesis_parts = [observed_change, mechanism, variant_wedge]
    thesis = " | ".join(part for part in thesis_parts if part) or claim_anchor.title
    exact_key = identity_anchor.exact_key() or canonical_hash(
        [batch_id, member_ids, "exact"]
    )
    structural_key = identity_anchor.structural_key() or canonical_hash(
        [batch_id, member_ids, "structural"]
    )
    values = {field: getattr(claim_anchor, field) for field in COMPLETENESS_FIELDS}
    completeness = (
        "complete"
        if all(values[field] not in (None, "") for field in COMPLETENESS_FIELDS)
        else "enriching"
    )
    return OpportunityDraft(
        opportunity_id=(
            "opportunity_" + canonical_hash(identity_anchor.candidate_id)[:32]
        ),
        candidate_id=claim_anchor.candidate_id,
        member_candidate_ids=member_ids,
        research_mode=lineage.research_mode,
        parent_opportunity_id=lineage.parent_opportunity_id,
        research_question=lineage.research_question,
        environment=identity_anchor.environment,
        version=max(item.version for item in ordered),
        known_at=max(item.known_at for item in ordered),
        snapshot_hash=canonical_hash(
            [item.model_dump(mode="json") for item in ordered]
        ),
        exact_key=exact_key,
        structural_key=structural_key,
        title=claim_anchor.title,
        thesis=thesis,
        entity_key=claim_anchor.entity_key,
        event_key=claim_anchor.event_key,
        catalyst_key=claim_anchor.catalyst_key,
        observed_change=observed_change,
        mechanism=mechanism,
        direction=claim_anchor.direction,
        expectation=claim_anchor.expectation,
        expectation_posture=claim_anchor.expectation_posture,
        variant_wedge=variant_wedge,
        why_now=claim_anchor.why_now,
        falsifier=claim_anchor.falsifier,
        first_rejection=claim_anchor.first_rejection,
        prediction=claim_anchor.prediction,
        investability=claim_anchor.investability,
        freshness_at=claim_anchor.freshness_at,
        horizon_days=claim_anchor.horizon_days,
        confidence=claim_anchor.confidence,
        evidence_ids=evidence_ids,
        audit_evidence_ids=audit_evidence_ids,
        completeness=completeness,
        beneficiary_path=claim_anchor.beneficiary_path,
        disconfirming_evidence=claim_anchor.disconfirming_evidence,
        next_test=claim_anchor.next_test,
        thesis_pillars=frozen_pillars,
        research_diligence=claim_anchor.research_diligence,
    )


def materialized_thesis_pillars(
    candidates: tuple[CandidateDraft, ...],
) -> tuple[ThesisPillar, ...]:
    """Merges semantically identical pillars while preserving frozen provenance."""

    thesis_pillars: dict[str, ThesisPillar] = {}
    for candidate in sorted(candidates, key=lambda item: item.candidate_id):
        for draft in candidate.thesis_pillars:
            pillar = materialize_pillar(
                draft,
                candidate_id=candidate.candidate_id,
                known_at=candidate.known_at,
                horizon_days=candidate.horizon_days,
                evidence_ids=candidate.evidence_ids,
            )
            existing = thesis_pillars.get(pillar.pillar_id)
            if existing is None:
                thesis_pillars[pillar.pillar_id] = pillar
                continue
            conservative = min(
                (existing, pillar), key=lambda item: (item.due_at, item.known_at)
            )
            thesis_pillars[pillar.pillar_id] = conservative.model_copy(
                update={
                    "source_candidate_ids": tuple(
                        dict.fromkeys(
                            (*existing.source_candidate_ids, candidate.candidate_id)
                        )
                    ),
                    "evidence_ids": tuple(
                        dict.fromkeys((*existing.evidence_ids, *candidate.evidence_ids))
                    )[:20],
                }
            )
    frozen_pillars = tuple(
        sorted(thesis_pillars.values(), key=lambda item: (item.due_at, item.pillar_id))
    )[:MAX_THESIS_PILLARS]
    return frozen_pillars
