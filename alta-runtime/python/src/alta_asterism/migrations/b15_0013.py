REVISION = "b15_0013"


INDEXES = (
    (
        "b15_event_environment_sequence",
        "ops.event(environment, sequence DESC)",
        "",
    ),
    (
        "b15_event_pipeline_sequence",
        "ops.event(environment, sequence DESC)",
        "WHERE aggregate_type = 'mvp_pipeline'",
    ),
    (
        "b15_event_source_posture",
        "ops.event(environment, aggregate_id, sequence DESC)",
        "WHERE event_type = 'source.posture'",
    ),
    (
        "b15_event_committee_sequence",
        "ops.event(environment, sequence DESC)",
        "WHERE event_type LIKE 'committee.%'",
    ),
    (
        "b15_event_aggregate_sequence",
        "ops.event(environment, aggregate_id, sequence DESC)",
        "",
    ),
    (
        "b15_run_recent",
        "research.run(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_run_role_recent",
        "research.run(environment, role, created_at DESC, id)",
        "",
    ),
    (
        "b15_candidate_recent",
        "research.candidate(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_opportunity_recent",
        "research.opportunity(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_rank_recent",
        "research.rank(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_expression_recent",
        "research.expression(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_shadow_position_recent",
        "research.shadow_position(environment, created_at DESC, id)",
        "",
    ),
    (
        "b15_assessment_recent",
        "research.assessment(environment, created_at DESC, id)",
        "",
    ),
)


def upgrade(cursor) -> None:
    for name, target, predicate in INDEXES:
        cursor.execute(f"CREATE INDEX {name} ON {target} {predicate}")


def downgrade(cursor) -> None:
    for name, target, _predicate in reversed(INDEXES):
        schema = target.split(".", 1)[0]
        cursor.execute(f"DROP INDEX {schema}.{name}")
