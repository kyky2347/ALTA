import json
from datetime import timedelta
from pathlib import Path

import pytest

from alta_asterism.foundry import (
    CandidateDraft,
    CompletionPatch,
    apply_completion,
    deduplicate,
    normalize_key,
)
from alta_asterism.investment_thesis import ThesisPillarDraft
from alta_asterism.opportunity_identity import (
    horizon_bucket,
    normalize_catalyst_bucket,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "b4" / "foundry_cases.json"


def test_catalyst_bucket_normalization_is_stable_and_legacy_safe() -> None:
    assert normalize_catalyst_bucket(" Shared_POLICY Reset ") == "shared-policy-reset"
    assert normalize_catalyst_bucket("政策冲击") == "政策冲击"
    assert normalize_catalyst_bucket(None) == "legacy-unclassified"


def fixture_candidates() -> tuple[dict, tuple[CandidateDraft, ...]]:
    payload = json.loads(FIXTURE.read_text())
    candidates = [CandidateDraft.model_validate(item) for item in payload["candidates"]]
    patch = CompletionPatch.model_validate(payload["completion_patch"])
    candidates = [
        apply_completion(item, patch)
        if item.candidate_id == patch.candidate_id
        else item
        for item in candidates
    ]
    return payload, tuple(candidates)


def test_completion_only_fills_missing_fields_from_frozen_evidence() -> None:
    payload = json.loads(FIXTURE.read_text())
    candidate = CandidateDraft.model_validate(payload["candidates"][-1])
    patch = CompletionPatch.model_validate(payload["completion_patch"])

    completed = apply_completion(candidate, patch)

    assert completed.missing_fields() == ()
    assert completed.completion_provenance == {
        field: ("evidence_completion",)
        for field in (
            "catalyst_key",
            "observed_change",
            "mechanism",
            "direction",
            "expectation_posture",
            "first_rejection",
            "prediction",
            "investability",
            "freshness_at",
        )
    }
    with pytest.raises(ValueError, match="outside the frozen candidate"):
        apply_completion(
            candidate,
            patch.model_copy(
                update={"provenance_evidence_ids": ("evidence_unfrozen",)}
            ),
        )

    exact = CandidateDraft.model_validate(payload["candidates"][0])
    with pytest.raises(ValueError, match="cannot overwrite"):
        apply_completion(
            exact,
            CompletionPatch(
                candidate_id=exact.candidate_id,
                mechanism="different mechanism",
                provenance_evidence_ids=exact.evidence_ids,
            ),
        )


def test_exact_and_structural_dedup_is_deterministic_and_avoids_wrong_merge() -> None:
    payload, candidates = fixture_candidates()

    result = deduplicate(payload["batch_id"], candidates)
    repeated = deduplicate(payload["batch_id"], tuple(reversed(candidates)))

    assert result == repeated
    assert len(result.opportunities) == 5
    assert {
        (relation.left_candidate_id, relation.right_candidate_id, relation.kind)
        for relation in result.relations
    } == {
        ("candidate_exact_a", "candidate_exact_b", "duplicate"),
        ("candidate_struct_a", "candidate_struct_b", "merge"),
        (
            "candidate_wrong_negative",
            "candidate_wrong_positive",
            "competing",
        ),
    }
    members = {item.member_candidate_ids for item in result.opportunities}
    assert ("candidate_exact_a", "candidate_exact_b") in members
    assert ("candidate_struct_a", "candidate_struct_b") in members
    assert ("candidate_wrong_negative",) in members
    assert ("candidate_wrong_positive",) in members
    assert normalize_key("政策＿变化 / 甲") == "政策-变化-甲"

    changed_mechanism = candidates[1].model_copy(
        update={
            "mechanism": "Different wording for the same event propagation",
            "horizon_days": candidates[0].horizon_days + 1,
        }
    )
    assert changed_mechanism.exact_key() == candidates[0].exact_key()


def test_dedup_rejects_duplicate_ids_and_unbounded_batches() -> None:
    payload, candidates = fixture_candidates()
    with pytest.raises(ValueError, match="IDs must be unique"):
        deduplicate(payload["batch_id"], (candidates[0], candidates[0]))
    with pytest.raises(ValueError, match="1 to 20"):
        deduplicate(payload["batch_id"], ())
    with pytest.raises(ValueError, match="1 to 20"):
        deduplicate(payload["batch_id"], tuple(candidates[0] for _ in range(21)))
    with pytest.raises(ValueError, match="between 1 and 365"):
        horizon_bucket(0)


def test_dedup_preserves_follow_up_lineage_without_changing_identity() -> None:
    payload, candidates = fixture_candidates()
    updated = tuple(
        item.model_copy(
            update={
                "research_mode": "follow_up",
                "parent_opportunity_id": "opportunity_prior",
                "research_question": "Did the changed fact reach consensus estimates?",
            }
        )
        if item.candidate_id == "candidate_exact_b"
        else item
        for item in candidates
    )

    opportunity = next(
        item
        for item in deduplicate(payload["batch_id"], updated).opportunities
        if item.member_candidate_ids == ("candidate_exact_a", "candidate_exact_b")
    )

    assert opportunity.research_mode == "follow_up"
    assert opportunity.parent_opportunity_id == "opportunity_prior"
    assert opportunity.research_question.startswith("Did the changed fact")


def test_foundry_freezes_and_merges_falsifiable_thesis_pillars() -> None:
    payload, candidates = fixture_candidates()
    pillar = ThesisPillarDraft(
        statement="The operating change reaches consensus estimates.",
        observable="The next versioned estimate snapshot",
        confirmation_condition="Estimates move in the mechanism's direction",
        invalidation_condition="Estimates remain unchanged after the catalyst",
        expected_by_days=5,
    )
    updated = tuple(
        item.model_copy(update={"thesis_pillars": (pillar,)})
        if item.candidate_id in {"candidate_exact_a", "candidate_exact_b"}
        else item
        for item in candidates
    )

    opportunity = next(
        item
        for item in deduplicate(payload["batch_id"], updated).opportunities
        if item.member_candidate_ids == ("candidate_exact_a", "candidate_exact_b")
    )

    assert len(opportunity.thesis_pillars) == 1
    assert opportunity.thesis_pillars[0].source_candidate_ids == (
        opportunity.candidate_id,
    )
    assert opportunity.thesis_pillars[0].due_at > opportunity.thesis_pillars[0].known_at


def test_foundry_never_synthesizes_one_claim_from_different_candidates() -> None:
    payload, candidates = fixture_candidates()
    anchor = candidates[0].model_copy(
        update={
            "why_now": None,
            "next_test": None,
            "confidence": 0.41,
        }
    )
    contributor = candidates[1].model_copy(
        update={
            "why_now": "A different Trader Mind supplied this timing claim.",
            "next_test": "A different Trader Mind supplied this next test.",
            "confidence": 0.91,
        }
    )

    opportunity = deduplicate(payload["batch_id"], (anchor, contributor)).opportunities[
        0
    ]

    assert opportunity.candidate_id == anchor.candidate_id
    assert opportunity.why_now is None
    assert opportunity.next_test is None
    assert opportunity.confidence == anchor.confidence
    assert opportunity.member_candidate_ids == (
        anchor.candidate_id,
        contributor.candidate_id,
    )
    assert opportunity.evidence_ids == anchor.evidence_ids
    assert opportunity.audit_evidence_ids == tuple(
        dict.fromkeys((*anchor.evidence_ids, *contributor.evidence_ids))
    )


def test_unrelated_contributor_evidence_never_enters_decision_claim() -> None:
    payload, candidates = fixture_candidates()
    anchor = candidates[0]
    contributor = candidates[1].model_copy(
        update={"evidence_ids": ("evidence_unrelated_contributor",)}
    )

    opportunity = deduplicate(payload["batch_id"], (anchor, contributor)).opportunities[
        0
    ]

    assert opportunity.evidence_ids == anchor.evidence_ids
    assert "evidence_unrelated_contributor" not in opportunity.evidence_ids
    assert "evidence_unrelated_contributor" in opportunity.audit_evidence_ids
    assert all(
        "evidence_unrelated_contributor" not in pillar.evidence_ids
        for pillar in opportunity.thesis_pillars
    )


def test_follow_up_candidate_owns_the_refreshed_claim_bundle() -> None:
    payload, candidates = fixture_candidates()
    follow_up = candidates[1].model_copy(
        update={
            "research_mode": "follow_up",
            "parent_opportunity_id": "opportunity_prior",
            "research_question": "Did the measurable operating fact change?",
            "why_now": "The assigned follow-up found a newly versioned fact.",
        }
    )

    opportunity = deduplicate(
        payload["batch_id"], (candidates[0], follow_up)
    ).opportunities[0]

    assert opportunity.candidate_id == follow_up.candidate_id
    assert opportunity.title == follow_up.title
    assert opportunity.why_now == follow_up.why_now
    assert opportunity.research_mode == "follow_up"


def test_latest_follow_up_owns_claim_and_contributor_cannot_add_a_pillar() -> None:
    payload, candidates = fixture_candidates()
    stale_pillar = ThesisPillarDraft(
        statement="A stale contributor claim should not enter the selected thesis.",
        observable="A stale contributor observable",
        confirmation_condition="The stale condition is confirmed",
        invalidation_condition="The stale condition is rejected",
        expected_by_days=4,
    )
    current_pillar = ThesisPillarDraft(
        statement="The latest follow-up claim remains measurable.",
        observable="The next versioned operating update",
        confirmation_condition="The latest operating signal persists",
        invalidation_condition="The latest operating signal reverses",
        expected_by_days=3,
    )
    stale = candidates[0].model_copy(
        update={
            "research_mode": "follow_up",
            "parent_opportunity_id": "opportunity_prior",
            "research_question": "What did the earlier follow-up observe?",
            "title": "Stale follow-up",
            "thesis_pillars": (stale_pillar,),
        }
    )
    current = candidates[1].model_copy(
        update={
            "research_mode": "follow_up",
            "parent_opportunity_id": "opportunity_prior",
            "research_question": "What does the latest evidence now show?",
            "known_at": stale.known_at + timedelta(minutes=1),
            "version": stale.version + 1,
            "title": "Current follow-up",
            "thesis_pillars": (current_pillar,),
        }
    )

    opportunity = deduplicate(payload["batch_id"], (stale, current)).opportunities[0]

    assert opportunity.candidate_id == current.candidate_id
    assert opportunity.title == "Current follow-up"
    assert tuple(item.statement for item in opportunity.thesis_pillars) == (
        current_pillar.statement,
    )
