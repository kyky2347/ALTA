import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from alta_asterism.b4_runtime import (
    DeliberationRepository,
    FoundryRepository,
)
from alta_asterism.database import Database
from alta_asterism.contracts import Environment
from alta_asterism.deliberation import (
    DiscussionPolicy,
    DiscussionRound,
    PrivateAssessment,
    run_short_discussion,
)
from alta_asterism.foundry import (
    CandidateDraft,
    CompletionPatch,
    OpportunityDraft,
    apply_completion,
    deduplicate,
)
from alta_asterism.live_source_flow import DatabaseSourceFlow
from alta_asterism.migrations import LATEST_REVISION, b1_0001, b3_0002
from alta_asterism.opportunity_registry import OpportunityRegistry
from alta_asterism.ranking import build_ranking_book
from alta_asterism.ranking_store import RankingRepository
from alta_asterism.research_diligence import ResearchDiligence
from alta_asterism.underwriting import (
    DecisionIntelligence,
    ScenarioCase,
    ScenarioUnderwriting,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "b4" / "foundry_cases.json"


def decision_grade_diligence() -> ResearchDiligence:
    return ResearchDiligence(
        posture="cross_checked",
        completed_tool_calls=4,
        active_research_calls=4,
        non_news_research_calls=3,
        source_families=("primary_web", "market_data", "versioned_web"),
        independent_source_domains=(
            "issuer.example",
            "exchange.example",
            "regulator.example",
        ),
        beneficiary_path_declared=True,
        counterevidence_declared=True,
        next_test_declared=True,
    )


def database_url(base_url: str, name: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit(parsed._replace(path=f"/{name}", query="", fragment=""))


@pytest.fixture
def empty_b4_database() -> str:
    base_url = os.environ["DATABASE_URL"]
    name = f"alta_test_b4_{uuid4().hex[:12]}"
    assert name.startswith("alta_test_b4_")
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database_url(base_url, name)
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


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
    candidates = [
        item.model_copy(update={"research_diligence": decision_grade_diligence()})
        for item in candidates
    ]
    return payload, tuple(candidates)


def seed_database(database: Database, candidates: tuple[CandidateDraft, ...]) -> None:
    run_ids = (
        "run_b4_fixture",
        "run_thesis_assessor",
        "run_disconfirming_assessor",
    )
    known_at = candidates[0].known_at
    with database.connect() as connection:
        for index, run_id in enumerate(run_ids):
            connection.execute(
                """INSERT INTO research.run
                (id, environment, version, known_at, role, status, input_hash,
                 frozen_input, budget, deadline_at, prompt_version,
                 tool_catalog_version, model_provider, model_id, trace_id,
                 tool_provenance, evidence_ids)
                VALUES (%s,'replay',1,%s,%s,'succeeded',%s,%s,%s,%s,
                        'b4-fixture-v1','none','deterministic','fixture',%s,
                        '[]'::jsonb,'{}'::text[])""",
                (
                    run_id,
                    known_at,
                    f"b4_role_{index}",
                    hashlib.sha256(run_id.encode()).hexdigest(),
                    Jsonb({"fixture": True, "run_id": run_id}),
                    Jsonb({"max_tool_calls": 0}),
                    known_at + timedelta(minutes=5),
                    f"trace_b4_{index}",
                ),
            )
        for candidate in candidates:
            raw_id = f"raw_{candidate.candidate_id}"
            content_hash = hashlib.sha256(candidate.candidate_id.encode()).hexdigest()
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body)
                VALUES (%s,'replay',1,%s,'b4_fixture',%s,%s,%s)""",
                (
                    raw_id,
                    candidate.known_at - timedelta(minutes=2),
                    candidate.candidate_id,
                    content_hash,
                    Jsonb({"fixture": True, "candidate_id": candidate.candidate_id}),
                ),
            )
            for evidence_id in candidate.evidence_ids:
                connection.execute(
                    """INSERT INTO research.evidence
                    (id, environment, version, known_at, raw_id, stance, summary)
                    VALUES (%s,'replay',1,%s,%s,'support',%s)""",
                    (
                        evidence_id,
                        candidate.known_at - timedelta(minutes=1),
                        raw_id,
                        f"Fixed evidence for {candidate.candidate_id}.",
                    ),
                )
            connection.execute(
                """INSERT INTO research.candidate
                (id, environment, version, known_at, run_id, title, why_now,
                 expectation, variant_wedge, falsifier, horizon_days,
                 confidence, evidence_ids)
                VALUES (%s,'replay',%s,%s,'run_b4_fixture',%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    candidate.candidate_id,
                    candidate.version,
                    candidate.known_at,
                    candidate.title,
                    candidate.why_now,
                    candidate.expectation,
                    candidate.variant_wedge,
                    candidate.falsifier,
                    candidate.horizon_days,
                    candidate.confidence,
                    list(candidate.evidence_ids),
                ),
            )


