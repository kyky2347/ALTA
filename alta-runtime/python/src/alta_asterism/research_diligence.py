from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import Field

from .expression_base import FrozenContract, contract_hash
from .trader_mind import ACTIVE_RESEARCH_TOOLS

RESEARCH_QUALITY_VERSION = "alta-research-quality-v1"
RESEARCH_DECISION_HURDLE = Decimal("0.60")


class ResearchTool(Protocol):
    tool_name: str
    status: str


class ResearchDiscovery(Protocol):
    source_locator: str


class ResearchDiligence(FrozenContract):
    """Auditable process posture; it is context, never market Evidence."""

    version: Literal["alta-research-diligence-v1"] = "alta-research-diligence-v1"
    posture: Literal["cross_checked", "screen_grade", "no_op"]
    completed_tool_calls: int = Field(ge=0, le=12)
    active_research_calls: int = Field(ge=0, le=12)
    non_news_research_calls: int = Field(ge=0, le=12)
    source_families: tuple[str, ...] = Field(default=(), max_length=10)
    independent_source_domains: tuple[str, ...] = Field(default=(), max_length=10)
    beneficiary_path_declared: bool = False
    counterevidence_declared: bool = False
    next_test_declared: bool = False
    reason_codes: tuple[str, ...] = Field(default=(), max_length=8)


def research_quality_components(
    diligence: ResearchDiligence | None,
) -> dict[str, Decimal]:
    """Materialize bounded process-quality inputs without treating them as Evidence."""

    if diligence is None or diligence.posture == "no_op":
        return {
            "research_quality": Decimal(0),
            "source_breadth": Decimal(0),
            "route_diversity": Decimal(0),
            "non_news_depth": Decimal(0),
        }

    source_breadth = min(
        Decimal(1), Decimal(len(diligence.independent_source_domains)) / Decimal(3)
    )
    route_diversity = min(
        Decimal(1), Decimal(len(diligence.source_families)) / Decimal(3)
    )
    non_news_depth = min(
        Decimal(1), Decimal(diligence.non_news_research_calls) / Decimal(2)
    )
    declared_controls = Decimal(
        sum(
            (
                diligence.beneficiary_path_declared,
                diligence.counterevidence_declared,
                diligence.next_test_declared,
            )
        )
    ) / Decimal(3)
    posture = Decimal(1) if diligence.posture == "cross_checked" else Decimal("0.35")
    score = (
        posture * Decimal("0.35")
        + source_breadth * Decimal("0.20")
        + route_diversity * Decimal("0.15")
        + non_news_depth * Decimal("0.15")
        + declared_controls * Decimal("0.15")
    )
    if diligence.posture == "screen_grade":
        score = min(score, Decimal("0.59"))
    return {
        "research_quality": score,
        "source_breadth": source_breadth,
        "route_diversity": route_diversity,
        "non_news_depth": non_news_depth,
    }


def build_research_diligence(
    *,
    tools: Sequence[ResearchTool],
    discoveries: Sequence[ResearchDiscovery],
    frozen_source_locators: Sequence[str],
    output: Any,
) -> ResearchDiligence:
    completed = tuple(item for item in tools if item.status == "completed")
    active = tuple(
        item for item in completed if item.tool_name in ACTIVE_RESEARCH_TOOLS
    )
    families = tuple(sorted({_tool_family(item.tool_name) for item in active}))
    non_news = tuple(
        item
        for item in active
        if _tool_family(item.tool_name) not in {"news_locator", "social_locator"}
    )
    domains = tuple(
        sorted(
            {
                hostname
                for locator in (
                    *(item.source_locator for item in discoveries),
                    *frozen_source_locators,
                )
                if (hostname := _hostname(locator)) is not None
            }
        )[:10]
    )
    if getattr(output, "kind", None) == "no_op":
        return ResearchDiligence(
            posture="no_op",
            completed_tool_calls=len(completed),
            active_research_calls=len(active),
            non_news_research_calls=len(non_news),
            source_families=families,
            independent_source_domains=domains,
        )

    beneficiary = bool(getattr(output, "beneficiary_path", None))
    counterevidence = bool(getattr(output, "disconfirming_evidence", None))
    next_test = bool(getattr(output, "next_test", None))
    reasons = []
    if len(active) < 2:
        reasons.append("research_path_not_cross_checked")
    if not non_news:
        reasons.append("non_news_research_absent")
    if len(domains) < 2:
        reasons.append("independent_source_breadth_limited")
    if not beneficiary:
        reasons.append("beneficiary_path_not_declared")
    if not counterevidence:
        reasons.append("counterevidence_not_declared")
    if not next_test:
        reasons.append("next_test_not_declared")
    return ResearchDiligence(
        posture="cross_checked" if not reasons else "screen_grade",
        completed_tool_calls=len(completed),
        active_research_calls=len(active),
        non_news_research_calls=len(non_news),
        source_families=families,
        independent_source_domains=domains,
        beneficiary_path_declared=beneficiary,
        counterevidence_declared=counterevidence,
        next_test_declared=next_test,
        reason_codes=tuple(reasons),
    )


def strongest_diligence(
    values: Sequence[ResearchDiligence | None],
) -> ResearchDiligence | None:
    available = tuple(item for item in values if item is not None)
    if not available:
        return None
    posture_rank = {"no_op": 0, "screen_grade": 1, "cross_checked": 2}
    return max(
        available,
        key=lambda item: (
            posture_rank[item.posture],
            len(item.independent_source_domains),
            item.non_news_research_calls,
            item.active_research_calls,
            contract_hash(item.model_dump(mode="json")),
        ),
    )


def _tool_family(tool_name: str) -> str:
    if tool_name == "alta_news_search":
        return "news_locator"
    if tool_name in {"alta_social_search", "alta_social_read"}:
        return "social_locator"
    if tool_name == "alta_finance_data":
        return "market_data"
    if tool_name == "alta_academic_search":
        return "academic_research"
    if tool_name in {"alta_web_archive", "alta_web_feed"}:
        return "versioned_web"
    return "primary_web"


def _hostname(locator: str) -> str | None:
    parsed = urlsplit(locator)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.lower().removeprefix("www.")
