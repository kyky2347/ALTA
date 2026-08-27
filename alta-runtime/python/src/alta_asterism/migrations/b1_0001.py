REVISION = "b1_0001"

TABLES = (
    "ops.job",
    "research.run",
    "research.raw",
    "research.evidence",
    "research.candidate",
    "research.opportunity",
    "research.assessment",
    "research.rank",
    "research.expression",
    "research.shadow_position",
    "ops.event",
)

COMMON = """
id text PRIMARY KEY,
environment alta_environment NOT NULL,
version integer NOT NULL CHECK (version > 0),
known_at timestamptz NOT NULL,
created_at timestamptz NOT NULL DEFAULT now()
"""

DEFINITIONS = {
    "ops.job": """
kind text NOT NULL, status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
subject_id text, priority integer NOT NULL DEFAULT 0 CHECK (priority BETWEEN -100 AND 100)
""",
    "research.run": """
job_id text REFERENCES ops.job(id), role text NOT NULL,
status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')), error_code text
""",
    "research.raw": """
source text NOT NULL, source_key text NOT NULL, content_hash char(64) NOT NULL CHECK (content_hash ~ '^[a-f0-9]{64}$'),
body jsonb NOT NULL CHECK (octet_length(body::text) <= 65536), UNIQUE (source, source_key, content_hash)
""",
    "research.evidence": """
raw_id text NOT NULL REFERENCES research.raw(id), stance text NOT NULL CHECK (stance IN ('support','oppose','unknown')),
summary text NOT NULL, event_time timestamptz
""",
    "research.candidate": """
run_id text NOT NULL REFERENCES research.run(id), title text NOT NULL, why_now text NOT NULL, expectation text NOT NULL,
variant_wedge text NOT NULL, falsifier text NOT NULL, horizon_days integer NOT NULL CHECK (horizon_days BETWEEN 1 AND 365),
confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1)
""",
    "research.opportunity": """
candidate_id text NOT NULL REFERENCES research.candidate(id), status text NOT NULL CHECK (status IN ('forming','ranked','shadow','closed','rejected')),
title text NOT NULL, thesis text NOT NULL, falsifier text NOT NULL, horizon_days integer NOT NULL CHECK (horizon_days BETWEEN 1 AND 365)
""",
    "research.assessment": """
opportunity_id text NOT NULL REFERENCES research.opportunity(id), run_id text NOT NULL REFERENCES research.run(id), assessor text NOT NULL,
verdict text NOT NULL CHECK (verdict IN ('advance','hold','reject')), score double precision NOT NULL CHECK (score BETWEEN 0 AND 1), rationale text NOT NULL
""",
    "research.rank": """
opportunity_id text NOT NULL REFERENCES research.opportunity(id), book text NOT NULL,
position integer NOT NULL CHECK (position > 0), score double precision NOT NULL CHECK (score BETWEEN 0 AND 1), UNIQUE (book, version, position)
""",
    "research.expression": """
opportunity_id text NOT NULL REFERENCES research.opportunity(id), opportunity_version integer NOT NULL CHECK (opportunity_version > 0),
kind text NOT NULL CHECK (kind IN ('stock','etf','wait')), status text NOT NULL CHECK (status IN ('proposed','validated','rejected','active','closed')), rationale text NOT NULL
""",
    "research.shadow_position": """
expression_id text NOT NULL REFERENCES research.expression(id), symbol text NOT NULL, side text NOT NULL CHECK (side IN ('long','short')),
quantity numeric NOT NULL CHECK (quantity > 0), status text NOT NULL CHECK (status IN ('open','closed'))
""",
    "ops.event": """
sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE, aggregate_type text NOT NULL, aggregate_id text NOT NULL, event_type text NOT NULL,
payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (octet_length(payload::text) <= 16384), correlation_id text, causation_id text
""",
}


def upgrade(cursor) -> None:
    cursor.execute("CREATE TYPE alta_environment AS ENUM ('replay','shadow','paper')")
    cursor.execute("CREATE SCHEMA ops")
    cursor.execute("CREATE SCHEMA research")
    for table, columns in DEFINITIONS.items():
        cursor.execute(f"CREATE TABLE {table} ({COMMON}, {columns})")
    cursor.execute("CREATE INDEX event_cursor_idx ON ops.event(sequence)")


def downgrade(cursor) -> None:
    cursor.execute("DROP SCHEMA research CASCADE")
    cursor.execute("DROP SCHEMA ops CASCADE")
    cursor.execute("DROP TYPE alta_environment")
