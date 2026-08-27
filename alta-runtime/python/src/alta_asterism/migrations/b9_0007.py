REVISION = "b9_0007"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.rank
        DROP CONSTRAINT b4_rank_horizon,
        ADD CONSTRAINT b9_rank_horizon CHECK (
            (horizon_min_days = 5 AND horizon_max_days = 20)
            OR (horizon_min_days = 1 AND horizon_max_days = 90)
        )"""
    )


def downgrade(cursor) -> None:
    cursor.execute(
        """UPDATE research.rank
        SET book = 'swing_5_20d', horizon_min_days = 5, horizon_max_days = 20
        WHERE horizon_min_days = 1 AND horizon_max_days = 90"""
    )
    cursor.execute(
        """ALTER TABLE research.rank
        DROP CONSTRAINT b9_rank_horizon,
        ADD CONSTRAINT b4_rank_horizon
            CHECK (horizon_min_days = 5 AND horizon_max_days = 20)"""
    )
