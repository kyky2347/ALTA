from psycopg.types.json import Jsonb

from .database import Database
from .foundry import OpportunityDraft
from .opportunity_identity import canonical_hash, normalize_key

MAX_REGISTRY_EVIDENCE = 20
MAX_REGISTRY_MEMBERS = 20


class OpportunityRegistry:
    """Resolves one Foundry batch against bounded cross-cycle Opportunity state."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def resolve(
        self, batch_id: str, opportunities: tuple[OpportunityDraft, ...]
    ) -> tuple[OpportunityDraft, ...]:
        incoming_ids = [item.opportunity_id for item in opportunities]
        resolved: list[OpportunityDraft] = []
        with self.database.connect() as connection:
            for incoming in opportunities:
                state = connection.execute(
                    """SELECT foundry_state, merge_parent_id
                    FROM research.opportunity WHERE id = %s""",
                    (incoming.opportunity_id,),
                ).fetchone()
                if state is None:
                    raise ValueError("incoming Opportunity is not materialized")
                if state[0] == "merged":
                    event = connection.execute(
                        """SELECT event_type FROM ops.event
                        WHERE correlation_id = %s
                          AND payload->>'incoming_opportunity_id' = %s
                          AND event_type IN
                            ('foundry.cross_cycle.refreshed',
                             'foundry.cross_cycle.suppressed',
                             'foundry.cross_cycle.position_updated')
                        ORDER BY sequence DESC LIMIT 1""",
                        (batch_id, incoming.opportunity_id),
                    ).fetchone()
                    if event and event[0] == "foundry.cross_cycle.refreshed":
                        resolved.append(
                            self._canonical_draft(connection, incoming, state[1])
                        )
                    continue

                parent = connection.execute(
                    """SELECT id, version, known_at, status,
                    member_candidate_ids, evidence_ids, snapshot_hash,
                    CASE WHEN exact_key = %s THEN 'exact_identity_v2'
                         ELSE 'structural_identity_v2' END
                    FROM research.opportunity
                    WHERE environment = %s AND foundry_state = 'active'
                      AND identity_version = 2
                      AND NOT (id = ANY(%s))
                      AND (exact_key = %s OR structural_key = %s)
                    ORDER BY CASE WHEN exact_key = %s THEN 0 ELSE 1 END,
                             known_at DESC, id
                    LIMIT 1 FOR UPDATE""",
                    (
                        incoming.exact_key,
                        incoming.environment.value,
                        incoming_ids,
                        incoming.exact_key,
                        incoming.structural_key,
                        incoming.exact_key,
                    ),
                ).fetchone()
                if parent is None:
                    resolved.append(incoming)
                    continue

                parent_hashes = self._evidence_hashes(connection, parent[5])
                incoming_hashes = self._evidence_hashes(
                    connection, incoming.evidence_ids
                )
                known_content_hashes = self._seen_content_hashes(connection, parent[0])
                new_evidence_ids = tuple(
                    evidence_id
                    for evidence_id in incoming.evidence_ids
                    if incoming_hashes[evidence_id] not in known_content_hashes
                )
                has_new_evidence = bool(new_evidence_ids)
                if not has_new_evidence:
                    action = "suppressed"
                elif parent[3] == "shadow":
                    action = "position_updated"
                else:
                    action = "refreshed"

                connection.execute(
                    """UPDATE research.opportunity SET foundry_state = 'merged',
                    merge_parent_id = %s, merge_revision = merge_revision + 1,
                    status = 'rejected' WHERE id = %s""",
                    (parent[0], incoming.opportunity_id),
                )
                canonical = None
                if has_new_evidence:
                    all_hashes = {**parent_hashes, **incoming_hashes}
                    evidence_ids = self._bounded_by_content(
                        (*incoming.evidence_ids, *parent[5]),
                        all_hashes,
                        MAX_REGISTRY_EVIDENCE,
                    )
                    member_ids = tuple(
                        dict.fromkeys((*incoming.member_candidate_ids, *parent[4]))
                    )[:MAX_REGISTRY_MEMBERS]
                    snapshot_hash = canonical_hash(
                        {
                            "registry": "cross-cycle-v1",
                            "parent_snapshot_hash": parent[6],
                            "incoming_snapshot_hash": incoming.snapshot_hash,
                            "evidence_content_hashes": [
                                all_hashes[item] for item in evidence_ids
                            ],
                        }
                    )
                    canonical = incoming.model_copy(
                        update={
                            "opportunity_id": parent[0],
                            "version": parent[1] + 1,
                            "known_at": max(parent[2], incoming.known_at),
                            "member_candidate_ids": member_ids,
                            "evidence_ids": evidence_ids,
                            "snapshot_hash": snapshot_hash,
                        }
                    )
                    self._refresh_parent(
                        connection,
                        canonical,
                        status=("shadow" if parent[3] == "shadow" else "forming"),
                    )

                event_type = f"foundry.cross_cycle.{action}"
                event_id = (
                    "event_"
                    + canonical_hash(
                        [batch_id, incoming.opportunity_id, parent[0], event_type]
                    )[:32]
                )
                connection.execute(
                    """INSERT INTO ops.event
                    (id, environment, version, known_at, aggregate_type,
                     aggregate_id, event_type, payload, correlation_id)
                    VALUES (%s,%s,1,%s,'opportunity',%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING""",
                    (
                        event_id,
                        incoming.environment.value,
                        incoming.known_at,
                        parent[0],
                        event_type,
                        Jsonb(
                            {
                                "batch_id": batch_id,
                                "incoming_opportunity_id": incoming.opportunity_id,
                                "canonical_opportunity_id": parent[0],
                                "match_rule": parent[7],
                                "new_evidence_ids": new_evidence_ids,
                                "canonical_version": (
                                    canonical.version if canonical else parent[1]
                                ),
                                "reason": (
                                    "new_evidence_for_active_position"
                                    if parent[3] == "shadow"
                                    else (
                                        "new_evidence_content"
                                        if has_new_evidence
                                        else "no_new_evidence_content"
                                    )
                                ),
                            }
                        ),
                        batch_id,
                    ),
                )
                if canonical is not None and parent[3] != "shadow":
                    resolved.append(canonical)
        return tuple(resolved)

    @staticmethod
    def _evidence_hashes(connection, evidence_ids) -> dict[str, str]:
        rows = connection.execute(
            """SELECT e.id, r.content_hash FROM research.evidence e
            JOIN research.raw r ON r.id = e.raw_id
            WHERE e.id = ANY(%s)""",
            (list(evidence_ids),),
        ).fetchall()
        result = dict(rows)
        if len(result) != len(evidence_ids):
            raise ValueError("Opportunity Registry evidence is incomplete")
        return result

    @staticmethod
    def _seen_content_hashes(connection, canonical_id: str) -> set[str]:
        rows = connection.execute(
            """SELECT DISTINCT r.content_hash
            FROM research.opportunity o
            CROSS JOIN LATERAL unnest(o.evidence_ids) AS seen(evidence_id)
            JOIN research.evidence e ON e.id = seen.evidence_id
            JOIN research.raw r ON r.id = e.raw_id
            WHERE o.id = %s OR o.merge_parent_id = %s""",
            (canonical_id, canonical_id),
        ).fetchall()
        return {row[0] for row in rows}

    @staticmethod
    def _bounded_by_content(
        evidence_ids: tuple[str, ...], hashes: dict[str, str], limit: int
    ) -> tuple[str, ...]:
        selected = []
        seen = set()
        for evidence_id in evidence_ids:
            content_hash = hashes[evidence_id]
            if content_hash in seen:
                continue
            seen.add(content_hash)
            selected.append(evidence_id)
            if len(selected) == limit:
                break
        return tuple(selected)

    @staticmethod
    def _canonical_draft(connection, incoming, parent_id) -> OpportunityDraft:
        parent = connection.execute(
            """SELECT version, known_at, member_candidate_ids, evidence_ids,
            snapshot_hash FROM research.opportunity WHERE id = %s""",
            (parent_id,),
        ).fetchone()
        if parent is None:
            raise ValueError("canonical Opportunity disappeared during recovery")
        return incoming.model_copy(
            update={
                "opportunity_id": parent_id,
                "version": parent[0],
                "known_at": parent[1],
                "member_candidate_ids": tuple(parent[2]),
                "evidence_ids": tuple(parent[3]),
                "snapshot_hash": parent[4],
            }
        )

    @staticmethod
    def _refresh_parent(
        connection, opportunity: OpportunityDraft, *, status: str
    ) -> None:
        connection.execute(
            """UPDATE research.opportunity SET version = %s, known_at = %s,
            candidate_id = %s, status = %s, title = %s, thesis = %s,
            falsifier = %s, horizon_days = %s, member_candidate_ids = %s,
            exact_key = %s, structural_key = %s, snapshot_hash = %s,
            merge_revision = merge_revision + 1, observed_change = %s,
            mechanism = %s, direction = %s, expectation = %s,
            expectation_posture = %s, variant_wedge = %s, why_now = %s,
            first_rejection = %s, prediction = %s, investability = %s,
            freshness_at = %s, evidence_ids = %s, completeness = %s,
            entity_key = %s, event_key = %s, catalyst_key = %s,
            identity_version = 2 WHERE id = %s""",
            (
                opportunity.version,
                opportunity.known_at,
                opportunity.candidate_id,
                status,
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
                normalize_key(opportunity.entity_key)
                if opportunity.entity_key
                else None,
                normalize_key(opportunity.event_key) if opportunity.event_key else None,
                (
                    normalize_key(opportunity.catalyst_key)
                    if opportunity.catalyst_key
                    else None
                ),
                opportunity.opportunity_id,
            ),
        )
