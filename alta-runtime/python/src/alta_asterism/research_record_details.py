"""Read-only, environment-bound source record inspection for the operator."""

from datetime import UTC, datetime

from .freshness import signal_freshness_fields


def candidate_detail(database, candidate_id: str, environment: str):
    # Deliberate projection, not the full agent prompt or provider response.
    fields = (
        "id",
        "runId",
        "version",
        "knownAt",
        "title",
        "whyNow",
        "expectation",
        "variantWedge",
        "falsifier",
        "horizonDays",
        "confidence",
        "alphaArchetype",
        "freshnessAt",
        "evidenceIds",
        "snapshotHash",
    )
    with database.connect() as connection:
        row = connection.execute(
            """SELECT id, run_id, version, known_at, title, why_now,
            expectation, variant_wedge, falsifier, horizon_days, confidence,
            alpha_archetype, (foundry_snapshot->>'freshness_at')::timestamptz,
            evidence_ids, foundry_snapshot_hash
            FROM research.candidate WHERE id = %s AND environment = %s""",
            (candidate_id, environment),
        ).fetchone()
        if row is None:
            return None
        evidence = connection.execute(
            """SELECT e.id, e.known_at, r.content_hash
            FROM research.evidence e JOIN research.raw r ON e.raw_id = r.id
            WHERE e.id = ANY(%s) AND e.environment = %s AND r.environment = %s
            ORDER BY e.id LIMIT 100""",
            (row[13], environment, environment),
        ).fetchall()
    return {
        **dict(zip(fields, row, strict=True)),
        **signal_freshness_fields(row[12], datetime.now(UTC)),
        "evidence": [
            dict(zip(("id", "knownAt", "contentHash"), item, strict=True))
            for item in evidence
        ],
    }
