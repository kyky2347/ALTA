from psycopg.types.json import Jsonb

from .b4_runtime import _event, _insert_event
from .database import Database
from .foundry import OpportunityDraft, canonical_hash
from .ranking import RankingBook


class RankingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def persist(
        self,
        book: RankingBook,
        opportunities: tuple[OpportunityDraft, ...],
    ) -> None:
        by_id = {item.opportunity_id: item for item in opportunities}
        with self.database.connect() as connection:
            for item in book.items:
                opportunity = by_id[item.opportunity_id]
                connection.execute(
                    """INSERT INTO research.rank
                    (id, environment, version, known_at, opportunity_id, book,
                     position, score, ranking_run_id, snapshot_hash,
                     horizon_min_days, horizon_max_days, components, gate_status,
                     reason_codes)
                    VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ranked',%s)
                    ON CONFLICT (id) DO NOTHING""",
                    (
                        item.rank_id,
                        opportunity.environment.value,
                        book.known_at,
                        item.opportunity_id,
                        book.book,
                        item.position,
                        item.score,
                        book.ranking_run_id,
                        item.snapshot_hash,
                        book.horizon_min_days,
                        book.horizon_max_days,
                        Jsonb(item.components),
                        [],
                    ),
                )
                connection.execute(
                    "UPDATE research.opportunity SET status = 'ranked' WHERE id = %s",
                    (item.opportunity_id,),
                )
            for gate in book.gates:
                if gate.status == "ranked":
                    continue
                opportunity = by_id[gate.opportunity_id]
                event_id = (
                    "event_"
                    + canonical_hash(
                        [book.ranking_run_id, gate.opportunity_id, gate.status]
                    )[:32]
                )
                _insert_event(
                    connection,
                    _event(
                        event_id=event_id,
                        environment=opportunity.environment,
                        known_at=book.known_at,
                        aggregate_type="opportunity",
                        aggregate_id=gate.opportunity_id,
                        event_type=f"ranking.gate.{gate.status}",
                        payload={
                            "book": book.book,
                            "ranking_run_id": book.ranking_run_id,
                            "reason_codes": gate.reason_codes,
                        },
                    ),
                )
