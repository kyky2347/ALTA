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
        tool_evidence_refs=(
            SimpleNamespace(
                tool_call_id="call_primary",
                evidence_role="primary_fact",
                source_locator="https://issuer.example/filing",
            ),
            SimpleNamespace(
                tool_call_id="call_primary",
                evidence_role="mechanism",
                source_locator="https://issuer.example/operating-bridge",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                evidence_role="market_context",
                source_locator="https://exchange.example/quote",
            ),
            SimpleNamespace(
                tool_call_id="call_news",
                evidence_role="counterevidence",
                source_locator="https://publisher.example/context",
            ),
        ),
    )
    result = build_research_diligence(
        tools=(
            SimpleNamespace(
                tool_call_id="call_primary",
                tool_name="alta_web_research",
                status="completed",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                tool_name="alta_finance_data",
                status="completed",
            ),
            SimpleNamespace(
                tool_call_id="call_news",
                tool_name="alta_news_search",
                status="completed",
            ),
        ),
        discoveries=(
            SimpleNamespace(
                tool_call_id="call_primary",
                source_locator="https://issuer.example/filing",
            ),
            SimpleNamespace(
                tool_call_id="call_primary",
                source_locator="https://issuer.example/operating-bridge",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                source_locator="https://exchange.example/quote",
            ),
            SimpleNamespace(
                tool_call_id="call_news",
                source_locator="https://publisher.example/context",
            ),
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
        "publisher.example",
    )
    assert result.reason_codes == ()
    assert result.evidence_roles == (
        "counterevidence",
        "market_context",
        "mechanism",
        "primary_fact",
    )
    assert result.counterevidence_source_distinct is True
    assert len(result.independent_evidence_origins) == 4
    assert result.cited_source_count == 4
    quality = research_quality_components(result)
    assert quality["research_quality"] == 1
    assert quality["source_breadth"] == 1


def test_news_only_candidate_remains_screen_grade_without_becoming_a_rejection() -> (
    None
):
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path=None,
        disconfirming_evidence=None,
        next_test=None,
        tool_evidence_refs=(
            SimpleNamespace(
                tool_call_id="call_news",
                evidence_role="counterevidence",
                source_locator="https://publisher.example/story",
            ),
        ),
    )
    result = build_research_diligence(
        tools=(
            SimpleNamespace(
                tool_call_id="call_news",
                tool_name="alta_news_search",
                status="completed",
            ),
        ),
        discoveries=(
            SimpleNamespace(
                tool_call_id="call_news",
                source_locator="https://publisher.example/story",
            ),
        ),
        frozen_source_locators=(),
        output=output,
    )

    assert result.posture == "screen_grade"
    assert "non_news_research_depth_limited" in result.reason_codes
    assert "counterevidence_not_declared" in result.reason_codes
    quality = research_quality_components(result)
    assert 0 < quality["research_quality"] < 0.6
    assert quality["non_news_depth"] == 0


def test_uncited_research_cannot_inflate_candidate_diligence() -> None:
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path="A measurable operating path is stated.",
        disconfirming_evidence="A rival explanation is stated.",
        next_test="Check the next primary operating update.",
        tool_evidence_refs=(),
    )
    result = build_research_diligence(
        tools=(
            SimpleNamespace(
                tool_call_id="call_primary",
                tool_name="alta_web_research",
                status="completed",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                tool_name="alta_finance_data",
                status="completed",
            ),
        ),
        discoveries=(
            SimpleNamespace(
                tool_call_id="call_primary",
                source_locator="https://issuer.example/filing",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                source_locator="https://exchange.example/quote",
            ),
        ),
        frozen_source_locators=(
            "https://frozen-one.example/evidence",
            "https://frozen-two.example/evidence",
        ),
        output=output,
    )

    assert result.posture == "screen_grade"
    assert result.active_research_calls == 2
    assert result.non_news_research_calls == 0
    assert result.source_families == ()
    assert "active_research_not_bound_to_candidate" in result.reason_codes
    assert "research_path_not_cross_checked" in result.reason_codes


def test_missing_process_record_never_invents_research_quality() -> None:
    assert research_quality_components(None) == {
        "research_quality": 0,
        "source_breadth": 0,
        "route_diversity": 0,
        "non_news_depth": 0,
        "origin_independence": 0,
    }


