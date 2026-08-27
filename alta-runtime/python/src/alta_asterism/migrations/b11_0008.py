from ..opportunity_identity import (
    exact_identity_key,
    normalize_key,
    structural_identity_key,
)

REVISION = "b11_0008"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.opportunity
        ADD COLUMN entity_key text,
        ADD COLUMN event_key text,
        ADD COLUMN catalyst_key text,
        ADD COLUMN identity_version integer NOT NULL DEFAULT 1,
        ADD CONSTRAINT b11_opportunity_entity_key_bound
            CHECK (entity_key IS NULL OR length(entity_key) BETWEEN 1 AND 128),
        ADD CONSTRAINT b11_opportunity_event_key_bound
            CHECK (event_key IS NULL OR length(event_key) BETWEEN 1 AND 128),
        ADD CONSTRAINT b11_opportunity_catalyst_key_bound
            CHECK (catalyst_key IS NULL OR length(catalyst_key) BETWEEN 1 AND 128),
        ADD CONSTRAINT b11_opportunity_identity_version
            CHECK (identity_version IN (1, 2))"""
    )
    rows = cursor.execute(
        """SELECT o.id, o.horizon_days, o.direction, c.foundry_snapshot
        FROM research.opportunity o
        JOIN research.candidate c ON c.id = o.candidate_id"""
    ).fetchall()
    for opportunity_id, horizon_days, stored_direction, snapshot in rows:
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        entity = snapshot.get("entity_key")
        event = snapshot.get("event_key")
        catalyst = snapshot.get("catalyst_key")
        direction = snapshot.get("direction") or stored_direction
        exact = exact_identity_key(entity, event, direction, horizon_days)
        structural = structural_identity_key(entity, catalyst, direction, horizon_days)
        cursor.execute(
            """UPDATE research.opportunity SET entity_key = %s,
            event_key = %s, catalyst_key = %s,
            exact_key = COALESCE(%s, exact_key),
            structural_key = COALESCE(%s, structural_key),
            identity_version = %s WHERE id = %s""",
            (
                normalize_key(entity) if entity else None,
                normalize_key(event) if event else None,
                normalize_key(catalyst) if catalyst else None,
                exact,
                structural,
                2 if exact is not None or structural is not None else 1,
                opportunity_id,
            ),
        )
    cursor.execute(
        """CREATE INDEX b11_opportunity_exact_active_idx
        ON research.opportunity(environment, exact_key)
        WHERE foundry_state = 'active'"""
    )
    cursor.execute(
        """CREATE INDEX b11_opportunity_structural_active_idx
        ON research.opportunity(environment, structural_key)
        WHERE foundry_state = 'active'"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP INDEX research.b11_opportunity_structural_active_idx")
    cursor.execute("DROP INDEX research.b11_opportunity_exact_active_idx")
    cursor.execute(
        """ALTER TABLE research.opportunity
        DROP CONSTRAINT b11_opportunity_identity_version,
        DROP CONSTRAINT b11_opportunity_catalyst_key_bound,
        DROP CONSTRAINT b11_opportunity_event_key_bound,
        DROP CONSTRAINT b11_opportunity_entity_key_bound,
        DROP COLUMN identity_version,
        DROP COLUMN catalyst_key,
        DROP COLUMN event_key,
        DROP COLUMN entity_key"""
    )
