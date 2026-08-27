from types import SimpleNamespace

from alta_asterism.research_diligence import (
    build_research_diligence,
    research_quality_components,
)


def test_cross_checked_research_requires_non_news_and_independent_sources() -> None:
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path="Pricing change reaches gross margin and estimates.",
        disconfirming_evidence="A competitor filing shows the change may be temporary.",
        next_test="Check the next reported gross-margin bridge.",
    )
    result = build_research_diligence(
        tools=(
            SimpleNamespace(tool_name="alta_web_research", status="completed"),
            SimpleNamespace(tool_name="alta_finance_data", status="completed"),
            SimpleNamespace(tool_name="alta_news_search", status="completed"),
        ),
        discoveries=(
            SimpleNamespace(source_locator="https://issuer.example/filing"),
            SimpleNamespace(source_locator="https://exchange.example/quote"),
        ),
        frozen_source_locators=(),
        output=output,
    )

    assert result.posture == "cross_checked"
    assert result.active_research_calls == 3
    assert result.non_news_research_calls == 2
    assert result.independent_source_domains == (
        "exchange.example",
        "issuer.example",
    )
    assert result.reason_codes == ()
    quality = research_quality_components(result)
    assert quality["research_quality"] > quality["source_breadth"]
    assert quality["research_quality"] > 0.9


def test_news_only_candidate_remains_screen_grade_without_becoming_a_rejection() -> (
    None
):
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path=None,
        disconfirming_evidence=None,
        next_test=None,
    )
    result = build_research_diligence(
        tools=(SimpleNamespace(tool_name="alta_news_search", status="completed"),),
        discoveries=(
            SimpleNamespace(source_locator="https://publisher.example/story"),
        ),
        frozen_source_locators=(),
        output=output,
    )

    assert result.posture == "screen_grade"
    assert "non_news_research_absent" in result.reason_codes
    assert "counterevidence_not_declared" in result.reason_codes
    quality = research_quality_components(result)
    assert 0 < quality["research_quality"] < 0.6
    assert quality["non_news_depth"] == 0


def test_missing_process_record_never_invents_research_quality() -> None:
    assert research_quality_components(None) == {
        "research_quality": 0,
        "source_breadth": 0,
        "route_diversity": 0,
        "non_news_depth": 0,
    }
