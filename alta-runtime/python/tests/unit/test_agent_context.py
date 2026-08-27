import json
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from alta_asterism.agent_context import (
    MAX_ROLE_FROZEN_INPUT_BYTES,
    assessment_context,
    evidence_context,
    fit_frozen_items,
    frozen_input_size,
    opportunity_context,
)
from alta_asterism.agentic_deliberation import PrivateAssessmentPayload
from alta_asterism.agentic_deliberation import AgenticDeliberator
from alta_asterism.agentic_roles import (
    StructuredRoleRunner,
    StructuredRoleUnavailable,
    _validate_structured_response,
)
from alta_asterism.contracts import Environment
from alta_asterism.deliberation import PrivateAssessment
from alta_asterism.foundry import OpportunityDraft
from alta_asterism.scouts import EvidenceSnapshot
from alta_asterism.underwriting import (
    DecisionIntelligence,
    ScenarioCase,
    ScenarioUnderwriting,
)


def large_opportunity(known_at: datetime) -> OpportunityDraft:
    narrative = "n" * 2_000
    return OpportunityDraft(
        opportunity_id="opportunity_context_fixture",
        candidate_id="candidate_context_fixture",
        member_candidate_ids=("candidate_context_fixture",),
        environment=Environment.SHADOW,
        version=1,
        known_at=known_at,
        snapshot_hash="a" * 64,
        exact_key="b" * 64,
        structural_key="c" * 64,
        title="Large but valid opportunity context",
        thesis=narrative,
        entity_key="SPY",
        event_key="context-event",
        catalyst_key="context-catalyst",
        observed_change=narrative,
        mechanism=narrative,
        direction="positive",
        expectation=narrative,
        expectation_posture="available",
        variant_wedge=narrative,
        why_now=narrative,
        falsifier=narrative,
        first_rejection=narrative,
        prediction=narrative,
        investability="ready",
        freshness_at=known_at,
        horizon_days=10,
        confidence=0.6,
        evidence_ids=tuple(f"evidence_{index}" for index in range(8)),
        completeness="complete",
    )


def large_assessment(opportunity: OpportunityDraft, assessor: str) -> PrivateAssessment:
    return PrivateAssessment(
        assessment_id=f"assessment_{assessor}",
        opportunity_id=opportunity.opportunity_id,
        run_id=f"run_{assessor}",
        assessor=assessor,
        snapshot_hash=opportunity.snapshot_hash,
        forecast_probability=0.6,
        evidence_quality=0.7,
        variant_wedge_quality=0.6,
        strongest_support="s" * 2_000,
        strongest_disconfirmation="d" * 2_000,
        first_rejection="r" * 2_000,
        missing_evidence=tuple("m" * 500 for _ in range(20)),
        recommendation="research",
        confidence=0.6,
        evidence_ids=opportunity.evidence_ids,
        rationale="x" * 4_000,
        underwriting=ScenarioUnderwriting(
            bull=ScenarioCase(
                probability=0.2,
                relative_alpha_bps=700,
                trigger="Bull trigger.",
                evidence_ids=opportunity.evidence_ids,
            ),
            base=ScenarioCase(
                probability=0.4,
                relative_alpha_bps=150,
                trigger="Base trigger.",
                evidence_ids=opportunity.evidence_ids,
            ),
            bear=ScenarioCase(
                probability=0.4,
                relative_alpha_bps=-500,
                trigger="Bear trigger.",
                evidence_ids=opportunity.evidence_ids,
            ),
            catalyst_clarity=0.6,
            crowding_risk=0.3,
            liquidity_risk=0.2,
            next_pricing_fact="The next primary update.",
            decision=DecisionIntelligence(
                what_is_priced_in="A normal update is priced in.",
                variant_view="The frozen evidence supports a faster path.",
                reference_class="Comparable revision events.",
                base_rate_probability=0.5,
                inside_view_probability=0.6,
                must_be_true=("The next observation confirms persistence.",),
                company_thesis_status="intact",
                security_thesis_readiness="ready",
                edge_half_life_days=10,
                dominant_uncertainty="Persistence of the measured change.",
                action_trigger="Re-underwrite at the next primary update.",
            ),
        ),
        locked_at=opportunity.known_at,
        prompt_version="fixture-v1",
        model_id="fixture-model",
    )


