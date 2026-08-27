from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from .contracts import Environment, Event
from .database import Database
from .deliberation import DiscussionOutcome, PrivateAssessment
from .foundry import (
    CandidateDraft,
    DedupResult,
    FoundryRelation,
    OpportunityDraft,
    canonical_hash,
    deduplicate,
    normalize_key,
)


def _insert_event(connection, event: Event) -> None:
    connection.execute(
        """INSERT INTO ops.event
        (id, environment, version, known_at, aggregate_type, aggregate_id,
         event_type, payload, correlation_id, causation_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO NOTHING""",
        (
            event.id,
            event.environment.value,
            event.version,
            event.known_at,
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            Jsonb(event.payload),
            event.correlation_id,
            event.causation_id,
        ),
    )


def _event(
    *,
    event_id: str,
    environment: Environment,
    known_at: datetime,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    return Event(
        id=event_id,
        environment=environment,
        version=1,
        known_at=known_at,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


class FoundryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def materialize(
        self, result: DedupResult, candidates: tuple[CandidateDraft, ...]
    ) -> None:
        if deduplicate(result.batch_id, candidates) != result:
            raise ValueError("Foundry result is not the deterministic candidate result")
        expected_ids = {
            candidate_id
            for opportunity in result.opportunities
            for candidate_id in opportunity.member_candidate_ids
        }
        if expected_ids != {item.candidate_id for item in candidates}:
            raise ValueError("Foundry result does not cover the frozen batch")
        environment = candidates[0].environment
        known_at = max(item.known_at for item in candidates)
        with self.database.connect() as connection:
            for candidate in candidates:
                self._freeze_candidate(connection, candidate)
            for opportunity in result.opportunities:
                self._insert_opportunity(connection, opportunity)
                if len(opportunity.member_candidate_ids) > 1:
                    merge_event_id = (
                        "event_"
                        + canonical_hash(
                            [result.batch_id, opportunity.member_candidate_ids, "merge"]
                        )[:32]
                    )
                    _insert_event(
                        connection,
                        _event(
                            event_id=merge_event_id,
                            environment=environment,
                            known_at=known_at,
                            aggregate_type="opportunity",
                            aggregate_id=opportunity.opportunity_id,
                            event_type="foundry.merge.applied",
                            payload={
                                "batch_id": result.batch_id,
                                "opportunity_id": opportunity.opportunity_id,
                                "member_candidate_ids": opportunity.member_candidate_ids,
                                "snapshot_hash": opportunity.snapshot_hash,
                            },
                            correlation_id=result.batch_id,
                        ),
                    )
            for relation in result.relations:
                _insert_event(
                    connection,
                    _event(
                        event_id=relation.relation_id,
                        environment=environment,
                        known_at=known_at,
                        aggregate_type="candidate_relation",
                        aggregate_id=relation.relation_id,
                        event_type="foundry.relation.recorded",
                        payload=relation.model_dump(mode="json"),
                        correlation_id=result.batch_id,
                    ),
                )

    def _freeze_candidate(self, connection, candidate: CandidateDraft) -> None:
        row = connection.execute(
            """SELECT environment::text, version, known_at, title, why_now,
            expectation, variant_wedge, falsifier, horizon_days, confidence,
            evidence_ids, alpha_archetype
            FROM research.candidate WHERE id = %s""",
            (candidate.candidate_id,),
        ).fetchone()
        expected = (
            candidate.environment.value,
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
            candidate.alpha_archetype,
        )
        if row != expected:
            raise ValueError("Foundry candidate does not match PostgreSQL")
        snapshot = candidate.model_dump(mode="json")
        snapshot_hash = canonical_hash(snapshot)
        result = connection.execute(
            """UPDATE research.candidate SET foundry_snapshot = %s,
            foundry_snapshot_hash = %s WHERE id = %s AND
            (foundry_snapshot_hash IS NULL OR foundry_snapshot_hash = %s)""",
            (
                Jsonb(snapshot),
                snapshot_hash,
                candidate.candidate_id,
                snapshot_hash,
            ),
        )
        if result.rowcount != 1:
            raise ValueError("candidate already has a different Foundry snapshot")

    def _insert_opportunity(self, connection, opportunity: OpportunityDraft) -> None:
        connection.execute(
            """INSERT INTO research.opportunity
            (id, environment, version, known_at, candidate_id, status, title,
             thesis, falsifier, horizon_days, member_candidate_ids, exact_key,
             structural_key, snapshot_hash, foundry_state, merge_parent_id,
             merge_revision, observed_change, mechanism, direction, expectation,
             expectation_posture, variant_wedge, why_now, first_rejection,
             prediction, investability, freshness_at, evidence_ids, completeness,
             entity_key, event_key, catalyst_key, identity_version)
            VALUES (%s,%s,%s,%s,%s,'forming',%s,%s,%s,%s,%s,%s,%s,%s,
                    'active',NULL,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,2)
            ON CONFLICT (id) DO NOTHING""",
            self._opportunity_values(opportunity),
        )

    @staticmethod
    def _opportunity_values(opportunity: OpportunityDraft) -> tuple[Any, ...]:
        return (
            opportunity.opportunity_id,
            opportunity.environment.value,
            opportunity.version,
            opportunity.known_at,
            opportunity.candidate_id,
            opportunity.title,
            opportunity.thesis,
            opportunity.falsifier or "",
            opportunity.horizon_days,
            list(opportunity.member_candidate_ids),
            opportunity.exact_key,
            opportunity.structural_key,
            opportunity.snapshot_hash,
            opportunity.observed_change,
            opportunity.mechanism,
            opportunity.direction or "unknown",
            opportunity.expectation,
            opportunity.expectation_posture,
            opportunity.variant_wedge,
            opportunity.why_now,
            opportunity.first_rejection,
            opportunity.prediction,
            opportunity.investability or "unknown",
            opportunity.freshness_at,
            list(opportunity.evidence_ids),
            opportunity.completeness,
            normalize_key(opportunity.entity_key) if opportunity.entity_key else None,
            normalize_key(opportunity.event_key) if opportunity.event_key else None,
            (
                normalize_key(opportunity.catalyst_key)
                if opportunity.catalyst_key
                else None
            ),
        )

    def undo_merge(self, merge_event_id: str, known_at: datetime) -> tuple[str, ...]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT environment::text, payload FROM ops.event
                WHERE id = %s AND event_type = 'foundry.merge.applied'""",
                (merge_event_id,),
            ).fetchone()
            if row is None:
                raise ValueError("merge event does not exist")
            environment = Environment(row[0])
            payload = row[1]
            revert_id = "event_" + canonical_hash([merge_event_id, "undo"])[:32]
            if connection.execute(
                "SELECT 1 FROM ops.event WHERE id = %s", (revert_id,)
            ).fetchone():
                return tuple(payload["member_candidate_ids"])
            candidate_rows = connection.execute(
                """SELECT id, foundry_snapshot FROM research.candidate
                WHERE id = ANY(%s) ORDER BY id""",
                (payload["member_candidate_ids"],),
            ).fetchall()
            if len(candidate_rows) != len(payload["member_candidate_ids"]) or any(
                snapshot is None for _, snapshot in candidate_rows
            ):
                raise ValueError("merge undo is missing a frozen candidate snapshot")
            singles = tuple(
                deduplicate(
                    payload["batch_id"],
                    (CandidateDraft.model_validate(snapshot),),
                ).opportunities[0]
                for _, snapshot in candidate_rows
            )
            anchor = singles[0]
            if anchor.opportunity_id != payload.get(
                "opportunity_id", anchor.opportunity_id
            ):
                raise ValueError("merge anchor is inconsistent")
            self._replace_opportunity(connection, anchor, known_at)
            for opportunity in singles[1:]:
                self._insert_opportunity(connection, opportunity)
            _insert_event(
                connection,
                _event(
                    event_id=revert_id,
                    environment=environment,
                    known_at=known_at,
                    aggregate_type="opportunity",
                    aggregate_id=anchor.opportunity_id,
                    event_type="foundry.merge.reverted",
                    payload={
                        "merge_event_id": merge_event_id,
                        "member_candidate_ids": payload["member_candidate_ids"],
                    },
                    correlation_id=payload["batch_id"],
                    causation_id=merge_event_id,
                ),
            )
        return tuple(item.candidate_id for item in singles)

    def _replace_opportunity(
        self, connection, opportunity: OpportunityDraft, known_at: datetime
    ) -> None:
        values = self._opportunity_values(opportunity)
        connection.execute(
            """UPDATE research.opportunity SET environment = %s,
            version = version + 1, known_at = %s, candidate_id = %s,
            status = 'forming', title = %s, thesis = %s, falsifier = %s,
            horizon_days = %s, member_candidate_ids = %s, exact_key = %s,
            structural_key = %s, snapshot_hash = %s, foundry_state = 'active',
            merge_parent_id = NULL, merge_revision = merge_revision + 1,
            observed_change = %s, mechanism = %s, direction = %s,
            expectation = %s, expectation_posture = %s, variant_wedge = %s,
            why_now = %s, first_rejection = %s, prediction = %s,
            investability = %s, freshness_at = %s, evidence_ids = %s,
            completeness = %s, entity_key = %s, event_key = %s,
            catalyst_key = %s, identity_version = 2 WHERE id = %s""",
            (
                values[1],
                known_at,
                *values[4:29],
                opportunity.opportunity_id,
            ),
        )

    def reverse_relation(self, relation_event_id: str, known_at: datetime) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT environment::text, payload, correlation_id FROM ops.event
                WHERE id = %s AND event_type = 'foundry.relation.recorded'""",
                (relation_event_id,),
            ).fetchone()
            if row is None:
                raise ValueError("relation event does not exist")
            revert_id = "event_" + canonical_hash([relation_event_id, "reverse"])[:32]
            _insert_event(
                connection,
                _event(
                    event_id=revert_id,
                    environment=Environment(row[0]),
                    known_at=known_at,
                    aggregate_type="candidate_relation",
                    aggregate_id=relation_event_id,
                    event_type="foundry.relation.reverted",
                    payload={"relation_event_id": relation_event_id},
                    correlation_id=row[2],
                    causation_id=relation_event_id,
                ),
            )
        return revert_id

    def active_relations(self, batch_id: str) -> tuple[FoundryRelation, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, event_type, payload FROM ops.event
                WHERE correlation_id = %s AND event_type IN
                ('foundry.relation.recorded','foundry.relation.reverted')
                ORDER BY sequence""",
                (batch_id,),
            ).fetchall()
        recorded = {
            event_id: FoundryRelation.model_validate(payload)
            for event_id, event_type, payload in rows
            if event_type == "foundry.relation.recorded"
        }
        reverted = {
            payload["relation_event_id"]
            for _, event_type, payload in rows
            if event_type == "foundry.relation.reverted"
        }
        active = [recorded[event_id] for event_id in recorded.keys() - reverted]
        return tuple(
            sorted(
                active,
                key=lambda item: (
                    item.left_candidate_id,
                    item.right_candidate_id,
                    item.kind,
                ),
            )
        )


class DeliberationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def lock_private_assessment(
        self, opportunity: OpportunityDraft, assessment: PrivateAssessment
    ) -> None:
        if (
            assessment.opportunity_id != opportunity.opportunity_id
            or assessment.snapshot_hash != opportunity.snapshot_hash
            or not set(assessment.evidence_ids).issubset(opportunity.evidence_ids)
        ):
            raise ValueError("private assessment does not match the frozen opportunity")
        with self.database.connect() as connection:
            inserted = connection.execute(
                """INSERT INTO research.assessment
                (id, environment, version, known_at, opportunity_id, run_id,
                 assessor, verdict, score, rationale, snapshot_hash,
                 assessment_kind, forecast_probability, evidence_quality,
                 variant_wedge_quality, strongest_support,
                 strongest_disconfirmation, first_rejection, missing_evidence,
                 recommendation, confidence, evidence_ids, locked_at,
                 prompt_version, model_id, underwriting)
                VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,'private',%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    assessment.assessment_id,
                    opportunity.environment.value,
                    opportunity.known_at,
                    opportunity.opportunity_id,
                    assessment.run_id,
                    assessment.assessor,
                    assessment.verdict,
                    assessment.score,
                    assessment.rationale,
                    assessment.snapshot_hash,
                    assessment.forecast_probability,
                    assessment.evidence_quality,
                    assessment.variant_wedge_quality,
                    assessment.strongest_support,
                    assessment.strongest_disconfirmation,
                    assessment.first_rejection,
                    list(assessment.missing_evidence),
                    assessment.recommendation,
                    assessment.confidence,
                    list(assessment.evidence_ids),
                    assessment.locked_at,
                    assessment.prompt_version,
                    assessment.model_id,
                    Jsonb(assessment.underwriting.model_dump(mode="json")),
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    """SELECT opportunity_id, run_id, assessor, verdict, score,
                    rationale, snapshot_hash, forecast_probability,
                    evidence_quality, variant_wedge_quality, strongest_support,
                    strongest_disconfirmation, first_rejection, missing_evidence,
                    recommendation, confidence, evidence_ids, locked_at,
                    prompt_version, model_id, underwriting
                    FROM research.assessment WHERE id = %s""",
                    (assessment.assessment_id,),
                ).fetchone()
                expected = (
                    assessment.opportunity_id,
                    assessment.run_id,
                    assessment.assessor,
                    assessment.verdict,
                    assessment.score,
                    assessment.rationale,
                    assessment.snapshot_hash,
                    assessment.forecast_probability,
                    assessment.evidence_quality,
                    assessment.variant_wedge_quality,
                    assessment.strongest_support,
                    assessment.strongest_disconfirmation,
                    assessment.first_rejection,
                    list(assessment.missing_evidence),
                    assessment.recommendation,
                    assessment.confidence,
                    list(assessment.evidence_ids),
                    assessment.locked_at,
                    assessment.prompt_version,
                    assessment.model_id,
                    assessment.underwriting.model_dump(mode="json"),
                )
                if existing != expected:
                    raise ValueError(
                        "assessment ID already has different immutable content"
                    )

    def share_private_assessments(
        self, opportunity: OpportunityDraft, known_at: datetime
    ) -> str:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, assessor, snapshot_hash, locked_at
                FROM research.assessment WHERE opportunity_id = %s
                AND assessment_kind = 'private' ORDER BY assessor""",
                (opportunity.opportunity_id,),
            ).fetchall()
            if (
                len(rows) != 2
                or {row[1] for row in rows}
                != {"thesis_assessor", "disconfirming_assessor"}
                or any(
                    row[2] != opportunity.snapshot_hash or row[3] is None
                    for row in rows
                )
            ):
                raise ValueError(
                    "both independent private assessments must lock before sharing"
                )
            event_id = (
                "event_"
                + canonical_hash(
                    [opportunity.opportunity_id, opportunity.snapshot_hash, "share"]
                )[:32]
            )
            _insert_event(
                connection,
                _event(
                    event_id=event_id,
                    environment=opportunity.environment,
                    known_at=known_at,
                    aggregate_type="opportunity",
                    aggregate_id=opportunity.opportunity_id,
                    event_type="assessment.private_shared",
                    payload={
                        "assessment_ids": [row[0] for row in rows],
                        "snapshot_hash": opportunity.snapshot_hash,
                    },
                ),
            )
        return event_id

    def record_discussion(
        self,
        opportunity: OpportunityDraft,
        outcome: DiscussionOutcome,
        known_at: datetime,
    ) -> None:
        if not outcome.eligible:
            return
        with self.database.connect() as connection:
            shared = connection.execute(
                """SELECT id FROM ops.event WHERE aggregate_id = %s
                AND event_type = 'assessment.private_shared'""",
                (opportunity.opportunity_id,),
            ).fetchone()
            if shared is None:
                raise ValueError("private assessments must be shared before discussion")
            for item in outcome.rounds:
                event_id = (
                    "event_"
                    + canonical_hash(
                        [
                            opportunity.opportunity_id,
                            opportunity.snapshot_hash,
                            item.round_number,
                        ]
                    )[:32]
                )
                _insert_event(
                    connection,
                    _event(
                        event_id=event_id,
                        environment=opportunity.environment,
                        known_at=known_at,
                        aggregate_type="opportunity",
                        aggregate_id=opportunity.opportunity_id,
                        event_type="committee.discussion_round",
                        payload=item.model_dump(mode="json"),
                        causation_id=shared[0],
                    ),
                )
            stop_id = (
                "event_"
                + canonical_hash(
                    [opportunity.opportunity_id, opportunity.snapshot_hash, "stop"]
                )[:32]
            )
            _insert_event(
                connection,
                _event(
                    event_id=stop_id,
                    environment=opportunity.environment,
                    known_at=known_at,
                    aggregate_type="opportunity",
                    aggregate_id=opportunity.opportunity_id,
                    event_type="committee.discussion_stopped",
                    payload={
                        "round_count": len(outcome.rounds),
                        "stop_reason": outcome.stop_reason,
                    },
                    causation_id=shared[0],
                ),
            )
