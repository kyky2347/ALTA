import hashlib
import math
import re
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ResearchMode = Literal["explore", "follow_up"]
OpportunityDrivePosture = Literal[
    "balanced",
    "expand_search",
    "resolve_backlog",
]
ResearchQuestionOrigin = Literal[
    "scout_next_test",
    "thesis_pillar",
    "disconfirming_assessor",
    "thesis_assessor",
    "first_rejection",
]
ResearchPriorityReason = Literal[
    "forming",
    "ranked",
    "disconfirming",
    "pillar",
    "thesis_assessor",
    "rejection",
    "next_test",
    "urgent",
    "near",
    "open",
]

MAX_OPEN_RESEARCH_QUESTIONS = 2
MAX_DRIVE_IDLE_STREAK = 12
MAX_DRIVE_PRIORITY_OPPORTUNITIES = 2
MAX_DRIVE_FOLLOW_UP_SCOUTS = 2
MAX_RESEARCH_QUEUE_ITEMS = 2


class OpenResearchQuestion(BaseModel):
    """A bounded non-Evidence question handed to the next research cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    origin: ResearchQuestionOrigin
    prompt: str = Field(min_length=3, max_length=160)


class ResearchQueueInput(BaseModel):
    """Minimal point-in-time Opportunity state used to allocate research."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str = Field(min_length=3, max_length=128)
    status: Literal["forming", "ranked", "shadow", "closed", "rejected"]
    known_at: datetime
    horizon_days: int = Field(ge=1, le=365)
    research_questions: tuple[OpenResearchQuestion, ...] = Field(
        default=(), max_length=MAX_OPEN_RESEARCH_QUESTIONS
    )

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "research queue Opportunity known_at must be timezone-aware"
            )
        return value


class ResearchQueueItem(BaseModel):
    """A replayable research priority; never Evidence or a trading signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str = Field(min_length=3, max_length=128)
    question_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    priority_score: int = Field(ge=0, le=100)
    remaining_days: int = Field(ge=1, le=365)
    reason_codes: tuple[ResearchPriorityReason, ...] = Field(min_length=3, max_length=3)


class ResearchAssignment(BaseModel):
    """An exact queue item assigned to one Trader Mind for this wake."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scout_id: str = Field(min_length=3, max_length=64)
    opportunity_id: str = Field(min_length=3, max_length=128)
    question_id: str = Field(pattern=r"^[a-f0-9]{16}$")


