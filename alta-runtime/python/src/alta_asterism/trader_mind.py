import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .research_agenda import ResearchMode

CORE_ACTIVE_RESEARCH_TOOLS = (
    "alta_web_search",
    "alta_web_research",
    "alta_web_batch_fetch",
    "alta_news_search",
    "alta_social_search",
    "alta_finance_data",
)
PRODUCTION_ACTIVE_RESEARCH_REQUIRED = True
TRADER_MIND_MEMORY_MODE = "bounded_non_evidence"
TRADER_MIND_MEMORY_SCHEMA = "alta.trader-mind-memory.v3"
TRADER_MIND_MEMORY_MAX_BYTES = 1_200
ACTIVE_RESEARCH_TOOLS = frozenset(
    {
        *CORE_ACTIVE_RESEARCH_TOOLS,
        "alta_web_crawl",
        "alta_web_feed",
        "alta_web_archive",
        "alta_academic_search",
    }
)
MEMORY_RESEARCH_TOOLS = ACTIVE_RESEARCH_TOOLS | {
    "alta_web_fetch",
    "alta_social_read",
}
MEMORY_COUNTER_LIMIT = 9_999
MEMORY_RECENT_LIMIT = 2


class ScoutConfig(BaseModel):
    """Immutable initial mandate and research surface for one Trader Mind."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scout_id: str
    version: str
    mission: str
    alpha_archetypes: tuple[str, ...] = Field(min_length=2, max_length=8)
    research_sequence: tuple[str, ...] = Field(min_length=3, max_length=8)
    skepticism: str = Field(min_length=1, max_length=800)
    primary_sources: tuple[str, ...]
    search_territories: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...] = (
        "discussion",
        "ranking",
        "expression",
        "broker",
    )


SCOUTS = (
    ScoutConfig(
        scout_id="change_event_scout",
        version="alpha-v7",
        mission=(
            "Identify newly changed facts whose causal earnings, cash-flow, or "
            "positioning implications may still be propagating into listed prices."
        ),
        alpha_archetypes=(
            "revision inflection",
            "post-earnings overreaction",
            "capital-allocation catalyst",
            "operating artifact inflection",
        ),
        research_sequence=(
            "Search recent primary disclosures and versioned news for a changed fact.",
            "Search non-news operating artifacts such as product pages, pricing, hiring, procurement, public release notes, traffic proxies, and ecosystem releases for a measurable state change; use feeds, sitemaps, and bounded archives to detect version changes that a headline missed.",
            "Query SEC submissions by ticker for Form 4, SC 13D/13G, 8-K, 10-Q/10-K, S-3, and 424B clues when ownership, incentives, financing, or operational disclosures could carry the change.",
            "Use public social discussion only to locate claims or narrative shifts, never as proof by itself.",
            "Batch-fetch the strongest independent primary pages and verify the causal earnings or cash-flow path.",
            "Check market data to determine whether price and expectations already absorbed the change.",
        ),
        skepticism=(
            "Reject recycled headlines, management narrative without measurable exposure, "
            "and events whose estimate path or beneficiary cannot be identified."
        ),
        primary_sources=("finlight_event", "company_filing"),
        search_territories=("event_primary_search",),
        allowed_tools=(
            *CORE_ACTIVE_RESEARCH_TOOLS,
            "alta_web_fetch",
            "alta_social_read",
            "alta_web_crawl",
            "alta_web_feed",
            "alta_web_archive",
        ),
    ),
    ScoutConfig(
        scout_id="market_dislocation_scout",
        version="alpha-v7",
        mission=(
            "Identify price, volume, volatility, breadth, or cross-asset "
            "dislocations with a testable non-technical catalyst or mechanism."
        ),
        alpha_archetypes=(
            "temporary dislocation",
            "peer relative-value",
            "over-earning reversal",
            "post-event drift",
            "forced-flow or volatility-surface dislocation",
        ),
        research_sequence=(
            "Scan price, volume, volatility-normalized surprise, persistent drift, overnight-versus-intraday discovery, options surface, breadth, ETF/peer-relative behavior, and cross-asset data for an anomaly or forced flow.",
            "Search news and the open web for a non-technical mechanism that can explain or contradict it, including index/ETF methodology, corporate actions, lockups, financing, borrow, and scheduled rebalances when publicly auditable.",
            "Batch-fetch the strongest independent mechanism and counterevidence sources before deciding the move is idiosyncratic.",
            "Search public social sources for positioning or narrative evidence and verify any claim elsewhere.",
            "Test whether the move is factor beta, stale data, or a genuinely idiosyncratic repricing gap.",
        ),
        skepticism=(
            "Reject technical moves without a falsifiable fundamental or event mechanism, "
            "and penalize stale bars, illiquidity, factor exposure, and inferred crowding."
        ),
        primary_sources=("massive_bar", "relative_market_move"),
        search_territories=("market_timeseries_scan",),
        allowed_tools=(
            *CORE_ACTIVE_RESEARCH_TOOLS,
            "alta_web_fetch",
            "alta_social_read",
            "alta_web_crawl",
        ),
    ),
    ScoutConfig(
        scout_id="causal_policy_scout",
        version="alpha-v6",
        mission=(
            "Trace underappreciated first- and second-order listed-equity effects "
            "from official policy, regulation, rates, commodities, and macro changes."
        ),
        alpha_archetypes=(
            "policy second-order beneficiary",
            "input-cost or rate transmission",
            "regulatory catalyst",
            "sector-neutral policy pair",
            "supply-chain transmission mismatch",
        ),
        research_sequence=(
            "Search official policy, regulatory, macro, and central-bank sources for a changed rule or state, then inspect agency dockets, procurement awards, grant notices, enforcement calendars, technical standards, and implementation feeds for the less obvious timing clue.",
            "Use academic and industry research to map first- and second-order transmission mechanisms.",
            "Batch-fetch independent official and issuer-level sources that can prove or reject the transmission path.",
            "Search news and public social discussion for affected entities, disputed assumptions, and implementation friction.",
            "Use market data to separate an underpriced equity effect from an obvious macro or sector factor move.",
        ),
        skepticism=(
            "Reject vague macro narratives, undated soft catalysts, and beneficiary claims "
            "without issuer-level exposure, timing, and a measurable transmission path."
        ),
        primary_sources=("official_policy", "official_macro"),
        search_territories=("official_policy_search",),
        allowed_tools=(
            *CORE_ACTIVE_RESEARCH_TOOLS,
            "alta_web_fetch",
            "alta_social_read",
            "alta_academic_search",
            "alta_web_crawl",
            "alta_web_feed",
            "alta_web_archive",
        ),
    ),
    ScoutConfig(
        scout_id="expectation_gap_scout",
        version="alpha-v6",
        mission=(
            "Find a measurable gap between market expectations and emerging "
            "fundamental evidence, including evidence that supports a short thesis."
        ),
        alpha_archetypes=(
            "expectation or revision gap",
            "narrative excess short",
            "quality trap",
            "accounting or cash-conversion divergence",
            "alternative-data KPI inflection",
        ),
        research_sequence=(
            "Search filings, estimate primitives, product or pricing changes, public social narratives, web artifacts, and ecosystem data for a disputed expectation; use bounded archive and crawl comparisons for quiet pricing, packaging, availability, release-note, partner, or disclosure drift. News is only one possible locator.",
            "Batch-fetch the strongest independent primary and counterevidence pages rather than relying on search snippets.",
            "Find a source-backed KPI, estimate path, cash-flow line, or catalyst that can resolve the dispute.",
            "Search explicitly for disconfirming evidence and the strongest reason consensus may be right.",
            "Use market data to test whether the proposed gap is already reflected in price, volatility, or peer valuation.",
        ),
        skepticism=(
            "Reject sentiment-only theses, unsupported claims about consensus or crowding, "
            "and gaps that lack an observable estimate path and first rejection."
        ),
        primary_sources=("expectation_primitive", "narrative_counterevidence"),
        search_territories=("expectation_counterevidence_search",),
        allowed_tools=(
            *CORE_ACTIVE_RESEARCH_TOOLS,
            "alta_web_fetch",
            "alta_social_read",
            "alta_academic_search",
            "alta_web_crawl",
            "alta_web_archive",
        ),
    ),
)


def validate_orthogonal_scouts(configs: tuple[ScoutConfig, ...] = SCOUTS) -> None:
    if len(configs) != 4 or len({item.scout_id for item in configs}) != 4:
        raise ValueError("B3 requires exactly four unique Scout configurations")
    for field in ("primary_sources", "search_territories"):
        seen: set[str] = set()
        for config in configs:
            values = set(getattr(config, field))
            if not values or seen.intersection(values):
                raise ValueError(
                    f"Scout {field} must be non-empty and pairwise disjoint"
                )
            seen.update(values)
    core_tools = set(CORE_ACTIVE_RESEARCH_TOOLS)
    for config in configs:
        if not core_tools.issubset(config.allowed_tools):
            raise ValueError(
                "every Trader Mind requires web, research, news, social, and finance discovery"
            )
        if not set(config.allowed_tools).issubset(
            ACTIVE_RESEARCH_TOOLS | {"alta_web_fetch", "alta_social_read"}
        ):
            raise ValueError("Trader Mind tool catalog contains a non-research tool")


validate_orthogonal_scouts()


class TraderMindMemory(BaseModel):
    """Bounded prior experience for one discovery Mind; never research Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scout_id: str = Field(min_length=3, max_length=64)
    version: int = Field(ge=1)
    known_at: datetime
    turn_count: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=TRADER_MIND_MEMORY_MAX_BYTES)

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Trader Mind memory known_at must be timezone-aware")
        return value


