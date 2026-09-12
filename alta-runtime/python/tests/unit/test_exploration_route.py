import pytest
from pydantic import ValidationError

from alta_asterism.contracts import Settings
from alta_asterism.exploration_route import exploration_start


def test_start_is_replayable_bounded_and_varies_across_wakes() -> None:
    universe = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
    first = exploration_start("wake-1", "change_event_scout", universe)
    assert first == exploration_start("wake-1", "change_event_scout", universe)
    assert len(first) == len(set(first)) == 3
    assert set(first) <= set(universe)
    routes = {
        exploration_start(f"wake-{i}", "change_event_scout", universe)
        for i in range(10)
    }
    assert len(routes) > 1
    assert exploration_start("wake-1", "scout", ("AAA",)) == ("AAA",)


def test_tool_budget_is_configurable_but_cannot_escape_hard_cap() -> None:
    base = dict(
        DATABASE_URL="postgresql://localhost/test", REDIS_URL="redis://localhost/0"
    )
    assert Settings(**base).scout_max_tool_calls == 11
    assert Settings(**base, ALTA_SCOUT_MAX_TOOL_CALLS=10).scout_max_tool_calls == 10
    for invalid in (0, 13):
        with pytest.raises(ValidationError):
            Settings(**base, ALTA_SCOUT_MAX_TOOL_CALLS=invalid)


def test_research_token_budget_preserves_operator_choice_and_hard_cap() -> None:
    base = dict(
        DATABASE_URL="postgresql://localhost/test", REDIS_URL="redis://localhost/0"
    )
    defaults = Settings(**base)
    assert defaults.scout_max_total_tokens == 98_000
    assert defaults.agent_deadline_seconds == 300
    chosen = Settings(
        **base,
        ALTA_SCOUT_MAX_TOTAL_TOKENS=40_000,
        ALTA_SCOUT_MAX_TOOL_CALLS=6,
        ALTA_AGENT_DEADLINE_SECONDS=120,
    )
    assert chosen.scout_max_total_tokens == 40_000
    assert chosen.safe_dump()["scout_max_total_tokens"] == 40_000
    assert chosen.scout_max_tool_calls == 6
    assert chosen.agent_deadline_seconds == 120
    for invalid in (999, 100_001):
        with pytest.raises(ValidationError):
            Settings(**base, ALTA_SCOUT_MAX_TOTAL_TOKENS=invalid)
