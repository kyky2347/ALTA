REVISION = "b3_0002"

RUN_COLUMNS = (
    "input_hash",
    "frozen_input",
    "budget",
    "deadline_at",
    "prompt_version",
    "tool_catalog_version",
    "model_provider",
    "model_id",
    "trace_id",
    "tool_provenance",
    "evidence_ids",
    "output_kind",
    "thread_id",
    "turn_id",
)


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.run
        ADD COLUMN input_hash char(64) NOT NULL DEFAULT repeat('0', 64)
            CHECK (input_hash ~ '^[a-f0-9]{64}$'),
        ADD COLUMN frozen_input jsonb NOT NULL DEFAULT '{}'::jsonb
            CHECK (jsonb_typeof(frozen_input) = 'object'),
        ADD COLUMN budget jsonb NOT NULL DEFAULT '{}'::jsonb
            CHECK (jsonb_typeof(budget) = 'object'),
        ADD COLUMN deadline_at timestamptz NOT NULL DEFAULT now(),
        ADD COLUMN prompt_version text NOT NULL DEFAULT 'pre-b3',
        ADD COLUMN tool_catalog_version text NOT NULL DEFAULT 'pre-b3',
        ADD COLUMN model_provider text NOT NULL DEFAULT 'unrecorded',
        ADD COLUMN model_id text NOT NULL DEFAULT 'unrecorded',
        ADD COLUMN trace_id text NOT NULL DEFAULT 'unrecorded',
        ADD COLUMN tool_provenance jsonb NOT NULL DEFAULT '[]'::jsonb
            CHECK (jsonb_typeof(tool_provenance) = 'array'),
        ADD COLUMN evidence_ids text[] NOT NULL DEFAULT '{}'::text[],
        ADD COLUMN output_kind text CHECK (output_kind IN ('candidate','no_op')),
        ADD COLUMN thread_id text,
        ADD COLUMN turn_id text"""
    )
    cursor.execute(
        """ALTER TABLE research.run
        ALTER COLUMN input_hash DROP DEFAULT,
        ALTER COLUMN frozen_input DROP DEFAULT,
        ALTER COLUMN budget DROP DEFAULT,
        ALTER COLUMN deadline_at DROP DEFAULT,
        ALTER COLUMN prompt_version DROP DEFAULT,
        ALTER COLUMN tool_catalog_version DROP DEFAULT,
        ALTER COLUMN model_provider DROP DEFAULT,
        ALTER COLUMN model_id DROP DEFAULT,
        ALTER COLUMN trace_id DROP DEFAULT"""
    )
    cursor.execute(
        """ALTER TABLE research.candidate
        ADD COLUMN evidence_ids text[] NOT NULL DEFAULT '{}'::text[]"""
    )


def downgrade(cursor) -> None:
    cursor.execute("ALTER TABLE research.candidate DROP COLUMN evidence_ids")
    cursor.execute(
        "ALTER TABLE research.run "
        + ", ".join(f"DROP COLUMN {column}" for column in RUN_COLUMNS)
    )