def private_assessments(
    opportunity: OpportunityDraft,
) -> tuple[PrivateAssessment, PrivateAssessment]:
    values = (
        ("thesis_assessor", "run_thesis_assessor", 0.76, 0.8, "advance"),
        ("disconfirming_assessor", "run_disconfirming_assessor", 0.66, 0.64, "wait"),
    )
    return tuple(
        PrivateAssessment(
            assessment_id=f"assessment_{assessor}_{opportunity.candidate_id}",
            opportunity_id=opportunity.opportunity_id,
            run_id=run_id,
            assessor=assessor,
            snapshot_hash=opportunity.snapshot_hash,
            forecast_probability=probability,
            evidence_quality=evidence_quality,
            variant_wedge_quality=0.7 if assessor == "thesis_assessor" else 0.56,
            strongest_support="The frozen primary record supports the mechanism.",
            strongest_disconfirmation="The take-up rate may remain below threshold.",
            first_rejection=opportunity.first_rejection or "Reject on failed premise.",
            missing_evidence=("future take-up update",),
            recommendation=recommendation,
            confidence=0.7 if assessor == "thesis_assessor" else 0.6,
            evidence_ids=opportunity.evidence_ids,
            rationale="Locked fixed private assessment; no hidden reasoning.",
            underwriting=ScenarioUnderwriting(
                bull=ScenarioCase(
                    probability=0.2,
                    relative_alpha_bps=750,
                    trigger="The catalyst propagates faster than expected.",
                    evidence_ids=opportunity.evidence_ids,
                ),
                base=ScenarioCase(
                    probability=round(probability - 0.2, 2),
                    relative_alpha_bps=180,
                    trigger="The mechanism partially reaches the prediction.",
                    evidence_ids=opportunity.evidence_ids,
                ),
                bear=ScenarioCase(
                    probability=round(1 - probability, 2),
                    relative_alpha_bps=-550,
                    trigger="The next update confirms the first rejection.",
                    evidence_ids=opportunity.evidence_ids,
                ),
                catalyst_clarity=0.68,
                crowding_risk=0.25,
                liquidity_risk=0.15,
                next_pricing_fact="The next primary operating update.",
                decision=DecisionIntelligence(
                    what_is_priced_in=opportunity.expectation,
                    variant_view=opportunity.variant_wedge,
                    reference_class="Comparable expectation-revision events.",
                    base_rate_probability=0.5,
                    inside_view_probability=probability,
                    must_be_true=(opportunity.prediction or opportunity.variant_wedge,),
                    company_thesis_status=(
                        "intact" if assessor == "thesis_assessor" else "watch"
                    ),
                    security_thesis_readiness=(
                        "ready" if assessor == "thesis_assessor" else "conditional"
                    ),
                    edge_half_life_days=min(opportunity.horizon_days, 30),
                    dominant_uncertainty="The speed of causal propagation.",
                    action_trigger="Re-underwrite at the next primary update.",
                ),
            ),
            locked_at=opportunity.known_at + timedelta(minutes=1),
            prompt_version="b4-private-fixture-v1",
            model_id="deterministic-fixture",
        )
        for assessor, run_id, probability, evidence_quality, recommendation in values
    )


