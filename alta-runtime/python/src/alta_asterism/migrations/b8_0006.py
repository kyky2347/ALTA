REVISION = "b8_0006"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.expression
        DROP CONSTRAINT expression_kind_check,
        ADD CONSTRAINT expression_kind_check
            CHECK (kind IN ('stock','etf','option','wait'))"""
    )


def downgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.expression
        DROP CONSTRAINT expression_kind_check,
        ADD CONSTRAINT expression_kind_check
            CHECK (kind IN ('stock','etf','wait'))"""
    )
