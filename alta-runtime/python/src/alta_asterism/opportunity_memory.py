from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .research_agenda import MAX_OPEN_RESEARCH_QUESTIONS, OpenResearchQuestion


class PriorOpportunitySnapshot(BaseModel):
    """Bounded registry memory supplied to Scouts; never research Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str = Field(min_length=3, max_length=128)
    version: int = Field(ge=1)
    known_at: datetime
    title: str = Field(min_length=1, max_length=256)
    entity_key: str | None = Field(default=None, max_length=128)
    direction: Literal["positive", "negative", "neutral", "unknown"]
    status: Literal["forming", "ranked", "shadow", "closed", "rejected"]
    summary: str = Field(min_length=1, max_length=480)
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    research_questions: tuple[OpenResearchQuestion, ...] = Field(
        default=(), max_length=MAX_OPEN_RESEARCH_QUESTIONS
    )

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("prior Opportunity known_at must be timezone-aware")
        return value
