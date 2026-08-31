from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from .database import Database
    from .market_research import MarketResearchAgenda


RESEARCH_ATTENTION_VERSION = "alta-research-attention-v2"
RESEARCH_ATTENTION_LOOKBACK_CANDIDATES = 64
RESEARCH_ATTENTION_MINIMUM_CANDIDATES = 4
RESEARCH_ATTENTION_CONCENTRATION_THRESHOLD = Decimal("0.50")
_RATIO_QUANTUM = Decimal("0.0001")
_BREADTH_QUANTUM = Decimal("0.01")

AttentionPosture = Literal["insufficient_sample", "balanced", "concentrated"]
AttentionMode = Literal["unconstrained", "continue_lead", "expand_coverage"]
HorizonBucket = Literal["short", "medium", "long"]
Direction = Literal["positive", "negative", "neutral", "unknown"]


def horizon_bucket(horizon_days: int) -> HorizonBucket:
    if horizon_days <= 14:
        return "short"
    if horizon_days <= 90:
        return "medium"
    return "long"


def canonical_entity_key(value: str) -> str:
    normalized = " ".join(value.split()).casefold()
    if not normalized or any(not character.isprintable() for character in normalized):
        raise ValueError("research attention entity key must be printable")
    encoded = normalized.encode()
    if len(encoded) > 128:
        normalized = encoded[:128].decode(errors="ignore").rstrip()
    if not normalized:
        raise ValueError("research attention entity key must be non-empty")
    return normalized


