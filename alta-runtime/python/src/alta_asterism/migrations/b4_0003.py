REVISION = "b4_0003"

CANDIDATE_COLUMNS = (
    "foundry_snapshot",
    "foundry_snapshot_hash",
)

OPPORTUNITY_COLUMNS = (
    "member_candidate_ids",
    "exact_key",
    "structural_key",
    "snapshot_hash",
    "foundry_state",
    "merge_parent_id",
    "merge_revision",
    "observed_change",
    "mechanism",
    "direction",
    "expectation",
    "expectation_posture",
    "variant_wedge",
    "why_now",
    "first_rejection",
    "prediction",
    "investability",
    "freshness_at",
    "evidence_ids",
    "completeness",
)

ASSESSMENT_COLUMNS = (
    "snapshot_hash",
    "assessment_kind",
    "forecast_probability",
    "evidence_quality",
    "variant_wedge_quality",
    "strongest_support",
    "strongest_disconfirmation",
    "first_rejection",
    "missing_evidence",
    "recommendation",
    "confidence",
    "evidence_ids",
    "locked_at",
    "prompt_version",
    "model_id",
)

RANK_COLUMNS = (
    "ranking_run_id",
    "snapshot_hash",
    "horizon_min_days",
    "horizon_max_days",
    "components",
    "gate_status",
    "reason_codes",
)


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.candidate
        ADD COLUMN foundry_snapshot jsonb,
        ADD COLUMN foundry_snapshot_hash char(64),
        ADD CONSTRAINT b4_candidate_foundry_snapshot
            CHECK (foundry_snapshot IS NULL OR
                (jsonb_typeof(foundry_snapshot) = 'object'
                 AND octet_length(foundry_snapshot::text) <= 65536)),
        ADD CONSTRAINT b4_candidate_foundry_snapshot_hash
            CHECK (foundry_snapshot_hash IS NULL OR
                foundry_snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_candidate_foundry_snapshot_pair
            CHECK ((foundry_snapshot IS NULL) = (foundry_snapshot_hash IS NULL))"""
    )
    cursor.execute(
        """CREATE FUNCTION research.reject_frozen_candidate_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.foundry_snapshot_hash IS NOT NULL THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'frozen Foundry candidate is immutable'
                        USING ERRCODE = '55000';
                ELSIF NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'frozen Foundry candidate is immutable'
                        USING ERRCODE = '55000';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b4_candidate_freeze
        BEFORE UPDATE OR DELETE ON research.candidate
        FOR EACH ROW EXECUTE FUNCTION research.reject_frozen_candidate_change()"""
    )
    cursor.execute(
        """ALTER TABLE research.opportunity
        ADD COLUMN member_candidate_ids text[],
        ADD COLUMN exact_key char(64),
        ADD COLUMN structural_key char(64),
        ADD COLUMN snapshot_hash char(64),
        ADD COLUMN foundry_state text,
        ADD COLUMN merge_parent_id text REFERENCES research.opportunity(id),
        ADD COLUMN merge_revision integer,
        ADD COLUMN observed_change text,
        ADD COLUMN mechanism text,
        ADD COLUMN direction text,
        ADD COLUMN expectation text,
        ADD COLUMN expectation_posture text,
        ADD COLUMN variant_wedge text,
        ADD COLUMN why_now text,
        ADD COLUMN first_rejection text,
        ADD COLUMN prediction text,
        ADD COLUMN investability text,
        ADD COLUMN freshness_at timestamptz,
        ADD COLUMN evidence_ids text[],
        ADD COLUMN completeness text"""
    )
    cursor.execute(
        """UPDATE research.opportunity SET
        member_candidate_ids = ARRAY[candidate_id],
        exact_key = repeat(md5(id || ':exact'), 2),
        structural_key = repeat(md5(id || ':structural'), 2),
        snapshot_hash = repeat(md5(id || ':snapshot'), 2),
        foundry_state = 'active', merge_revision = 1,
        direction = 'unknown', expectation_posture = 'unavailable',
        investability = 'unknown', evidence_ids = '{}'::text[],
        completeness = 'enriching'"""
    )
    cursor.execute(
        """ALTER TABLE research.opportunity
        ALTER COLUMN member_candidate_ids SET NOT NULL,
        ALTER COLUMN exact_key SET NOT NULL,
        ALTER COLUMN structural_key SET NOT NULL,
        ALTER COLUMN snapshot_hash SET NOT NULL,
        ALTER COLUMN foundry_state SET NOT NULL,
        ALTER COLUMN merge_revision SET NOT NULL,
        ALTER COLUMN direction SET NOT NULL,
        ALTER COLUMN expectation_posture SET NOT NULL,
        ALTER COLUMN investability SET NOT NULL,
        ALTER COLUMN evidence_ids SET NOT NULL,
        ALTER COLUMN completeness SET NOT NULL,
        ADD CONSTRAINT b4_opportunity_members_nonempty
            CHECK (cardinality(member_candidate_ids) > 0),
        ADD CONSTRAINT b4_opportunity_exact_key
            CHECK (exact_key ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_opportunity_structural_key
            CHECK (structural_key ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_opportunity_snapshot_hash
            CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_opportunity_foundry_state
            CHECK (foundry_state IN ('active','merged')),
        ADD CONSTRAINT b4_opportunity_merge_revision
            CHECK (merge_revision > 0),
        ADD CONSTRAINT b4_opportunity_direction
            CHECK (direction IN ('positive','negative','neutral','unknown')),
        ADD CONSTRAINT b4_opportunity_expectation_posture
            CHECK (expectation_posture IN ('available','proxy_only','unavailable')),
        ADD CONSTRAINT b4_opportunity_investability
            CHECK (investability IN ('ready','limited','unknown')),
        ADD CONSTRAINT b4_opportunity_completeness
            CHECK (completeness IN ('complete','enriching','rejected'))"""
    )

    cursor.execute(
        """ALTER TABLE research.assessment
        ADD COLUMN snapshot_hash char(64),
        ADD COLUMN assessment_kind text,
        ADD COLUMN forecast_probability double precision,
        ADD COLUMN evidence_quality double precision,
        ADD COLUMN variant_wedge_quality double precision,
        ADD COLUMN strongest_support text,
        ADD COLUMN strongest_disconfirmation text,
        ADD COLUMN first_rejection text,
        ADD COLUMN missing_evidence text[],
        ADD COLUMN recommendation text,
        ADD COLUMN confidence double precision,
        ADD COLUMN evidence_ids text[],
        ADD COLUMN locked_at timestamptz,
        ADD COLUMN prompt_version text,
        ADD COLUMN model_id text"""
    )
    cursor.execute(
        """UPDATE research.assessment SET
        snapshot_hash = repeat(md5(id || ':assessment'), 2),
        assessment_kind = 'private', forecast_probability = score,
        evidence_quality = score, variant_wedge_quality = score,
        strongest_support = rationale,
        strongest_disconfirmation = rationale,
        first_rejection = rationale, missing_evidence = '{}'::text[],
        recommendation = CASE verdict
            WHEN 'advance' THEN 'advance'
            WHEN 'reject' THEN 'reject'
            ELSE 'wait' END,
        confidence = score, evidence_ids = '{}'::text[],
        locked_at = created_at, prompt_version = 'pre-b4', model_id = 'unrecorded'"""
    )
    cursor.execute(
        """ALTER TABLE research.assessment
        ALTER COLUMN snapshot_hash SET NOT NULL,
        ALTER COLUMN assessment_kind SET NOT NULL,
        ALTER COLUMN forecast_probability SET NOT NULL,
        ALTER COLUMN evidence_quality SET NOT NULL,
        ALTER COLUMN variant_wedge_quality SET NOT NULL,
        ALTER COLUMN strongest_support SET NOT NULL,
        ALTER COLUMN strongest_disconfirmation SET NOT NULL,
        ALTER COLUMN first_rejection SET NOT NULL,
        ALTER COLUMN missing_evidence SET NOT NULL,
        ALTER COLUMN recommendation SET NOT NULL,
        ALTER COLUMN confidence SET NOT NULL,
        ALTER COLUMN evidence_ids SET NOT NULL,
        ALTER COLUMN locked_at SET NOT NULL,
        ALTER COLUMN prompt_version SET NOT NULL,
        ALTER COLUMN model_id SET NOT NULL,
        ADD CONSTRAINT b4_assessment_snapshot_hash
            CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_assessment_kind CHECK (assessment_kind = 'private'),
        ADD CONSTRAINT b4_assessment_probability
            CHECK (forecast_probability BETWEEN 0 AND 1),
        ADD CONSTRAINT b4_assessment_evidence_quality
            CHECK (evidence_quality BETWEEN 0 AND 1),
        ADD CONSTRAINT b4_assessment_wedge_quality
            CHECK (variant_wedge_quality BETWEEN 0 AND 1),
        ADD CONSTRAINT b4_assessment_recommendation
            CHECK (recommendation IN ('research','wait','reject','advance')),
        ADD CONSTRAINT b4_assessment_confidence CHECK (confidence BETWEEN 0 AND 1),
        ADD CONSTRAINT b4_private_assessment_identity
            UNIQUE (opportunity_id, snapshot_hash, assessor, assessment_kind)"""
    )
    cursor.execute(
        """CREATE FUNCTION research.reject_locked_assessment_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.locked_at IS NOT NULL THEN
                RAISE EXCEPTION 'locked private assessment is immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b4_assessment_lock
        BEFORE UPDATE OR DELETE ON research.assessment
        FOR EACH ROW EXECUTE FUNCTION research.reject_locked_assessment_change()"""
    )

    cursor.execute(
        """ALTER TABLE research.rank
        ADD COLUMN ranking_run_id text,
        ADD COLUMN snapshot_hash char(64),
        ADD COLUMN horizon_min_days integer,
        ADD COLUMN horizon_max_days integer,
        ADD COLUMN components jsonb,
        ADD COLUMN gate_status text,
        ADD COLUMN reason_codes text[]"""
    )
    cursor.execute(
        """UPDATE research.rank SET
        ranking_run_id = 'pre-b4-v' || version,
        snapshot_hash = repeat(md5(id || ':rank'), 2),
        horizon_min_days = 5, horizon_max_days = 20,
        components = '{}'::jsonb, gate_status = 'ranked',
        reason_codes = '{}'::text[]"""
    )
    cursor.execute(
        """ALTER TABLE research.rank
        ALTER COLUMN ranking_run_id SET NOT NULL,
        ALTER COLUMN snapshot_hash SET NOT NULL,
        ALTER COLUMN horizon_min_days SET NOT NULL,
        ALTER COLUMN horizon_max_days SET NOT NULL,
        ALTER COLUMN components SET NOT NULL,
        ALTER COLUMN gate_status SET NOT NULL,
        ALTER COLUMN reason_codes SET NOT NULL,
        DROP CONSTRAINT rank_book_version_position_key,
        ADD CONSTRAINT b4_rank_snapshot_hash
            CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b4_rank_horizon
            CHECK (horizon_min_days = 5 AND horizon_max_days = 20),
        ADD CONSTRAINT b4_rank_components
            CHECK (jsonb_typeof(components) = 'object'),
        ADD CONSTRAINT b4_rank_gate_status CHECK (gate_status = 'ranked'),
        ADD CONSTRAINT b4_rank_run_position
            UNIQUE (book, ranking_run_id, position),
        ADD CONSTRAINT b4_rank_run_opportunity
            UNIQUE (book, ranking_run_id, opportunity_id)"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP TRIGGER b4_candidate_freeze ON research.candidate")
    cursor.execute("DROP FUNCTION research.reject_frozen_candidate_change()")
    cursor.execute("DROP TRIGGER b4_assessment_lock ON research.assessment")
    cursor.execute("DROP FUNCTION research.reject_locked_assessment_change()")
    cursor.execute(
        """ALTER TABLE research.rank
        DROP CONSTRAINT b4_rank_run_opportunity,
        DROP CONSTRAINT b4_rank_run_position,
        DROP CONSTRAINT b4_rank_gate_status,
        DROP CONSTRAINT b4_rank_components,
        DROP CONSTRAINT b4_rank_horizon,
        DROP CONSTRAINT b4_rank_snapshot_hash"""
    )
    cursor.execute(
        "ALTER TABLE research.rank "
        + ", ".join(f"DROP COLUMN {column}" for column in RANK_COLUMNS)
        + ", ADD CONSTRAINT rank_book_version_position_key "
        "UNIQUE (book, version, position)"
    )
    cursor.execute(
        "ALTER TABLE research.assessment "
        "DROP CONSTRAINT b4_private_assessment_identity, "
        "DROP CONSTRAINT b4_assessment_confidence, "
        "DROP CONSTRAINT b4_assessment_recommendation, "
        "DROP CONSTRAINT b4_assessment_wedge_quality, "
        "DROP CONSTRAINT b4_assessment_evidence_quality, "
        "DROP CONSTRAINT b4_assessment_probability, "
        "DROP CONSTRAINT b4_assessment_kind, "
        "DROP CONSTRAINT b4_assessment_snapshot_hash, "
        + ", ".join(f"DROP COLUMN {column}" for column in ASSESSMENT_COLUMNS)
    )
    cursor.execute(
        "ALTER TABLE research.opportunity "
        "DROP CONSTRAINT b4_opportunity_completeness, "
        "DROP CONSTRAINT b4_opportunity_investability, "
        "DROP CONSTRAINT b4_opportunity_expectation_posture, "
        "DROP CONSTRAINT b4_opportunity_direction, "
        "DROP CONSTRAINT b4_opportunity_merge_revision, "
        "DROP CONSTRAINT b4_opportunity_foundry_state, "
        "DROP CONSTRAINT b4_opportunity_snapshot_hash, "
        "DROP CONSTRAINT b4_opportunity_structural_key, "
        "DROP CONSTRAINT b4_opportunity_exact_key, "
        "DROP CONSTRAINT b4_opportunity_members_nonempty, "
        + ", ".join(f"DROP COLUMN {column}" for column in OPPORTUNITY_COLUMNS)
    )
    cursor.execute(
        "ALTER TABLE research.candidate "
        "DROP CONSTRAINT b4_candidate_foundry_snapshot_pair, "
        "DROP CONSTRAINT b4_candidate_foundry_snapshot_hash, "
        "DROP CONSTRAINT b4_candidate_foundry_snapshot, "
        + ", ".join(f"DROP COLUMN {column}" for column in CANDIDATE_COLUMNS)
    )
