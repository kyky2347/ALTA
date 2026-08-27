REVISION = "b7_0005"

TABLES = (
    "research.run_artifact",
    "research.mind_state",
    "ops.source_cursor",
)

RUN_COLUMNS = (
    "actual_usage",
    "latency_ms",
    "attempt_count",
)


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.run DROP CONSTRAINT run_output_kind_check,
        ADD CONSTRAINT run_output_kind_check
        CHECK (output_kind IN ('candidate','no_op','role_output'))"""
    )
    cursor.execute(
        """ALTER TABLE research.raw
        DROP CONSTRAINT raw_source_source_key_content_hash_key,
        ADD CONSTRAINT b7_raw_environment_identity
            UNIQUE (environment, source, source_key, content_hash)"""
    )
    cursor.execute(
        """CREATE FUNCTION research.reject_raw_or_evidence_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'raw evidence is append-only'
                USING ERRCODE = '55000';
        END
        $$"""
    )
    for table in ("raw", "evidence"):
        cursor.execute(
            f"""CREATE TRIGGER b7_{table}_append_only
            BEFORE UPDATE OR DELETE ON research.{table}
            FOR EACH ROW EXECUTE FUNCTION research.reject_raw_or_evidence_change()"""
        )

    cursor.execute(
        """ALTER TABLE research.run
        ADD COLUMN actual_usage jsonb NOT NULL DEFAULT '{}'::jsonb
            CHECK (jsonb_typeof(actual_usage) = 'object'
                   AND octet_length(actual_usage::text) <= 4096),
        ADD COLUMN latency_ms integer
            CHECK (latency_ms IS NULL OR latency_ms >= 0),
        ADD COLUMN attempt_count integer NOT NULL DEFAULT 0
            CHECK (attempt_count >= 0)"""
    )
    cursor.execute(
        """ALTER TABLE research.run
        ADD CONSTRAINT b7_run_frozen_input_bound
            CHECK (octet_length(frozen_input::text) <= 8192),
        ADD CONSTRAINT b7_run_tool_provenance_bound
            CHECK (octet_length(tool_provenance::text) <= 16384)"""
    )

    cursor.execute(
        """CREATE TABLE research.run_artifact (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL,
        version integer NOT NULL CHECK (version > 0),
        known_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        run_id text NOT NULL REFERENCES research.run(id),
        artifact_kind text NOT NULL
            CHECK (artifact_kind IN
                   ('scout_output','role_output','failure','rolling_summary')),
        schema_version text NOT NULL,
        content jsonb NOT NULL
            CHECK (octet_length(content::text) <= 16384),
        content_hash char(64) NOT NULL
            CHECK (content_hash ~ '^[a-f0-9]{64}$'),
        UNIQUE (run_id, artifact_kind, version)
        )"""
    )
    cursor.execute(
        """CREATE TABLE research.mind_state (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL,
        version integer NOT NULL CHECK (version > 0),
        known_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        scout_id text NOT NULL,
        thread_id text,
        turn_count integer NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
        context_tokens integer NOT NULL DEFAULT 0 CHECK (context_tokens >= 0),
        started_at timestamptz NOT NULL,
        rolling_summary text NOT NULL DEFAULT ''
            CHECK (octet_length(rolling_summary) <= 8192),
        open_questions text[] NOT NULL DEFAULT '{}'::text[],
        evidence_ids text[] NOT NULL DEFAULT '{}'::text[],
        model_provider text NOT NULL,
        model_id text NOT NULL,
        prompt_version text NOT NULL,
        tool_catalog_version text NOT NULL,
        UNIQUE (environment, scout_id)
        )"""
    )
    cursor.execute(
        """CREATE TABLE ops.source_cursor (
        id text PRIMARY KEY,
        environment alta_environment NOT NULL,
        version integer NOT NULL CHECK (version > 0),
        known_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        source text NOT NULL,
        cursor text NOT NULL CHECK (octet_length(cursor) <= 2048),
        UNIQUE (environment, source)
        )"""
    )
    cursor.execute(
        """CREATE FUNCTION research.reject_run_artifact_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'run artifacts are append-only'
                USING ERRCODE = '55000';
        END
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b7_run_artifact_append_only
        BEFORE UPDATE OR DELETE ON research.run_artifact
        FOR EACH ROW EXECUTE FUNCTION research.reject_run_artifact_change()"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP TRIGGER b7_run_artifact_append_only ON research.run_artifact")
    cursor.execute("DROP FUNCTION research.reject_run_artifact_change()")
    cursor.execute("DROP TABLE ops.source_cursor")
    cursor.execute("DROP TABLE research.mind_state")
    cursor.execute("DROP TABLE research.run_artifact")
    cursor.execute(
        "UPDATE research.run SET output_kind = NULL WHERE output_kind = 'role_output'"
    )
    cursor.execute(
        """ALTER TABLE research.run DROP CONSTRAINT run_output_kind_check,
        ADD CONSTRAINT run_output_kind_check
        CHECK (output_kind IN ('candidate','no_op'))"""
    )
    cursor.execute(
        """ALTER TABLE research.run
        DROP CONSTRAINT b7_run_tool_provenance_bound,
        DROP CONSTRAINT b7_run_frozen_input_bound,
        DROP COLUMN attempt_count,
        DROP COLUMN latency_ms,
        DROP COLUMN actual_usage"""
    )
    for table in ("evidence", "raw"):
        cursor.execute(f"DROP TRIGGER b7_{table}_append_only ON research.{table}")
    cursor.execute("DROP FUNCTION research.reject_raw_or_evidence_change()")
    cursor.execute(
        """ALTER TABLE research.raw
        DROP CONSTRAINT b7_raw_environment_identity,
        ADD CONSTRAINT raw_source_source_key_content_hash_key
            UNIQUE (source, source_key, content_hash)"""
    )
