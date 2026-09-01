from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import Field

from .expression_base import FrozenContract, contract_hash
from .trader_mind import ACTIVE_RESEARCH_TOOLS

RESEARCH_QUALITY_VERSION = "alta-research-quality-v4"
RESEARCH_DECISION_HURDLE = Decimal("0.60")
REQUIRED_EVIDENCE_ROLES = frozenset(
    {"primary_fact", "mechanism", "market_context", "counterevidence"}
)


class ResearchTool(Protocol):
    tool_call_id: str
    tool_name: str
    status: str


class ResearchDiscovery(Protocol):
    tool_call_id: str
    source_locator: str


class ResearchDiligence(FrozenContract):
    """Auditable process posture; it is context, never market Evidence."""

    version: Literal[
        "alta-research-diligence-v1",
        "alta-research-diligence-v2",
        "alta-research-diligence-v3",
    ] = "alta-research-diligence-v3"
    posture: Literal["cross_checked", "screen_grade", "no_op"]
    completed_tool_calls: int = Field(ge=0, le=12)
    active_research_calls: int = Field(ge=0, le=12)
    cited_research_calls: int = Field(default=0, ge=0, le=12)
    non_news_research_calls: int = Field(ge=0, le=12)
    source_families: tuple[str, ...] = Field(default=(), max_length=10)
    independent_source_domains: tuple[str, ...] = Field(default=(), max_length=10)
    independent_evidence_origins: tuple[str, ...] = Field(default=(), max_length=10)
    cited_source_count: int = Field(default=0, ge=0, le=20)
    source_role_collisions: int = Field(default=0, ge=0, le=10)
    evidence_roles: tuple[str, ...] = Field(default=(), max_length=4)
    counterevidence_source_distinct: bool = False
    beneficiary_path_declared: bool = False
    counterevidence_declared: bool = False
    next_test_declared: bool = False
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)


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
            "origin_independence": Decimal(0),
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
    origin_independence = min(
        Decimal(1), Decimal(len(diligence.independent_evidence_origins)) / Decimal(3)
    )
    role_coverage = Decimal(
        len(REQUIRED_EVIDENCE_ROLES.intersection(diligence.evidence_roles))
    ) / Decimal(len(REQUIRED_EVIDENCE_ROLES))
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
        posture * Decimal("0.25")
        + source_breadth * Decimal("0.15")
        + route_diversity * Decimal("0.10")
        + non_news_depth * Decimal("0.15")
        + declared_controls * Decimal("0.10")
        + role_coverage * Decimal("0.15")
        + origin_independence * Decimal("0.10")
    )
    if diligence.posture == "screen_grade":
        score = min(score, Decimal("0.59"))
    return {
        "research_quality": score,
        "source_breadth": source_breadth,
        "route_diversity": route_diversity,
        "non_news_depth": non_news_depth,
        "origin_independence": origin_independence,
    }