def test_realistic_role_contexts_stay_below_the_database_hard_bound() -> None:
    known_at = datetime(2026, 8, 23, 14, tzinfo=UTC)
    opportunity = large_opportunity(known_at)
    evidence = tuple(
        EvidenceSnapshot(
            evidence_id=evidence_id,
            raw_id=f"raw_{index}",
            source="fixture",
            territory="finlight_event",
            source_locator=f"https://fixture.invalid/{index}",
            known_at=known_at,
            content_hash=f"{index:x}" * 64,
            summary="e" * 2_000,
        )
        for index, evidence_id in enumerate(opportunity.evidence_ids, start=1)
    )
    assessment_input = {
        "opportunity": opportunity_context(opportunity),
        "evidence": [evidence_context(item) for item in evidence],
    }
    discussion_input = {
        "opportunity": opportunity_context(opportunity, narrative_bytes=240),
        "private_assessments": [
            assessment_context(large_assessment(opportunity, assessor))
            for assessor in ("thesis_assessor", "disconfirming_assessor")
        ],
    }

    assert frozen_input_size(assessment_input) <= MAX_ROLE_FROZEN_INPUT_BYTES
    assert frozen_input_size(discussion_input) <= MAX_ROLE_FROZEN_INPUT_BYTES


def test_structured_role_rejects_oversized_input_before_database_or_model() -> None:
    runner = StructuredRoleRunner(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        model_provider="fixture",
        model_id="fixture-model",
    )

    with pytest.raises(StructuredRoleUnavailable, match="frozen_input_budget"):
        runner.run(
            cycle_id="oversized-fixture-cycle",
            run_id="run_oversized_fixture",
            role="fixture_role",
            prompt={"mission": "bounded input check"},
            output_type=PrivateAssessmentPayload,
            frozen_input={"payload": "x" * (MAX_ROLE_FROZEN_INPUT_BYTES + 1)},
            evidence_ids=(),
            known_at=datetime(2026, 8, 23, 14, tzinfo=UTC),
            prompt_version="fixture-v1",
        )


