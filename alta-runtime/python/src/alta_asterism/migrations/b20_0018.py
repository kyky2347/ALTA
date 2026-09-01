REVISION = "b20_0018"

TABLES = ()


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE ops.paper_intent
        DROP CONSTRAINT paper_intent_quantity_check,
        DROP CONSTRAINT paper_intent_expected_position_before_check,
        DROP CONSTRAINT paper_intent_check"""
    )
    cursor.execute(
        """ALTER TABLE ops.paper_intent
        ADD CONSTRAINT paper_intent_quantity_check CHECK (
            quantity > 0 AND quantity = trunc(quantity) AND quantity <= 1000000
        ),
        ADD CONSTRAINT paper_intent_expected_position_before_check CHECK (
            expected_position_before >= 0
            AND expected_position_before = trunc(expected_position_before)
            AND expected_position_before <= 1000000
        ),
        ADD CONSTRAINT paper_intent_direction_check CHECK (
            (operation = 'open' AND action = 'BUY'
             AND expected_position_before = 0)
            OR (operation = 'close' AND action = 'SELL'
                AND expected_position_before = quantity)
        )"""
    )


def downgrade(cursor) -> None:
    cursor.execute(
        """DELETE FROM ops.paper_intent
        WHERE quantity <> 1 OR expected_position_before NOT IN (0, 1)"""
    )
    cursor.execute(
        """ALTER TABLE ops.paper_intent
        DROP CONSTRAINT paper_intent_quantity_check,
        DROP CONSTRAINT paper_intent_expected_position_before_check,
        DROP CONSTRAINT paper_intent_direction_check"""
    )
    cursor.execute(
        """ALTER TABLE ops.paper_intent
        ADD CONSTRAINT paper_intent_quantity_check CHECK (quantity = 1),
        ADD CONSTRAINT paper_intent_expected_position_before_check CHECK (
            expected_position_before IN (0, 1)
        ),
        ADD CONSTRAINT paper_intent_check CHECK (
            (operation = 'open' AND action = 'BUY'
             AND expected_position_before = 0)
            OR (operation = 'close' AND action = 'SELL'
                AND expected_position_before = 1)
        )"""
    )
