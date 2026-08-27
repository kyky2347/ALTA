REVISION = "b12_0009"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.run
        ADD COLUMN cycle_id text,
        ADD CONSTRAINT b12_run_cycle_id_bound CHECK (
            cycle_id IS NULL OR cycle_id ~ '^[a-z0-9][a-z0-9_-]{2,63}$'
        )"""
    )
    cursor.execute(
        """UPDATE research.run AS run SET cycle_id = job.subject_id
        FROM ops.job AS job WHERE run.job_id = job.id
        AND job.subject_id ~ '^[a-z0-9][a-z0-9_-]{2,63}$'"""
    )
    cursor.execute(
        """CREATE INDEX b12_run_cycle_idx
        ON research.run(environment, cycle_id, role) WHERE cycle_id IS NOT NULL"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP INDEX research.b12_run_cycle_idx")
    cursor.execute(
        """ALTER TABLE research.run
        DROP CONSTRAINT b12_run_cycle_id_bound,
        DROP COLUMN cycle_id"""
    )