def test_repeated_origin_and_same_domain_counterevidence_are_not_independent() -> None:
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path="A measurable operating path is stated.",
        disconfirming_evidence="A rival explanation is stated.",
        next_test="Check the next primary operating update.",
        tool_evidence_refs=(
            SimpleNamespace(
                tool_call_id="call_primary",
                evidence_role="primary_fact",
                source_locator="https://issuer.example/filing",
            ),
            SimpleNamespace(
                tool_call_id="call_mechanism",
                evidence_role="mechanism",
                source_locator="https://issuer.example/filing-copy",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                evidence_role="market_context",
                source_locator="https://market.example/quote",
            ),
            SimpleNamespace(
                tool_call_id="call_counter",
                evidence_role="counterevidence",
                source_locator="https://issuer.example/risk",
            ),
        ),
    )
    repeated = "f" * 64
    discoveries = tuple(
        SimpleNamespace(
            tool_call_id=reference.tool_call_id,
            source_locator=reference.source_locator,
            origin_fingerprint=(
                repeated
                if reference.evidence_role in {"primary_fact", "mechanism"}
                else ("e" if reference.evidence_role == "market_context" else "d") * 64
            ),
        )
        for reference in output.tool_evidence_refs
    )
    tools = (
        SimpleNamespace(
            tool_call_id="call_primary",
            tool_name="alta_web_research",
            status="completed",
        ),
        SimpleNamespace(
            tool_call_id="call_mechanism",
            tool_name="alta_web_batch_fetch",
            status="completed",
        ),
        SimpleNamespace(
            tool_call_id="call_market",
            tool_name="alta_finance_data",
            status="completed",
        ),
        SimpleNamespace(
            tool_call_id="call_counter",
            tool_name="alta_news_search",
            status="completed",
        ),
    )

    result = build_research_diligence(
        tools=tools,
        discoveries=discoveries,
        frozen_source_locators=(),
        output=output,
    )

    assert result.posture == "screen_grade"
    assert len(result.independent_evidence_origins) == 3
    assert "independent_source_breadth_limited" in result.reason_codes
    assert "counterevidence_source_not_distinct" in result.reason_codes


def test_repeated_source_records_cannot_masquerade_as_three_origin_checks() -> None:
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path="A measurable operating path is stated.",
        disconfirming_evidence="An independent rival explanation is stated.",
        next_test="Check the next primary operating update.",
        tool_evidence_refs=(
            SimpleNamespace(
                tool_call_id="call_primary",
                evidence_role="primary_fact",
                source_locator="https://issuer.example/filing",
            ),
            SimpleNamespace(
                tool_call_id="call_mechanism",
                evidence_role="mechanism",
                source_locator="https://operations.example/kpi",
            ),
            SimpleNamespace(
                tool_call_id="call_market",
                evidence_role="market_context",
                source_locator="https://market.example/quote",
            ),
            SimpleNamespace(
                tool_call_id="call_counter",
                evidence_role="counterevidence",
                source_locator="https://counter.example/rival",
            ),
        ),
    )
    discoveries = tuple(
        SimpleNamespace(
            tool_call_id=reference.tool_call_id,
            source_locator=reference.source_locator,
            origin_fingerprint=(
                "a" * 64
                if reference.evidence_role in {"primary_fact", "mechanism"}
                else "b" * 64
            ),
        )
        for reference in output.tool_evidence_refs
    )
    tools = tuple(
        SimpleNamespace(
            tool_call_id=reference.tool_call_id,
            tool_name=(
                "alta_finance_data"
                if reference.evidence_role == "market_context"
                else "alta_web_batch_fetch"
            ),
            status="completed",
        )
        for reference in output.tool_evidence_refs
    )

    result = build_research_diligence(
        tools=tools,
        discoveries=discoveries,
        frozen_source_locators=(),
        output=output,
    )

    assert result.posture == "screen_grade"
    assert len(result.independent_source_domains) == 4
    assert len(result.independent_evidence_origins) == 2
    assert "independent_evidence_origins_limited" in result.reason_codes


def test_frozen_mirror_keeps_origin_identity_across_research_cycles() -> None:
    origin = "a" * 64
    output = SimpleNamespace(
        kind="candidate",
        beneficiary_path="A measurable operating path is stated.",
        disconfirming_evidence="A rival explanation is stated.",
        next_test="Check the next versioned update.",
        tool_evidence_refs=(
            SimpleNamespace(
                tool_call_id="mirror_call",
                evidence_role="primary_fact",
                source_locator="https://mirror.example/release-copy",
            ),
        ),
    )
    result = build_research_diligence(
        tools=(
            SimpleNamespace(
                tool_call_id="mirror_call",
                tool_name="alta_web_batch_fetch",
                status="completed",
            ),
        ),
        discoveries=(
            SimpleNamespace(
                tool_call_id="mirror_call",
                source_locator="https://mirror.example/release-copy",
                origin_fingerprint=origin,
            ),
        ),
        frozen_source_locators=("https://issuer.example/release",),
        frozen_origin_fingerprints=(origin,),
        output=output,
    )

    assert result.independent_evidence_origins == (origin,)
    assert "independent_evidence_origins_limited" in result.reason_codes