def build_research_diligence(
    *,
    tools: Sequence[ResearchTool],
    discoveries: Sequence[ResearchDiscovery],
    frozen_source_locators: Sequence[str],
    frozen_origin_fingerprints: Sequence[str] = (),
    output: Any,
) -> ResearchDiligence:
    (
        completed,
        active,
        cited_active,
        tools_by_call,
        cited_refs,
        cited_tool_pairs,
    ) = _cited_research(tools, output)
    families = tuple(sorted({_tool_family(item.tool_name) for item in cited_active}))
    roles = _evidence_roles(cited_refs)
    non_news = tuple(
        item
        for item in cited_active
        if _tool_family(item.tool_name) not in {"news_locator", "social_locator"}
    )
    cited_locators, domains, origin_by_pair, origins = _source_independence(
        discoveries,
        cited_tool_pairs,
        frozen_source_locators,
        frozen_origin_fingerprints,
    )
    source_role_collisions = _source_role_collision_count(cited_refs)
    common = {
        "completed_tool_calls": len(completed),
        "active_research_calls": len(active),
        "cited_research_calls": len(cited_active),
        "non_news_research_calls": len(non_news),
        "source_families": families,
        "independent_source_domains": domains,
        "independent_evidence_origins": origins,
        "cited_source_count": len(cited_locators),
        "source_role_collisions": source_role_collisions,
        "evidence_roles": roles,
    }
    if getattr(output, "kind", None) == "no_op":
        return ResearchDiligence(posture="no_op", **common)

    beneficiary = bool(getattr(output, "beneficiary_path", None))
    counterevidence = bool(getattr(output, "disconfirming_evidence", None))
    next_test = bool(getattr(output, "next_test", None))
    counterevidence_source_distinct = _counterevidence_is_distinct(
        cited_refs, origin_by_pair
    )
    role_families = _role_families(cited_refs, tools_by_call)
    reasons = _diligence_reason_codes(
        active=active,
        cited_active=cited_active,
        non_news=non_news,
        domains=domains,
        origins=origins,
        roles=roles,
        role_families=role_families,
        counterevidence_source_distinct=counterevidence_source_distinct,
        beneficiary=beneficiary,
        counterevidence=counterevidence,
        next_test=next_test,
    )
    return ResearchDiligence(
        posture="cross_checked" if not reasons else "screen_grade",
        **common,
        counterevidence_source_distinct=counterevidence_source_distinct,
        beneficiary_path_declared=beneficiary,
        counterevidence_declared=counterevidence,
        next_test_declared=next_test,
        reason_codes=reasons,
    )


def _cited_research(
    tools: Sequence[ResearchTool], output: Any
) -> tuple[tuple, tuple, tuple, dict[str, ResearchTool], tuple, set[tuple[str, str]]]:
    completed = tuple(item for item in tools if item.status == "completed")
    active = tuple(
        item for item in completed if item.tool_name in ACTIVE_RESEARCH_TOOLS
    )
    cited_tool_pairs = {
        (item.tool_call_id, item.source_locator)
        for item in getattr(output, "tool_evidence_refs", ())
        if item.tool_call_id is not None
    }
    cited_tool_call_ids = {item[0] for item in cited_tool_pairs}
    cited_active = tuple(
        item
        for item in active
        if getattr(item, "tool_call_id", None) in cited_tool_call_ids
    )
    tools_by_call = {item.tool_call_id: item for item in cited_active}
    cited_refs = tuple(
        item
        for item in getattr(output, "tool_evidence_refs", ())
        if item.tool_call_id in tools_by_call
    )
    return completed, active, cited_active, tools_by_call, cited_refs, cited_tool_pairs


def _evidence_roles(cited_refs: Sequence[Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                role
                for item in cited_refs
                if (role := getattr(item, "evidence_role", None))
                in REQUIRED_EVIDENCE_ROLES
            }
        )
    )


def _source_independence(
    discoveries: Sequence[ResearchDiscovery],
    cited_tool_pairs: set[tuple[str, str]],
    frozen_source_locators: Sequence[str],
    frozen_origin_fingerprints: Sequence[str],
) -> tuple[
    tuple[str, ...], tuple[str, ...], dict[tuple[str, str], str], tuple[str, ...]
]:
    cited_discoveries = tuple(
        item
        for item in discoveries
        if (getattr(item, "tool_call_id", None), item.source_locator)
        in cited_tool_pairs
    )
    cited_tool_locators = tuple(item.source_locator for item in cited_discoveries)
    cited_locators = tuple(
        dict.fromkeys((*cited_tool_locators, *frozen_source_locators))
    )
    domains = tuple(
        sorted(
            {
                hostname
                for locator in cited_locators
                if (hostname := _hostname(locator)) is not None
            }
        )[:10]
    )
    origin_by_pair = {
        (item.tool_call_id, item.source_locator): _discovery_origin(item)
        for item in cited_discoveries
    }
    durable_origins = tuple(
        value
        for value in frozen_origin_fingerprints
        if isinstance(value, str) and len(value) == 64
    ) or tuple(
        contract_hash({"source_locator": locator}) for locator in frozen_source_locators
    )
    origins = tuple(
        sorted(
            {
                *origin_by_pair.values(),
                *durable_origins,
            }
        )[:10]
    )
    return cited_locators, domains, origin_by_pair, origins


