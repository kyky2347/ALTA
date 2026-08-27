from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from alta_asterism.ingest import SourceEnvelope
from alta_asterism.market_data import MassiveMarketData
from alta_asterism.massive import (
    CapturedMassiveRecord,
    MassiveAccessMode,
    MassiveResult,
)


NOW = datetime(2026, 8, 23, 15, tzinfo=UTC)


def captured(
    payload: dict,
    record_id: str,
    *,
    event_at: datetime = NOW,
    known_at: datetime = NOW,
) -> CapturedMassiveRecord:
    envelope = SourceEnvelope(
        source_id="massive",
        source_record_id=record_id,
        channel="rest",
        payload=payload,
        received_at=known_at,
        semantic_event_at=event_at,
    )
    return CapturedMassiveRecord(
        envelope=envelope,
        raw_id=f"raw_{record_id}",
        raw_version=1,
        content_hash="a" * 64,
        known_at=known_at,
    )


class FakeAdapter:
    result = MassiveResult(MassiveAccessMode.DEDICATED, "healthy", "fixture")

    def capture(self, _dataset, symbols):
        symbol = symbols[0]
        return SimpleNamespace(
            result=self.result,
            records=(
                captured(
                    {
                        "symbol": symbol,
                        "snapshot": {
                            "last_quote": {"bid_price": 99.9, "ask_price": 100.0},
                            "day": {"volume": 2_000_000},
                        },
                    },
                    f"stock:{symbol}",
                ),
            ),
        )

    def capture_option_chain(self, query):
        return SimpleNamespace(
            result=self.result,
            records=(
                captured(
                    {
                        "underlying_symbol": query.underlying_symbol,
                        "option_snapshot": {
                            "details": {
                                "ticker": "SPY260918C00500000",
                                "contract_type": "call",
                                "expiration_date": "2026-09-18",
                                "strike_price": 500,
                            },
                            "last_quote": {"bid": 9.8, "ask": 10.2},
                            "greeks": {"delta": 0.5},
                            "open_interest": 1000,
                        },
                    },
                    "option:SPY260918C00500000",
                ),
            ),
        )


def test_massive_market_data_sizes_equity_and_selects_liquid_option() -> None:
    market = MassiveMarketData(FakeAdapter(), clock=lambda: NOW)

    equity = market.equity(
        "etf",
        "SH",
        underlying_symbol="SPY",
        metadata={"daily_target": "-1x", "path_dependency": "daily_reset"},
    )
    option = market.option("SPY", "positive", 21)

    assert equity.instrument is not None
    assert equity.instrument.quantity == 100
    assert equity.instrument.symbol == "SH"
    assert equity.instrument.underlying_symbol == "SPY"
    assert equity.instrument.metadata == {
        "notional_limit": "10000",
        "observed_day_volume": "2000000",
        "observed_day_dollar_volume": "199900000.00",
        "daily_target": "-1x",
        "path_dependency": "daily_reset",
    }
    assert option.instrument is not None
    assert option.instrument.kind == "option"
    assert option.instrument.quantity == 500
    assert option.instrument.metadata["contracts"] == 5


def test_forward_quote_polls_until_exchange_and_known_times_follow_intent() -> None:
    class SequencedAdapter(FakeAdapter):
        def __init__(self) -> None:
            self.calls = 0

        def capture(self, _dataset, symbols):
            symbol = symbols[0]
            offset = self.calls
            self.calls += 1
            event_at = NOW + timedelta(seconds=offset)
            known_at = event_at + timedelta(milliseconds=700)
            return SimpleNamespace(
                result=self.result,
                records=(
                    captured(
                        {
                            "symbol": symbol,
                            "snapshot": {
                                "last_quote": {
                                    "bid_price": 99.9,
                                    "ask_price": 100.0,
                                }
                            },
                        },
                        f"stock:{symbol}:{offset}",
                        event_at=event_at,
                        known_at=known_at,
                    ),
                ),
            )

    adapter = SequencedAdapter()
    sleeps = []
    market = MassiveMarketData(
        adapter,
        forward_quote_timeout_seconds=1,
        forward_quote_poll_seconds=0.5,
        sleeper=sleeps.append,
    )

    quote = market.forward_quote(
        "stock",
        "SPY",
        committed_at=NOW,
        frozen_latency_ms=500,
    )

    assert quote is not None
    assert (quote.as_of, quote.known_at) == (
        NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=1, milliseconds=700),
    )
    assert adapter.calls == 2
    assert sleeps == [0.5]
