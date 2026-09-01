import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .cycle_recovery import recover_frozen_wake
from .database import Database
from .expression import contract_hash
from .mind_worker import MindClient
from .mvp_fixture import MvpFixture
from .mvp_research_flow import MvpResearchFlow, ResearchRuntimeConfig
from .mvp_shadow_flow import MvpShadowFlow
from .mvp_source_flow import MvpSourceFlow, SourcePosture
from .ranking import RankingBook

STAGES = (
    "schedule_wake",
    "scouts",
    "foundry",
    "private_assessment_debate",
    "ranking",
    "expression",
    "shadow_open",
    "monitor_exit",
)
MAX_EXPRESSION_ATTEMPTS = 3


class MvpFaultInjected(RuntimeError):
    pass


class MvpRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    demo_id: str
    status: Literal["MVP_RUNNING", "MVP_IDLE"] = "MVP_RUNNING"
    replayed: bool
    replay_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_postures: dict[str, SourcePosture]
    scout_statuses: dict[str, str]
    candidate_ids: tuple[str, ...]
    opportunity_ids: tuple[str, ...]
    top_opportunity_id: str | None
    selected_opportunity_id: str | None
    expression_id: str | None
    shadow_position_id: str | None
    event_cursor: int = Field(ge=1)


class MvpOrchestrator:
    def __init__(
        self,
        database: Database,
        fixture: MvpFixture,
        mind_client: MindClient,
        *,
        source_flow=None,
        shadow_flow=None,
        research_config: ResearchRuntimeConfig | None = None,
        role_runner=None,
        deliberator=None,
    ) -> None:
        self.database = database
        self.fixture = fixture
        self.source = source_flow or MvpSourceFlow(database, fixture)
        self.research = MvpResearchFlow(
            database,
            mind_client,
            config=research_config,
            role_runner=role_runner,
            deliberator=deliberator,
        )
        self.shadow = shadow_flow or MvpShadowFlow(database, fixture)
        self.use_wall_clock = bool(research_config and research_config.use_wall_clock)

    def run(
        self,
        demo_id: str,
        wake_at: datetime,
        *,
        source_overrides: dict[str, SourcePosture] | None = None,
        fault_after_stage: str | None = None,
    ) -> MvpRunResult:
        self._validate_request(demo_id, wake_at, source_overrides, fault_after_stage)
        completed = self._completed_result(demo_id)
        if completed is not None:
            return completed.model_copy(update={"replayed": True})

        recovered_wake = recover_frozen_wake(self.database, demo_id)
        if recovered_wake is None:
            frozen_input, source_postures = self.source.schedule_and_wake(
                demo_id, wake_at, source_overrides or {}
            )
        else:
            frozen_input, source_postures = recovered_wake
        monitored_positions: tuple[str, ...] = ()
        monitor_existing = getattr(self.shadow, "monitor_existing", None)
        if monitor_existing is not None:
            monitored_positions = monitor_existing(demo_id, wake_at, frozen_input)
        self._checkpoint(demo_id, "schedule_wake", wake_at, fault_after_stage)

        outcomes = self.research.run_scouts(
            demo_id, frozen_input, source_postures=source_postures
        )
        scout_statuses = {item.scout_id: item.status for item in outcomes}
        self._checkpoint(
            demo_id,
            "scouts",
            self._stage_time(wake_at, 4),
            fault_after_stage,
        )

        candidates, opportunities = self.research.materialize_candidates(
            demo_id, outcomes, wake_at
        )
        self._checkpoint(
            demo_id,
            "foundry",
            self._stage_time(wake_at, 7),
            fault_after_stage,
        )
        if not opportunities:
            return self._complete_idle(
                demo_id,
                wake_at,
                source_postures,
                scout_statuses,
                candidates,
                fault_after_stage,
                monitored_positions,
            )

        assessments, discussions = self.research.assess_and_debate(
            demo_id, opportunities, wake_at
        )
        self._checkpoint(
            demo_id,
            "private_assessment_debate",
            self._stage_time(wake_at, 11),
            fault_after_stage,
        )

        book = self.research.rank(
            demo_id, opportunities, assessments, discussions, wake_at
        )
        self._checkpoint(
            demo_id,
            "ranking",
            self._stage_time(wake_at, 13),
            fault_after_stage,
        )
        if not book.items:
            return self._complete_idle(
                demo_id,
                wake_at,
                source_postures,
                scout_statuses,
                candidates,
                fault_after_stage,
                monitored_positions,
                opportunities=opportunities,
                book=book,
                idle_reason="no_opportunity_ranked",
            )

        ranked_top = next(
            item
            for item in opportunities
            if item.opportunity_id == book.items[0].opportunity_id
        )
        opportunities_by_id = {item.opportunity_id: item for item in opportunities}
        expression_attempts = []
        first_proposal = None
        selected_opportunity = None
        selected_proposal = None
        for ranked_item in book.items[:MAX_EXPRESSION_ATTEMPTS]:
            opportunity = opportunities_by_id[ranked_item.opportunity_id]
            candidate_proposal = self.shadow.express(demo_id, opportunity, wake_at)
            if first_proposal is None:
                first_proposal = candidate_proposal
            expression_attempts.append(
                [
                    opportunity.opportunity_id,
                    candidate_proposal.expression_id,
                    candidate_proposal.kind,
                ]
            )
            if candidate_proposal.kind != "wait":
                selected_opportunity = opportunity
                selected_proposal = candidate_proposal
                break
        proposal = selected_proposal or first_proposal
        if proposal is None:
            raise ValueError("ranked book did not produce an expression attempt")
        action_opportunity = selected_opportunity or ranked_top
        self._checkpoint(
            demo_id,
            "expression",
            self._stage_time(wake_at, 17),
            fault_after_stage,
        )

        shadow_position_id = None
        ledger_hashes: list[str] = []
        if proposal.kind == "wait":
            self._checkpoint(
                demo_id,
                "shadow_open",
                self._stage_time(wake_at, 20),
                fault_after_stage,
            )
            self._checkpoint(
                demo_id,
                "monitor_exit",
                self._stage_time(wake_at, 36),
                fault_after_stage,
            )
        else:
            opened = self.shadow.open_shadow(
                demo_id, action_opportunity, proposal, wake_at
            )
            if opened is not None:
                thesis, open_ledger = opened
                shadow_position_id = thesis.position_id
                ledger_hashes.append(open_ledger.hash())
            self._checkpoint(
                demo_id,
                "shadow_open",
                self._stage_time(wake_at, 20),
                fault_after_stage,
            )

            if opened is not None and not getattr(
                self.shadow, "defer_position_monitoring", False
            ):
                close_ledger = self.shadow.monitor_and_exit(
                    demo_id, proposal, thesis, open_ledger, wake_at
                )
                ledger_hashes.append(close_ledger.hash())
            self._checkpoint(
                demo_id,
                "monitor_exit",
                self._stage_time(wake_at, 36),
                fault_after_stage,
            )

        snapshot = {
            "fixture_version": self.fixture.fixture_version,
            "demo_id": demo_id,
            "source_postures": source_postures,
            "scout_statuses": scout_statuses,
            "candidate_ids": [item.candidate_id for item in candidates],
            "opportunities": [
                [item.opportunity_id, item.snapshot_hash] for item in opportunities
            ],
            "ranking": self._ranking_snapshot(book),
            "top_opportunity_id": ranked_top.opportunity_id,
            "selected_opportunity_id": (
                selected_opportunity.opportunity_id
                if selected_opportunity is not None
                else None
            ),
            "expression_attempts": expression_attempts,
            "expression": [proposal.expression_id, proposal.hash()],
            "shadow_position_id": shadow_position_id,
            "ledger": ledger_hashes,
            "monitored_position_ids": list(monitored_positions),
            "capital_mode": self.shadow.capital_mode,
        }
        replay_hash = contract_hash(snapshot)
        self._persist_completion(demo_id, wake_at, snapshot, replay_hash)
        result = self._completed_result(demo_id)
        if result is None:
            raise ValueError("MVP completion event was not persisted")
        return result

    def replay(self, demo_id: str) -> MvpRunResult:
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", demo_id) is None:
            raise ValueError("demo_id must be an explicit bounded identifier")
        completed = self._completed_result(demo_id)
        if completed is None:
            raise ValueError("completed replay snapshot does not exist")
        return completed.model_copy(update={"replayed": True})

    @staticmethod
    def _validate_request(
        demo_id: str,
        wake_at: datetime,
        source_overrides: dict[str, SourcePosture] | None,
        fault_after_stage: str | None,
    ) -> None:
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", demo_id) is None:
            raise ValueError("demo_id must be an explicit bounded identifier")
        if wake_at.tzinfo is None or wake_at.utcoffset() is None:
            raise ValueError("wake_at must be timezone-aware")
        if fault_after_stage is not None and fault_after_stage not in STAGES:
            raise ValueError("fault_after_stage is unknown")
        if source_overrides is not None and any(
            value not in ("healthy", "disabled", "stale")
            for value in source_overrides.values()
        ):
            raise ValueError("source posture is unknown")

    @staticmethod
    def _ranking_snapshot(book: RankingBook) -> list[list]:
        return [
            [item.opportunity_id, item.position, item.score, item.snapshot_hash]
            for item in book.items
        ]

    def _checkpoint(
        self,
        demo_id: str,
        stage: str,
        known_at: datetime,
        fault_after_stage: str | None,
    ) -> None:
        self._append_stage_event(
            demo_id,
            "mvp.stage.completed",
            stage,
            known_at,
        )
        if fault_after_stage == stage:
            raise MvpFaultInjected(f"fixture crash after {stage}")

    def _append_stage_event(
        self,
        demo_id: str,
        event_type: str,
        stage: str,
        known_at: datetime,
        reason: str | None = None,
    ) -> None:
        payload = {"demo_id": demo_id, "stage": stage}
        if reason is not None:
            payload["reason"] = reason
        event = _contract_event(
            event_type=event_type,
            aggregate_type="mvp_pipeline",
            aggregate_id=demo_id,
            environment=Environment.SHADOW,
            known_at=known_at,
            payload=payload,
            correlation_id=demo_id,
        )
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT known_at FROM ops.event WHERE id = %s", (event.id,)
            ).fetchone()
            if existing is not None:
                event = event.model_copy(update={"known_at": existing[0]})
            _append_event(connection, event)

    def _stage_time(self, wake_at: datetime, offset_seconds: int) -> datetime:
        if self.use_wall_clock:
            return datetime.now(UTC)
        return wake_at + timedelta(seconds=offset_seconds)

    def _complete_idle(
        self,
        demo_id: str,
        wake_at: datetime,
        source_postures: dict[str, SourcePosture],
        scout_statuses: dict[str, str],
        candidates: tuple,
        fault_after_stage: str | None,
        monitored_positions: tuple[str, ...] = (),
        *,
        opportunities: tuple = (),
        book: RankingBook | None = None,
        idle_reason: str = "no_opportunity_survived",
    ) -> MvpRunResult:
        skipped_stages = (
            (
                (11, "private_assessment_debate"),
                (13, "ranking"),
                (17, "expression"),
                (20, "shadow_open"),
                (36, "monitor_exit"),
            )
            if book is None
            else (
                (17, "expression"),
                (20, "shadow_open"),
                (36, "monitor_exit"),
            )
        )
        for offset, stage in skipped_stages:
            known_at = self._stage_time(wake_at, offset)
            self._append_stage_event(
                demo_id,
                "mvp.stage.skipped",
                stage,
                known_at,
                idle_reason,
            )
            if fault_after_stage == stage:
                raise MvpFaultInjected(f"fixture crash after {stage}")
        snapshot = {
            "status": "MVP_IDLE",
            "fixture_version": self.fixture.fixture_version,
            "demo_id": demo_id,
            "source_postures": source_postures,
            "scout_statuses": scout_statuses,
            "candidate_ids": [item.candidate_id for item in candidates],
            "opportunities": [
                [item.opportunity_id, item.snapshot_hash] for item in opportunities
            ],
            "ranking": self._ranking_snapshot(book) if book is not None else [],
            "top_opportunity_id": None,
            "selected_opportunity_id": None,
            "expression_attempts": [],
            "expression": None,
            "shadow_position_id": None,
            "ledger": [],
            "monitored_position_ids": list(monitored_positions),
            "capital_mode": self.shadow.capital_mode,
            "idle_reason": idle_reason,
        }
        replay_hash = contract_hash(snapshot)
        self._persist_completion(demo_id, wake_at, snapshot, replay_hash)
        result = self._completed_result(demo_id)
        if result is None:
            raise ValueError("MVP idle completion event was not persisted")
        return result

    def _persist_completion(
        self,
        demo_id: str,
        wake_at: datetime,
        snapshot: dict,
        replay_hash: str,
    ) -> None:
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="mvp.pipeline.completed",
                    aggregate_type="mvp_pipeline",
                    aggregate_id=demo_id,
                    environment=Environment.SHADOW,
                    known_at=self._stage_time(wake_at, 37),
                    payload={"snapshot": snapshot, "replay_hash": replay_hash},
                    correlation_id=demo_id,
                ),
            )

    def _completed_result(self, demo_id: str) -> MvpRunResult | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT sequence, payload FROM ops.event
                WHERE aggregate_id = %s
                AND event_type = 'mvp.pipeline.completed'
                ORDER BY sequence DESC LIMIT 1""",
                (demo_id,),
            ).fetchone()
        if row is None:
            return None
        payload = row[1]
        snapshot = payload["snapshot"]
        if contract_hash(snapshot) != payload["replay_hash"]:
            raise ValueError("MVP replay snapshot hash mismatch")
        opportunity_ids = tuple(item[0] for item in snapshot["opportunities"])
        expression = snapshot.get("expression")
        return MvpRunResult(
            demo_id=demo_id,
            status=snapshot.get("status", "MVP_RUNNING"),
            replayed=False,
            replay_hash=payload["replay_hash"],
            source_postures=snapshot["source_postures"],
            scout_statuses=snapshot["scout_statuses"],
            candidate_ids=tuple(snapshot["candidate_ids"]),
            opportunity_ids=opportunity_ids,
            top_opportunity_id=snapshot.get("top_opportunity_id"),
            selected_opportunity_id=snapshot.get("selected_opportunity_id"),
            expression_id=expression[0] if expression else None,
            shadow_position_id=snapshot["shadow_position_id"],
            event_cursor=row[0],
        )