class OpportunityDrive(BaseModel):
    """Deterministic process pressure for exploration and follow-up allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["alta-opportunity-drive-v2"] = "alta-opportunity-drive-v2"
    posture: OpportunityDrivePosture = "balanced"
    idle_streak: int = Field(default=0, ge=0, le=MAX_DRIVE_IDLE_STREAK)
    assigned_mode: ResearchMode = "explore"
    route_change_required: bool = False
    research_queue: tuple[ResearchQueueItem, ...] = Field(
        default=(), max_length=MAX_RESEARCH_QUEUE_ITEMS
    )
    research_assignments: tuple[ResearchAssignment, ...] = Field(
        default=(), max_length=MAX_DRIVE_FOLLOW_UP_SCOUTS
    )
    assigned_research: ResearchAssignment | None = None

    @model_validator(mode="after")
    def research_allocation_is_consistent(self) -> "OpportunityDrive":
        queue_keys = {
            (item.opportunity_id, item.question_id): item
            for item in self.research_queue
        }
        if len(queue_keys) != len(self.research_queue):
            raise ValueError("research queue items must be unique")
        assignment_scouts = [item.scout_id for item in self.research_assignments]
        assignment_keys = [
            (item.opportunity_id, item.question_id)
            for item in self.research_assignments
        ]
        if len(assignment_scouts) != len(set(assignment_scouts)):
            raise ValueError("research assignments require unique Trader Minds")
        if len(assignment_keys) != len(set(assignment_keys)):
            raise ValueError("research assignments require unique questions")
        for assignment in self.research_assignments:
            queued = queue_keys.get((assignment.opportunity_id, assignment.question_id))
            if queued is None:
                raise ValueError(
                    "research assignment must exactly match its queue item"
                )
        queue_opportunity_ids = tuple(
            dict.fromkeys(item.opportunity_id for item in self.research_queue)
        )
        if len(queue_opportunity_ids) > MAX_DRIVE_PRIORITY_OPPORTUNITIES:
            raise ValueError("research queue exceeds the Opportunity priority bound")
        if self.assigned_research is not None:
            if self.assigned_research not in self.research_assignments:
                raise ValueError("assigned research must exist in global assignments")
            if self.assigned_mode != "follow_up":
                raise ValueError("assigned research requires follow_up mode")
        elif self.assigned_mode == "follow_up":
            raise ValueError("follow_up mode requires an exact research assignment")
        return self

    @property
    def priority_opportunity_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.opportunity_id for item in self.research_queue))

    @property
    def follow_up_scout_ids(self) -> tuple[str, ...]:
        return tuple(item.scout_id for item in self.research_assignments)

    def for_scout(self, scout_id: str) -> "OpportunityDrive":
        assignment = next(
            (item for item in self.research_assignments if item.scout_id == scout_id),
            None,
        )
        assigned_mode: ResearchMode = "follow_up" if assignment else "explore"
        queue = (
            tuple(
                item
                for item in self.research_queue
                if assignment is not None
                and item.opportunity_id == assignment.opportunity_id
                and item.question_id == assignment.question_id
            )
            if assignment is not None
            else ()
        )
        return self.model_copy(
            update={
                "assigned_mode": assigned_mode,
                "assigned_research": assignment,
                "research_queue": queue,
                "research_assignments": (assignment,) if assignment else (),
            }
        )

    def restrict_to_opportunities(
        self, opportunity_ids: set[str]
    ) -> "OpportunityDrive":
        queue = tuple(
            item
            for item in self.research_queue
            if item.opportunity_id in opportunity_ids
        )
        queue_keys = {(item.opportunity_id, item.question_id) for item in queue}
        assignments = tuple(
            item
            for item in self.research_assignments
            if (item.opportunity_id, item.question_id) in queue_keys
        )
        assigned = (
            self.assigned_research if self.assigned_research in assignments else None
        )
        update = {
            "research_queue": queue,
            "research_assignments": assignments,
            "assigned_research": assigned,
            "assigned_mode": "follow_up" if assigned is not None else "explore",
        }
        if not queue:
            update.update(
                {
                    "posture": (
                        "expand_search" if self.route_change_required else "balanced"
                    ),
                }
            )
        return self.model_copy(update=update)


_STATUS_WEIGHT = {"forming": 25, "ranked": 20}
_STATUS_REASON: dict[str, ResearchPriorityReason] = {
    "forming": "forming",
    "ranked": "ranked",
}
_ORIGIN_WEIGHT = {
    "disconfirming_assessor": 40,
    "thesis_pillar": 34,
    "thesis_assessor": 32,
    "first_rejection": 30,
    "scout_next_test": 26,
}
_ORIGIN_REASON: dict[str, ResearchPriorityReason] = {
    "disconfirming_assessor": "disconfirming",
    "thesis_pillar": "pillar",
    "thesis_assessor": "thesis_assessor",
    "first_rejection": "rejection",
    "scout_next_test": "next_test",
}


def _urgency(remaining_days: int) -> tuple[int, ResearchPriorityReason]:
    if remaining_days <= 3:
        return 30, "urgent"
    if remaining_days <= 14:
        return 22, "near"
    return 10, "open"


def build_research_queue(
    *,
    wake_at: datetime,
    opportunities: tuple[ResearchQueueInput, ...],
) -> tuple[ResearchQueueItem, ...]:
    """Prioritize exact questions by decision value and horizon, not conviction."""

    if wake_at.tzinfo is None or wake_at.utcoffset() is None:
        raise ValueError("research queue wake_at must be timezone-aware")
    candidates: list[ResearchQueueItem] = []
    for opportunity in opportunities:
        if opportunity.status not in _STATUS_WEIGHT or opportunity.known_at >= wake_at:
            continue
        expires_at = opportunity.known_at + timedelta(days=opportunity.horizon_days)
        remaining_seconds = (expires_at - wake_at).total_seconds()
        if remaining_seconds <= 0:
            continue
        remaining_days = min(365, max(1, math.ceil(remaining_seconds / 86_400)))
        urgency_weight, urgency_reason = _urgency(remaining_days)
        for question in opportunity.research_questions:
            score = min(
                100,
                _STATUS_WEIGHT[opportunity.status]
                + _ORIGIN_WEIGHT[question.origin]
                + urgency_weight,
            )
            candidates.append(
                ResearchQueueItem(
                    opportunity_id=opportunity.opportunity_id,
                    question_id=question.question_id,
                    priority_score=score,
                    remaining_days=remaining_days,
                    reason_codes=(
                        _STATUS_REASON[opportunity.status],
                        _ORIGIN_REASON[question.origin],
                        urgency_reason,
                    ),
                )
            )
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item.priority_score,
            item.remaining_days,
            item.opportunity_id,
            item.question_id,
        ),
    )
    selected: list[ResearchQueueItem] = []
    represented: set[str] = set()
    for item in ordered:
        if item.opportunity_id in represented:
            continue
        represented.add(item.opportunity_id)
        selected.append(item)
        if len(represented) == MAX_DRIVE_PRIORITY_OPPORTUNITIES:
            break
    for item in ordered:
        if item in selected or item.opportunity_id not in represented:
            continue
        selected.append(item)
        if len(selected) == MAX_RESEARCH_QUEUE_ITEMS:
            break
    return tuple(selected[:MAX_RESEARCH_QUEUE_ITEMS])


def build_opportunity_drive(
    *,
    cycle_id: str,
    idle_streak: int,
    research_queue: tuple[ResearchQueueItem, ...],
    scout_ids: tuple[str, ...],
) -> OpportunityDrive:
    """Allocate exact follow-ups while preserving independent discovery seats."""

    bounded_idle_streak = min(max(idle_streak, 0), MAX_DRIVE_IDLE_STREAK)
    queue = tuple(research_queue[:MAX_RESEARCH_QUEUE_ITEMS])
    if queue and scout_ids:
        digest = hashlib.sha256(cycle_id.encode()).digest()
        offset = int.from_bytes(digest[:4], "big") % len(scout_ids)
        follow_up_count = min(
            MAX_DRIVE_FOLLOW_UP_SCOUTS,
            len(queue),
            max(0, len(scout_ids) - 2),
        )
        follow_up_scout_ids = tuple(
            scout_ids[(offset + index) % len(scout_ids)]
            for index in range(follow_up_count)
        )
        assignments = tuple(
            ResearchAssignment(
                scout_id=scout_id,
                opportunity_id=item.opportunity_id,
                question_id=item.question_id,
            )
            for scout_id, item in zip(
                follow_up_scout_ids, queue[:follow_up_count], strict=True
            )
        )
        return OpportunityDrive(
            posture="resolve_backlog",
            idle_streak=bounded_idle_streak,
            route_change_required=bounded_idle_streak >= 2,
            research_queue=queue,
            research_assignments=assignments,
        )
    if bounded_idle_streak >= 2:
        return OpportunityDrive(
            posture="expand_search",
            idle_streak=bounded_idle_streak,
            route_change_required=True,
        )
    return OpportunityDrive(idle_streak=bounded_idle_streak)


def _bounded_question(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= 160:
        return normalized
    return normalized[:160].rstrip()


def _identity(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


def research_question_id(
    opportunity_id: str, origin: ResearchQuestionOrigin, prompt: str
) -> str:
    """Return the stable identity of one bounded Opportunity question."""

    return hashlib.sha256(
        f"{opportunity_id}\0{origin}\0{_identity(_bounded_question(prompt))}".encode()
    ).hexdigest()[:16]


def build_open_research_questions(
    *,
    opportunity_id: str,
    next_test: str | None,
    first_rejection: str | None,
    assessor_questions: tuple[tuple[str, str], ...] = (),
    thesis_questions: tuple[str, ...] = (),
) -> tuple[OpenResearchQuestion, ...]:
    """Build a deterministic, high-information agenda without ranking an idea."""

    ordered: list[tuple[ResearchQuestionOrigin, str]] = []
    if next_test:
        ordered.append(("scout_next_test", next_test))
    ordered.extend(
        ("disconfirming_assessor", question)
        for assessor, question in assessor_questions
        if assessor == "disconfirming_assessor" and question
    )
    ordered.extend(("thesis_pillar", question) for question in thesis_questions)
    ordered.extend(
        ("thesis_assessor", question)
        for assessor, question in assessor_questions
        if assessor == "thesis_assessor" and question
    )
    if first_rejection:
        ordered.append(("first_rejection", first_rejection))

    questions: list[OpenResearchQuestion] = []
    seen: set[str] = set()
    for origin, raw_prompt in ordered:
        prompt = _bounded_question(raw_prompt)
        identity = _identity(prompt)
        if len(identity) < 3 or identity in seen:
            continue
        seen.add(identity)
        questions.append(
            OpenResearchQuestion(
                question_id=research_question_id(opportunity_id, origin, prompt),
                origin=origin,
                prompt=prompt,
            )
        )
        if len(questions) == MAX_OPEN_RESEARCH_QUESTIONS:
            break
    return tuple(questions)
