import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from .deliberation import PrivateAssessment
from .foundry import OpportunityDraft
from .scouts import EvidenceSnapshot

# Keep a serialization safety margin below the durable 8,192-byte DB bound.
MAX_ROLE_FROZEN_INPUT_BYTES = 8_000


def bounded_text(value: str | None, maximum_bytes: int) -> str | None:
    if value is None:
        return None
    encoded = value.encode()
    if len(encoded) <= maximum_bytes:
        return value
    return encoded[:maximum_bytes].decode(errors="ignore").rstrip()


def opportunity_context(
    opportunity: OpportunityDraft, *, narrative_bytes: int = 320
) -> dict[str, Any]:
    """Returns the decision fields without duplicating a full durable snapshot."""
    return {
        "opportunity_id": opportunity.opportunity_id,
        "research_mode": opportunity.research_mode,
        "parent_opportunity_id": opportunity.parent_opportunity_id,
        "research_question": bounded_text(opportunity.research_question, 240),
        "version": opportunity.version,
        "known_at": opportunity.known_at.isoformat(),
        "snapshot_hash": opportunity.snapshot_hash,
        "title": bounded_text(opportunity.title, 256),
        "entity_key": opportunity.entity_key,
        "observed_change": bounded_text(opportunity.observed_change, narrative_bytes),
        "mechanism": bounded_text(opportunity.mechanism, narrative_bytes),
        "direction": opportunity.direction,
        "expectation": bounded_text(opportunity.expectation, narrative_bytes),
        "expectation_posture": opportunity.expectation_posture,
        "variant_wedge": bounded_text(opportunity.variant_wedge, narrative_bytes),
        "why_now": bounded_text(opportunity.why_now, narrative_bytes),
        "falsifier": bounded_text(opportunity.falsifier, narrative_bytes),
        "first_rejection": bounded_text(opportunity.first_rejection, narrative_bytes),
        "prediction": bounded_text(opportunity.prediction, narrative_bytes),
        "beneficiary_path": bounded_text(opportunity.beneficiary_path, narrative_bytes),
        "disconfirming_evidence": bounded_text(
            opportunity.disconfirming_evidence, narrative_bytes
        ),
        "next_test": bounded_text(opportunity.next_test, narrative_bytes),
        "thesis_pillars": [
            {
                "pillar_id": item.pillar_id,
                "statement": bounded_text(item.statement, 160),
                "observable": bounded_text(item.observable, 120),
                "confirmation_condition": bounded_text(
                    item.confirmation_condition, 160
                ),
                "invalidation_condition": bounded_text(
                    item.invalidation_condition, 160
                ),
                "due_at": item.due_at.isoformat(),
            }
            for item in opportunity.thesis_pillars
        ],
        "research_diligence": (
            opportunity.research_diligence.model_dump(mode="json")
            if opportunity.research_diligence is not None
            else None
        ),
        "investability": opportunity.investability,
        "freshness_at": (
            opportunity.freshness_at.isoformat()
            if opportunity.freshness_at is not None
            else None
        ),
        "horizon_days": opportunity.horizon_days,
        "confidence": opportunity.confidence,
        "evidence_ids": opportunity.evidence_ids,
    }


def evidence_context(
    evidence: EvidenceSnapshot, *, summary_bytes: int = 240
) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source": evidence.source,
        "territory": evidence.territory,
        "known_at": evidence.known_at.isoformat(),
        "content_hash": evidence.content_hash,
        "summary": bounded_text(evidence.summary, summary_bytes),
    }


def assessment_context(assessment: PrivateAssessment) -> dict[str, Any]:
    decision = assessment.underwriting.decision
    return {
        "assessment_id": assessment.assessment_id,
        "assessor": assessment.assessor,
        "forecast_probability": assessment.forecast_probability,
        "evidence_quality": assessment.evidence_quality,
        "variant_wedge_quality": assessment.variant_wedge_quality,
        "strongest_support": bounded_text(assessment.strongest_support, 180),
        "strongest_disconfirmation": bounded_text(
            assessment.strongest_disconfirmation, 180
        ),
        "first_rejection": bounded_text(assessment.first_rejection, 180),
        "missing_evidence": tuple(
            bounded_text(item, 72) for item in assessment.missing_evidence[:3]
        ),
        "recommendation": assessment.recommendation,
        "confidence": assessment.confidence,
        "evidence_ids": assessment.evidence_ids,
        "rationale": bounded_text(assessment.rationale, 240),
        "underwriting": {
            "benchmark_symbol": assessment.underwriting.benchmark_symbol,
            "expected_alpha_bps": str(
                assessment.underwriting.expected_alpha_bps.quantize(Decimal("0.01"))
            ),
            "bull_alpha_bps": assessment.underwriting.bull.relative_alpha_bps,
            "base_alpha_bps": assessment.underwriting.base.relative_alpha_bps,
            "bear_alpha_bps": assessment.underwriting.bear.relative_alpha_bps,
            "catalyst_clarity": assessment.underwriting.catalyst_clarity,
            "crowding_risk": assessment.underwriting.crowding_risk,
            "liquidity_risk": assessment.underwriting.liquidity_risk,
            "next_pricing_fact": bounded_text(
                assessment.underwriting.next_pricing_fact, 160
            ),
            "decision": (
                {
                    "what_is_priced_in": bounded_text(decision.what_is_priced_in, 80),
                    "variant_view": bounded_text(decision.variant_view, 80),
                    "reference_class": bounded_text(decision.reference_class, 64),
                    "base_rate_probability": decision.base_rate_probability,
                    "inside_view_probability": decision.inside_view_probability,
                    "must_be_true": tuple(
                        bounded_text(item, 48) for item in decision.must_be_true[:2]
                    ),
                    "company_thesis_status": decision.company_thesis_status,
                    "security_thesis_readiness": decision.security_thesis_readiness,
                    "edge_half_life_days": decision.edge_half_life_days,
                    "dominant_uncertainty": bounded_text(
                        decision.dominant_uncertainty, 64
                    ),
                    "action_trigger": bounded_text(decision.action_trigger, 64),
                }
                if decision is not None
                else None
            ),
        },
    }


def frozen_input_size(value: dict[str, Any]) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode()
    )


def require_bounded_frozen_input(value: dict[str, Any]) -> None:
    if frozen_input_size(value) > MAX_ROLE_FROZEN_INPUT_BYTES:
        raise ValueError("structured role frozen input exceeds hard byte budget")


def fit_frozen_items(
    base: dict[str, Any], field: str, items: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Adds ordered items until the structured-role byte budget is exhausted."""
    fitted = {**base, field: []}
    require_bounded_frozen_input(fitted)
    for item in items:
        candidate = {**fitted, field: [*fitted[field], item]}
        if frozen_input_size(candidate) > MAX_ROLE_FROZEN_INPUT_BYTES:
            break
        fitted = candidate
    return fitted