class ResearchAttentionObservation(BaseModel):
    """One production Candidate trial known before a research wake."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=3, max_length=128)
    scout_id: str = Field(min_length=3, max_length=64)
    entity_key: str = Field(min_length=1, max_length=128)
    alpha_archetype: str = Field(
        default="legacy_unclassified", min_length=1, max_length=96
    )
    horizon_days: int = Field(default=30, ge=1, le=365)
    direction: Direction = "unknown"
    known_at: datetime

    @field_validator("entity_key")
    @classmethod
    def entity_is_canonical(cls, value: str) -> str:
        return canonical_entity_key(value)

    @field_validator("known_at")
    @classmethod
    def known_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research attention observation must be timezone-aware")
        return value


class ResearchAttentionAssignment(BaseModel):
    """A non-Evidence research seat; it cannot rank or allocate capital."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scout_id: str = Field(min_length=3, max_length=64)
    mode: AttentionMode
    deprioritized_entities: tuple[str, ...] = Field(default=(), max_length=3)
    target_archetype: str | None = Field(default=None, min_length=1, max_length=96)
    target_horizon_bucket: HorizonBucket | None = None
    directive: str = Field(min_length=3, max_length=560)

    @field_validator("deprioritized_entities")
    @classmethod
    def entities_are_canonical_and_unique(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        normalized = tuple(canonical_entity_key(item) for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("deprioritized research entities must be unique")
        return normalized

    @model_validator(mode="after")
    def mode_matches_entities(self) -> ResearchAttentionAssignment:
        if self.mode == "expand_coverage" and not self.deprioritized_entities:
            raise ValueError("coverage expansion requires a deprioritized entity")
        if self.mode != "expand_coverage" and self.deprioritized_entities:
            raise ValueError("only coverage expansion may deprioritize entities")
        return self


class ResearchAttentionPortfolio(BaseModel):
    """Point-in-time research breadth control derived only from prior trials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["alta-research-attention-v1", "alta-research-attention-v2"] = (
        RESEARCH_ATTENTION_VERSION
    )
    known_at: datetime
    observed_through: datetime | None = None
    maximum_window: int = RESEARCH_ATTENTION_LOOKBACK_CANDIDATES
    minimum_sample: int = RESEARCH_ATTENTION_MINIMUM_CANDIDATES
    concentration_threshold: Decimal = RESEARCH_ATTENTION_CONCENTRATION_THRESHOLD
    sample_size: int = Field(ge=0, le=RESEARCH_ATTENTION_LOOKBACK_CANDIDATES)
    unique_entities: int = Field(ge=0, le=RESEARCH_ATTENTION_LOOKBACK_CANDIDATES)
    top_entity: str | None = Field(default=None, min_length=1, max_length=128)
    top_entity_share: Decimal | None = Field(default=None, ge=0, le=1)
    concentration_hhi: Decimal | None = Field(default=None, ge=0, le=1)
    effective_breadth: Decimal | None = Field(default=None, ge=1)
    unique_archetypes: int = Field(
        default=0, ge=0, le=RESEARCH_ATTENTION_LOOKBACK_CANDIDATES
    )
    archetype_effective_breadth: Decimal | None = Field(default=None, ge=1)
    horizon_mix: dict[str, int] = Field(default_factory=dict)
    direction_mix: dict[str, int] = Field(default_factory=dict)
    posture: AttentionPosture
    continuation_scout_id: str | None = Field(default=None, min_length=3, max_length=64)
    assignments: tuple[ResearchAttentionAssignment, ...] = Field(
        default=(), max_length=4
    )

    @field_validator("known_at")
    @classmethod
    def known_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research attention wake must be timezone-aware")
        return value

    @field_validator("observed_through")
    @classmethod
    def observed_through_is_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("research attention observation cutoff must be aware")
        return value

    @field_validator("top_entity")
    @classmethod
    def top_entity_is_canonical(cls, value: str | None) -> str | None:
        return canonical_entity_key(value) if value is not None else None

    @model_validator(mode="after")
    def portfolio_is_consistent(self) -> ResearchAttentionPortfolio:
        scout_ids = tuple(item.scout_id for item in self.assignments)
        if len(scout_ids) != len(set(scout_ids)):
            raise ValueError(
                "research attention assignments require unique Trader Minds"
            )
        if self.observed_through is not None and self.observed_through >= self.known_at:
            raise ValueError(
                "research attention cannot observe the current wake or future"
            )
        metrics = (
            self.top_entity,
            self.top_entity_share,
            self.concentration_hhi,
            self.effective_breadth,
        )
        if self.sample_size == 0 and any(item is not None for item in metrics):
            raise ValueError("empty research attention cannot expose concentration")
        if self.sample_size > 0 and any(item is None for item in metrics):
            raise ValueError("observed research attention requires complete metrics")
        continuing = tuple(
            item for item in self.assignments if item.mode == "continue_lead"
        )
        expanding = tuple(
            item for item in self.assignments if item.mode == "expand_coverage"
        )
        if self.posture == "concentrated":
            if (
                self.top_entity is None
                or self.continuation_scout_id is None
                or len(continuing) != 1
                or continuing[0].scout_id != self.continuation_scout_id
                or len(expanding) != max(0, len(self.assignments) - 1)
                or any(
                    self.top_entity not in item.deprioritized_entities
                    for item in expanding
                )
            ):
                raise ValueError(
                    "concentrated attention requires one continuation seat"
                )
        elif self.continuation_scout_id is not None or continuing or expanding:
            raise ValueError("non-concentrated attention must remain unconstrained")
        return self

    def assignment_for(self, scout_id: str) -> ResearchAttentionAssignment | None:
        return next(
            (item for item in self.assignments if item.scout_id == scout_id), None
        )

    def for_scout(self, scout_id: str) -> ResearchAttentionPortfolio:
        if self.assignment_for(scout_id) is None:
            raise ValueError("research attention has no assignment for Trader Mind")
        # Keep the complete allocation in every immutable role snapshot. That makes
        # restart recovery able to prove that all Minds observed one identical
        # portfolio, rather than trying to infer a global allocation from fragments.
        return self


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        _RATIO_QUANTUM, rounding=ROUND_HALF_EVEN
    )


def _continuation_scout(
    observations: tuple[ResearchAttentionObservation, ...],
    top_entity: str,
    scout_ids: tuple[str, ...],
) -> str:
    by_scout: dict[str, list[ResearchAttentionObservation]] = defaultdict(list)
    for item in observations:
        if item.entity_key == top_entity and item.scout_id in scout_ids:
            by_scout[item.scout_id].append(item)
    if not by_scout:
        return scout_ids[0]
    return min(
        by_scout,
        key=lambda scout_id: (
            -len(by_scout[scout_id]),
            -max(item.known_at.timestamp() for item in by_scout[scout_id]),
            scout_id,
        ),
    )


def build_research_attention_portfolio(
    *,
    wake_at: datetime,
    universe: tuple[str, ...],
    scout_ids: tuple[str, ...],
    observations: tuple[ResearchAttentionObservation, ...],
    scout_archetypes: dict[str, tuple[str, ...]] | None = None,
) -> ResearchAttentionPortfolio:
    if wake_at.tzinfo is None or wake_at.utcoffset() is None:
        raise ValueError("research attention wake must be timezone-aware")
    if not scout_ids or len(scout_ids) != len(set(scout_ids)):
        raise ValueError("research attention requires unique Trader Mind IDs")
    if not universe:
        raise ValueError("research attention requires an explicit universe")
    if any(item.known_at >= wake_at for item in observations):
        raise ValueError("research attention observation must predate its wake")
    archetypes_by_scout = scout_archetypes or {}
    unknown_scouts = set(archetypes_by_scout) - set(scout_ids)
    if unknown_scouts:
        raise ValueError("research attention archetypes include an unknown Trader Mind")
    if any(not values for values in archetypes_by_scout.values()):
        raise ValueError("research attention archetype mandates cannot be empty")

    deduplicated: dict[str, ResearchAttentionObservation] = {}
    for item in sorted(
        observations,
        key=lambda value: (value.known_at, value.candidate_id),
        reverse=True,
    ):
        deduplicated.setdefault(item.candidate_id, item)
    window = tuple(deduplicated.values())[:RESEARCH_ATTENTION_LOOKBACK_CANDIDATES]
    archetype_counts = Counter(item.alpha_archetype for item in window)
    horizon_counts = Counter(horizon_bucket(item.horizon_days) for item in window)
    direction_counts = Counter(item.direction for item in window)

    def coverage_target(scout_id: str, index: int) -> tuple[str | None, HorizonBucket]:
        available = archetypes_by_scout.get(scout_id, ())
        target_archetype = (
            min(available, key=lambda value: (archetype_counts[value], value))
            if available
            else None
        )
        buckets: tuple[HorizonBucket, ...] = ("short", "medium", "long")
        target_horizon = min(
            buckets,
            key=lambda value: (
                horizon_counts[value],
                (buckets.index(value) - index) % 3,
            ),
        )
        return target_archetype, target_horizon

    if not window:
        empty_assignments = []
        for index, scout_id in enumerate(scout_ids):
            target_archetype, target_horizon = coverage_target(scout_id, index)
            empty_assignments.append(
                ResearchAttentionAssignment(
                    scout_id=scout_id,
                    mode="unconstrained",
                    target_archetype=target_archetype,
                    target_horizon_bucket=target_horizon,
                    directive=(
                        "Explore independently; no production Candidate concentration sample is mature. "
                        f"Start search in the {target_horizon} horizon"
                        + (
                            f" and {target_archetype} archetype"
                            if target_archetype
                            else ""
                        )
                        + ", then follow stronger contradictory evidence or return no_op."
                    ),
                )
            )
        return ResearchAttentionPortfolio(
            known_at=wake_at,
            sample_size=0,
            unique_entities=0,
            posture="insufficient_sample",
            horizon_mix={item: 0 for item in ("short", "medium", "long")},
            direction_mix={
                item: 0 for item in ("positive", "negative", "neutral", "unknown")
            },
            assignments=tuple(empty_assignments),
        )

    counts = Counter(item.entity_key for item in window)
    latest_by_entity = {
        entity: max(item.known_at for item in window if item.entity_key == entity)
        for entity in counts
    }
    top_entity = min(
        counts,
        key=lambda entity: (
            -counts[entity],
            -latest_by_entity[entity].timestamp(),
            entity,
        ),
    )
    sample_size = len(window)
    top_share = _ratio(counts[top_entity], sample_size)
    exact_shares = tuple(
        Decimal(count) / Decimal(sample_size) for count in counts.values()
    )
    exact_hhi = sum((share * share for share in exact_shares), Decimal(0))
    hhi = exact_hhi.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)
    effective_breadth = (Decimal(1) / exact_hhi).quantize(
        _BREADTH_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    exact_archetype_shares = tuple(
        Decimal(count) / Decimal(sample_size) for count in archetype_counts.values()
    )
    archetype_hhi = sum((share * share for share in exact_archetype_shares), Decimal(0))
    archetype_effective_breadth = (Decimal(1) / archetype_hhi).quantize(
        _BREADTH_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    concentrated = (
        sample_size >= RESEARCH_ATTENTION_MINIMUM_CANDIDATES
        and len(universe) > 1
        and top_share > RESEARCH_ATTENTION_CONCENTRATION_THRESHOLD
    )
    posture: AttentionPosture = (
        "insufficient_sample"
        if sample_size < RESEARCH_ATTENTION_MINIMUM_CANDIDATES
        else "concentrated"
        if concentrated
        else "balanced"
    )
    continuation = (
        _continuation_scout(window, top_entity, scout_ids) if concentrated else None
    )
    assignments = []
    for index, scout_id in enumerate(scout_ids):
        target_archetype, target_horizon = coverage_target(scout_id, index)
        target_clause = (
            f" Begin with the under-covered {target_horizon} horizon"
            + (f" / {target_archetype} lane" if target_archetype else " lane")
            + "; abandon it if evidence is weaker than another admissible lead."
        )
        if continuation is None:
            assignments.append(
                ResearchAttentionAssignment(
                    scout_id=scout_id,
                    mode="unconstrained",
                    target_archetype=target_archetype,
                    target_horizon_bucket=target_horizon,
                    directive=(
                        "Explore independently; the recent production Candidate set is not concentrated."
                        + target_clause
                    ),
                )
            )
        elif scout_id == continuation:
            assignments.append(
                ResearchAttentionAssignment(
                    scout_id=scout_id,
                    mode="continue_lead",
                    target_archetype=target_archetype,
                    target_horizon_bucket=target_horizon,
                    directive=(
                        f"Retain the single {top_entity} continuation seat, but require a new source, changed fact, or causal prediction."
                        + target_clause
                    ),
                )
            )
        else:
            assignments.append(
                ResearchAttentionAssignment(
                    scout_id=scout_id,
                    mode="expand_coverage",
                    deprioritized_entities=(top_entity,),
                    target_archetype=target_archetype,
                    target_horizon_bucket=target_horizon,
                    directive=(
                        f"Expand independent coverage beyond {top_entity}; do not return another exploratory Candidate for that entity this wake."
                        + target_clause
                    ),
                )
            )
    return ResearchAttentionPortfolio(
        known_at=wake_at,
        observed_through=max(item.known_at for item in window),
        sample_size=sample_size,
        unique_entities=len(counts),
        top_entity=top_entity,
        top_entity_share=top_share,
        concentration_hhi=hhi,
        effective_breadth=effective_breadth,
        unique_archetypes=len(archetype_counts),
        archetype_effective_breadth=archetype_effective_breadth,
        horizon_mix={
            item: horizon_counts[item] for item in ("short", "medium", "long")
        },
        direction_mix={
            item: direction_counts[item]
            for item in ("positive", "negative", "neutral", "unknown")
        },
        posture=posture,
        continuation_scout_id=continuation,
        assignments=tuple(assignments),
    )


def apply_research_attention_to_market_agenda(
    agenda: MarketResearchAgenda,
    attention: ResearchAttentionPortfolio,
) -> MarketResearchAgenda:
    """Remove only screen seeds that conflict with a frozen expansion seat."""

    assignments = {item.scout_id: item for item in attention.assignments}
    seeds = tuple(
        seed
        for seed in agenda.seeds
        if not (
            (assignment := assignments.get(seed.assigned_scout_id)) is not None
            and assignment.mode == "expand_coverage"
            and any(
                canonical_entity_key(symbol) in assignment.deprioritized_entities
                for symbol in seed.symbols
            )
        )
    )
    return agenda.model_copy(update={"seeds": seeds})


class ResearchAttentionProjector:
    """Reads production Candidate trials at a strict point-in-time cutoff."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def at(
        self,
        environment: str,
        universe: tuple[str, ...],
        scout_ids: tuple[str, ...],
        wake_at: datetime,
        scout_archetypes: dict[str, tuple[str, ...]] | None = None,
    ) -> ResearchAttentionPortfolio:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT candidate.id, run.role,
                candidate.foundry_snapshot->>'entity_key',
                coalesce(candidate.foundry_snapshot->>'alpha_archetype',
                         'legacy_unclassified'),
                coalesce((candidate.foundry_snapshot->>'horizon_days')::integer, 30),
                coalesce(candidate.foundry_snapshot->>'direction', 'unknown'),
                candidate.known_at
                FROM research.candidate candidate
                JOIN research.run run ON run.id = candidate.run_id
                WHERE candidate.environment = %s AND run.environment = %s
                  AND candidate.known_at < %s
                  AND run.cycle_id LIKE 'live-%%'
                  AND candidate.foundry_snapshot->>'entity_key' IS NOT NULL
                  AND btrim(candidate.foundry_snapshot->>'entity_key') <> ''
                ORDER BY candidate.known_at DESC, candidate.id DESC
                LIMIT %s""",
                (
                    environment,
                    environment,
                    wake_at,
                    RESEARCH_ATTENTION_LOOKBACK_CANDIDATES,
                ),
            ).fetchall()
        observations = tuple(
            ResearchAttentionObservation(
                candidate_id=row[0],
                scout_id=row[1],
                entity_key=row[2],
                alpha_archetype=row[3],
                horizon_days=row[4],
                direction=row[5],
                known_at=row[6],
            )
            for row in rows
        )
        return build_research_attention_portfolio(
            wake_at=wake_at,
            universe=universe,
            scout_ids=scout_ids,
            observations=observations,
            scout_archetypes=scout_archetypes,
        )

    def public_summary(
        self,
        environment: str,
        universe: tuple[str, ...],
        scout_ids: tuple[str, ...],
        scout_archetypes: dict[str, tuple[str, ...]] | None = None,
    ) -> dict[str, object]:
        attention = self.at(
            environment,
            universe,
            scout_ids,
            datetime.now(UTC),
            scout_archetypes,
        )
        warning = (
            "Research attention is concentrated; one continuation seat is preserved while the remaining Trader Minds expand entity coverage."
            if attention.posture == "concentrated"
            else "Research attention breadth is descriptive process control, not Evidence, Alpha, rank, or permission to trade."
        )
        return {
            "version": attention.version,
            "knownAt": attention.known_at.isoformat(),
            "observedThrough": (
                attention.observed_through.isoformat()
                if attention.observed_through is not None
                else None
            ),
            "maximumWindow": attention.maximum_window,
            "minimumSample": attention.minimum_sample,
            "concentrationThreshold": str(attention.concentration_threshold),
            "sampleSize": attention.sample_size,
            "uniqueEntities": attention.unique_entities,
            "topEntity": attention.top_entity,
            "topEntityShare": (
                str(attention.top_entity_share)
                if attention.top_entity_share is not None
                else None
            ),
            "concentrationHhi": (
                str(attention.concentration_hhi)
                if attention.concentration_hhi is not None
                else None
            ),
            "effectiveBreadth": (
                str(attention.effective_breadth)
                if attention.effective_breadth is not None
                else None
            ),
            "uniqueArchetypes": attention.unique_archetypes,
            "archetypeEffectiveBreadth": (
                str(attention.archetype_effective_breadth)
                if attention.archetype_effective_breadth is not None
                else None
            ),
            "horizonMix": attention.horizon_mix,
            "directionMix": attention.direction_mix,
            "posture": attention.posture,
            "continuationScoutId": attention.continuation_scout_id,
            "assignments": [
                {
                    "scoutId": item.scout_id,
                    "mode": item.mode,
                    "deprioritizedEntities": list(item.deprioritized_entities),
                    "targetArchetype": item.target_archetype,
                    "targetHorizonBucket": item.target_horizon_bucket,
                    "directive": item.directive,
                }
                for item in attention.assignments
            ],
            "warning": warning,
        }
