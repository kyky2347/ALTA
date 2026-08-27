REVISION = "b13_0011"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.assessment
        ADD COLUMN underwriting jsonb,
        ADD CONSTRAINT b13_assessment_underwriting CHECK (
            underwriting IS NULL OR (
                jsonb_typeof(underwriting) = 'object'
                AND octet_length(underwriting::text) <= 8192
            )
        )"""
    )


def downgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.assessment
        DROP CONSTRAINT b13_assessment_underwriting,
        DROP COLUMN underwriting"""
    )