def test_structured_role_parser_accepts_one_valid_wrapped_contract() -> None:
    adapter = TypeAdapter(PrivateAssessmentPayload)
    payload = {
        "forecast_probability": 0.6,
        "evidence_quality": 0.7,
        "variant_wedge_quality": 0.65,
        "strongest_support": "A bounded support point.",
        "strongest_disconfirmation": "A bounded counterpoint.",
        "first_rejection": "The next primary-source update reverses the fact.",
        "missing_evidence": [],
        "recommendation": "research",
        "confidence": 0.55,
        "evidence_ids": ["evidence_fixture"],
        "rationale": "A bounded evidence-first rationale.",
        "underwriting": {
            "benchmark_symbol": "SPY",
            "bull": {
                "probability": 0.2,
                "relative_alpha_bps": 700,
                "trigger": "Bull trigger.",
                "evidence_ids": ["evidence_fixture"],
            },
            "base": {
                "probability": 0.4,
                "relative_alpha_bps": 150,
                "trigger": "Base trigger.",
                "evidence_ids": ["evidence_fixture"],
            },
            "bear": {
                "probability": 0.4,
                "relative_alpha_bps": -500,
                "trigger": "Bear trigger.",
                "evidence_ids": ["evidence_fixture"],
            },
            "catalyst_clarity": 0.6,
            "crowding_risk": 0.3,
            "liquidity_risk": 0.2,
            "next_pricing_fact": "The next primary update.",
            "decision": {
                "what_is_priced_in": "A normal update is priced in.",
                "variant_view": "The frozen evidence supports a faster path.",
                "reference_class": "Comparable revision events.",
                "base_rate_probability": 0.5,
                "inside_view_probability": 0.6,
                "must_be_true": ["The next observation confirms persistence."],
                "company_thesis_status": "intact",
                "security_thesis_readiness": "ready",
                "edge_half_life_days": 10,
                "dominant_uncertainty": "Persistence of the measured change.",
                "action_trigger": "Re-underwrite at the next primary update.",
            },
        },
    }

    parsed = _validate_structured_response(
        adapter,
        json.dumps(payload) + "\n<provider_trailing_marker>",
    )

    assert parsed == PrivateAssessmentPayload.model_validate(payload)
    with pytest.raises(ValidationError):
        _validate_structured_response(
            adapter,
            json.dumps(payload) + "\n" + json.dumps({**payload, "confidence": 0.56}),
        )

    inconsistent = {**payload, "forecast_probability": 0.3}
    with pytest.raises(ValidationError, match="scenario distribution"):
        PrivateAssessmentPayload.model_validate(inconsistent)

    missing_decision = {
        **payload,
        "underwriting": {
            key: value
            for key, value in payload["underwriting"].items()
            if key != "decision"
        },
    }
    with pytest.raises(ValidationError, match="requires decision intelligence"):
        PrivateAssessmentPayload.model_validate(missing_decision)


def test_ordered_evidence_is_fitted_without_exceeding_the_role_budget() -> None:
    items = [
        {"evidence_id": f"evidence_{index}", "summary": "e" * 500}
        for index in range(100)
    ]

    fitted = fit_frozen_items(
        {"positions": [{"position_id": "position_1", "thesis": "t" * 2_000}]},
        "new_evidence",
        items,
    )

    assert 0 < len(fitted["new_evidence"]) < len(items)
    assert fitted["new_evidence"] == items[: len(fitted["new_evidence"])]
    assert frozen_input_size(fitted) <= MAX_ROLE_FROZEN_INPUT_BYTES


def test_private_assessment_fits_evidence_and_hides_omitted_ids() -> None:
    known_at = datetime(2026, 8, 23, 14, tzinfo=UTC)
    opportunity = large_opportunity(known_at).model_copy(
        update={
            "beneficiary_path": "b" * 2_000,
            "disconfirming_evidence": "d" * 2_000,
            "next_test": "t" * 2_000,
            "evidence_ids": tuple(f"evidence_{index}" for index in range(20)),
        }
    )
    evidence = [
        {
            "evidence_id": evidence_id,
            "known_at": known_at.isoformat(),
            "stance": "support",
            "summary": "e" * 120,
            "source": "fixture",
            "content_hash": f"{index:x}" * 64,
        }
        for index, evidence_id in enumerate(opportunity.evidence_ids, start=1)
    ]

    class CapturingRunner:
        model_provider = "fixture"
        model_id = "fixture-model"

        def run(self, **kwargs):
            frozen = kwargs["frozen_input"]
            assert frozen_input_size(frozen) <= MAX_ROLE_FROZEN_INPUT_BYTES
            visible = tuple(item["evidence_id"] for item in frozen["evidence"])
            assert 0 < len(visible) < len(opportunity.evidence_ids)
            assert tuple(frozen["opportunity"]["evidence_ids"]) == visible
            raise RuntimeError("captured fitted private input")

    class CapturingDeliberator(AgenticDeliberator):
        def _load_assessment(self, _assessment_id):
            return None

    deliberator = CapturingDeliberator(
        None,
        CapturingRunner(),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="captured fitted private input"):
        deliberator._assessment(  # noqa: SLF001
            "fitting-cycle",
            opportunity,
            {"evidence": evidence},
            "thesis_assessor",
            known_at,
        )
