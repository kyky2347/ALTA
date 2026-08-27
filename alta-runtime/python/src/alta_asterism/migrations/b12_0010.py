REVISION = "b12_0010"


def upgrade(cursor) -> None:
    cursor.execute(
        """CREATE FUNCTION ops.reject_b12_evaluation_event_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.event_type LIKE 'evaluation.%' THEN
                RAISE EXCEPTION 'evaluation bindings are append-only'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END
        $$"""
    )
    cursor.execute(
        """CREATE TRIGGER b12_evaluation_event_append_only
        BEFORE UPDATE OR DELETE ON ops.event
        FOR EACH ROW EXECUTE FUNCTION ops.reject_b12_evaluation_event_change()"""
    )


def downgrade(cursor) -> None:
    cursor.execute("DROP TRIGGER b12_evaluation_event_append_only ON ops.event")
    cursor.execute("DROP FUNCTION ops.reject_b12_evaluation_event_change()")