def bounded_mind_summary(
    value: str, maximum_bytes: int = TRADER_MIND_MEMORY_MAX_BYTES
) -> str:
    normalized = " ".join(value.split())
    encoded = normalized.encode()
    if len(encoded) <= maximum_bytes:
        return normalized
    return encoded[:maximum_bytes].decode(errors="ignore").rstrip()


def _bounded_source_count(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return min(max(parsed, 0), 20)


def _memory_counts(value: object, allowed: frozenset[str]) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): min(max(value, 0), MEMORY_COUNTER_LIMIT)
        for key, value in value.items()
        if key in allowed and isinstance(value, int)
    }


def _memory_event(
    *,
    outcome: object,
    research_mode: object,
    finding: object,
    why_now: object,
    first_rejection: object,
    tools: object,
    sources: object,
) -> dict[str, object]:
    raw_tools = tools if isinstance(tools, (list, tuple)) else ()
    return {
        "outcome": outcome if outcome in {"candidate", "no_op"} else "no_op",
        "research_mode": (
            research_mode if research_mode in {"explore", "follow_up"} else "explore"
        ),
        "finding": bounded_mind_summary(str(finding), 120),
        "why_now": bounded_mind_summary(str(why_now), 80),
        "first_rejection": bounded_mind_summary(str(first_rejection), 80),
        "tools": [tool for tool in raw_tools if tool in MEMORY_RESEARCH_TOOLS][:6],
        "sources": _bounded_source_count(sources),
    }


