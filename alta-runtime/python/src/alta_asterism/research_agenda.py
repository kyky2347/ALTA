import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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

MAX_OPEN_RESEARCH_QUESTIONS = 2
MAX_DRIVE_IDLE_STREAK = 12
MAX_DRIVE_PRIORITY_OPPORTUNITIES = 2
MAX_DRIVE_FOLLOW_UP_SCOUTS = 2


class OpportunityDrive(BaseModel):
    """Deterministic process pressure for exploration and follow-up allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["alta-opportunity-drive-v1"] = "alta-opportunity-drive-v1"
    posture: OpportunityDrivePosture = "balanced"
    idle_streak: int = Field(default=0, ge=0, le=MAX_DRIVE_IDLE_STREAK)
    assigned_mode: ResearchMode = "explore"
    route_change_required: bool = False
    priority_opportunity_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_DRIVE_PRIORITY_OPPORTUNITIES
    )
    follow_up_scout_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_DRIVE_FOLLOW_UP_SCOUTS
    )
    directive: str = Field(
        default=(
            "Continue independent discovery; follow an existing Opportunity only "
            "when its frozen open question fits this Mind."
        ),
        min_length=3,
        max_length=320,
    )

    def for_scout(self, scout_id: str) -> "OpportunityDrive":
        assigned_mode: ResearchMode = (
            "follow_up"
            if scout_id in self.follow_up_scout_ids and self.priority_opportunity_ids
            else "explore"
        )
        return self.model_copy(update={"assigned_mode": assigned_mode})


def build_opportunity_drive(
    *,
    cycle_id: str,
    idle_streak: int,
    priority_opportunity_ids: tuple[str, ...],
    scout_ids: tuple[str, ...],
) -> OpportunityDrive:
    """Allocate bounded research effort without turning history into Evidence."""

    bounded_idle_streak = min(max(idle_streak, 0), MAX_DRIVE_IDLE_STREAK)
    priorities = tuple(
        dict.fromkeys(priority_opportunity_ids[:MAX_DRIVE_PRIORITY_OPPORTUNITIES])
    )
    if priorities and scout_ids:
        digest = hashlib.sha256(cycle_id.encode()).digest()
        offset = int.from_bytes(digest[:4], "big") % len(scout_ids)
        follow_up_count = min(MAX_DRIVE_FOLLOW_UP_SCOUTS, len(scout_ids))
        follow_up_scout_ids = tuple(
            scout_ids[(offset + index) % len(scout_ids)]
            for index in range(follow_up_count)
        )
        return OpportunityDrive(
            posture="resolve_backlog",
            idle_streak=bounded_idle_streak,
            route_change_required=bounded_idle_streak >= 2,
            priority_opportunity_ids=priorities,
            follow_up_scout_ids=follow_up_scout_ids,
            directive=(
                "Resolve one compatible frozen open question with genuinely new "
                "evidence if assigned follow_up; otherwise continue orthogonal "
                "discovery. Change route when recent cycles were idle."
            ),
        )
    if bounded_idle_streak >= 2:
        return OpportunityDrive(
            posture="expand_search",
            idle_streak=bounded_idle_streak,
            route_change_required=True,
            directive=(
                "Recent cycles found no actionable Opportunity. Change the entity, "
                "source class, or causal hypothesis before repeating prior work, "
                "while staying inside this Mind's mandate."
            ),
        )
    return OpportunityDrive(idle_streak=bounded_idle_streak)


class OpenResearchQuestion(BaseModel):
    """A bounded non-Evidence question handed to the next research cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    origin: ResearchQuestionOrigin
    prompt: str = Field(min_length=3, max_length=160)


def _bounded_question(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= 160:
        return normalized
    return normalized[:160].rstrip()


def _identity(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


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
    ordered.extend(("thesis_pillar", question) for question in thesis_questions)
    ordered.extend(
        ("disconfirming_assessor", question)
        for assessor, question in assessor_questions
        if assessor == "disconfirming_assessor" and question
    )
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
                question_id=hashlib.sha256(
                    f"{opportunity_id}\0{origin}\0{identity}".encode()
                ).hexdigest()[:16],
                origin=origin,
                prompt=prompt,
            )
        )
        if len(questions) == MAX_OPEN_RESEARCH_QUESTIONS:
            break
    return tuple(questions)
