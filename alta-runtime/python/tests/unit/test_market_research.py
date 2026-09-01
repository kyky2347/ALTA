from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alta_asterism.market_research import build_market_research_agenda


WAKE_AT = datetime(2026, 8, 24, 15, tzinfo=UTC)


def _bar(
    symbol: str,
    day_offset: int,
    close: Decimal,
    *,
    volume: Decimal = Decimal("1000000"),
    known_at: datetime | None = None,
    open_price: Decimal | None = None,
    session_days_ago: int | None = None,
) -> tuple:
    session = WAKE_AT.date() - timedelta(
        days=(6 - day_offset if session_days_ago is None else session_days_ago)
    )
    open_price = open_price or close * Decimal("0.995")
    return (
        f"raw_{symbol}_{day_offset}",
        f"{day_offset + 1:064x}"[-64:],
        known_at or WAKE_AT - timedelta(minutes=max(1, 60 - day_offset)),
        {
            "semanticTimes": {
                "eventAt": datetime.combine(
                    session, datetime.min.time(), tzinfo=UTC
                ).isoformat()
            },
            "payload": {
                "symbol": symbol,
                "aggregate": {
                    "open": str(open_price),
                    "high": str(max(open_price, close) * Decimal("1.01")),
                    "low": str(min(open_price, close) * Decimal("0.99")),
                    "close": str(close),
                    "volume": str(volume),
                },
            },
        },
    )


def _history(
    symbol: str, closes: tuple[int, ...], *, last_volume: int = 1_000_000
) -> tuple[tuple, ...]:
    return tuple(
        _bar(
            symbol,
            index,
            Decimal(close),
            volume=Decimal(last_volume if index == len(closes) - 1 else 1_000_000),
            session_days_ago=len(closes) - index,
        )
        for index, close in enumerate(closes)
    )


def test_completed_bar_screen_builds_bounded_orthogonal_research_funnel() -> None:
    universe = ("SPY", "AAPL", "MSFT", "NVDA", "XOM", "JPM", "LLY")
    rows = (
        *_history("SPY", (100, 101, 101, 102, 102, 103)),
        *_history("AAPL", (100, 100, 100, 100, 101, 112), last_volume=3_000_000),
        *_history("MSFT", (100, 100, 101, 101, 102, 103)),
        *_history("NVDA", (100, 99, 98, 97, 96, 91)),
        *_history("XOM", (100, 101, 102, 103, 104, 107)),
        *_history("JPM", (100, 100, 99, 99, 98, 97)),
        *_history("LLY", (100, 101, 101, 100, 100, 101)),
    )

    agenda = build_market_research_agenda(
        rows=rows, universe=universe, known_at=WAKE_AT
    )
    repeated = build_market_research_agenda(
        rows=tuple(reversed(rows)), universe=universe, known_at=WAKE_AT
    )

    assert agenda == repeated
    assert agenda.posture == "screen_ready"
    assert agenda.benchmark_symbol == "SPY"
    assert agenda.completed_sessions == 6
    assert len(agenda.seeds) == 4
    assert {item.assigned_scout_id for item in agenda.seeds} == {
        "change_event_scout",
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
    }
    assert all(
        any("not Evidence" in test for test in item.required_tests)
        for item in agenda.seeds
    )
    market = agenda.for_scout("market_dislocation_scout")
    assert len(market.seeds) == 1
    assert market.seeds[0].observations[0].completed_session < WAKE_AT.date()
    assert market.snapshot_hash == agenda.snapshot_hash


def test_current_session_and_future_known_bars_cannot_change_frozen_screen() -> None:
    universe = ("SPY", "AAPL")
    completed = (
        *_history("SPY", (100, 100, 100, 100, 100, 100)),
        *_history("AAPL", (100, 100, 100, 100, 100, 110), last_volume=3_000_000),
    )
    current_session = _bar("AAPL", 6, Decimal("500"), volume=Decimal("9000000"))
    future_known = _bar(
        "AAPL",
        5,
        Decimal("900"),
        known_at=WAKE_AT + timedelta(seconds=1),
    )

    baseline = build_market_research_agenda(
        rows=completed, universe=universe, known_at=WAKE_AT
    )
    guarded = build_market_research_agenda(
        rows=(*completed, current_session, future_known),
        universe=universe,
        known_at=WAKE_AT,
    )

    assert guarded == baseline


def test_thin_history_is_visible_but_cannot_manufacture_a_seed() -> None:
    agenda = build_market_research_agenda(
        rows=_history("SPY", (100, 101, 102)),
        universe=("SPY",),
        known_at=WAKE_AT,
    )

    assert agenda.posture == "thin_history"
    assert agenda.completed_sessions == 3
    assert agenda.seeds == ()


def test_quiet_persistent_drift_gets_volatility_normalized_expectation_work() -> None:
    universe = ("SPY", "AAPL")
    rows = (
        *_history("SPY", tuple(100 for _ in range(21))),
        *_history(
            "AAPL",
            (
                *tuple(100 for _ in range(16)),
                101,
                102,
                104,
                106,
                108,
            ),
        ),
    )

    agenda = build_market_research_agenda(
        rows=rows, universe=universe, known_at=WAKE_AT
    )
    seed = agenda.for_scout("expectation_gap_scout").seeds[0]
    observation = seed.observations[0]

    assert agenda.version == "alta-market-research-agenda-v2"
    assert agenda.completed_sessions == 21
    assert seed.screen_type == "persistent_expectation_drift"
    assert observation.relative_five_day_surprise is not None
    assert observation.relative_five_day_surprise >= Decimal("4")
    assert observation.one_day_surprise is not None
    assert "accumulating evidence" in seed.research_question


def test_price_discovery_is_decomposed_into_overnight_and_intraday_moves() -> None:
    history = list(_history("AAPL", (100, 100, 100, 100, 100, 110)))
    latest = _bar(
        "AAPL",
        5,
        Decimal("110"),
        open_price=Decimal("108"),
        session_days_ago=1,
    )
    history[-1] = latest
    rows = (
        *_history("SPY", (100, 100, 100, 100, 100, 100)),
        *history,
    )

    agenda = build_market_research_agenda(
        rows=rows, universe=("SPY", "AAPL"), known_at=WAKE_AT
    )
    observation = agenda.for_scout("market_dislocation_scout").seeds[0].observations[0]

    assert observation.overnight_gap_bps == Decimal("800.00")
    assert observation.intraday_return_bps == Decimal("185.19")
