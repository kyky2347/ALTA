import hashlib
from dataclasses import dataclass, field
from typing import Any

from .context_budget import canonical_json_bytes
from .database import Database
from .research_agenda import OpportunityDrive
from .scouts import SCOUTS, FrozenScoutInput


class FrozenCycleSnapshotError(ValueError):
    """Durable cycle state cannot be reconciled without changing frozen evidence."""


def frozen_wake_hash(
    frozen_input: FrozenScoutInput, source_postures: dict[str, str]
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "frozen_input": frozen_input.model_dump(mode="json"),
                "source_postures": dict(sorted(source_postures.items())),
            }
        )
    ).hexdigest()


def _validated_source_postures(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise FrozenCycleSnapshotError(
            "frozen wake is missing its source posture snapshot"
        )
    postures = {}
    for source_id, posture in value.items():
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(posture, str)
            or not posture
        ):
            raise FrozenCycleSnapshotError("frozen wake has invalid source posture")
        postures[source_id] = posture
    return dict(sorted(postures.items()))


def _load_recovery_rows(database: Database, cycle_id: str):
    with database.connect() as connection:
        snapshots = connection.execute(
            """SELECT environment::text, known_at, frozen_input,
            source_postures, snapshot_hash
            FROM research.scout_batch_snapshot
            WHERE cycle_id = %s ORDER BY id""",
            (cycle_id,),
        ).fetchall()
        runs = connection.execute(
            """SELECT r.role, r.frozen_input FROM research.run r
            JOIN ops.job j ON j.id = r.job_id
            WHERE j.subject_id = %s AND j.kind = 'scout_batch'
            ORDER BY r.role, r.id""",
            (cycle_id,),
        ).fetchall()
        postures = connection.execute(
            """SELECT payload->>'source_id', payload->>'posture'
            FROM ops.event WHERE correlation_id = %s
              AND event_type = 'source.posture' ORDER BY sequence""",
            (cycle_id,),
        ).fetchall()
    return snapshots, runs, postures


def _recover_global_snapshot(snapshot, runs, cycle_id: str, roles: tuple[str, ...]):
    present_roles = tuple(row[0] for row in runs)
    if len(present_roles) != len(set(present_roles)) or not set(present_roles).issubset(
        roles
    ):
        raise FrozenCycleSnapshotError(
            "cycle has an invalid role set for its global frozen snapshot"
        )
    environment, known_at, frozen_value, posture_value, expected_hash = snapshot
    try:
        frozen = FrozenScoutInput.model_validate(frozen_value)
    except (TypeError, ValueError) as error:
        raise FrozenCycleSnapshotError(
            "cycle has an invalid global frozen snapshot"
        ) from error
    postures = _validated_source_postures(posture_value)
    identity = (frozen.wake_id, frozen.environment.value, frozen.known_at)
    if identity != (cycle_id, environment, known_at):
        raise FrozenCycleSnapshotError(
            "global frozen snapshot disagrees with its cycle identity"
        )
    if frozen_wake_hash(frozen, postures) != expected_hash:
        raise FrozenCycleSnapshotError("global frozen snapshot hash mismatch")
    return frozen, postures


def _legacy_role_inputs(rows, roles: tuple[str, ...]) -> dict[str, FrozenScoutInput]:
    present_roles = {row[0] for row in rows}
    if len(rows) != len(present_roles):
        raise FrozenCycleSnapshotError(
            "incomplete cycle has duplicate Scout role snapshots"
        )
    if present_roles != set(roles):
        raise FrozenCycleSnapshotError(
            "legacy partial Scout snapshot set has no global recovery anchor"
        )
    try:
        result = {
            role: FrozenScoutInput.model_validate(value["input"])
            for role, value in rows
        }
    except (KeyError, TypeError, ValueError) as error:
        raise FrozenCycleSnapshotError(
            "incomplete cycle has an invalid Scout snapshot"
        ) from error
    identities = {
        (
            item.wake_id,
            item.environment,
            item.known_at,
            item.universe,
            item.expectation_posture,
        )
        for item in result.values()
    }
    if len(identities) != 1:
        raise FrozenCycleSnapshotError(
            "incomplete cycle Scout snapshots disagree on the wake"
        )
    return result


