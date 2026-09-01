REVISION = "b17_0015"

TABLES = ("ops.paper_intent",)


def upgrade(cursor) -> None:
    cursor.execute(
        """CREATE TABLE ops.paper_intent (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL CHECK (environment = 'shadow'),
        version integer NOT NULL DEFAULT 1 CHECK (version > 0),
        known_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL,
        account_sha256 char(64) NOT NULL
            CHECK (account_sha256 ~ '^[a-f0-9]{64}$'),
        client_order_id text NOT NULL UNIQUE
            CHECK (client_order_id ~ '^alta-[a-f0-9]{32}$'),
        cycle_id text NOT NULL,
        position_id text NOT NULL,
        expression_id text NOT NULL,
        operation text NOT NULL CHECK (operation IN ('open', 'close')),
        action text NOT NULL CHECK (action IN ('BUY', 'SELL')),
        symbol text NOT NULL CHECK (symbol ~ '^[A-Z][A-Z0-9.-]{0,14}$'),
        quantity numeric NOT NULL CHECK (quantity = 1),
        limit_price numeric NOT NULL CHECK (limit_price > 0),
        expected_position_before numeric NOT NULL
            CHECK (expected_position_before IN (0, 1)),
        request_hash char(64) NOT NULL
            CHECK (request_hash ~ '^[a-f0-9]{64}$'),
        state text NOT NULL CHECK (state IN (
            'prepared', 'dispatching', 'broker_filled', 'broker_not_filled',
            'local_committed', 'abandoned', 'manual_review'
        )),
        local_commit jsonb NOT NULL
            CHECK (jsonb_typeof(local_commit) = 'object'
                   AND octet_length(local_commit::text) <= 65536),
        broker_result jsonb
            CHECK (broker_result IS NULL OR (
                jsonb_typeof(broker_result) = 'object'
                AND octet_length(broker_result::text) <= 16384
            )),
        failure_code text CHECK (
            failure_code IS NULL OR failure_code ~ '^[a-z0-9_.-]{1,64}$'
        ),
        CHECK ((operation = 'open' AND action = 'BUY'
                AND expected_position_before = 0)
               OR (operation = 'close' AND action = 'SELL'
                   AND expected_position_before = 1))
        )"""
    )
    cursor.execute(
        """CREATE UNIQUE INDEX b17_paper_intent_one_unresolved_per_account
        ON ops.paper_intent(account_sha256)
        WHERE state IN ('prepared', 'dispatching', 'broker_filled', 'manual_review')"""
    )
    cursor.execute(
        """CREATE INDEX b17_paper_intent_recovery
        ON ops.paper_intent(environment, state, known_at, id)"""
    )
    cursor.execute(
        """CREATE INDEX b17_paper_intent_position
        ON ops.paper_intent(position_id, known_at, id)"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP INDEX ops.b17_paper_intent_position")
    cursor.execute("DROP INDEX ops.b17_paper_intent_recovery")
    cursor.execute("DROP INDEX ops.b17_paper_intent_one_unresolved_per_account")
    cursor.execute("DROP TABLE ops.paper_intent")
