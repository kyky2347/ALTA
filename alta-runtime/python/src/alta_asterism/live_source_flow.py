import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

from .alpha_feedback import AlphaFeedbackProjector
from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .database import Database
from .implementation import PortfolioRiskPolicy
from .investment_thesis import pillar_research_question
from .massive import MassiveDataset
from .market_research_projection import MarketResearchAgendaProjector
from .opportunity_memory import PriorOpportunitySnapshot
from .opportunity_continuity import (
    MAX_ACTIVE_OPPORTUNITY_SCAN,
    build_opportunity_continuity,
)
from .portfolio_construction import PortfolioConstructor
from .portfolio_intelligence import build_portfolio_research_mandate
from .research_agenda import (
    build_open_research_questions,
    build_opportunity_drive,
    next_follow_up_at,
)
from .research_incentive import build_research_incentives
from .research_attention import (
    ResearchAttentionProjector,
    apply_research_attention_to_market_agenda,
)
from .scouts import EvidenceSnapshot, FrozenScoutInput
from .scout_repository import ScoutRepository
from .trader_mind import SCOUTS, TraderMindMemory, bounded_mind_summary


@dataclass
class _ConnectorRetryGate:
    """In-process exponential backoff for optional upstream connectors."""

    failures: int = 0
    retry_at: datetime | None = None

    def blocked(self, known_at: datetime) -> bool:
        return self.retry_at is not None and known_at < self.retry_at

    def record(self, known_at: datetime, posture: str) -> None:
        if posture in {"healthy", "disabled"}:
            self.failures = 0
            self.retry_at = None
            return
        self.failures = min(self.failures + 1, 6)
        delay = min(3_600, 60 * 2 ** (self.failures - 1))
        self.retry_at = known_at + timedelta(seconds=delay)

    def reason(self, known_at: datetime) -> str:
        remaining = (
            max(1, int((self.retry_at - known_at).total_seconds()))
            if self.retry_at is not None
            else 1
        )
        return f"connector_backoff:{remaining}s"


def _text_prefix(value: str, maximum_bytes: int = 480) -> str:
    normalized = " ".join(value.split())
    encoded = normalized.encode()
    if len(encoded) <= maximum_bytes:
        return normalized
    return encoded[:maximum_bytes].decode(errors="ignore").rstrip()