def _merge_unique(target: dict, ordered: list, items, key, message: str) -> None:
    for item in items:
        identity = key(item)
        existing = target.get(identity)
        if existing is not None and existing != item:
            raise FrozenCycleSnapshotError(message)
        if existing is None:
            target[identity] = item
            ordered.append(item)


def _merge_optional(current, value, message: str):
    if value is None:
        return current
    if current is not None and current != value:
        raise FrozenCycleSnapshotError(message)
    return value


@dataclass
class _LegacyWakeAccumulator:
    evidence: list = field(default_factory=list)
    evidence_by_id: dict = field(default_factory=dict)
    opportunities: list = field(default_factory=list)
    opportunities_by_id: dict = field(default_factory=dict)
    memories: list = field(default_factory=list)
    memories_by_scout: dict = field(default_factory=dict)
    feedback: list = field(default_factory=list)
    feedback_by_scout: dict = field(default_factory=dict)
    incentives: list = field(default_factory=list)
    incentives_by_scout: dict = field(default_factory=dict)
    market_seeds: list = field(default_factory=list)
    market_seeds_by_id: dict = field(default_factory=dict)
    research_queue: dict = field(default_factory=dict)
    research_assignments: dict = field(default_factory=dict)
    research_attention: Any = None
    opportunity_continuity: Any = None
    market_agenda: Any = None
    market_agenda_base: Any = None
    opportunity_drive_core: Any = None

    def add(self, frozen: FrozenScoutInput) -> None:
        self._add_drive(frozen.opportunity_drive)
        self._add_collections(frozen)
        self._add_optional_state(frozen)

    def _add_drive(self, drive: OpportunityDrive) -> None:
        drive_core = drive.model_copy(
            update={
                "assigned_mode": "explore",
                "assigned_research": None,
                "research_queue": (),
                "research_assignments": (),
            }
        )
        self.opportunity_drive_core = _merge_optional(
            self.opportunity_drive_core,
            drive_core,
            "Scout snapshots disagree on the research director state",
        )
        _merge_unique(
            self.research_queue,
            [],
            drive.research_queue,
            lambda item: (item.opportunity_id, item.question_id),
            "Scout snapshots disagree on a research queue item",
        )
        _merge_unique(
            self.research_assignments,
            [],
            drive.research_assignments,
            lambda item: item.scout_id,
            "Scout snapshots disagree on a research assignment",
        )

    def _add_collections(self, frozen: FrozenScoutInput) -> None:
        specs = (
            (
                self.evidence_by_id,
                self.evidence,
                frozen.evidence,
                lambda x: x.evidence_id,
                "Scout snapshots disagree on frozen evidence",
            ),
            (
                self.opportunities_by_id,
                self.opportunities,
                frozen.prior_opportunities,
                lambda x: x.opportunity_id,
                "Scout snapshots disagree on prior Opportunity",
            ),
            (
                self.memories_by_scout,
                self.memories,
                frozen.trader_mind_memories,
                lambda x: x.scout_id,
                "Scout snapshots disagree on Trader Mind memory",
            ),
            (
                self.feedback_by_scout,
                self.feedback,
                frozen.alpha_feedback,
                lambda x: x.scout_id,
                "Scout snapshots disagree on Alpha feedback",
            ),
            (
                self.incentives_by_scout,
                self.incentives,
                frozen.research_incentives,
                lambda x: x.scout_id,
                "Scout snapshots disagree on research incentive",
            ),
        )
        for target, ordered, items, key, message in specs:
            _merge_unique(target, ordered, items, key, message)

    def _add_optional_state(self, frozen: FrozenScoutInput) -> None:
        self.research_attention = _merge_optional(
            self.research_attention,
            frozen.research_attention_portfolio,
            "Scout snapshots disagree on research attention portfolio",
        )
        self.opportunity_continuity = _merge_optional(
            self.opportunity_continuity,
            frozen.opportunity_continuity,
            "Scout snapshots disagree on Opportunity continuity",
        )
        agenda = frozen.market_research_agenda
        if agenda is None:
            return
        self.market_agenda = agenda
        self.market_agenda_base = _merge_optional(
            self.market_agenda_base,
            agenda.model_copy(update={"seeds": ()}),
            "Scout snapshots disagree on market research agenda",
        )
        _merge_unique(
            self.market_seeds_by_id,
            self.market_seeds,
            agenda.seeds,
            lambda item: item.seed_id,
            "Scout snapshots disagree on market research seed",
        )

    def rebuild_drive(self) -> OpportunityDrive:
        ordered_queue = tuple(
            sorted(
                self.research_queue.values(),
                key=lambda item: (
                    -item.priority_score,
                    item.remaining_days,
                    item.opportunity_id,
                    item.question_id,
                ),
            )
        )
        positions = {
            (item.opportunity_id, item.question_id): index
            for index, item in enumerate(ordered_queue)
        }
        if any(
            (item.opportunity_id, item.question_id) not in positions
            for item in self.research_assignments.values()
        ):
            raise FrozenCycleSnapshotError(
                "Scout snapshots contain an orphaned research assignment"
            )
        assignments = tuple(
            sorted(
                self.research_assignments.values(),
                key=lambda item: positions[(item.opportunity_id, item.question_id)],
            )
        )
        if self.opportunity_drive_core is None:
            raise FrozenCycleSnapshotError(
                "incomplete cycle is missing its research director state"
            )
        try:
            return OpportunityDrive.model_validate(
                {
                    **self.opportunity_drive_core.model_dump(mode="python"),
                    "research_queue": ordered_queue,
                    "research_assignments": assignments,
                }
            )
        except ValueError as error:
            raise FrozenCycleSnapshotError(
                "incomplete cycle has an invalid research director state"
            ) from error

    def rebuild_wake(self, base: FrozenScoutInput) -> FrozenScoutInput:
        agenda = self.market_agenda
        if agenda is not None:
            agenda = agenda.model_copy(
                update={
                    "seeds": tuple(
                        sorted(
                            self.market_seeds,
                            key=lambda item: item.assigned_scout_id,
                        )
                    )
                }
            )
        try:
            return FrozenScoutInput.model_validate(
                base.model_copy(
                    update={
                        "evidence": tuple(self.evidence),
                        "prior_opportunities": tuple(self.opportunities),
                        "trader_mind_memories": tuple(self.memories),
                        "alpha_feedback": tuple(self.feedback),
                        "research_incentives": tuple(self.incentives),
                        "research_attention_portfolio": self.research_attention,
                        "opportunity_continuity": self.opportunity_continuity,
                        "opportunity_drive": self.rebuild_drive(),
                        "market_research_agenda": agenda,
                    }
                ).model_dump(mode="python")
            )
        except ValueError as error:
            raise FrozenCycleSnapshotError(
                "incomplete cycle cannot rebuild a valid frozen wake"
            ) from error


