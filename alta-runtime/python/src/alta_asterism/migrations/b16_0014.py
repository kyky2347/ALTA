REVISION = "b16_0014"

TABLES = ("research.scout_batch_snapshot",)


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE ops.job
        ADD COLUMN attempt_count integer NOT NULL DEFAULT 1
            CHECK (attempt_count > 0)"""
    )
    cursor.execute(
        """CREATE TABLE research.scout_batch_snapshot (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL,
        version integer NOT NULL CHECK (version > 0),
        known_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        job_id text NOT NULL UNIQUE REFERENCES ops.job(id),
        cycle_id text NOT NULL UNIQUE,
        snapshot_hash char(64) NOT NULL
            CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
        frozen_input jsonb NOT NULL
            CHECK (jsonb_typeof(frozen_input) = 'object'
                   AND octet_length(frozen_input::text) <= 32768),
        source_postures jsonb NOT NULL
            CHECK (jsonb_typeof(source_postures) = 'object'
                   AND octet_length(source_postures::text) <= 8192)
        )"""
    )
    cursor.execute(
        """CREATE INDEX b16_scout_batch_snapshot_cycle
        ON research.scout_batch_snapshot(environment, cycle_id)"""
    )
    cursor.execute(
        """CREATE FUNCTION research.reject_scout_batch_snapshot_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'scout batch global snapshots are immutable';
        END;
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b16_scout_batch_snapshot_append_only
        BEFORE UPDATE OR DELETE ON research.scout_batch_snapshot
        FOR EACH ROW EXECUTE FUNCTION
            research.reject_scout_batch_snapshot_change()"""
    )


def downgrade(cursor) -> None:
    cursor.execute(
        """DROP TRIGGER b16_scout_batch_snapshot_append_only
        ON research.scout_batch_snapshot"""
    )
    cursor.execute("DROP FUNCTION research.reject_scout_batch_snapshot_change()")
    cursor.execute("DROP INDEX research.b16_scout_batch_snapshot_cycle")
    cursor.execute("DROP TABLE research.scout_batch_snapshot")
    cursor.execute("ALTER TABLE ops.job DROP COLUMN attempt_count")
