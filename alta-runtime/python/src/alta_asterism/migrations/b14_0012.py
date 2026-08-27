REVISION = "b14_0012"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.candidate
        ADD COLUMN alpha_archetype text NOT NULL DEFAULT 'legacy_unclassified',
        ADD CONSTRAINT b14_candidate_alpha_archetype CHECK (
            alpha_archetype = btrim(alpha_archetype)
            AND char_length(alpha_archetype) BETWEEN 3 AND 96
        )"""
    )
    cursor.execute(
        """CREATE INDEX b14_candidate_alpha_attribution
        ON research.candidate(environment, alpha_archetype, known_at)"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP INDEX research.b14_candidate_alpha_attribution")
    cursor.execute(
        """ALTER TABLE research.candidate
        DROP CONSTRAINT b14_candidate_alpha_archetype,
        DROP COLUMN alpha_archetype"""
    )
