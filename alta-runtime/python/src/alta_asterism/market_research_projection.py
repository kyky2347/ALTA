from datetime import datetime

from .contracts import Environment
from .database import Database
from .market_research import MarketResearchAgenda, build_market_research_agenda

_MAX_RAW_ROWS = 5_000


class MarketResearchAgendaProjector:
    """Point-in-time persistence edge for the pure completed-bar screen."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def at(
        self,
        environment: Environment,
        universe: tuple[str, ...],
        known_at: datetime,
    ) -> MarketResearchAgenda:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, content_hash, known_at, body
                FROM research.raw
                WHERE environment = %s AND source = 'massive' AND known_at <= %s
                  AND source_key LIKE 'daily:%%'
                  AND body->'payload'->>'symbol' = ANY(%s)
                ORDER BY known_at DESC, id DESC LIMIT %s""",
                (environment.value, known_at, list(universe), _MAX_RAW_ROWS),
            ).fetchall()
        return build_market_research_agenda(
            rows=tuple(rows), universe=universe, known_at=known_at
        )
