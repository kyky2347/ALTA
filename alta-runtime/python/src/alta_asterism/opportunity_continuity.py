from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .opportunity_memory import PriorOpportunitySnapshot
from .research_agenda import ResearchQueueInput, ResearchQueueItem, build_research_queue


OPPORTUNITY_CONTINUITY_VERSION = "alta-opportunity-continuity-v2"
MAX_ACTIVE_OPPORTUNITY_SCAN = 32
MAX_FROZEN_OPPORTUNITIES = 4
EXPIRING_WINDOW_DAYS = 14

ContinuityPosture = Literal["empty", "healthy", "backlog", "expiring", "stale"]


def decision_deadline(opportunity: PriorOpportunitySnapshot) -> datetime:
    return opportunity.decision_deadline_at or (
        opportunity.known_at + timedelta(days=opportunity.horizon_days)
    )


class OpportunityContinuityPortfolio(BaseModel):
    """Point-in-time research continuity; process state, never Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[
        "alta-opportunity-continuity-v1", "alta-opportunity-continuity-v2"
    ] = OPPORTUNITY_CONTINUITY_VERSION
    known_at: datetime
    scan_limit: int = MAX_ACTIVE_OPPORTUNITY_SCAN
    frozen_limit: int = MAX_FROZEN_OPPORTUNITIES
    registry_active: int = Field(ge=0, le=100_000)
    scanned_active: int = Field(ge=0, le=MAX_ACTIVE_OPPORTUNITY_SCAN)
    frozen_active: int = Field(ge=0, le=MAX_FROZEN_OPPORTUNITIES)
    pending_questions: int = Field(ge=0, le=MAX_ACTIVE_OPPORTUNITY_SCAN * 2)
    deferred_questions: int = Field(default=0, ge=0, le=MAX_ACTIVE_OPPORTUNITY_SCAN * 2)
    next_research_due_at: datetime | None = None
    expiring_active: int = Field(ge=0, le=MAX_ACTIVE_OPPORTUNITY_SCAN)
    stale_active: int = Field(ge=0, le=MAX_ACTIVE_OPPORTUNITY_SCAN)
    oldest_active_days: int = Field(ge=0, le=3650)
    earliest_decision_deadline_at: datetime | None = None
    selected_opportunity_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_FROZEN_OPPORTUNITIES
    )
    priority_opportunity_ids: tuple[str, ...] = Field(default=(), max_length=2)
    selection_truncated: bool = False
    registry_scan_saturated: bool = False
    posture: ContinuityPosture
    warning: str = Field(min_length=3, max_length=400)

    @field_validator(
        "known_at", "earliest_decision_deadline_at", "next_research_due_at"
    )
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("opportunity continuity timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def counts_and_selection_are_consistent(self) -> OpportunityContinuityPortfolio:
        if self.frozen_active != len(self.selected_opportunity_ids):
            raise ValueError("continuity frozen count must match selected IDs")
        if len(set(self.selected_opportunity_ids)) != len(
            self.selected_opportunity_ids
        ):
            raise ValueError("continuity selected Opportunity IDs must be unique")
        if not set(self.priority_opportunity_ids).issubset(
            self.selected_opportunity_ids
        ):
            raise ValueError("continuity priorities must be frozen")
        if self.selection_truncated != (self.scanned_active > self.frozen_active):
            raise ValueError("continuity truncation flag does not match counts")
        if self.registry_active < self.scanned_active:
            raise ValueError("continuity registry count cannot be below its scan")
        if self.registry_scan_saturated != (self.registry_active > self.scanned_active):
            raise ValueError(
                "continuity registry saturation flag does not match counts"
            )
        if (self.deferred_questions > 0) != (self.next_research_due_at is not None):
            raise ValueError("deferred research requires an exact next due time")
        return self

    def public_summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "knownAt": self.known_at.isoformat(),
            "scanLimit": self.scan_limit,
            "frozenLimit": self.frozen_limit,
            "registryActive": self.registry_active,
            "scannedActive": self.scanned_active,
            "frozenActive": self.frozen_active,
            "pendingQuestions": self.pending_questions,
            "deferredQuestions": self.deferred_questions,
            "nextResearchDueAt": (
                self.next_research_due_at.isoformat()
                if self.next_research_due_at is not None
                else None
            ),
            "expiringActive": self.expiring_active,
            "staleActive": self.stale_active,
            "oldestActiveDays": self.oldest_active_days,
            "earliestDecisionDeadlineAt": (
                self.earliest_decision_deadline_at.isoformat()
                if self.earliest_decision_deadline_at is not None
                else None
            ),
            "selectedOpportunityIds": list(self.selected_opportunity_ids),
            "priorityOpportunityIds": list(self.priority_opportunity_ids),
            "selectionTruncated": self.selection_truncated,
            "registryScanSaturated": self.registry_scan_saturated,
            "posture": self.posture,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class OpportunityContinuitySelection:
    frozen_opportunities: tuple[PriorOpportunitySnapshot, ...]
    research_queue: tuple[ResearchQueueItem, ...]
    portfolio: OpportunityContinuityPortfolio


def build_opportunity_continuity(
    *,
    wake_at: datetime,
    opportunities: tuple[PriorOpportunitySnapshot, ...],
    registry_active: int | None = None,
    deferred_questions: int = 0,
    next_research_due_at: datetime | None = None,
) -> OpportunityContinuitySelection:
    """Select globally valuable follow-ups before applying the prompt byte bound."""

    if wake_at.tzinfo is None or wake_at.utcoffset() is None:
        raise ValueError("opportunity continuity wake must be timezone-aware")
    if len(opportunities) > MAX_ACTIVE_OPPORTUNITY_SCAN:
        raise ValueError("opportunity continuity exceeds its active scan limit")
    active_count = len(opportunities) if registry_active is None else registry_active
    if active_count < len(opportunities) or active_count > 100_000:
        raise ValueError("opportunity continuity registry count is invalid")
    if any(item.known_at >= wake_at for item in opportunities):
        raise ValueError("opportunity continuity cannot observe the current wake")
    if deferred_questions < 0 or deferred_questions > MAX_ACTIVE_OPPORTUNITY_SCAN * 2:
        raise ValueError("opportunity continuity deferred count is invalid")
    if (deferred_questions > 0) != (next_research_due_at is not None):
        raise ValueError("deferred research requires an exact next due time")

    queue = build_research_queue(
        wake_at=wake_at,
        opportunities=tuple(
            ResearchQueueInput(
                opportunity_id=item.opportunity_id,
                status=item.status,
                known_at=item.known_at,
                horizon_days=item.horizon_days,
                decision_deadline_at=item.decision_deadline_at,
                research_questions=item.research_questions,
            )
            for item in opportunities
        ),
    )
    priority_ids = tuple(dict.fromkeys(item.opportunity_id for item in queue))
    by_id = {item.opportunity_id: item for item in opportunities}
    selected = [by_id[item] for item in priority_ids]
    selected_ids = set(priority_ids)
    selected.extend(
        item
        for item in opportunities
        if item.opportunity_id not in selected_ids
        and len(selected) < MAX_FROZEN_OPPORTUNITIES
    )
    frozen = tuple(selected[:MAX_FROZEN_OPPORTUNITIES])

    deadlines = tuple(decision_deadline(item) for item in opportunities)
    stale = sum(deadline <= wake_at for deadline in deadlines)
    expiring = sum(
        wake_at < deadline <= wake_at + timedelta(days=EXPIRING_WINDOW_DAYS)
        for deadline in deadlines
    )
    oldest_days = max(
        (min(3650, max(0, (wake_at - item.known_at).days)) for item in opportunities),
        default=0,
    )
    truncated = len(opportunities) > len(frozen)
    if not opportunities:
        posture: ContinuityPosture = "empty"
        warning = "No active Opportunity requires continuity tracking."
    elif stale:
        posture = "stale"
        warning = (
            "At least one active Opportunity passed its frozen decision deadline; "
            "it is excluded from fresh capital decisions and retained for audit."
        )
    elif expiring:
        posture = "expiring"
        warning = (
            "At least one active Opportunity is inside its next fourteen-day "
            "decision window and receives deadline-aware follow-up priority."
        )
    elif truncated or active_count > len(opportunities):
        posture = "backlog"
        warning = (
            "The active registry exceeds a bounded research window; fixed deadlines "
            "are ordered before a bounded subset is frozen for the Trader Minds."
        )
    else:
        posture = "healthy"
        warning = (
            "Every active Opportunity fits the bounded continuity window; this "
            "state allocates research only and does not validate a thesis."
        )
    portfolio = OpportunityContinuityPortfolio(
        known_at=wake_at,
        registry_active=active_count,
        scanned_active=len(opportunities),
        frozen_active=len(frozen),
        pending_questions=sum(len(item.research_questions) for item in opportunities),
        deferred_questions=deferred_questions,
        next_research_due_at=next_research_due_at,
        expiring_active=expiring,
        stale_active=stale,
        oldest_active_days=oldest_days,
        earliest_decision_deadline_at=min(deadlines) if deadlines else None,
        selected_opportunity_ids=tuple(item.opportunity_id for item in frozen),
        priority_opportunity_ids=priority_ids,
        selection_truncated=truncated,
        registry_scan_saturated=active_count > len(opportunities),
        posture=posture,
        warning=warning,
    )
    return OpportunityContinuitySelection(
        frozen_opportunities=frozen,
        research_queue=queue,
        portfolio=portfolio,
    )


def load_latest_opportunity_continuity(
    database, environment: str
) -> dict[str, object] | None:
    """Load the newest frozen continuity state without recomputing history."""

    with database.connect() as connection:
        row = connection.execute(
            """SELECT frozen_input->'input'->'opportunity_continuity'
            FROM research.run
            WHERE environment = %s AND cycle_id LIKE 'live-%%'
              AND frozen_input->'input' ? 'opportunity_continuity'
              AND frozen_input->'input'->'opportunity_continuity' <> 'null'::jsonb
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            (environment,),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return OpportunityContinuityPortfolio.model_validate(row[0]).public_summary()