def test_upgrade_from_populated_b3_backfills_b4_contracts(
    empty_b4_database: str,
) -> None:
    database = Database(empty_b4_database)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA alta_meta")
            cursor.execute(
                """CREATE TABLE alta_meta.schema_migration (
                revision text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now())"""
            )
            for migration in (b1_0001, b3_0002):
                migration.upgrade(cursor)
                cursor.execute(
                    "INSERT INTO alta_meta.schema_migration (revision) VALUES (%s)",
                    (migration.REVISION,),
                )
        connection.execute(
            """INSERT INTO research.run
            (id, environment, version, known_at, role, status, input_hash,
             frozen_input, budget, deadline_at, prompt_version,
             tool_catalog_version, model_provider, model_id, trace_id,
             tool_provenance, evidence_ids)
            VALUES ('run_populated_b3','replay',1,now(),'fixture','succeeded',%s,
                    '{}'::jsonb,'{}'::jsonb,now(),'b3','b3','fixture','fixture',
                    'trace_b3','[]'::jsonb,'{}'::text[])""",
            ("a" * 64,),
        )
        connection.execute(
            """INSERT INTO research.candidate
            (id, environment, version, known_at, run_id, title, why_now,
             expectation, variant_wedge, falsifier, horizon_days, confidence,
             evidence_ids)
            VALUES ('candidate_populated_b3','replay',1,now(),'run_populated_b3',
                    'Legacy candidate','Legacy why now','Legacy expectation',
                    'Legacy wedge','Legacy falsifier',10,0.5,'{}'::text[])"""
        )
        connection.execute(
            """INSERT INTO research.opportunity
            (id, environment, version, known_at, candidate_id, status, title,
             thesis, falsifier, horizon_days)
            VALUES ('opportunity_populated_b3','replay',1,now(),
                    'candidate_populated_b3','forming','Legacy opportunity',
                    'Legacy thesis','Legacy falsifier',10)"""
        )
        connection.execute(
            """INSERT INTO research.assessment
            (id, environment, version, known_at, opportunity_id, run_id,
             assessor, verdict, score, rationale)
            VALUES ('assessment_populated_b3','replay',1,now(),
                    'opportunity_populated_b3','run_populated_b3','legacy',
                    'hold',0.5,'Legacy rationale')"""
        )
        connection.execute(
            """INSERT INTO research.rank
            (id, environment, version, known_at, opportunity_id, book,
             position, score)
            VALUES ('rank_populated_b3','replay',1,now(),
                    'opportunity_populated_b3','legacy',1,0.5)"""
        )

    assert database.upgrade() == LATEST_REVISION
    with database.connect() as connection:
        opportunity = connection.execute(
            """SELECT member_candidate_ids, foundry_state, merge_revision,
            expectation_posture, investability, completeness
            FROM research.opportunity"""
        ).fetchone()
        assessment = connection.execute(
            """SELECT assessment_kind, forecast_probability, recommendation,
            locked_at IS NOT NULL FROM research.assessment"""
        ).fetchone()
        rank = connection.execute(
            """SELECT ranking_run_id, horizon_min_days, horizon_max_days,
            gate_status FROM research.rank"""
        ).fetchone()
    assert opportunity == (
        ["candidate_populated_b3"],
        "active",
        1,
        "unavailable",
        "unknown",
        "enriching",
    )
    assert assessment == ("private", 0.5, "wait", True)
    assert rank == ("pre-b4-v1", 5, 20, "ranked")
    assert database.downgrade() == "base"
    assert database.upgrade() == LATEST_REVISION


