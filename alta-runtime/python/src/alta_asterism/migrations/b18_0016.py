REVISION = "b18_0016"

TABLES = ("ops.autonomous_owner",)


def upgrade(cursor) -> None:
    cursor.execute(
        """CREATE TABLE ops.autonomous_owner (
        owner_key text PRIMARY KEY CHECK (length(owner_key) BETWEEN 1 AND 128),
        environment alta_environment NOT NULL DEFAULT 'shadow'
            CHECK (environment = 'shadow'),
        epoch bigint NOT NULL CHECK (epoch > 0),
        token_digest char(64) NOT NULL
            CHECK (token_digest ~ '^[a-f0-9]{64}$'),
        backend_pid integer,
        acquired_at timestamptz NOT NULL,
        revoked_at timestamptz,
        CHECK ((backend_pid IS NOT NULL AND revoked_at IS NULL)
               OR (backend_pid IS NULL AND revoked_at IS NOT NULL))
        )"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP TABLE ops.autonomous_owner")
