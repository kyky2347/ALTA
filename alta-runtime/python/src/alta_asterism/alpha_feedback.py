import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import Environment
from .research_agenda import ResearchMode
from .trader_mind import ACTIVE_RESEARCH_TOOLS

MIN_MIND_BENCHMARKED_POSITIONS = 30
MIN_SLICE_BENCHMARKED_POSITIONS = 10
MAX_ARCHETYPE_SLICES = 8
MAX_RESEARCH_ROUTE_SLICES = 2
MAX_RESEARCH_MODE_SLICES = 2
ALPHA_FEEDBACK_MODE = "mature_pit_non_evidence"
ALPHA_LOWER_BOUND_Z = Decimal("2.241")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal(0)) / Decimal(len(values))


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _alpha_lower_confidence_bound(
    values: tuple[Decimal, ...], *, mature: bool
) -> Decimal | None:
    """Four-Mind Bonferroni one-sided bound for mature outcome samples."""

    if not mature or not values:
        return None
    mean = _mean(values)
    if mean is None or len(values) == 1:
        return mean
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
    standard_error = (variance / Decimal(len(values))).sqrt()
    return mean - ALPHA_LOWER_BOUND_Z * standard_error


def _alpha_values(
    observations: tuple["AlphaOutcomeObservation", ...],
) -> tuple[Decimal, ...]:
    return tuple(
        item.realized_alpha_bps
        for item in observations
        if item.realized_alpha_bps is not None
    )