def test_b4_foundry_private_discussion_and_single_book_pipeline(
    empty_b4_database: str,
) -> None:
    database = Database(empty_b4_database)
    database.upgrade()
    payload, candidates = fixture_candidates()
    seed_database(database, candidates)
    result = deduplicate(payload["batch_id"], candidates)
    foundry = FoundryRepository(database)

    foundry.materialize(result, candidates)
    foundry.materialize(result, candidates)

    with database.connect() as connection:
        counts = connection.execute(
            """SELECT
            (SELECT count(*) FROM research.opportunity),
            (SELECT count(*) FROM ops.event
                WHERE event_type = 'foundry.merge.applied'),
            (SELECT count(*) FROM ops.event
                WHERE event_type = 'foundry.relation.recorded'),
            (SELECT count(*) FROM research.candidate
                WHERE foundry_snapshot_hash IS NOT NULL)"""
        ).fetchone()
    assert counts == (5, 2, 3, 7)
    assert foundry.active_relations(payload["batch_id"]) == result.relations
    with database.connect() as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """UPDATE research.candidate SET title = 'mutated'
                WHERE id = 'candidate_exact_a'"""
            )
        connection.rollback()

    duplicate_relation = next(
        item for item in result.relations if item.kind == "duplicate"
    )
    foundry.reverse_relation(
        duplicate_relation.relation_id, candidates[0].known_at + timedelta(minutes=1)
    )
    assert duplicate_relation not in foundry.active_relations(payload["batch_id"])

    exact_opportunity = next(
        item
        for item in result.opportunities
        if item.member_candidate_ids == ("candidate_exact_a", "candidate_exact_b")
    )
    with database.connect() as connection:
        merge_event_id = connection.execute(
            """SELECT id FROM ops.event WHERE aggregate_id = %s
            AND event_type = 'foundry.merge.applied'""",
            (exact_opportunity.opportunity_id,),
        ).fetchone()[0]
    restored = foundry.undo_merge(
        merge_event_id, candidates[0].known_at + timedelta(minutes=2)
    )
    assert restored == ("candidate_exact_a", "candidate_exact_b")
    with database.connect() as connection:
        restored_members = connection.execute(
            """SELECT member_candidate_ids FROM research.opportunity
            WHERE candidate_id = ANY(%s) ORDER BY candidate_id""",
            (list(restored),),
        ).fetchall()
    assert restored_members == [
        (["candidate_exact_a"],),
        (["candidate_exact_b"],),
    ]

    opportunity = next(
        item
        for item in result.opportunities
        if item.member_candidate_ids == ("candidate_struct_a", "candidate_struct_b")
    )
    assessments = private_assessments(opportunity)
    deliberation = DeliberationRepository(database)
    deliberation.lock_private_assessment(opportunity, assessments[0])
    with pytest.raises(ValueError, match="both independent"):
        deliberation.share_private_assessments(
            opportunity, opportunity.known_at + timedelta(minutes=2)
        )
    deliberation.lock_private_assessment(opportunity, assessments[1])
    with database.connect() as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """UPDATE research.assessment SET score = 0.99
                WHERE id = %s""",
                (assessments[0].assessment_id,),
            )
        connection.rollback()
    deliberation.share_private_assessments(
        opportunity, opportunity.known_at + timedelta(minutes=2)
    )

    discussion = run_short_discussion(
        opportunity,
        assessments,
        preliminary_position=1,
        rounds=(
            DiscussionRound(
                round_number=1,
                summary="No new evidence, testable claim, or material belief update.",
                evidence_ids=opportunity.evidence_ids,
            ),
            DiscussionRound(
                round_number=2,
                summary="This fixed round is beyond the stop condition.",
                testable_claims=("Should not be consumed",),
            ),
        ),
        policy=DiscussionPolicy(),
    )
    with database.connect() as connection:
        evidence_before = connection.execute(
            "SELECT count(*) FROM research.evidence"
        ).fetchone()[0]
    deliberation.record_discussion(
        opportunity, discussion, opportunity.known_at + timedelta(minutes=3)
    )
    with database.connect() as connection:
        evidence_after = connection.execute(
            "SELECT count(*) FROM research.evidence"
        ).fetchone()[0]
        discussion_events = connection.execute(
            """SELECT event_type FROM ops.event WHERE aggregate_id = %s
            AND event_type LIKE 'committee.%%' ORDER BY sequence""",
            (opportunity.opportunity_id,),
        ).fetchall()
    assert evidence_after == evidence_before
    assert discussion_events == [
        ("committee.discussion_round",),
        ("committee.discussion_stopped",),
    ]
    assert discussion.stop_reason == "no_information_gain"

    book = build_ranking_book(
        "ranking_b4_fixture_v1",
        (opportunity,),
        {opportunity.opportunity_id: assessments},
        {opportunity.opportunity_id: discussion},
        opportunity.known_at + timedelta(minutes=4),
    )
    RankingRepository(database).persist(book, (opportunity,))
    with database.connect() as connection:
        rank = connection.execute(
            """SELECT book, position, horizon_min_days, horizon_max_days,
            gate_status, components FROM research.rank"""
        ).fetchone()
        forbidden_counts = connection.execute(
            """SELECT
            (SELECT count(*) FROM research.expression),
            (SELECT count(*) FROM research.shadow_position)"""
        ).fetchone()
    assert rank[0:5] == ("opportunity_1_90d", 1, 1, 90, "ranked")
    assert set(rank[5]) == {
        "effective_probability",
        "evidence_quality",
        "variant_wedge_quality",
        "freshness",
        "investability",
        "expectation_posture",
        "private_disagreement",
        "consensus_expected_alpha_bps",
        "conservative_expected_alpha_bps",
        "forecast_dispersion_bps",
        "forecast_uncertainty_reserve_bps",
        "uncertainty_adjusted_expected_alpha_bps",
        "expected_alpha_score",
        "downside_resilience",
        "payoff_asymmetry",
        "catalyst_clarity",
        "crowding_risk",
        "liquidity_risk",
        "scenario_disagreement",
        "decision_readiness",
        "edge_half_life_days",
        "base_rate_probability",
        "inside_view_probability",
        "variant_probability_lift",
        "conservative_variant_probability_lift",
        "variant_edge_strength",
        "research_quality",
        "research_source_breadth",
        "research_route_diversity",
        "research_non_news_depth",
    }
    assert forbidden_counts == (0, 0)