def _source_role_collision_count(cited_refs: Sequence[Any]) -> int:
    roles_by_locator: dict[str, set[str]] = {}
    for item in cited_refs:
        role = getattr(item, "evidence_role", None)
        if role in REQUIRED_EVIDENCE_ROLES:
            roles_by_locator.setdefault(item.source_locator, set()).add(role)
    return sum(len(locator_roles) > 1 for locator_roles in roles_by_locator.values())


def _counterevidence_is_distinct(
    cited_refs: Sequence[Any], origin_by_pair: dict[tuple[str, str], str]
) -> bool:
    primary_refs = {
        (item.tool_call_id, item.source_locator)
        for item in cited_refs
        if getattr(item, "evidence_role", None) in {"primary_fact", "mechanism"}
    }
    counter_refs = {
        (item.tool_call_id, item.source_locator)
        for item in cited_refs
        if getattr(item, "evidence_role", None) == "counterevidence"
    }
    primary_domains = {_hostname(locator) for _, locator in primary_refs}
    primary_origins = {origin_by_pair.get(pair) for pair in primary_refs}
    return any(
        _hostname(locator) not in primary_domains
        and origin_by_pair.get((call_id, locator)) not in primary_origins
        for call_id, locator in counter_refs
    )


def _role_families(
    cited_refs: Sequence[Any], tools_by_call: dict[str, ResearchTool]
) -> dict[str, set[str]]:
    return {
        role: {
            _tool_family(tools_by_call[item.tool_call_id].tool_name)
            for item in cited_refs
            if getattr(item, "evidence_role", None) == role
        }
        for role in REQUIRED_EVIDENCE_ROLES
    }


def _diligence_reason_codes(
    *,
    active: Sequence[Any],
    cited_active: Sequence[Any],
    non_news: Sequence[Any],
    domains: Sequence[str],
    origins: Sequence[str],
    roles: Sequence[str],
    role_families: dict[str, set[str]],
    counterevidence_source_distinct: bool,
    beneficiary: bool,
    counterevidence: bool,
    next_test: bool,
) -> tuple[str, ...]:
    primary_fact_bound = bool(
        role_families["primary_fact"].difference({"news_locator", "social_locator"})
    )
    mechanism_bound = bool(
        role_families["mechanism"].difference({"news_locator", "social_locator"})
    )
    checks = (
        (len(cited_active) < 3, "research_path_not_cross_checked"),
        (bool(active) and not cited_active, "active_research_not_bound_to_candidate"),
        (len(non_news) < 2, "non_news_research_depth_limited"),
        (len(domains) < 3, "independent_source_breadth_limited"),
        (len(origins) < 3, "independent_evidence_origins_limited"),
        (not primary_fact_bound, "primary_fact_not_bound"),
        (not mechanism_bound, "mechanism_not_bound"),
        (
            "market_data" not in role_families["market_context"],
            "market_context_not_bound",
        ),
        ("counterevidence" not in roles, "counterevidence_not_bound"),
        (
            "counterevidence" in roles and not counterevidence_source_distinct,
            "counterevidence_source_not_distinct",
        ),
        (not beneficiary, "beneficiary_path_not_declared"),
        (not counterevidence, "counterevidence_not_declared"),
        (not next_test, "next_test_not_declared"),
    )
    return tuple(reason for failed, reason in checks if failed)


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
            len(item.independent_evidence_origins),
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
    if tool_name == "alta_web_batch_fetch":
        return "primary_web"
    return "primary_web"


def _discovery_origin(item: ResearchDiscovery) -> str:
    value = getattr(item, "origin_fingerprint", None)
    content = getattr(item, "content", None)
    if not value and isinstance(content, dict):
        value = content.get("origin_fingerprint")
    if isinstance(value, str) and len(value) == 64:
        return value
    return contract_hash({"source_locator": item.source_locator})


def _hostname(locator: str) -> str | None:
    parsed = urlsplit(locator)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.lower().removeprefix("www.")
