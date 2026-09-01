import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from statistics import median
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .expression_base import FrozenContract

_BPS = Decimal(10_000)
_METRIC_QUANTUM = Decimal("0.01")
_RATIO_QUANTUM = Decimal("0.001")
_SURPRISE_QUANTUM = Decimal("0.01")
_MAX_BARS_PER_SYMBOL = 24
_MINIMUM_ROBUST_RETURNS = 4
_ROBUST_SIGMA_FLOOR_BPS = Decimal(35)

MarketScreenType = Literal[
    "price_volume_dislocation",
    "relative_dislocation",
    "volatility_adjusted_dislocation",
    "persistent_expectation_drift",
    "range_expansion",
    "breadth_dispersion",
]


class MarketScreenObservation(FrozenContract):
    """Point-in-time screen output; it is a research locator, not Evidence."""

    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,15}$")
    completed_session: date
    one_day_return_bps: Decimal
    five_day_return_bps: Decimal | None = None
    benchmark_relative_five_day_bps: Decimal | None = None
    volume_ratio: Decimal | None = Field(default=None, ge=0, le=100)
    range_ratio: Decimal | None = Field(default=None, ge=0, le=100)
    overnight_gap_bps: Decimal | None = None
    intraday_return_bps: Decimal | None = None
    return_volatility_bps: Decimal | None = Field(default=None, ge=0)
    one_day_surprise: Decimal | None = Field(default=None, ge=0, le=50)
    relative_five_day_surprise: Decimal | None = Field(default=None, ge=0, le=50)


class MarketResearchSeed(FrozenContract):
    """A bounded anomaly question assigned to one orthogonal Trader Mind."""

    seed_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    screen_type: MarketScreenType
    assigned_scout_id: Literal[
        "change_event_scout",
        "market_dislocation_scout",
        "causal_policy_scout",
        "expectation_gap_scout",
    ]
    symbols: tuple[str, ...] = Field(min_length=1, max_length=4)
    priority_score: Decimal = Field(ge=0, le=1)
    observations: tuple[MarketScreenObservation, ...] = Field(
        min_length=1, max_length=4
    )
    research_question: str = Field(min_length=10, max_length=360)
    first_rejection: str = Field(min_length=10, max_length=260)
    required_tests: tuple[str, ...] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def observations_match_symbols(self) -> "MarketResearchSeed":
        observed = tuple(item.symbol for item in self.observations)
        if len(observed) != len(set(observed)) or not set(observed).issubset(
            self.symbols
        ):
            raise ValueError(
                "market screen observations must match unique seed symbols"
            )
        return self