def _legacy_postures(rows) -> dict[str, str]:
    postures = {}
    for source_id, posture in rows:
        existing = postures.get(source_id)
        if existing is not None and existing != posture:
            raise FrozenCycleSnapshotError(
                "incomplete cycle has conflicting source posture snapshots"
            )
        postures[source_id] = posture
    if not postures:
        raise FrozenCycleSnapshotError(
            "incomplete cycle is missing its source posture snapshot"
        )
    return postures


def recover_frozen_wake(
    database: Database, cycle_id: str
) -> tuple[FrozenScoutInput, dict[str, str]] | None:
    """Rebuild an incomplete cycle only from its immutable Scout snapshots."""
    roles = tuple(item.scout_id for item in SCOUTS)
    snapshots, runs, posture_rows = _load_recovery_rows(database, cycle_id)
    if len(snapshots) > 1:
        raise FrozenCycleSnapshotError("cycle has duplicate global frozen snapshots")
    if snapshots:
        return _recover_global_snapshot(snapshots[0], runs, cycle_id, roles)
    if not runs:
        return None
    by_role = _legacy_role_inputs(runs, roles)
    accumulator = _LegacyWakeAccumulator()
    for role in roles:
        accumulator.add(by_role[role])
    return accumulator.rebuild_wake(by_role[roles[0]]), _legacy_postures(posture_rows)
