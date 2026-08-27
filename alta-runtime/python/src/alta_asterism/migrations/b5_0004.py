REVISION = "b5_0004"


def upgrade(cursor) -> None:
    cursor.execute(
        """ALTER TABLE research.expression
        ADD COLUMN opportunity_snapshot_hash char(64),
        ADD COLUMN evidence_refs jsonb,
        ADD COLUMN evidence_set_hash char(64),
        ADD COLUMN binding_hash char(64),
        ADD COLUMN symbol text,
        ADD COLUMN side text,
        ADD COLUMN decision_known_at timestamptz,
        ADD COLUMN quote_snapshot jsonb,
        ADD COLUMN validation jsonb,
        ADD COLUMN expression_hash char(64),
        ADD COLUMN policy_version text"""
    )
    cursor.execute(
        """UPDATE research.expression expression SET
        opportunity_snapshot_hash = opportunity.snapshot_hash,
        evidence_refs = COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'evidence_id', evidence.id,
                'version', evidence.version,
                'known_at', evidence.known_at) ORDER BY evidence.id)
            FROM research.evidence evidence
            WHERE evidence.id = ANY(opportunity.evidence_ids)
        ), '[]'::jsonb),
        evidence_set_hash = repeat(md5(expression.id || ':legacy-evidence'), 2),
        binding_hash = repeat(md5(expression.id || ':legacy-binding'), 2),
        decision_known_at = expression.known_at,
        validation = jsonb_build_object(
            'status', expression.status,
            'reason_codes', jsonb_build_array('pre-b5')),
        expression_hash = repeat(md5(expression.id || ':legacy-expression'), 2),
        policy_version = 'pre-b5'
        FROM research.opportunity opportunity
        WHERE opportunity.id = expression.opportunity_id"""
    )
    cursor.execute(
        """ALTER TABLE research.expression
        ALTER COLUMN opportunity_snapshot_hash SET NOT NULL,
        ALTER COLUMN evidence_refs SET NOT NULL,
        ALTER COLUMN evidence_set_hash SET NOT NULL,
        ALTER COLUMN binding_hash SET NOT NULL,
        ALTER COLUMN decision_known_at SET NOT NULL,
        ALTER COLUMN validation SET NOT NULL,
        ALTER COLUMN expression_hash SET NOT NULL,
        ALTER COLUMN policy_version SET NOT NULL,
        ADD CONSTRAINT b5_expression_opportunity_snapshot_hash
            CHECK (opportunity_snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_expression_evidence_refs
            CHECK (jsonb_typeof(evidence_refs) = 'array'
                   AND octet_length(evidence_refs::text) <= 16384),
        ADD CONSTRAINT b5_expression_evidence_set_hash
            CHECK (evidence_set_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_expression_binding_hash
            CHECK (binding_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_expression_side CHECK (side IS NULL OR side = 'long'),
        ADD CONSTRAINT b5_expression_quote_snapshot
            CHECK (quote_snapshot IS NULL OR
                   (jsonb_typeof(quote_snapshot) = 'object'
                    AND octet_length(quote_snapshot::text) <= 16384)),
        ADD CONSTRAINT b5_expression_validation
            CHECK (jsonb_typeof(validation) = 'object'
                   AND octet_length(validation::text) <= 16384),
        ADD CONSTRAINT b5_expression_hash
            CHECK (expression_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_expression_hash_unique UNIQUE (expression_hash)"""
    )

    cursor.execute(
        """ALTER TABLE research.shadow_position
        ADD COLUMN opportunity_id text REFERENCES research.opportunity(id),
        ADD COLUMN opportunity_version integer,
        ADD COLUMN opportunity_snapshot_hash char(64),
        ADD COLUMN evidence_refs jsonb,
        ADD COLUMN evidence_set_hash char(64),
        ADD COLUMN binding_hash char(64),
        ADD COLUMN expression_version integer,
        ADD COLUMN expression_hash char(64),
        ADD COLUMN entry_transaction_id text,
        ADD COLUMN entry_price numeric,
        ADD COLUMN entry_commission numeric,
        ADD COLUMN opened_at timestamptz,
        ADD COLUMN position_thesis jsonb,
        ADD COLUMN thesis_hash char(64),
        ADD COLUMN exit_decision jsonb,
        ADD COLUMN exit_transaction_id text,
        ADD COLUMN exit_price numeric,
        ADD COLUMN exit_commission numeric,
        ADD COLUMN closed_at timestamptz,
        ADD COLUMN ledger_version text"""
    )
    cursor.execute(
        """UPDATE research.shadow_position position SET
        opportunity_id = expression.opportunity_id,
        opportunity_version = expression.opportunity_version,
        opportunity_snapshot_hash = expression.opportunity_snapshot_hash,
        evidence_refs = expression.evidence_refs,
        evidence_set_hash = expression.evidence_set_hash,
        binding_hash = expression.binding_hash,
        expression_version = expression.version,
        expression_hash = expression.expression_hash,
        opened_at = position.known_at,
        closed_at = CASE WHEN position.status = 'closed' THEN position.known_at END,
        ledger_version = 'pre-b5'
        FROM research.expression expression
        WHERE expression.id = position.expression_id"""
    )
    cursor.execute(
        """ALTER TABLE research.shadow_position
        ALTER COLUMN opportunity_id SET NOT NULL,
        ALTER COLUMN opportunity_version SET NOT NULL,
        ALTER COLUMN opportunity_snapshot_hash SET NOT NULL,
        ALTER COLUMN evidence_refs SET NOT NULL,
        ALTER COLUMN evidence_set_hash SET NOT NULL,
        ALTER COLUMN binding_hash SET NOT NULL,
        ALTER COLUMN expression_version SET NOT NULL,
        ALTER COLUMN expression_hash SET NOT NULL,
        ALTER COLUMN opened_at SET NOT NULL,
        ALTER COLUMN ledger_version SET NOT NULL,
        ADD CONSTRAINT b5_shadow_opportunity_version
            CHECK (opportunity_version > 0),
        ADD CONSTRAINT b5_shadow_opportunity_snapshot_hash
            CHECK (opportunity_snapshot_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_shadow_evidence_refs
            CHECK (jsonb_typeof(evidence_refs) = 'array'
                   AND octet_length(evidence_refs::text) <= 16384),
        ADD CONSTRAINT b5_shadow_evidence_set_hash
            CHECK (evidence_set_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_shadow_binding_hash
            CHECK (binding_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_shadow_expression_version CHECK (expression_version > 0),
        ADD CONSTRAINT b5_shadow_expression_hash
            CHECK (expression_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_shadow_entry_price
            CHECK (entry_price IS NULL OR entry_price > 0),
        ADD CONSTRAINT b5_shadow_entry_commission
            CHECK (entry_commission IS NULL OR entry_commission >= 0),
        ADD CONSTRAINT b5_shadow_position_thesis
            CHECK (position_thesis IS NULL OR
                   (jsonb_typeof(position_thesis) = 'object'
                    AND octet_length(position_thesis::text) <= 16384)),
        ADD CONSTRAINT b5_shadow_thesis_hash
            CHECK (thesis_hash IS NULL OR thesis_hash ~ '^[a-f0-9]{64}$'),
        ADD CONSTRAINT b5_shadow_exit_decision
            CHECK (exit_decision IS NULL OR
                   (jsonb_typeof(exit_decision) = 'object'
                    AND octet_length(exit_decision::text) <= 16384)),
        ADD CONSTRAINT b5_shadow_exit_price
            CHECK (exit_price IS NULL OR exit_price > 0),
        ADD CONSTRAINT b5_shadow_exit_commission
            CHECK (exit_commission IS NULL OR exit_commission >= 0),
        ADD CONSTRAINT b5_shadow_close_pair
            CHECK ((status = 'open' AND closed_at IS NULL) OR
                   (status = 'closed' AND closed_at IS NOT NULL))"""
    )
    cursor.execute(
        """CREATE UNIQUE INDEX b5_shadow_expression_unique
        ON research.shadow_position(expression_id)"""
    )

    cursor.execute(
        """CREATE FUNCTION ops.reject_b5_ledger_event_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.event_type LIKE 'shadow.%'
               OR OLD.event_type LIKE 'position.%' THEN
                RAISE EXCEPTION 'B5 shadow ledger events are append-only'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b5_ledger_event_append_only
        BEFORE UPDATE OR DELETE ON ops.event
        FOR EACH ROW EXECUTE FUNCTION ops.reject_b5_ledger_event_change()"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP TRIGGER b5_ledger_event_append_only ON ops.event")
    cursor.execute("DROP FUNCTION ops.reject_b5_ledger_event_change()")
    cursor.execute("DROP INDEX research.b5_shadow_expression_unique")
    cursor.execute(
        """ALTER TABLE research.shadow_position
        DROP CONSTRAINT b5_shadow_close_pair,
        DROP CONSTRAINT b5_shadow_exit_commission,
        DROP CONSTRAINT b5_shadow_exit_price,
        DROP CONSTRAINT b5_shadow_exit_decision,
        DROP CONSTRAINT b5_shadow_thesis_hash,
        DROP CONSTRAINT b5_shadow_position_thesis,
        DROP CONSTRAINT b5_shadow_entry_commission,
        DROP CONSTRAINT b5_shadow_entry_price,
        DROP CONSTRAINT b5_shadow_expression_hash,
        DROP CONSTRAINT b5_shadow_expression_version,
        DROP CONSTRAINT b5_shadow_binding_hash,
        DROP CONSTRAINT b5_shadow_evidence_set_hash,
        DROP CONSTRAINT b5_shadow_evidence_refs,
        DROP CONSTRAINT b5_shadow_opportunity_snapshot_hash,
        DROP CONSTRAINT b5_shadow_opportunity_version,
        DROP COLUMN ledger_version,
        DROP COLUMN closed_at,
        DROP COLUMN exit_commission,
        DROP COLUMN exit_price,
        DROP COLUMN exit_transaction_id,
        DROP COLUMN exit_decision,
        DROP COLUMN thesis_hash,
        DROP COLUMN position_thesis,
        DROP COLUMN opened_at,
        DROP COLUMN entry_commission,
        DROP COLUMN entry_price,
        DROP COLUMN entry_transaction_id,
        DROP COLUMN expression_hash,
        DROP COLUMN expression_version,
        DROP COLUMN binding_hash,
        DROP COLUMN evidence_set_hash,
        DROP COLUMN evidence_refs,
        DROP COLUMN opportunity_snapshot_hash,
        DROP COLUMN opportunity_version,
        DROP COLUMN opportunity_id"""
    )
    cursor.execute(
        """ALTER TABLE research.expression
        DROP CONSTRAINT b5_expression_hash_unique,
        DROP CONSTRAINT b5_expression_hash,
        DROP CONSTRAINT b5_expression_validation,
        DROP CONSTRAINT b5_expression_quote_snapshot,
        DROP CONSTRAINT b5_expression_side,
        DROP CONSTRAINT b5_expression_binding_hash,
        DROP CONSTRAINT b5_expression_evidence_set_hash,
        DROP CONSTRAINT b5_expression_evidence_refs,
        DROP CONSTRAINT b5_expression_opportunity_snapshot_hash,
        DROP COLUMN policy_version,
        DROP COLUMN expression_hash,
        DROP COLUMN validation,
        DROP COLUMN quote_snapshot,
        DROP COLUMN decision_known_at,
        DROP COLUMN side,
        DROP COLUMN symbol,
        DROP COLUMN binding_hash,
        DROP COLUMN evidence_set_hash,
        DROP COLUMN evidence_refs,
        DROP COLUMN opportunity_snapshot_hash"""
    )