class MarketResearchAgenda(FrozenContract):
    """Frozen screen funnel that directs verification without creating a fact."""

    version: Literal[
        "alta-market-research-agenda-v1", "alta-market-research-agenda-v2"
    ] = "alta-market-research-agenda-v2"
    known_at: datetime
    posture: Literal["unavailable", "thin_history", "screen_ready"]
    benchmark_symbol: str | None = Field(
        default=None, pattern=r"^[A-Z0-9][A-Z0-9.-]{0,15}$"
    )
    completed_sessions: int = Field(ge=0, le=_MAX_BARS_PER_SYMBOL)
    seeds: tuple[MarketResearchSeed, ...] = Field(default=(), max_length=4)
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("market research agenda known_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def seeds_are_unique_and_consistent(self) -> "MarketResearchAgenda":
        ids = tuple(item.seed_id for item in self.seeds)
        scouts = tuple(item.assigned_scout_id for item in self.seeds)
        if len(ids) != len(set(ids)):
            raise ValueError("market research seed IDs must be unique")
        if len(scouts) != len(set(scouts)):
            raise ValueError("one market research seed may be assigned per Trader Mind")
        if self.posture != "screen_ready" and self.seeds:
            raise ValueError("thin or unavailable market history cannot create seeds")
        return self

    def for_scout(self, scout_id: str) -> "MarketResearchAgenda":
        return self.model_copy(
            update={
                "seeds": tuple(
                    item for item in self.seeds if item.assigned_scout_id == scout_id
                )
            }
        )


@dataclass(frozen=True)
class _CompletedBar:
    raw_id: str
    content_hash: str
    known_at: datetime
    symbol: str
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class _ScreenMetrics:
    observation: MarketScreenObservation
    relative_strength: Decimal
    price_volume_strength: Decimal
    range_strength: Decimal
    one_day_surprise_strength: Decimal
    relative_surprise_strength: Decimal
    persistent_drift_strength: Decimal


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _field(value: dict[str, Any], long_name: str, short_name: str) -> Decimal | None:
    return _decimal(value.get(long_name, value.get(short_name)))


def _parse_bar(row: tuple[Any, ...], known_at: datetime) -> _CompletedBar | None:
    raw_id, content_hash, row_known_at, body = row
    if not isinstance(body, dict) or row_known_at > known_at:
        return None
    payload = body.get("payload")
    times = body.get("semanticTimes")
    if not isinstance(payload, dict) or not isinstance(times, dict):
        return None
    symbol = payload.get("symbol")
    aggregate = payload.get("aggregate")
    event_at = times.get("eventAt")
    if not isinstance(symbol, str) or not isinstance(aggregate, dict) or not event_at:
        return None
    try:
        bar_at = datetime.fromisoformat(str(event_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if bar_at.tzinfo is None or bar_at.utcoffset() is None:
        return None
    session = bar_at.date()
    if session >= known_at.date():
        return None
    open_price = _field(aggregate, "open", "o")
    high = _field(aggregate, "high", "h")
    low = _field(aggregate, "low", "l")
    close = _field(aggregate, "close", "c")
    volume = _field(aggregate, "volume", "v")
    if (
        None in (open_price, high, low, close, volume)
        or min(open_price, high, low, close) <= 0
        or volume < 0
        or high < low
    ):
        return None
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        return None
    return _CompletedBar(
        raw_id=str(raw_id),
        content_hash=str(content_hash),
        known_at=row_known_at,
        symbol=normalized_symbol,
        session=session,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _completed_history(
    rows: tuple[tuple[Any, ...], ...], universe: tuple[str, ...], known_at: datetime
) -> dict[str, tuple[_CompletedBar, ...]]:
    allowed = set(universe)
    by_symbol_date: dict[tuple[str, date], _CompletedBar] = {}
    for row in rows:
        bar = _parse_bar(row, known_at)
        if bar is None or bar.symbol not in allowed:
            continue
        key = (bar.symbol, bar.session)
        current = by_symbol_date.get(key)
        if current is None or (bar.known_at, bar.raw_id) > (
            current.known_at,
            current.raw_id,
        ):
            by_symbol_date[key] = bar
    histories: dict[str, tuple[_CompletedBar, ...]] = {}
    for symbol in universe:
        history = sorted(
            (
                bar
                for (item_symbol, _), bar in by_symbol_date.items()
                if item_symbol == symbol
            ),
            key=lambda item: (item.session, item.known_at, item.raw_id),
        )[-_MAX_BARS_PER_SYMBOL:]
        if history:
            histories[symbol] = tuple(history)
    return histories


def _bps(latest: Decimal, earlier: Decimal) -> Decimal:
    return ((latest / earlier - Decimal(1)) * _BPS).quantize(
        _METRIC_QUANTUM, rounding=ROUND_HALF_EVEN
    )


def _ratio(latest: Decimal, history: tuple[Decimal, ...]) -> Decimal | None:
    positive = tuple(value for value in history if value > 0)
    if not positive:
        return None
    baseline = Decimal(str(median(positive)))
    if baseline <= 0:
        return None
    return (latest / baseline).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)


def _return_series(history: tuple[_CompletedBar, ...]) -> tuple[Decimal, ...]:
    return tuple(
        _bps(current.close, previous.close)
        for previous, current in zip(history, history[1:], strict=False)
        if previous.close > 0
    )


def _robust_surprise(
    value: Decimal, history: tuple[Decimal, ...]
) -> tuple[Decimal | None, Decimal | None]:
    """Return a robust z-like surprise and its historical sigma in bps."""

    if len(history) < _MINIMUM_ROBUST_RETURNS:
        return None, None
    center = Decimal(str(median(history)))
    deviations = tuple(abs(item - center) for item in history)
    median_absolute_deviation = Decimal(str(median(deviations)))
    robust_sigma = max(
        _ROBUST_SIGMA_FLOOR_BPS,
        median_absolute_deviation * Decimal("1.4826"),
    )
    surprise = min(Decimal(50), abs(value - center) / robust_sigma).quantize(
        _SURPRISE_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    return surprise, robust_sigma.quantize(_METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _relative_return_history(
    history: tuple[_CompletedBar, ...], benchmark: tuple[_CompletedBar, ...]
) -> tuple[Decimal, ...]:
    benchmark_by_date = {item.session: item for item in benchmark}
    relative: list[Decimal] = []
    for previous, current in zip(history, history[1:], strict=False):
        benchmark_previous = benchmark_by_date.get(previous.session)
        benchmark_current = benchmark_by_date.get(current.session)
        if benchmark_previous is None or benchmark_current is None:
            continue
        relative.append(
            _bps(current.close, previous.close)
            - _bps(benchmark_current.close, benchmark_previous.close)
        )
    return tuple(relative)


def _metrics(
    history: tuple[_CompletedBar, ...], benchmark: tuple[_CompletedBar, ...] | None
) -> _ScreenMetrics | None:
    if len(history) < 6:
        return None
    recent = history[-1]
    previous = history[-2]
    one_day = _bps(recent.close, previous.close)
    five_day = _bps(recent.close, history[-6].close)
    overnight_gap = _bps(recent.open, previous.close)
    intraday_return = _bps(recent.close, recent.open)
    benchmark_relative = None
    if benchmark is not None and len(benchmark) >= 6:
        benchmark_by_date = {item.session: item for item in benchmark}
        start = benchmark_by_date.get(history[-6].session)
        end = benchmark_by_date.get(recent.session)
        if start is not None and end is not None:
            benchmark_relative = five_day - _bps(end.close, start.close)
    prior_returns = _return_series(history[:-1])[-15:]
    one_day_surprise, return_volatility = _robust_surprise(one_day, prior_returns)
    relative_five_day_surprise = None
    if benchmark is not None and benchmark_relative is not None:
        relative_returns = _relative_return_history(history[:-1], benchmark)[-15:]
        if len(relative_returns) >= _MINIMUM_ROBUST_RETURNS:
            relative_center = Decimal(str(median(relative_returns))) * Decimal(5)
            _, daily_sigma = _robust_surprise(
                benchmark_relative / Decimal(5), relative_returns
            )
            if daily_sigma is not None:
                five_day_sigma = daily_sigma * Decimal(5).sqrt()
                relative_five_day_surprise = min(
                    Decimal(50),
                    abs(benchmark_relative - relative_center) / five_day_sigma,
                ).quantize(_SURPRISE_QUANTUM, rounding=ROUND_HALF_EVEN)
    prior = history[-6:-1]
    volume_ratio = _ratio(recent.volume, tuple(item.volume for item in prior))
    recent_range = (recent.high - recent.low) / previous.close
    prior_ranges = tuple(
        (item.high - item.low) / item.open for item in prior if item.open > 0
    )
    range_ratio = _ratio(recent_range, prior_ranges)
    observation = MarketScreenObservation(
        symbol=recent.symbol,
        completed_session=recent.session,
        one_day_return_bps=one_day,
        five_day_return_bps=five_day,
        benchmark_relative_five_day_bps=benchmark_relative,
        volume_ratio=volume_ratio,
        range_ratio=range_ratio,
        overnight_gap_bps=overnight_gap,
        intraday_return_bps=intraday_return,
        return_volatility_bps=return_volatility,
        one_day_surprise=one_day_surprise,
        relative_five_day_surprise=relative_five_day_surprise,
    )
    relative_basis = abs(
        benchmark_relative if benchmark_relative is not None else five_day
    )
    relative_strength = min(Decimal(1), relative_basis / Decimal(600))
    price_move_strength = min(Decimal(1), abs(one_day) / Decimal(350))
    volume_strength = min(
        Decimal(1),
        max(Decimal(0), (volume_ratio or Decimal(1)) - Decimal(1)) / Decimal(2),
    )
    range_strength = min(
        Decimal(1),
        max(Decimal(0), (range_ratio or Decimal(1)) - Decimal(1)) / Decimal(2),
    )
    one_day_surprise_strength = min(
        Decimal(1), (one_day_surprise or Decimal(0)) / Decimal(4)
    )
    relative_surprise_strength = min(
        Decimal(1), (relative_five_day_surprise or Decimal(0)) / Decimal(4)
    )
    drift_share = (
        max(
            Decimal(0),
            min(
                Decimal(1),
                (abs(benchmark_relative) - abs(one_day)) / abs(benchmark_relative),
            ),
        )
        if benchmark_relative not in (None, Decimal(0))
        else Decimal(0)
    )
    persistent_drift_strength = (
        relative_surprise_strength * Decimal("0.70") + drift_share * Decimal("0.30")
        if drift_share >= Decimal("0.55")
        else Decimal(0)
    )
    return _ScreenMetrics(
        observation=observation,
        relative_strength=relative_strength,
        price_volume_strength=(
            price_move_strength * Decimal("0.70") + volume_strength * Decimal("0.30")
        ),
        range_strength=(
            price_move_strength * Decimal("0.55") + range_strength * Decimal("0.45")
        ),
        one_day_surprise_strength=one_day_surprise_strength,
        relative_surprise_strength=relative_surprise_strength,
        persistent_drift_strength=persistent_drift_strength,
    )


def _score(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(1), value)).quantize(
        _RATIO_QUANTUM, rounding=ROUND_HALF_EVEN
    )


def _seed_id(
    screen_type: MarketScreenType,
    scout_id: str,
    observations: tuple[MarketScreenObservation, ...],
) -> str:
    identity = [
        screen_type,
        scout_id,
        [[item.symbol, item.completed_session.isoformat()] for item in observations],
    ]
    return hashlib.sha256(
        json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()[:16]


def _single_symbol_seed(
    *,
    screen_type: MarketScreenType,
    scout_id: Literal[
        "change_event_scout",
        "market_dislocation_scout",
        "expectation_gap_scout",
    ],
    metrics: _ScreenMetrics,
    score: Decimal,
    benchmark_symbol: str | None,
) -> MarketResearchSeed:
    item = metrics.observation
    comparison = benchmark_symbol or "its liquid peer set"
    if screen_type == "price_volume_dislocation":
        question = f"Why did {item.symbol} move with abnormal completed-session volume, and is the cause a new operating fact whose earnings or cash-flow effect is still propagating?"
        rejection = "Reject first if the move is only broad beta, stale/partial data, rebalance flow, or a fully disclosed fact already reflected in expectations."
    elif screen_type == "relative_dislocation":
        question = f"What explains {item.symbol}'s five-session gap versus {comparison}, what is already priced in, and is there a falsifiable fundamental or forced-flow wedge?"
        rejection = "Reject first if the gap is explained by factor exposure, benchmark composition, illiquidity, or a denominator/expectation reset that the screen does not observe."
    elif screen_type == "volatility_adjusted_dislocation":
        question = f"Why is {item.symbol}'s completed-session move unusual relative to its own prior volatility, how much occurred overnight versus intraday, and is there a new causal fact rather than a volatility-regime change?"
        rejection = "Reject first if the normalized surprise comes from a split, bad bar, volatility-regime break, illiquidity, broad factor shock, or an already-absorbed disclosure."
    elif screen_type == "persistent_expectation_drift":
        question = f"What accumulating evidence explains {item.symbol}'s persistent five-session gap versus {comparison}, and is a quiet estimate, operating, positioning, or forced-flow change still under-reflected?"
        rejection = "Reject first if the drift is ordinary factor exposure, sector momentum, stale pricing, repeated public information, or lacks a measurable estimate or cash-flow resolution path."
    else:
        question = f"What caused {item.symbol}'s completed-session range expansion, and does primary evidence support a time-bounded information transition rather than noise?"
        rejection = "Reject first if the range comes from an incomplete bar, ordinary market volatility, a mechanical adjustment, or no identifiable causal path."
    observations = (item,)
    return MarketResearchSeed(
        seed_id=_seed_id(screen_type, scout_id, observations),
        screen_type=screen_type,
        assigned_scout_id=scout_id,
        symbols=(item.symbol,),
        priority_score=_score(score),
        observations=observations,
        research_question=question,
        first_rejection=rejection,
        required_tests=(
            "Re-fetch current market data and verify the completed-bar anomaly and liquidity.",
            "Find a primary or independently cross-checked causal source; the screen itself is not Evidence.",
            "Test the strongest factor, flow, and consensus-correct rival; compare the move with frozen volatility history and decompose overnight from intraday price discovery because the normalized score is only a locator.",
        ),
    )


def _breadth_seed(
    metrics: tuple[_ScreenMetrics, ...], benchmark_symbol: str | None
) -> MarketResearchSeed | None:
    if len(metrics) < 5:
        return None
    observations = tuple(
        item.observation
        for item in sorted(
            metrics,
            key=lambda value: (
                -abs(value.observation.five_day_return_bps or Decimal(0)),
                value.observation.symbol,
            ),
        )[:4]
    )
    returns = tuple(item.observation.five_day_return_bps for item in metrics)
    clean_returns = tuple(value for value in returns if value is not None)
    if len(clean_returns) < 5:
        return None
    center = sum(clean_returns, Decimal(0)) / Decimal(len(clean_returns))
    dispersion = (
        sum((value - center) ** 2 for value in clean_returns)
        / Decimal(len(clean_returns))
    ).sqrt()
    positive_fraction = Decimal(sum(value > 0 for value in clean_returns)) / Decimal(
        len(clean_returns)
    )
    breadth_extreme = abs(positive_fraction - Decimal("0.5")) * Decimal(2)
    strength = max(min(Decimal(1), dispersion / Decimal(500)), breadth_extreme)
    if strength < Decimal("0.45"):
        return None
    symbols = tuple(item.symbol for item in observations)
    comparison = benchmark_symbol or "the investable universe"
    return MarketResearchSeed(
        seed_id=_seed_id("breadth_dispersion", "causal_policy_scout", observations),
        screen_type="breadth_dispersion",
        assigned_scout_id="causal_policy_scout",
        symbols=symbols,
        priority_score=_score(strength),
        observations=observations,
        research_question=(
            f"What common policy, macro, input-cost, or supply-chain transmission explains the widening completed-session dispersion around {comparison}, and which issuer exposure is least priced?"
        ),
        first_rejection=(
            "Reject first if the cross-section is explained by ordinary factor loadings, sector composition, stale bars, or no issuer-level transmission path."
        ),
        required_tests=(
            "Verify breadth and relative moves with current finance data; the screen itself is not Evidence.",
            "Trace the proposed driver from an official or primary source to issuer-level exposure and timing.",
            "Test a sector/factor-neutral rival explanation and identify the next observable resolution point.",
        ),
    )


def build_market_research_agenda(
    *,
    rows: tuple[tuple[Any, ...], ...],
    universe: tuple[str, ...],
    known_at: datetime,
) -> MarketResearchAgenda:
    """Builds a deterministic completed-bar screen that never becomes Evidence."""

    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("market research known_at must be timezone-aware")
    histories = _completed_history(rows, universe, known_at)
    snapshot_rows = tuple(
        (bar.raw_id, bar.content_hash, bar.known_at.isoformat())
        for symbol in universe
        for bar in histories.get(symbol, ())
    )
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_rows, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    completed_sessions = max((len(value) for value in histories.values()), default=0)
    if not histories:
        return MarketResearchAgenda(
            known_at=known_at,
            posture="unavailable",
            completed_sessions=0,
            snapshot_hash=snapshot_hash,
        )
    benchmark_symbol = "SPY" if "SPY" in histories else None
    benchmark = histories.get(benchmark_symbol) if benchmark_symbol else None
    metrics = tuple(
        value
        for symbol in universe
        if symbol != benchmark_symbol
        and (value := _metrics(histories.get(symbol, ()), benchmark)) is not None
    )
    if not metrics:
        return MarketResearchAgenda(
            known_at=known_at,
            posture="thin_history",
            benchmark_symbol=benchmark_symbol,
            completed_sessions=completed_sessions,
            snapshot_hash=snapshot_hash,
        )

    seeds: list[MarketResearchSeed] = []
    strongest_market = max(
        metrics,
        key=lambda item: (
            item.relative_strength
            + item.price_volume_strength
            + item.range_strength
            + item.one_day_surprise_strength
            + item.relative_surprise_strength,
            item.observation.symbol,
        ),
    )
    market_score = max(
        strongest_market.relative_strength,
        strongest_market.price_volume_strength,
        strongest_market.range_strength,
        strongest_market.one_day_surprise_strength,
        strongest_market.relative_surprise_strength,
    )
    if market_score >= Decimal("0.40"):
        market_type: MarketScreenType
        if strongest_market.relative_surprise_strength == market_score:
            market_type = "volatility_adjusted_dislocation"
        elif strongest_market.one_day_surprise_strength == market_score:
            market_type = "volatility_adjusted_dislocation"
        elif strongest_market.relative_strength == market_score:
            market_type = "relative_dislocation"
        elif strongest_market.price_volume_strength == market_score:
            market_type = "price_volume_dislocation"
        else:
            market_type = "range_expansion"
        seeds.append(
            _single_symbol_seed(
                screen_type=market_type,
                scout_id="market_dislocation_scout",
                metrics=strongest_market,
                score=market_score,
                benchmark_symbol=benchmark_symbol,
            )
        )

    change_candidates = tuple(
        item
        for item in metrics
        if (item.observation.volume_ratio or Decimal(0)) >= Decimal("1.4")
        and abs(item.observation.one_day_return_bps) >= Decimal(150)
    )
    if change_candidates:
        strongest_change = max(
            change_candidates,
            key=lambda item: (item.price_volume_strength, item.observation.symbol),
        )
        seeds.append(
            _single_symbol_seed(
                screen_type="price_volume_dislocation",
                scout_id="change_event_scout",
                metrics=strongest_change,
                score=strongest_change.price_volume_strength,
                benchmark_symbol=benchmark_symbol,
            )
        )

    expectation_candidates = tuple(
        item
        for item in metrics
        if max(
            item.relative_strength,
            item.relative_surprise_strength,
            item.persistent_drift_strength,
        )
        >= Decimal("0.50")
    )
    if expectation_candidates:
        strongest_expectation = max(
            expectation_candidates,
            key=lambda item: (
                max(
                    item.persistent_drift_strength,
                    item.relative_surprise_strength,
                    item.relative_strength,
                ),
                item.observation.symbol,
            ),
        )
        expectation_score = max(
            strongest_expectation.persistent_drift_strength,
            strongest_expectation.relative_surprise_strength,
            strongest_expectation.relative_strength,
        )
        expectation_type: MarketScreenType = (
            "persistent_expectation_drift"
            if strongest_expectation.persistent_drift_strength >= Decimal("0.75")
            else (
                "volatility_adjusted_dislocation"
                if strongest_expectation.relative_surprise_strength == expectation_score
                else "relative_dislocation"
            )
        )
        seeds.append(
            _single_symbol_seed(
                screen_type=expectation_type,
                scout_id="expectation_gap_scout",
                metrics=strongest_expectation,
                score=expectation_score,
                benchmark_symbol=benchmark_symbol,
            )
        )

    if (breadth := _breadth_seed(metrics, benchmark_symbol)) is not None:
        seeds.append(breadth)
    return MarketResearchAgenda(
        known_at=known_at,
        posture="screen_ready",
        benchmark_symbol=benchmark_symbol,
        completed_sessions=completed_sessions,
        seeds=tuple(sorted(seeds, key=lambda item: item.assigned_scout_id)),
        snapshot_hash=snapshot_hash,
    )