def _current_memory(
    prior: dict[str, object],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[dict[str, object]]]:
    outcomes = _memory_counts(prior.get("outcomes"), frozenset({"candidate", "no_op"}))
    research_modes = _memory_counts(
        prior.get("research_modes"), frozenset({"explore", "follow_up"})
    )
    tools = _memory_counts(prior.get("tool_uses"), MEMORY_RESEARCH_TOOLS)
    recent_values = prior.get("recent")
    if not isinstance(recent_values, list):
        return outcomes, research_modes, tools, []
    recent = []
    for item in reversed(recent_values):
        if isinstance(item, dict):
            recent.append(
                _memory_event(
                    outcome=item.get("outcome"),
                    research_mode=item.get("research_mode"),
                    finding=item.get("finding", ""),
                    why_now=item.get("why_now", ""),
                    first_rejection=item.get("first_rejection", ""),
                    tools=item.get("tools"),
                    sources=item.get("sources", 0),
                )
            )
            break
    return outcomes, research_modes, tools, recent


def _legacy_memory(
    prior: dict[str, object],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[dict[str, object]]]:
    outcome = prior.get("outcome")
    if not isinstance(outcome, str):
        return {}, {}, {}, []
    return (
        {outcome: 1},
        {},
        {},
        [
            _memory_event(
                outcome=outcome,
                research_mode="explore",
                finding=prior.get("finding", ""),
                why_now=prior.get("why_now", ""),
                first_rejection=prior.get("first_rejection", ""),
                tools=prior.get("completed_tools"),
                sources=prior.get("collected_sources", 0),
            )
        ],
    )


def _load_prior_memory(
    previous_summary: str | None,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[dict[str, object]]]:
    if not previous_summary:
        return {}, {}, {}, []
    try:
        prior = json.loads(previous_summary)
    except json.JSONDecodeError:
        return {}, {}, {}, []
    if not isinstance(prior, dict):
        return {}, {}, {}, []
    if prior.get("schema") in {
        TRADER_MIND_MEMORY_SCHEMA,
        "alta.trader-mind-memory.v2",
    }:
        return _current_memory(prior)
    return _legacy_memory(prior)


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = min(counts.get(key, 0) + 1, MEMORY_COUNTER_LIMIT)


def experience_summary(
    *,
    previous_summary: str | None,
    outcome: str,
    finding: str,
    why_now: str | None,
    first_rejection: str | None,
    completed_tools: tuple[str, ...],
    collected_sources: int,
    research_mode: ResearchMode = "explore",
) -> str:
    """Evolve bounded process memory without turning prior claims into Evidence."""

    prior_outcomes, prior_research_modes, prior_tools, recent = _load_prior_memory(
        previous_summary
    )
    _increment_count(prior_outcomes, outcome)
    _increment_count(prior_research_modes, research_mode)
    tools = list(dict.fromkeys(completed_tools))[:6]
    for tool in tools:
        _increment_count(prior_tools, tool)
    recent.append(
        _memory_event(
            outcome=outcome,
            research_mode=research_mode,
            finding=finding,
            why_now=why_now or "",
            first_rejection=first_rejection or "",
            tools=tools,
            sources=collected_sources,
        )
    )
    payload = {
        "schema": TRADER_MIND_MEMORY_SCHEMA,
        "outcomes": dict(sorted(prior_outcomes.items())),
        "research_modes": dict(sorted(prior_research_modes.items())),
        "tool_uses": dict(
            sorted(prior_tools.items(), key=lambda item: (-item[1], item[0]))[:8]
        ),
        "recent": recent[-MEMORY_RECENT_LIMIT:],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    if len(encoded.encode()) > TRADER_MIND_MEMORY_MAX_BYTES:
        payload["recent"] = payload["recent"][-1:]
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    if len(encoded.encode()) > TRADER_MIND_MEMORY_MAX_BYTES:
        raise ValueError("Trader Mind memory exceeds its hard byte budget")
    return encoded
