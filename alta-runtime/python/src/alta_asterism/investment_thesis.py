from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_THESIS_PILLARS = 4


class ThesisPillarDraft(BaseModel):
    """One falsifiable causal claim proposed by a Trader Mind.

    A draft is research judgment, not a risk rule.  The original wording is
    frozen so later reviews can add evidence without rewriting the thesis.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=3, max_length=500)
    observable: str = Field(min_length=3, max_length=300)
    confirmation_condition: str = Field(min_length=3, max_length=500)
    invalidation_condition: str = Field(min_length=3, max_length=500)
    expected_by_days: int = Field(ge=1, le=365)


class ThesisPillar(BaseModel):
    """Point-in-time thesis claim carried into expression and monitoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pillar_id: str = Field(pattern=r"^pillar_[a-f0-9]{32}$")
    source_candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=3, max_length=500)
    observable: str = Field(min_length=3, max_length=300)
    confirmation_condition: str = Field(min_length=3, max_length=500)
    invalidation_condition: str = Field(min_length=3, max_length=500)
    known_at: datetime
    expected_by_days: int = Field(ge=1, le=365)
    due_at: datetime
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_point_in_time(self) -> "ThesisPillar":
        for value, name in ((self.known_at, "known_at"), (self.due_at, "due_at")):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"thesis pillar {name} must be timezone-aware")
        if self.due_at != self.known_at + timedelta(days=self.expected_by_days):
            raise ValueError("thesis pillar due_at does not match its frozen horizon")
        if len(set(self.source_candidate_ids)) != len(self.source_candidate_ids):
            raise ValueError("thesis pillar source candidates must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("thesis pillar evidence IDs must be unique")
        return self


def _identity(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


def pillar_identity(draft: ThesisPillarDraft) -> str:
    semantic_key = "\0".join(
        _identity(value)
        for value in (
            draft.statement,
            draft.observable,
            draft.confirmation_condition,
            draft.invalidation_condition,
        )
    )
    return "pillar_" + hashlib.sha256(semantic_key.encode()).hexdigest()[:32]


def materialize_pillar(
    draft: ThesisPillarDraft,
    *,
    candidate_id: str,
    known_at: datetime,
    horizon_days: int,
    evidence_ids: tuple[str, ...],
) -> ThesisPillar:
    if draft.expected_by_days > horizon_days:
        raise ValueError("thesis pillar cannot resolve after the Opportunity horizon")
    return ThesisPillar(
        pillar_id=pillar_identity(draft),
        source_candidate_ids=(candidate_id,),
        statement=draft.statement,
        observable=draft.observable,
        confirmation_condition=draft.confirmation_condition,
        invalidation_condition=draft.invalidation_condition,
        known_at=known_at,
        expected_by_days=draft.expected_by_days,
        due_at=known_at + timedelta(days=draft.expected_by_days),
        evidence_ids=evidence_ids,
    )


def pillar_research_question(pillar: ThesisPillar | dict) -> str:
    """Turns a frozen claim into a bounded follow-up question, never Evidence."""

    observable = (
        pillar.observable if isinstance(pillar, ThesisPillar) else pillar["observable"]
    )
    confirmation = (
        pillar.confirmation_condition
        if isinstance(pillar, ThesisPillar)
        else pillar["confirmation_condition"]
    )
    invalidation = (
        pillar.invalidation_condition
        if isinstance(pillar, ThesisPillar)
        else pillar["invalidation_condition"]
    )
    return f"Verify {observable}: confirm if {confirmation}; reject if {invalidation}."
