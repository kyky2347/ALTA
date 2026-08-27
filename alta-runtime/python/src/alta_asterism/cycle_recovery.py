from .database import Database
from .scouts import SCOUTS, FrozenScoutInput


def recover_frozen_wake(
    database: Database, cycle_id: str
) -> tuple[FrozenScoutInput, dict[str, str]] | None:
    """Rebuilds an incomplete cycle only from its immutable Scout snapshots."""
    roles = tuple(item.scout_id for item in SCOUTS)
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT r.role, r.frozen_input FROM research.run r
            JOIN ops.job j ON j.id = r.job_id
            WHERE j.subject_id = %s AND j.kind = 'scout_batch'
              AND r.role = ANY(%s) ORDER BY r.role""",
            (cycle_id, list(roles)),
        ).fetchall()
        posture_rows = connection.execute(
            """SELECT payload->>'source_id', payload->>'posture'
            FROM ops.event WHERE correlation_id = %s
              AND event_type = 'source.posture' ORDER BY sequence""",
            (cycle_id,),
        ).fetchall()
    if not rows:
        return None
    by_role = {
        role: FrozenScoutInput.model_validate(value["input"]) for role, value in rows
    }
    if len(rows) != len(roles) or set(by_role) != set(roles):
        raise ValueError("incomplete cycle has a partial Scout snapshot set")
    identities = {
        (
            item.wake_id,
            item.environment,
            item.known_at,
            item.universe,
            item.expectation_posture,
        )
        for item in by_role.values()
    }
    if len(identities) != 1:
        raise ValueError("incomplete cycle Scout snapshots disagree on the wake")
    evidence = []
    seen_evidence = {}
    prior_opportunities = []
    seen_opportunities = {}
    memories = []
    seen_minds = {}
    feedback = []
    seen_feedback = {}
    for role in roles:
        for item in by_role[role].evidence:
            existing = seen_evidence.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on frozen evidence")
            if existing is None:
                seen_evidence[item.evidence_id] = item
                evidence.append(item)
        for item in by_role[role].prior_opportunities:
            existing = seen_opportunities.get(item.opportunity_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on prior Opportunity")
            if existing is None:
                seen_opportunities[item.opportunity_id] = item
                prior_opportunities.append(item)
        for item in by_role[role].trader_mind_memories:
            existing = seen_minds.get(item.scout_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on Trader Mind memory")
            if existing is None:
                seen_minds[item.scout_id] = item
                memories.append(item)
        for item in by_role[role].alpha_feedback:
            existing = seen_feedback.get(item.scout_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on Alpha feedback")
            if existing is None:
                seen_feedback[item.scout_id] = item
                feedback.append(item)
    frozen = by_role[roles[0]].model_copy(
        update={
            "evidence": tuple(evidence),
            "prior_opportunities": tuple(prior_opportunities),
            "trader_mind_memories": tuple(memories),
            "alpha_feedback": tuple(feedback),
        }
    )
    postures = {source_id: posture for source_id, posture in posture_rows}
    if not postures:
        raise ValueError("incomplete cycle is missing its source posture snapshot")
    return frozen, postures
