from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .alpha_feedback import (
    MIN_MIND_BENCHMARKED_POSITIONS,
    TraderMindAlphaFeedback,
)

RESEARCH_INCENTIVE_MODE = "delayed_symmetric_alpha_v1"
MAX_REWARD_TOOL_CALLS = 1
MAX_REWARD_TOKENS = 8_000

ResearchIncentiveState = Literal[
    "prospective",
    "calibrating",
    "earned",
    "recovery",
]


class ResearchIncentive(BaseModel):
    """Revocable research-only reward derived from frozen outcome feedback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["alta-research-incentive-v1"] = "alta-research-incentive-v1"
    scout_id: str = Field(min_length=3, max_length=64)
    state: ResearchIncentiveState
    benchmarked_positions: int = Field(ge=0)
    minimum_positions: int = Field(ge=1)
    feedback_snapshot_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    alpha_lower_confidence_bps: Decimal | None = None
    bonus_tool_calls: int = Field(default=0, ge=0, le=MAX_REWARD_TOOL_CALLS)
    bonus_total_tokens: int = Field(default=0, ge=0, le=MAX_REWARD_TOKENS)
    directive: str = Field(min_length=3, max_length=420)

    @model_validator(mode="after")
    def reward_is_mature_symmetric_and_research_only(self) -> "ResearchIncentive":
        earned = self.state == "earned"
        if earned and (
            self.benchmarked_positions < self.minimum_positions
            or self.feedback_snapshot_hash is None
            or self.alpha_lower_confidence_bps is None
            or self.alpha_lower_confidence_bps <= 0
            or self.bonus_tool_calls != MAX_REWARD_TOOL_CALLS
            or self.bonus_total_tokens != MAX_REWARD_TOKENS
        ):
            raise ValueError("earned research incentive requires mature positive Alpha")
        if not earned and (self.bonus_tool_calls or self.bonus_total_tokens):
            raise ValueError("unearned research incentive cannot increase a budget")
        if self.state in {"prospective", "calibrating"} and (
            self.alpha_lower_confidence_bps is not None
        ):
            raise ValueError("immature research incentive cannot expose Alpha")
        return self


def _incentive_for_feedback(
    feedback: TraderMindAlphaFeedback,
) -> ResearchIncentive:
    common = {
        "scout_id": feedback.scout_id,
        "benchmarked_positions": feedback.benchmarked_positions,
        "minimum_positions": feedback.minimum_mind_positions,
        "feedback_snapshot_hash": feedback.snapshot_hash,
        "alpha_lower_confidence_bps": feedback.alpha_lower_confidence_bps,
    }
    if not feedback.mature:
        return ResearchIncentive(
            **common,
            state="calibrating",
            directive=(
                f"Future research bonus contract is active; {feedback.benchmarked_positions}/"
                f"{feedback.minimum_mind_positions} benchmarked closes are available. "
                "Performance remains hidden until maturity. Candidate count, confidence, "
                "turnover, and raw profit earn no credit."
            ),
        )
    if (
        feedback.alpha_lower_confidence_bps is not None
        and feedback.alpha_lower_confidence_bps > 0
    ):
        return ResearchIncentive(
            **common,
            state="earned",
            bonus_tool_calls=MAX_REWARD_TOOL_CALLS,
            bonus_total_tokens=MAX_REWARD_TOKENS,
            directive=(
                "One additional research call and 8,000 tokens are earned for this "
                "wake because the maturity-gated, cost-adjusted benchmark Alpha lower "
                "bound is positive. The bonus is revocable; durable out-of-sample Alpha "
                "keeps it, while Candidate volume, confidence, and turnover earn nothing."
            ),
        )
    return ResearchIncentive(
        **common,
        state="recovery",
        directive=(
            "No research bonus is earned because conservative benchmark Alpha is not "
            "positive. Change the entity, source class, or causal hypothesis; reduce "
            "repetition rather than increasing Candidate volume or trading activity."
        ),
    )


def build_research_incentives(
    feedback: tuple[TraderMindAlphaFeedback, ...],
    *,
    scout_ids: tuple[str, ...],
) -> tuple[ResearchIncentive, ...]:
    """Build one deterministic, non-capital incentive contract per Trader Mind."""

    by_scout = {item.scout_id: item for item in feedback}
    if len(by_scout) != len(feedback):
        raise ValueError("research incentive feedback IDs must be unique")
    incentives = []
    for scout_id in scout_ids:
        item = by_scout.get(scout_id)
        if item is not None:
            incentives.append(_incentive_for_feedback(item))
            continue
        incentives.append(
            ResearchIncentive(
                scout_id=scout_id,
                state="prospective",
                benchmarked_positions=0,
                minimum_positions=MIN_MIND_BENCHMARKED_POSITIONS,
                directive=(
                    "Future research bonus contract is active. A bonus becomes available "
                    "only after enough benchmarked Shadow closes establish a positive "
                    "cost-adjusted Alpha lower bound. Candidate count, confidence, "
                    "turnover, and raw profit earn no credit."
                ),
            )
        )
    return tuple(incentives)