def _mature_alpha_metrics(
    values: tuple[Decimal, ...], *, mature: bool
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if not mature:
        return None, None, None
    return (
        _mean(values),
        _ratio(sum(value > 0 for value in values), len(values)),
        min(values),
    )


class AlphaContributor(BaseModel):
    """Immutable research credit captured when a Shadow position opens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=3, max_length=128)
    scout_id: str = Field(min_length=3, max_length=64)
    alpha_archetype: str = Field(min_length=3, max_length=96)
    research_mode: ResearchMode = "explore"
    research_route: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("research_route")
    @classmethod
    def route_is_unique_and_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("research route tools must be unique")
        if any(tool not in ACTIVE_RESEARCH_TOOLS for tool in value):
            raise ValueError("research route contains an unbounded tool")
        return value


class AlphaOutcomeObservation(BaseModel):
    """One contributor's point-in-time credit for one closed Shadow position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position_id: str = Field(min_length=3, max_length=128)
    scout_id: str = Field(min_length=3, max_length=64)
    alpha_archetype: str = Field(min_length=3, max_length=96)
    research_mode: ResearchMode = "explore"
    research_route: tuple[str, ...] = Field(default=(), max_length=12)
    known_at: datetime
    net_return_bps: Decimal
    realized_alpha_bps: Decimal | None = None

    @field_validator("known_at")
    @classmethod
    def known_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Alpha outcome known_at must be timezone-aware")
        return value


class AlphaSliceFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alpha_archetype: str = Field(min_length=3, max_length=96)
    closed_positions: int = Field(ge=1)
    benchmarked_positions: int = Field(ge=0)
    mature: bool
    mean_realized_alpha_bps: Decimal | None = None
    positive_alpha_rate: Decimal | None = Field(default=None, ge=0, le=1)
    worst_realized_alpha_bps: Decimal | None = None


class ResearchRouteFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str = Field(pattern=r"^[a-f0-9]{12}$")
    tools: tuple[str, ...] = Field(min_length=1, max_length=12)
    benchmarked_positions: int = Field(ge=1)
    mature: bool
    mean_realized_alpha_bps: Decimal | None = None


class ResearchModeFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    research_mode: ResearchMode
    closed_positions: int = Field(ge=1)
    benchmarked_positions: int = Field(ge=0)
    mature: bool
    mean_realized_alpha_bps: Decimal | None = None
    positive_alpha_rate: Decimal | None = Field(default=None, ge=0, le=1)
    worst_realized_alpha_bps: Decimal | None = None


class TraderMindAlphaFeedback(BaseModel):
    """Outcome feedback for one Mind; never Evidence or an allocation rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scout_id: str = Field(min_length=3, max_length=64)
    known_at: datetime
    minimum_mind_positions: int = Field(ge=1)
    minimum_slice_positions: int = Field(ge=1)
    closed_positions: int = Field(ge=1)
    benchmarked_positions: int = Field(ge=0)
    mature: bool
    mean_net_return_bps: Decimal | None = None
    mean_realized_alpha_bps: Decimal | None = None
    alpha_lower_confidence_bps: Decimal | None = None
    positive_alpha_rate: Decimal | None = Field(default=None, ge=0, le=1)
    worst_realized_alpha_bps: Decimal | None = None
    archetypes: tuple[AlphaSliceFeedback, ...] = Field(
        default=(), max_length=MAX_ARCHETYPE_SLICES
    )
    research_routes: tuple[ResearchRouteFeedback, ...] = Field(
        default=(), max_length=MAX_RESEARCH_ROUTE_SLICES
    )
    research_modes: tuple[ResearchModeFeedback, ...] = Field(
        default=(), max_length=MAX_RESEARCH_MODE_SLICES
    )
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("known_at")
    @classmethod
    def known_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Alpha feedback known_at must be timezone-aware")
        return value


def _archetype_feedback(
    grouped: dict[str, dict[str, AlphaOutcomeObservation]],
    *,
    mind_mature: bool,
    minimum_slice_positions: int,
) -> tuple[AlphaSliceFeedback, ...]:
    feedback = []
    for archetype, positions in sorted(
        grouped.items(), key=lambda item: (-len(item[1]), item[0])
    )[:MAX_ARCHETYPE_SLICES]:
        values = tuple(positions.values())
        alphas = _alpha_values(values)
        mature = mind_mature and len(alphas) >= minimum_slice_positions
        mean_alpha, positive_rate, worst_alpha = _mature_alpha_metrics(
            alphas, mature=mature
        )
        feedback.append(
            AlphaSliceFeedback(
                alpha_archetype=archetype,
                closed_positions=len(values),
                benchmarked_positions=len(alphas),
                mature=mature,
                mean_realized_alpha_bps=mean_alpha,
                positive_alpha_rate=positive_rate,
                worst_realized_alpha_bps=worst_alpha,
            )
        )
    return tuple(feedback)


def _route_feedback(
    grouped: dict[tuple[str, ...], dict[str, AlphaOutcomeObservation]],
    *,
    mind_mature: bool,
    minimum_slice_positions: int,
) -> tuple[ResearchRouteFeedback, ...]:
    feedback = []
    for route, positions in sorted(
        grouped.items(), key=lambda item: (-len(item[1]), item[0])
    ):
        alphas = _alpha_values(tuple(positions.values()))
        if not alphas:
            continue
        mature = mind_mature and len(alphas) >= minimum_slice_positions
        feedback.append(
            ResearchRouteFeedback(
                route_id=_canonical_hash(route)[:12],
                tools=route,
                benchmarked_positions=len(alphas),
                mature=mature,
                mean_realized_alpha_bps=_mean(alphas) if mature else None,
            )
        )
        if len(feedback) == MAX_RESEARCH_ROUTE_SLICES:
            break
    return tuple(feedback)


def _research_mode_feedback(
    grouped: dict[ResearchMode, dict[str, AlphaOutcomeObservation]],
    *,
    mind_mature: bool,
    minimum_slice_positions: int,
) -> tuple[ResearchModeFeedback, ...]:
    feedback = []
    for research_mode, positions in sorted(grouped.items()):
        values = tuple(positions.values())
        alphas = _alpha_values(values)
        mature = mind_mature and len(alphas) >= minimum_slice_positions
        mean_alpha, positive_rate, worst_alpha = _mature_alpha_metrics(
            alphas, mature=mature
        )
        feedback.append(
            ResearchModeFeedback(
                research_mode=research_mode,
                closed_positions=len(values),
                benchmarked_positions=len(alphas),
                mature=mature,
                mean_realized_alpha_bps=mean_alpha,
                positive_alpha_rate=positive_rate,
                worst_realized_alpha_bps=worst_alpha,
            )
        )
    return tuple(feedback)


def _feedback_payload(
    *,
    scout_id: str,
    observations: tuple[AlphaOutcomeObservation, ...],
    minimum_mind_positions: int,
    minimum_slice_positions: int,
) -> dict[str, Any]:
    mind_observations = tuple(
        {
            item.position_id: item
            for item in sorted(
                observations,
                key=lambda value: (
                    value.known_at,
                    value.position_id,
                    value.alpha_archetype,
                    value.research_mode,
                    value.research_route,
                ),
            )
        }.values()
    )
    benchmarked = tuple(
        item for item in mind_observations if item.realized_alpha_bps is not None
    )
    mind_mature = len(benchmarked) >= minimum_mind_positions
    alpha_values = _alpha_values(benchmarked)
    net_values = tuple(item.net_return_bps for item in mind_observations)

    by_archetype: dict[str, dict[str, AlphaOutcomeObservation]] = defaultdict(dict)
    by_route: dict[tuple[str, ...], dict[str, AlphaOutcomeObservation]] = defaultdict(
        dict
    )
    by_mode: dict[ResearchMode, dict[str, AlphaOutcomeObservation]] = defaultdict(dict)
    for item in observations:
        by_archetype[item.alpha_archetype].setdefault(item.position_id, item)
        by_mode[item.research_mode].setdefault(item.position_id, item)
        if item.research_route:
            by_route[item.research_route].setdefault(item.position_id, item)

    return {
        "scout_id": scout_id,
        "known_at": max(item.known_at for item in mind_observations),
        "minimum_mind_positions": minimum_mind_positions,
        "minimum_slice_positions": minimum_slice_positions,
        "closed_positions": len(mind_observations),
        "benchmarked_positions": len(benchmarked),
        "mature": mind_mature,
        "mean_net_return_bps": _mean(net_values) if mind_mature else None,
        "mean_realized_alpha_bps": _mean(alpha_values) if mind_mature else None,
        "alpha_lower_confidence_bps": _alpha_lower_confidence_bound(
            alpha_values, mature=mind_mature
        ),
        "positive_alpha_rate": (
            _ratio(sum(value > 0 for value in alpha_values), len(alpha_values))
            if mind_mature
            else None
        ),
        "worst_realized_alpha_bps": min(alpha_values) if mind_mature else None,
        "archetypes": _archetype_feedback(
            by_archetype,
            mind_mature=mind_mature,
            minimum_slice_positions=minimum_slice_positions,
        ),
        "research_routes": _route_feedback(
            by_route,
            mind_mature=mind_mature,
            minimum_slice_positions=minimum_slice_positions,
        ),
        "research_modes": _research_mode_feedback(
            by_mode,
            mind_mature=mind_mature,
            minimum_slice_positions=minimum_slice_positions,
        ),
    }


def build_alpha_feedback(
    observations: tuple[AlphaOutcomeObservation, ...],
    *,
    minimum_mind_positions: int = MIN_MIND_BENCHMARKED_POSITIONS,
    minimum_slice_positions: int = MIN_SLICE_BENCHMARKED_POSITIONS,
) -> tuple[TraderMindAlphaFeedback, ...]:
    """Builds deterministic feedback and hides performance before maturity."""

    if minimum_slice_positions > minimum_mind_positions:
        raise ValueError("slice maturity cannot exceed Mind maturity")
    by_scout: dict[str, list[AlphaOutcomeObservation]] = defaultdict(list)
    seen: set[tuple[str, str, str, ResearchMode, tuple[str, ...]]] = set()
    for item in sorted(
        observations,
        key=lambda value: (
            value.known_at,
            value.position_id,
            value.scout_id,
            value.alpha_archetype,
            value.research_mode,
            value.research_route,
        ),
    ):
        identity = (
            item.position_id,
            item.scout_id,
            item.alpha_archetype,
            item.research_mode,
            item.research_route,
        )
        if identity in seen:
            continue
        seen.add(identity)
        by_scout[item.scout_id].append(item)

    feedback = []
    for scout_id, values in sorted(by_scout.items()):
        payload = _feedback_payload(
            scout_id=scout_id,
            observations=tuple(values),
            minimum_mind_positions=minimum_mind_positions,
            minimum_slice_positions=minimum_slice_positions,
        )
        serialized_payload = {
            **payload,
            "archetypes": [
                item.model_dump(mode="json") for item in payload["archetypes"]
            ],
            "research_routes": [
                item.model_dump(mode="json") for item in payload["research_routes"]
            ],
            "research_modes": [
                item.model_dump(mode="json") for item in payload["research_modes"]
            ],
        }
        feedback.append(
            TraderMindAlphaFeedback(
                **payload,
                snapshot_hash=_canonical_hash(serialized_payload),
            )
        )
    return tuple(feedback)


def load_alpha_contributors(
    connection,
    member_candidate_ids: tuple[str, ...],
) -> tuple[AlphaContributor, ...]:
    """Loads only a complete, valid contributor set for a frozen Opportunity."""

    if not member_candidate_ids:
        return ()
    rows = connection.execute(
        """SELECT c.id, r.role, c.alpha_archetype, r.tool_provenance,
        r.frozen_input->'scout'->'alpha_archetypes', c.foundry_snapshot
        FROM research.candidate c
        JOIN research.run r ON r.id = c.run_id
        WHERE c.id = ANY(%s)
        ORDER BY c.id""",
        (list(member_candidate_ids),),
    ).fetchall()
    if {row[0] for row in rows} != set(member_candidate_ids):
        return ()
    contributors = []
    for (
        candidate_id,
        scout_id,
        alpha_archetype,
        provenance,
        raw_archetypes,
        foundry_snapshot,
    ) in rows:
        allowed_archetypes = (
            tuple(raw_archetypes) if isinstance(raw_archetypes, list) else ()
        )
        if alpha_archetype not in allowed_archetypes:
            return ()
        research_mode = (
            foundry_snapshot.get("research_mode", "explore")
            if isinstance(foundry_snapshot, dict)
            else "explore"
        )
        if research_mode not in {"explore", "follow_up"}:
            return ()
        route = tuple(
            dict.fromkeys(
                str(item.get("tool_name"))
                for item in provenance
                if isinstance(item, dict)
                and item.get("status") == "completed"
                and item.get("tool_name") in ACTIVE_RESEARCH_TOOLS
            )
        )[:12]
        contributors.append(
            AlphaContributor(
                candidate_id=candidate_id,
                scout_id=scout_id,
                alpha_archetype=alpha_archetype,
                research_mode=research_mode,
                research_route=route,
            )
        )
    return tuple(contributors)


class AlphaFeedbackProjector:
    """Reads append-only Shadow outcomes at a strict point-in-time cutoff."""

    def __init__(
        self,
        database,
        *,
        minimum_mind_positions: int = MIN_MIND_BENCHMARKED_POSITIONS,
        minimum_slice_positions: int = MIN_SLICE_BENCHMARKED_POSITIONS,
    ) -> None:
        self.database = database
        self.minimum_mind_positions = minimum_mind_positions
        self.minimum_slice_positions = minimum_slice_positions

    def at(
        self, environment: Environment | str, wake_at: datetime
    ) -> tuple[TraderMindAlphaFeedback, ...]:
        environment_value = (
            environment.value if isinstance(environment, Environment) else environment
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT event.aggregate_id, event.known_at, event.payload,
                position.position_thesis
                FROM ops.event event
                JOIN research.shadow_position position
                  ON position.id = event.aggregate_id
                WHERE event.environment = %s
                  AND event.event_type = 'position.performance.measured'
                  AND position.status = 'closed'
                  AND event.payload->>'cost_adjusted' = 'true'
                  AND event.known_at < %s
                ORDER BY event.sequence""",
                (environment_value, wake_at),
            ).fetchall()
        observations = []
        for position_id, known_at, payload, thesis in rows:
            contributors = payload.get("alpha_contributors")
            if not isinstance(contributors, list):
                contributors = (
                    thesis.get("alpha_contributors", [])
                    if isinstance(thesis, dict)
                    else []
                )
            try:
                net_return = Decimal(payload["net_return_bps"])
                realized_alpha = (
                    Decimal(payload["realized_alpha_bps"])
                    if payload.get("realized_alpha_bps") is not None
                    else None
                )
            except (KeyError, TypeError, ValueError):
                continue
            for raw_contributor in contributors:
                try:
                    contributor = AlphaContributor.model_validate(raw_contributor)
                except ValueError:
                    continue
                observations.append(
                    AlphaOutcomeObservation(
                        position_id=position_id,
                        scout_id=contributor.scout_id,
                        alpha_archetype=contributor.alpha_archetype,
                        research_mode=contributor.research_mode,
                        research_route=contributor.research_route,
                        known_at=known_at,
                        net_return_bps=net_return,
                        realized_alpha_bps=realized_alpha,
                    )
                )
        return build_alpha_feedback(
            tuple(observations),
            minimum_mind_positions=self.minimum_mind_positions,
            minimum_slice_positions=self.minimum_slice_positions,
        )

    def public_summary(self, environment: Environment | str) -> dict[str, Any]:
        values = self.at(environment, datetime.now(UTC))
        from .research_incentive import (
            MAX_REWARD_TOKENS,
            MAX_REWARD_TOOL_CALLS,
            RESEARCH_INCENTIVE_MODE,
            build_research_incentives,
        )
        from .trader_mind import SCOUTS

        incentives = build_research_incentives(
            values, scout_ids=tuple(item.scout_id for item in SCOUTS)
        )
        return {
            "mode": ALPHA_FEEDBACK_MODE,
            "automaticPolicyChanges": False,
            "automaticResearchBudgetChanges": True,
            "incentivePolicy": {
                "mode": RESEARCH_INCENTIVE_MODE,
                "alphaLowerBoundZ": str(ALPHA_LOWER_BOUND_Z),
                "maximumBonusToolCalls": MAX_REWARD_TOOL_CALLS,
                "maximumBonusTokens": MAX_REWARD_TOKENS,
                "capitalInfluence": False,
                "rankingInfluence": False,
                "brokerInfluence": False,
            },
            "minimumMindBenchmarkedPositions": self.minimum_mind_positions,
            "minimumSliceBenchmarkedPositions": self.minimum_slice_positions,
            "minds": [item.model_dump(mode="json") for item in values],
            "researchIncentives": [item.model_dump(mode="json") for item in incentives],
        }
