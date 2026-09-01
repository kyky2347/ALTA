REVISION = "b19_0017"

TABLES = ("ops.paper_drain",)


def upgrade(cursor) -> None:
    cursor.execute(
        """CREATE TABLE ops.paper_drain (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL CHECK (environment = 'shadow'),
        version integer NOT NULL DEFAULT 1 CHECK (version > 0),
        known_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL,
        account_sha256 char(64) NOT NULL
            CHECK (account_sha256 ~ '^[a-f0-9]{64}$'),
        authorization_generation bigint NOT NULL
            CHECK (authorization_generation > 0),
        state text NOT NULL CHECK (state IN (
            'requested', 'draining', 'completed', 'manual_review'
        )),
        last_snapshot jsonb CHECK (
            last_snapshot IS NULL OR (
                jsonb_typeof(last_snapshot) = 'object'
                AND octet_length(last_snapshot::text) <= 16384
            )
        ),
        failure_code text CHECK (
            failure_code IS NULL OR failure_code ~ '^[a-z0-9_.-]{1,64}$'
        ),
        UNIQUE (account_sha256, authorization_generation)
        )"""
    )
    cursor.execute(
        """CREATE UNIQUE INDEX b19_paper_drain_one_active_per_account
        ON ops.paper_drain(account_sha256)
        WHERE state IN ('requested', 'draining', 'manual_review')"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP INDEX ops.b19_paper_drain_one_active_per_account")
    cursor.execute("DROP TABLE ops.paper_drain")