def test_cross_cycle_registry_suppresses_same_content_and_refreshes_new_evidence(
    empty_b4_database: str,
) -> None:
    database = Database(empty_b4_database)
    database.upgrade()
    payload, candidates = fixture_candidates()
    seed_database(database, candidates)
    foundry = FoundryRepository(database)
    registry = OpportunityRegistry(database)
    initial = deduplicate(payload["batch_id"], candidates)
    foundry.materialize(initial, candidates)
    assert registry.resolve(payload["batch_id"], initial.opportunities) == (
        initial.opportunities
    )
    parent = next(
        item
        for item in initial.opportunities
        if item.member_candidate_ids == ("candidate_exact_a", "candidate_exact_b")
    )

    def repeated_candidate(
        candidate_id: str,
        evidence_id: str,
        content_hash: str,
        *,
        source: str = "b4_fixture",
        fixture: bool = True,
        updates: dict | None = None,
    ) -> CandidateDraft:
        candidate = candidates[0].model_copy(
            update={
                "candidate_id": candidate_id,
                "known_at": candidates[0].known_at + timedelta(hours=1),
                "mechanism": "Equivalent mechanism expressed with new wording",
                "evidence_ids": (evidence_id,),
                **(updates or {}),
            }
        )
        with database.connect() as connection:
            raw_id = f"raw_{candidate_id}"
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body)
                VALUES (%s,'replay',1,%s,%s,%s,%s,%s)""",
                (
                    raw_id,
                    candidate.known_at - timedelta(minutes=2),
                    source,
                    candidate_id,
                    content_hash,
                    Jsonb({"fixture": fixture, "candidate_id": candidate_id}),
                ),
            )
            connection.execute(
                """INSERT INTO research.evidence
                (id, environment, version, known_at, raw_id, stance, summary)
                VALUES (%s,'replay',1,%s,%s,'support','Registry fixture')""",
                (evidence_id, candidate.known_at - timedelta(minutes=1), raw_id),
            )
            connection.execute(
                """INSERT INTO research.candidate
                (id, environment, version, known_at, run_id, title, why_now,
                 expectation, variant_wedge, falsifier, horizon_days,
                 confidence, evidence_ids)
                VALUES (%s,'replay',1,%s,'run_b4_fixture',%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    candidate_id,
                    candidate.known_at,
                    candidate.title,
                    candidate.why_now,
                    candidate.expectation,
                    candidate.variant_wedge,
                    candidate.falsifier,
                    candidate.horizon_days,
                    candidate.confidence,
                    [evidence_id],
                ),
            )
        return candidate

    with database.connect() as connection:
        same_hash = connection.execute(
            """SELECT r.content_hash FROM research.evidence e
            JOIN research.raw r ON r.id = e.raw_id
            WHERE e.id = 'evidence_exact_a'"""
        ).fetchone()[0]
    duplicate = repeated_candidate(
        "candidate_exact_repeat", "evidence_exact_repeat", same_hash
    )
    duplicate_result = deduplicate("batch_registry_duplicate", (duplicate,))
    foundry.materialize(duplicate_result, (duplicate,))
    assert (
        registry.resolve("batch_registry_duplicate", duplicate_result.opportunities)
        == ()
    )

    changed = repeated_candidate(
        "candidate_exact_update", "evidence_exact_update", "f" * 64
    )
    changed_result = deduplicate("batch_registry_update", (changed,))
    foundry.materialize(changed_result, (changed,))
    refreshed = registry.resolve("batch_registry_update", changed_result.opportunities)
    recovered = registry.resolve("batch_registry_update", changed_result.opportunities)

    assert refreshed == recovered
    assert len(refreshed) == 1
    assert refreshed[0].opportunity_id == parent.opportunity_id
    assert refreshed[0].version == 2
    assert "evidence_exact_update" in refreshed[0].evidence_ids
    with database.connect() as connection:
        connection.execute(
            "UPDATE research.opportunity SET status = 'shadow' WHERE id = %s",
            (parent.opportunity_id,),
        )
    position_update = repeated_candidate(
        "candidate_exact_position_update",
        "evidence_exact_position_update",
        "e" * 64,
    )
    position_result = deduplicate("batch_registry_position", (position_update,))
    foundry.materialize(position_result, (position_update,))
    assert (
        registry.resolve("batch_registry_position", position_result.opportunities) == ()
    )
    assert (
        registry.resolve("batch_registry_position", position_result.opportunities) == ()
    )

    memory_candidate = repeated_candidate(
        "candidate_memory_real",
        "evidence_memory_real",
        "d" * 64,
        source="official_policy",
        fixture=False,
        updates={
            "title": "Auditable memory candidate",
            "entity_key": "memory-entity",
            "event_key": "memory-event",
            "catalyst_key": "memory-catalyst",
            "next_test": "Verify whether the operating signal reached estimates.",
        },
    )
    memory_result = deduplicate("batch_registry_memory", (memory_candidate,))
    foundry.materialize(memory_result, (memory_candidate,))
    assert registry.resolve("batch_registry_memory", memory_result.opportunities) == (
        memory_result.opportunities
    )
    memory, _ = DatabaseSourceFlow(
        database,
        ("SPY",),
        environment=Environment.REPLAY,
    ).schedule_and_wake(
        "cycle_registry_memory",
        candidates[0].known_at + timedelta(hours=2),
        {},
    )
    remembered_ids = {item.opportunity_id for item in memory.prior_opportunities}
    assert memory_result.opportunities[0].opportunity_id in remembered_ids
    assert parent.opportunity_id not in remembered_ids
    remembered = next(
        item
        for item in memory.prior_opportunities
        if item.opportunity_id == memory_result.opportunities[0].opportunity_id
    )
    assert remembered.research_questions[0].origin == "scout_next_test"
    assert remembered.research_questions[0].prompt.startswith("Verify whether")
    queue = memory.opportunity_drive.research_queue
    assignments = memory.opportunity_drive.research_assignments
    assert 1 <= len(queue) <= 2
    assert {item.opportunity_id for item in queue} == {remembered.opportunity_id}
    assert {item.question_id for item in queue}.issubset(
        {item.question_id for item in remembered.research_questions}
    )
    assert any(item.reason_codes[1] == "next_test" for item in queue)
    assert len(assignments) == len(queue)
    assert len({item.question_id for item in assignments}) == len(assignments)
    for assignment in assignments:
        scoped_drive = memory.opportunity_drive.for_scout(assignment.scout_id)
        assert scoped_drive.assigned_mode == "follow_up"
        assert scoped_drive.assigned_research == assignment
    with database.connect() as connection:
        events = connection.execute(
            """SELECT event_type, payload->>'reason' FROM ops.event
            WHERE event_type LIKE 'foundry.cross_cycle.%%'
            ORDER BY sequence"""
        ).fetchall()
        states = connection.execute(
            """SELECT id, foundry_state, merge_parent_id
            FROM research.opportunity
            WHERE id = ANY(%s) ORDER BY id""",
            (
                [
                    duplicate_result.opportunities[0].opportunity_id,
                    changed_result.opportunities[0].opportunity_id,
                    position_result.opportunities[0].opportunity_id,
                ],
            ),
        ).fetchall()
    assert events == [
        ("foundry.cross_cycle.suppressed", "no_new_evidence_content"),
        ("foundry.cross_cycle.refreshed", "new_evidence_content"),
        (
            "foundry.cross_cycle.position_updated",
            "new_evidence_for_active_position",
        ),
    ]
    assert set(states) == {
        (
            changed_result.opportunities[0].opportunity_id,
            "merged",
            parent.opportunity_id,
        ),
        (
            duplicate_result.opportunities[0].opportunity_id,
            "merged",
            parent.opportunity_id,
        ),
        (
            position_result.opportunities[0].opportunity_id,
            "merged",
            parent.opportunity_id,
        ),
    }
