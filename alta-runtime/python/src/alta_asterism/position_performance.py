from datetime import UTC, datetime
from decimal import Decimal

from .b5_runtime import _append_event, _contract_event
from .contracts import Environment
from .database import Database
from .market_data import MassiveMarketData
from .shadow import PositionThesis


class PositionPerformanceRecorder:
    """Persists benchmark-relative, cost-adjusted Shadow results."""

    def __init__(
        self, database: Database, market_data: MassiveMarketData | None
    ) -> None:
        self.database = database
        self.market_data = market_data

    def record_benchmark(self, position_id: str, expression_id: str) -> None:
        if self.market_data is None:
            return
        quote = self.market_data.quote("etf", "SPY")
        if quote is None:
            return
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="position.benchmark.open",
                    aggregate_type="shadow_position",
                    aggregate_id=position_id,
                    environment=Environment.SHADOW,
                    known_at=quote.known_at,
                    payload={
                        "symbol": "SPY",
                        "midpoint": str((quote.bid + quote.ask) / Decimal(2)),
                        "quote": quote.model_dump(mode="json"),
                    },
                    correlation_id=expression_id,
                ),
            )

    def record_result(
        self,
        thesis: PositionThesis,
        entry_price: Decimal,
        entry_commission: Decimal,
        exit_price: Decimal,
        exit_commission: Decimal,
        quantity: Decimal,
    ) -> None:
        entry_value = entry_price * quantity
        gross_pnl = (exit_price - entry_price) * quantity
        net_pnl = gross_pnl - entry_commission - exit_commission
        gross_return_bps = gross_pnl / entry_value * Decimal(10_000)
        net_return_bps = net_pnl / entry_value * Decimal(10_000)
        benchmark_return_bps = None
        benchmark_close = (
            self.market_data.quote("etf", "SPY") if self.market_data else None
        )
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT payload FROM ops.event WHERE aggregate_id = %s
                AND event_type = 'position.benchmark.open'
                ORDER BY sequence DESC LIMIT 1""",
                (thesis.position_id,),
            ).fetchone()
            if row is not None and benchmark_close is not None:
                benchmark_open = Decimal(row[0]["midpoint"])
                close_midpoint = (benchmark_close.bid + benchmark_close.ask) / Decimal(
                    2
                )
                benchmark_return_bps = (
                    (close_midpoint - benchmark_open) / benchmark_open * Decimal(10_000)
                )
            alpha_bps = (
                net_return_bps - benchmark_return_bps
                if benchmark_return_bps is not None
                else None
            )
            payload = {
                "position_id": thesis.position_id,
                "opportunity_id": thesis.binding.opportunity_id,
                "gross_pnl": str(gross_pnl),
                "net_pnl": str(net_pnl),
                "gross_return_bps": str(gross_return_bps),
                "net_return_bps": str(net_return_bps),
                "benchmark_symbol": "SPY",
                "benchmark_return_bps": (
                    str(benchmark_return_bps)
                    if benchmark_return_bps is not None
                    else None
                ),
                "realized_alpha_bps": (
                    str(alpha_bps) if alpha_bps is not None else None
                ),
                "cost_adjusted": True,
                "alpha_contributors": [
                    item.model_dump(mode="json") for item in thesis.alpha_contributors
                ],
                "thesis_pillar_ids": [item.pillar_id for item in thesis.thesis_pillars],
            }
            _append_event(
                connection,
                _contract_event(
                    event_type="position.performance.measured",
                    aggregate_type="shadow_position",
                    aggregate_id=thesis.position_id,
                    environment=Environment.SHADOW,
                    known_at=datetime.now(UTC),
                    payload=payload,
                    correlation_id=thesis.binding.opportunity_id,
                ),
            )
