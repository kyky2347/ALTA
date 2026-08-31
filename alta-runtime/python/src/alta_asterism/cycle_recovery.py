from .database import Database
from .research_agenda import OpportunityDrive
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
    incentives = []
    seen_incentives = {}
    research_attention = None
    opportunity_continuity = None
    market_agenda = None
    market_agenda_base = None
    market_seeds = []
    seen_market_seeds = {}
    opportunity_drive_core = None
    research_queue = {}
    research_assignments = {}
    for role in roles:
        scoped_drive = by_role[role].opportunity_drive
        drive_core = scoped_drive.model_copy(
            update={
                "assigned_mode": "explore",
                "assigned_research": None,
                "research_queue": (),
                "research_assignments": (),
            }
        )
        if opportunity_drive_core is not None and opportunity_drive_core != drive_core:
            raise ValueError("Scout snapshots disagree on the research director state")
        opportunity_drive_core = drive_core
        for item in scoped_drive.research_queue:
            key = (item.opportunity_id, item.question_id)
            existing = research_queue.get(key)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on a research queue item")
            research_queue[key] = item
        for item in scoped_drive.research_assignments:
            existing = research_assignments.get(item.scout_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on a research assignment")
            research_assignments[item.scout_id] = item
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
        for item in by_role[role].research_incentives:
            existing = seen_incentives.get(item.scout_id)
            if existing is not None and existing != item:
                raise ValueError("Scout snapshots disagree on research incentive")
            if existing is None:
                seen_incentives[item.scout_id] = item
                incentives.append(item)
        attention = by_role[role].research_attention_portfolio
        if attention is not None:
            if research_attention is not None and research_attention != attention:
                raise ValueError(
                    "Scout snapshots disagree on research attention portfolio"
                )
            research_attention = attention
        continuity = by_role[role].opportunity_continuity
        if continuity is not None:
            if (
                opportunity_continuity is not None
                and opportunity_continuity != continuity
            ):
                raise ValueError("Scout snapshots disagree on Opportunity continuity")
            opportunity_continuity = continuity
        agenda = by_role[role].market_research_agenda
        if agenda is not None:
            agenda_base = agenda.model_copy(update={"seeds": ()})
            if market_agenda_base is not None and market_agenda_base != agenda_base:
                raise ValueError("Scout snapshots disagree on market research agenda")
            market_agenda = agenda
            market_agenda_base = agenda_base
            for item in agenda.seeds:
                existing = seen_market_seeds.get(item.seed_id)
                if existing is not None and existing != item:
                    raise ValueError("Scout snapshots disagree on market research seed")
                if existing is None:
                    seen_market_seeds[item.seed_id] = item
                    market_seeds.append(item)
    if market_agenda is not None:
        market_agenda = market_agenda.model_copy(
            update={
                "seeds": tuple(
                    sorted(market_seeds, key=lambda item: item.assigned_scout_id)
                )
            }
        )
    ordered_queue = tuple(
        sorted(
            research_queue.values(),
            key=lambda item: (
                -item.priority_score,
                item.remaining_days,
                item.opportunity_id,
                item.question_id,
            ),
        )
    )
    queue_positions = {
        (item.opportunity_id, item.question_id): index
        for index, item in enumerate(ordered_queue)
    }
    ordered_assignments = tuple(
        sorted(
            research_assignments.values(),
            key=lambda item: queue_positions[(item.opportunity_id, item.question_id)],
        )
    )
    if opportunity_drive_core is None:
        raise ValueError("incomplete cycle is missing its research director state")
    opportunity_drive = OpportunityDrive.model_validate(
        {
            **opportunity_drive_core.model_dump(mode="python"),
            "research_queue": ordered_queue,
            "research_assignments": ordered_assignments,
        }
    )
    frozen = by_role[roles[0]].model_copy(
        update={
            "evidence": tuple(evidence),
            "prior_opportunities": tuple(prior_opportunities),
            "trader_mind_memories": tuple(memories),
            "alpha_feedback": tuple(feedback),
            "research_incentives": tuple(incentives),
            "research_attention_portfolio": research_attention,
            "opportunity_continuity": opportunity_continuity,
            "opportunity_drive": opportunity_drive,
            "market_research_agenda": market_agenda,
        }
    )
    postures = {source_id: posture for source_id, posture in posture_rows}
    if not postures:
        raise ValueError("incomplete cycle is missing its source posture snapshot")
    return frozen, postures