def _first_text(value: Any) -> str | None:
    preferred = {"title", "headline", "summary", "description", "name", "text"}
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in preferred and isinstance(child, str) and child.strip():
                return _text_prefix(child)
        for child in value.values():
            found = _first_text(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value[:10]:
            found = _first_text(child)
            if found:
                return found
    return None


def _market_summary(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return None
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        return None
    aggregate = payload.get("aggregate")
    if isinstance(aggregate, dict):
        fields = {
            "open": aggregate.get("open"),
            "high": aggregate.get("high"),
            "low": aggregate.get("low"),
            "close": aggregate.get("close"),
            "volume": aggregate.get("volume"),
        }
        values = ", ".join(
            f"{key}={value}" for key, value in fields.items() if value is not None
        )
        return _text_prefix(f"{symbol} adjusted daily market bar: {values}.")
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        quote = snapshot.get("last_quote") or snapshot.get("lastQuote") or {}
        if not isinstance(quote, dict):
            quote = {}
        bid = quote.get("bid_price", quote.get("bidPrice"))
        ask = quote.get("ask_price", quote.get("askPrice"))
        change = snapshot.get("todays_change_percent", snapshot.get("todaysChangePerc"))
        return _text_prefix(
            f"{symbol} market snapshot: bid={bid}, ask={ask}, "
            f"today_change_percent={change}."
        )
    return None


def _body_event_time(body: Any) -> datetime | None:
    if not isinstance(body, dict):
        return None
    times = body.get("semanticTimes")
    if not isinstance(times, dict) or not times.get("eventAt"):
        return None
    try:
        value = datetime.fromisoformat(str(times["eventAt"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None and value.utcoffset() is not None else None


def _balanced_rows(rows: list[tuple], limit: int) -> list[tuple]:
    by_source: dict[str, list[tuple]] = {}
    for row in rows:
        by_source.setdefault(row[2], []).append(row)
    selected: list[tuple] = []
    sources = sorted(by_source)
    while len(selected) < limit and sources:
        remaining = []
        for source in sources:
            bucket = by_source[source]
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) == limit:
                    break
            if bucket:
                remaining.append(source)
        sources = remaining
    return selected


def _public_locator(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"url", "uri", "source_url", "sourceurl"} and isinstance(
                child, str
            ):
                parsed = urlsplit(child)
                if (
                    parsed.scheme == "https"
                    and parsed.hostname
                    and parsed.username is None
                    and parsed.password is None
                ):
                    return urlunsplit(
                        (parsed.scheme, parsed.netloc, parsed.path, "", "")
                    )
            found = _public_locator(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value[:20]:
            found = _public_locator(child)
            if found:
                return found
    return None


def _territory(source: str) -> str:
    normalized = source.lower()
    if "massive" in normalized or "market" in normalized or "price" in normalized:
        return "massive_bar"
    if "policy" in normalized or "official" in normalized or "sec" in normalized:
        return "official_policy"
    if "expect" in normalized or "consensus" in normalized:
        return "expectation_primitive"
    return "finlight_event"


class DatabaseSourceFlow:
    """Builds a bounded point-in-time wake from durable Raw/Evidence records."""

    NORMALIZER_VERSION = "live-evidence-v1"

    def __init__(
        self,
        database: Database,
        universe: tuple[str, ...],
        *,
        environment: Environment = Environment.SHADOW,
        max_evidence: int = 8,
        portfolio_policy: PortfolioRiskPolicy | None = None,
        anchor_wakes: bool = True,
    ) -> None:
        if not 1 <= max_evidence <= 12:
            raise ValueError("live source max_evidence must be between 1 and 12")
        self.database = database
        self.universe = universe
        self.environment = environment
        self.max_evidence = max_evidence
        self.anchor_wakes = anchor_wakes
        self.portfolio_policy = portfolio_policy or PortfolioRiskPolicy()
        self.portfolio_constructor = PortfolioConstructor(
            database, self.portfolio_policy
        )
        self.market_research = MarketResearchAgendaProjector(database)
        self.research_attention = ResearchAttentionProjector(database)

    def schedule_and_wake(
        self,
        cycle_id: str,
        wake_at: datetime,
        overrides: dict[str, str],
    ) -> tuple[FrozenScoutInput, dict[str, str]]:
        if overrides:
            raise ValueError("live source posture cannot be overridden by a demo flag")
        if wake_at.tzinfo is None or wake_at.utcoffset() is None:
            raise ValueError("live wake_at must be timezone-aware")
        with self.database.connect() as connection:
            self._record_wake(connection, cycle_id, wake_at)
            self._materialize_raw(connection, wake_at)
            rows = connection.execute(
                """SELECT e.id, e.raw_id, r.source, r.content_hash, e.known_at,
                e.summary, r.body, CASE
                WHEN r.body->>'origin_fingerprint' ~ '^[a-f0-9]{64}$'
                THEN r.body->>'origin_fingerprint' END
                FROM research.evidence e
                JOIN research.raw r ON r.id = e.raw_id
                WHERE e.environment = %s AND r.environment = %s
                  AND e.known_at <= %s AND r.known_at <= %s
                  AND lower(r.source) NOT LIKE '%%fixture%%'
                  AND coalesce(r.body->>'fixture','false') <> 'true'
                ORDER BY e.known_at DESC, e.id LIMIT %s""",
                (
                    self.environment.value,
                    self.environment.value,
                    wake_at,
                    wake_at,
                    self.max_evidence * 8,
                ),
            ).fetchall()
            rows = _balanced_rows(rows, self.max_evidence)
            (
                active_opportunities,
                registry_active,
                deferred_questions,
                next_research_due_at,
            ) = self._prior_opportunities(connection, wake_at)
            idle_streak = self._idle_streak(connection, wake_at)
            trader_mind_memories = self._trader_mind_memories(connection, wake_at)
            postures = self._record_postures(connection, cycle_id, wake_at, rows)
        alpha_feedback = AlphaFeedbackProjector(self.database).at(
            self.environment, wake_at
        )
        portfolio_research_mandate = build_portfolio_research_mandate(
            self.portfolio_constructor.load_state(wake_at),
            self.portfolio_policy,
            wake_at,
        )
        scout_ids = tuple(item.scout_id for item in SCOUTS)
        research_attention_portfolio = self.research_attention.at(
            self.environment.value,
            self.universe,
            scout_ids,
            wake_at,
            {item.scout_id: item.alpha_archetypes for item in SCOUTS},
        )
        market_research_agenda = apply_research_attention_to_market_agenda(
            self.market_research.at(self.environment, self.universe, wake_at),
            research_attention_portfolio,
        )
        continuity_selection = build_opportunity_continuity(
            wake_at=wake_at,
            opportunities=active_opportunities,
            registry_active=registry_active,
            deferred_questions=deferred_questions,
            next_research_due_at=next_research_due_at,
        )
        snapshots = tuple(
            EvidenceSnapshot(
                evidence_id=row[0],
                raw_id=row[1],
                source=row[2],
                territory=_territory(row[2]),
                source_locator=(_public_locator(row[6]) or f"alta://database/{row[1]}"),
                known_at=row[4],
                content_hash=row[3],
                origin_fingerprint=row[7],
                summary=_text_prefix(row[5]),
            )
            for row in rows
        )
        posture = "available" if snapshots else "unavailable"
        evidence = snapshots
        prior = continuity_selection.frozen_opportunities
        continuity = continuity_selection.portfolio
        memories = trader_mind_memories
        feedback = alpha_feedback
        incentives = build_research_incentives(feedback, scout_ids=scout_ids)
        agenda = market_research_agenda
        attention = research_attention_portfolio
        mandate = portfolio_research_mandate
        while True:
            drive = build_opportunity_drive(
                cycle_id=cycle_id,
                idle_streak=idle_streak,
                research_queue=continuity_selection.research_queue,
                scout_ids=scout_ids,
            )
            try:
                frozen = FrozenScoutInput(
                    wake_id=cycle_id,
                    environment=self.environment,
                    known_at=wake_at,
                    universe=self.universe,
                    evidence=evidence,
                    prior_opportunities=prior,
                    opportunity_continuity=continuity,
                    opportunity_drive=drive,
                    market_research_agenda=agenda,
                    trader_mind_memories=memories,
                    alpha_feedback=feedback,
                    research_incentives=incentives,
                    research_attention_portfolio=attention,
                    portfolio_research_mandate=mandate,
                    expectation_posture=posture,
                )
                if self.anchor_wakes:
                    ScoutRepository(self.database).start_batch(
                        f"batch_{cycle_id}", frozen, postures
                    )
                return frozen, postures
            except ValidationError as error:
                if "frozen input exceeds the hard byte budget" not in str(error):
                    raise

            # Preserve the freshest evidence and prioritized follow-up questions.
            # Lower-priority process context is shed deterministically until the
            # immutable hand-off fits its contract, instead of failing the cycle.
            priority_ids = set(drive.priority_opportunity_ids)
            removable_prior = next(
                (
                    index
                    for index in range(len(prior) - 1, -1, -1)
                    if prior[index].opportunity_id not in priority_ids
                ),
                None,
            )
            if removable_prior is not None:
                prior = prior[:removable_prior] + prior[removable_prior + 1 :]
                continuity = continuity.model_copy(
                    update={
                        "frozen_active": len(prior),
                        "selected_opportunity_ids": tuple(
                            item.opportunity_id for item in prior
                        ),
                        "selection_truncated": continuity.scanned_active > len(prior),
                    }
                )
            elif memories:
                memories = ()
            elif feedback or incentives:
                feedback = ()
                incentives = ()
            elif mandate is not None:
                mandate = None
            elif attention is not None:
                attention = None
            elif agenda is not None:
                agenda = None
            elif evidence:
                evidence = evidence[:-1]
            elif prior and not priority_ids:
                prior = prior[:-1]
                continuity = continuity.model_copy(
                    update={
                        "frozen_active": len(prior),
                        "selected_opportunity_ids": tuple(
                            item.opportunity_id for item in prior
                        ),
                        "selection_truncated": continuity.scanned_active > len(prior),
                    }
                )
            else:
                raise ValueError("live frozen input cannot fit its hard byte budget")

    def _trader_mind_memories(
        self, connection, wake_at: datetime
    ) -> tuple[TraderMindMemory, ...]:
        rows = connection.execute(
            """SELECT scout_id, version, known_at, turn_count, rolling_summary
            FROM research.mind_state
            WHERE environment = %s AND known_at < %s AND rolling_summary <> ''
            ORDER BY scout_id LIMIT 4""",
            (self.environment.value, wake_at),
        ).fetchall()
        return tuple(
            TraderMindMemory(
                scout_id=row[0],
                version=row[1],
                known_at=row[2],
                turn_count=row[3],
                summary=bounded_mind_summary(row[4]),
            )
            for row in rows
        )

    def _idle_streak(self, connection, wake_at: datetime) -> int:
        rows = connection.execute(
            """SELECT payload->'snapshot'->>'status'
            FROM ops.event
            WHERE environment = %s AND event_type = 'mvp.pipeline.completed'
              AND aggregate_id LIKE 'live-%%' AND known_at < %s
            ORDER BY sequence DESC LIMIT 12""",
            (self.environment.value, wake_at),
        ).fetchall()
        streak = 0
        for (status,) in rows:
            if status != "MVP_IDLE":
                break
            streak += 1
        return streak

    def _prior_opportunities(self, connection, wake_at: datetime):
        rows = connection.execute(
            """SELECT o.id, o.version, o.known_at, o.title, o.entity_key,
            o.direction, o.status, o.thesis, o.horizon_days, o.snapshot_hash,
            deadline.decision_deadline_at,
            (SELECT jsonb_agg(c.foundry_snapshot ORDER BY member.ordinality)
             FROM unnest(o.member_candidate_ids) WITH ORDINALITY
                  AS member(candidate_id, ordinality)
             JOIN research.candidate c ON c.id = member.candidate_id
             WHERE c.foundry_snapshot IS NOT NULL),
            count(*) OVER ()
            FROM research.opportunity o
            LEFT JOIN LATERAL (
                SELECT min((pillar->>'due_at')::timestamptz)
                       AS decision_deadline_at
                FROM research.candidate candidate,
                     LATERAL jsonb_array_elements(
                         coalesce(candidate.foundry_snapshot->'thesis_pillars',
                                  '[]'::jsonb)
                     ) pillar
                WHERE candidate.id = ANY(o.member_candidate_ids)
                  AND pillar->>'due_at' ~
                      '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
            ) deadline ON true
            WHERE o.environment = %s AND foundry_state = 'active'
              AND o.status IN ('forming', 'ranked', 'shadow')
              AND o.known_at < %s
              AND cardinality(o.evidence_ids) > 0
              AND NOT EXISTS (
                SELECT 1 FROM unnest(o.evidence_ids) AS remembered(evidence_id)
                JOIN research.evidence e ON e.id = remembered.evidence_id
                JOIN research.raw r ON r.id = e.raw_id
                WHERE lower(r.source) LIKE '%%fixture%%'
                   OR coalesce(r.body->>'fixture','false') = 'true'
              )
            ORDER BY
              (coalesce(deadline.decision_deadline_at,
                        o.known_at + make_interval(days => o.horizon_days)) <= %s),
              coalesce(deadline.decision_deadline_at,
                       o.known_at + make_interval(days => o.horizon_days)),
              o.known_at DESC, o.id
            LIMIT %s""",
            (
                self.environment.value,
                wake_at,
                wake_at,
                MAX_ACTIVE_OPPORTUNITY_SCAN,
            ),
        ).fetchall()
        opportunity_ids = [row[0] for row in rows]
        follow_up_attempt_rows = (
            connection.execute(
                """SELECT DISTINCT ON (assigned->>'opportunity_id',
                                               assigned->>'question_id')
                assigned->>'opportunity_id', assigned->>'question_id',
                run.known_at,
                (SELECT prior.value->>'snapshot_hash'
                 FROM jsonb_array_elements(
                     coalesce(
                         run.frozen_input->'input'->'prior_opportunities',
                         '[]'::jsonb
                     )
                 ) WITH ORDINALITY AS prior(value, ordinality)
                 WHERE prior.value->>'opportunity_id' =
                       assigned->>'opportunity_id'
                 ORDER BY prior.ordinality
                 LIMIT 1)
                FROM research.run run
                JOIN research.run_artifact artifact ON artifact.run_id = run.id
                  AND artifact.environment = run.environment
                  AND artifact.artifact_kind = 'scout_output'
                CROSS JOIN LATERAL (
                    SELECT run.frozen_input->'input'->'opportunity_drive'
                      ->'assigned_research' AS assigned
                ) assignment
                WHERE run.environment = %s AND run.status = 'succeeded'
                  AND run.known_at < %s
                  AND assigned->>'opportunity_id' = ANY(%s)
                  AND run.frozen_input->'input'->'opportunity_drive'
                        ->>'assigned_mode' = 'follow_up'
                  AND artifact.content->'output'->>'research_mode' = 'follow_up'
                ORDER BY assigned->>'opportunity_id', assigned->>'question_id',
                         run.known_at DESC, run.id DESC""",
                (self.environment.value, wake_at, opportunity_ids),
            ).fetchall()
            if opportunity_ids
            else []
        )
        follow_up_attempts = {
            (row[0], row[1]): (row[2], row[3]) for row in follow_up_attempt_rows
        }
        assessment_rows = (
            connection.execute(
                """SELECT assessment.opportunity_id, assessment.assessor,
                assessment.missing_evidence
                FROM research.assessment assessment
                JOIN research.opportunity opportunity
                  ON opportunity.id = assessment.opportunity_id
                 AND opportunity.environment = assessment.environment
                 AND opportunity.snapshot_hash = assessment.snapshot_hash
                WHERE assessment.opportunity_id = ANY(%s)
                  AND assessment.environment = %s
                  AND assessment.assessment_kind = 'private'
                  AND assessment.locked_at < %s
                ORDER BY assessment.opportunity_id, assessment.assessor""",
                (opportunity_ids, self.environment.value, wake_at),
            ).fetchall()
            if opportunity_ids
            else []
        )
        assessments_by_opportunity: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
        for opportunity_id, assessor, questions in assessment_rows:
            assessments_by_opportunity.setdefault(opportunity_id, []).append(
                (assessor, questions)
            )
        snapshots = []
        deferred_questions = 0
        next_research_due_at: datetime | None = None
        for row in rows:
            assessor_questions = tuple(
                (assessor, question)
                for assessor, questions in assessments_by_opportunity.get(row[0], ())
                for question in questions
            )
            candidate_snapshots = (
                tuple(item for item in row[11] if isinstance(item, dict))
                if isinstance(row[11], list)
                else ()
            )
            next_test = next(
                (
                    item["next_test"]
                    for item in candidate_snapshots
                    if item.get("next_test")
                ),
                None,
            )
            first_rejection = next(
                (
                    item["first_rejection"]
                    for item in candidate_snapshots
                    if item.get("first_rejection")
                ),
                None,
            )
            thesis_questions = tuple(
                pillar_research_question(pillar)
                for item in candidate_snapshots
                for pillar in item.get("thesis_pillars", ())
                if isinstance(pillar, dict)
            )[:2]
            questions = build_open_research_questions(
                opportunity_id=row[0],
                next_test=next_test,
                first_rejection=first_rejection,
                assessor_questions=assessor_questions,
                thesis_questions=thesis_questions,
            )
            due_questions = []
            deadline_at = row[10] or row[2] + timedelta(days=row[8])
            for question in questions:
                attempt = follow_up_attempts.get((row[0], question.question_id))
                if attempt is None or attempt[1] != row[9]:
                    due_questions.append(question)
                    continue
                eligible_at = next_follow_up_at(
                    attempted_at=attempt[0], deadline_at=deadline_at
                )
                if eligible_at <= wake_at:
                    due_questions.append(question)
                    continue
                deferred_questions += 1
                next_research_due_at = (
                    eligible_at
                    if next_research_due_at is None
                    else min(next_research_due_at, eligible_at)
                )
            snapshots.append(
                PriorOpportunitySnapshot(
                    opportunity_id=row[0],
                    version=row[1],
                    known_at=row[2],
                    title=row[3],
                    entity_key=row[4],
                    direction=row[5],
                    status=row[6],
                    horizon_days=row[8],
                    decision_deadline_at=row[10],
                    summary=_text_prefix(row[7], maximum_bytes=240),
                    snapshot_hash=row[9],
                    research_questions=tuple(due_questions),
                )
            )
        registry_active = int(rows[0][12]) if rows else 0
        return (
            tuple(snapshots),
            registry_active,
            deferred_questions,
            next_research_due_at,
        )

    def _record_wake(self, connection, cycle_id: str, wake_at: datetime) -> None:
        for event_type, aggregate_type in (
            ("schedule.wake_due", "schedule"),
            ("wake.created", "wake"),
        ):
            _append_event(
                connection,
                _contract_event(
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=cycle_id,
                    environment=self.environment,
                    known_at=wake_at,
                    payload={
                        "cycle_id": cycle_id,
                        "mode": "database_pit",
                        "universe": self.universe,
                    },
                    correlation_id=cycle_id,
                ),
            )

    def _materialize_raw(self, connection, wake_at: datetime) -> None:
        rows = connection.execute(
            """SELECT r.id, r.known_at, r.source, r.body FROM research.raw r
            LEFT JOIN research.evidence e ON e.raw_id = r.id
            WHERE r.environment = %s AND r.known_at <= %s AND e.id IS NULL
              AND r.source_key NOT LIKE 'option-snapshot:%%'
              AND lower(r.source) NOT LIKE '%%fixture%%'
              AND coalesce(r.body->>'fixture','false') <> 'true'
            ORDER BY r.known_at, r.id LIMIT 100""",
            (self.environment.value, wake_at),
        ).fetchall()
        for raw_id, known_at, source, body in rows:
            summary = _market_summary(body) or _first_text(body)
            if not summary:
                summary = f"New versioned {source} record {raw_id}."
            evidence_id = (
                "evidence_"
                + hashlib.sha256(
                    f"{raw_id}\0{self.NORMALIZER_VERSION}".encode()
                ).hexdigest()[:32]
            )
            connection.execute(
                """INSERT INTO research.evidence
                (id, environment, version, known_at, raw_id, stance, summary,
                 event_time)
                VALUES (%s,%s,1,%s,%s,'unknown',%s,%s)
                ON CONFLICT (id) DO NOTHING""",
                (
                    evidence_id,
                    self.environment.value,
                    known_at,
                    raw_id,
                    summary,
                    _body_event_time(body),
                ),
            )

    def _record_postures(
        self, connection, cycle_id: str, wake_at: datetime, rows: list[tuple]
    ) -> dict[str, str]:
        counts: dict[str, int] = {}
        for row in rows:
            counts[row[2]] = counts.get(row[2], 0) + 1
        postures = {source: "healthy" for source in sorted(counts)}
        if not postures:
            postures["durable_database"] = "degraded"
        for source, posture in postures.items():
            _append_event(
                connection,
                _contract_event(
                    event_type="source.posture",
                    aggregate_type="source",
                    aggregate_id=f"{cycle_id}:{source}",
                    environment=self.environment,
                    known_at=wake_at,
                    payload={
                        "cycle_id": cycle_id,
                        "source_id": source,
                        "posture": posture,
                        "evidence_count": counts.get(source, 0),
                        "reason": (
                            "pit_evidence_available"
                            if posture == "healthy"
                            else "no_durable_evidence_scout_search_allowed"
                        ),
                    },
                    correlation_id=cycle_id,
                ),
            )
        return postures


class IngestingSourceFlow:
    """Polls configured durable connectors, then freezes the prior PIT cutoff."""

    def __init__(
        self,
        database_flow: DatabaseSourceFlow,
        finlight_adapter=None,
        massive_adapter=None,
        massive_daily_cursor=None,
        massive_discovery_enabled: bool = False,
    ) -> None:
        self.database_flow = database_flow
        # The outer flow owns the complete anchor because transport posture is
        # part of the immutable wake contract.
        self.database_flow.anchor_wakes = False
        self.finlight_adapter = finlight_adapter
        self.massive_adapter = massive_adapter
        self.massive_daily_cursor = massive_daily_cursor
        self.massive_discovery_enabled = massive_discovery_enabled
        self._finlight_retry = _ConnectorRetryGate()
        self._massive_retry = _ConnectorRetryGate()

    def schedule_and_wake(
        self, cycle_id: str, wake_at: datetime, overrides: dict[str, str]
    ) -> tuple[FrozenScoutInput, dict[str, str]]:
        reset_budget = getattr(self.massive_adapter, "reset_budget", None)
        if reset_budget is not None:
            reset_budget(cycle_id)
        existing_transport = self._existing_transport_postures(cycle_id)
        if existing_transport is not None:
            frozen, postures = self.database_flow.schedule_and_wake(
                cycle_id, wake_at, overrides
            )
            combined_postures = {**postures, **existing_transport}
            ScoutRepository(self.database_flow.database).start_batch(
                f"batch_{cycle_id}", frozen, combined_postures
            )
            return frozen, combined_postures
        ingestion_posture = "disabled"
        reason = "finlight_key_not_injected"
        if self.finlight_adapter is not None:
            if self._finlight_retry.blocked(wake_at):
                ingestion_posture = "degraded"
                reason = self._finlight_retry.reason(wake_at)
            else:
                try:
                    result = self.finlight_adapter.run_once()
                    ingestion_posture = result.posture
                    reason = result.reason
                except Exception as error:
                    ingestion_posture = "degraded"
                    reason = f"connector_error:{type(error).__name__}"
                self._finlight_retry.record(wake_at, ingestion_posture)
        if self._massive_retry.blocked(wake_at):
            massive_posture = "degraded"
            massive_reason = self._massive_retry.reason(wake_at)
        else:
            try:
                massive_posture, massive_reason = self._ingest_massive(wake_at)
            except Exception as error:
                massive_posture = "degraded"
                massive_reason = f"connector_error:{type(error).__name__}"
            self._massive_retry.record(wake_at, massive_posture)
        frozen, postures = self.database_flow.schedule_and_wake(
            cycle_id, wake_at, overrides
        )
        with self.database_flow.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="source.posture",
                    aggregate_type="source",
                    aggregate_id=f"{cycle_id}:finlight_transport",
                    environment=self.database_flow.environment,
                    known_at=wake_at,
                    payload={
                        "cycle_id": cycle_id,
                        "source_id": "finlight_transport",
                        "posture": ingestion_posture,
                        "reason": reason,
                    },
                    correlation_id=cycle_id,
                ),
            )
            _append_event(
                connection,
                _contract_event(
                    event_type="source.posture",
                    aggregate_type="source",
                    aggregate_id=f"{cycle_id}:massive_transport",
                    environment=self.database_flow.environment,
                    known_at=wake_at,
                    payload={
                        "cycle_id": cycle_id,
                        "source_id": "massive_transport",
                        "posture": massive_posture,
                        "reason": massive_reason,
                    },
                    correlation_id=cycle_id,
                ),
            )
        combined_postures = {
            **postures,
            "finlight_transport": ingestion_posture,
            "massive_transport": massive_posture,
        }
        ScoutRepository(self.database_flow.database).start_batch(
            f"batch_{cycle_id}", frozen, combined_postures
        )
        return frozen, combined_postures

    def _existing_transport_postures(self, cycle_id: str) -> dict[str, str] | None:
        with self.database_flow.database.connect() as connection:
            rows = connection.execute(
                """SELECT payload->>'source_id', payload->>'posture'
                FROM ops.event WHERE correlation_id = %s
                  AND event_type = 'source.posture'
                  AND payload->>'source_id' IN
                      ('finlight_transport','massive_transport')
                ORDER BY sequence""",
                (cycle_id,),
            ).fetchall()
        postures = {source_id: posture for source_id, posture in rows}
        if set(postures) != {"finlight_transport", "massive_transport"}:
            return None
        return postures

    def _ingest_massive(self, wake_at: datetime) -> tuple[str, str]:
        if self.massive_adapter is None:
            return "disabled", "massive_key_not_injected_or_disabled"
        if not self.massive_discovery_enabled:
            return "disabled", "reserved_for_instrument_confirmation"
        snapshot = self.massive_adapter.fetch(
            MassiveDataset.STOCK_SNAPSHOTS, self.database_flow.universe
        )
        posture = snapshot.posture
        reasons = [f"snapshot:{snapshot.reason}"]
        date_cursor = wake_at.date().isoformat()
        previous = (
            self.massive_daily_cursor.load()
            if self.massive_daily_cursor is not None
            else None
        )
        if previous != date_cursor and posture == "healthy":
            daily = self.massive_adapter.fetch(
                MassiveDataset.DAILY_BARS, self.database_flow.universe
            )
            reasons.append(f"daily:{daily.reason}")
            if daily.posture == "healthy" and self.massive_daily_cursor is not None:
                self.massive_daily_cursor.save(date_cursor)
            elif daily.posture != "healthy":
                posture = daily.posture
        return posture, ";".join(reasons)
