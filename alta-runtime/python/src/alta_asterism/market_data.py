import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Literal

from .expression import QuoteSnapshot
from .massive import MassiveDataset, MassiveRestAdapter, OptionChainQuery


def _value(value: Any, *names: str) -> Any:
    if not isinstance(value, dict):
        return None
    for name in names:
        if name in value:
            return value[name]
    return None


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


@dataclass(frozen=True)
class MarketInstrument:
    kind: Literal["stock", "etf", "option"]
    symbol: str
    underlying_symbol: str
    quote: QuoteSnapshot
    quantity: Decimal
    metadata: dict[str, Any]


@dataclass(frozen=True)
class InstrumentSelection:
    instrument: MarketInstrument | None
    reason: str


class MassiveMarketData:
    """Persists every consulted quote before returning a deterministic instrument."""

    def __init__(
        self,
        adapter: MassiveRestAdapter,
        *,
        max_notional: Decimal = Decimal("10000"),
        max_option_contracts: int = 5,
        min_option_open_interest: Decimal = Decimal("50"),
        max_option_spread_bps: Decimal = Decimal("1200"),
        forward_quote_timeout_seconds: float = 3,
        forward_quote_poll_seconds: float = 0.5,
        sleeper=time.sleep,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        if max_notional <= 0 or max_option_contracts <= 0:
            raise ValueError("market-data position limits must be positive")
        if not 0 <= forward_quote_timeout_seconds <= 30:
            raise ValueError("forward quote timeout must be between 0 and 30 seconds")
        if not 0.05 <= forward_quote_poll_seconds <= 5:
            raise ValueError("forward quote polling must be between 0.05 and 5 seconds")
        self.adapter = adapter
        self.max_notional = max_notional
        self.max_option_contracts = max_option_contracts
        self.min_option_open_interest = min_option_open_interest
        self.max_option_spread_bps = max_option_spread_bps
        self.forward_quote_timeout_seconds = forward_quote_timeout_seconds
        self.forward_quote_poll_seconds = forward_quote_poll_seconds
        self.sleeper = sleeper
        self.clock = clock

    def equity(
        self,
        kind: Literal["stock", "etf"],
        symbol: str,
        *,
        underlying_symbol: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InstrumentSelection:
        capture = self.adapter.capture(MassiveDataset.STOCK_SNAPSHOTS, (symbol,))
        if capture.result.posture != "healthy":
            return InstrumentSelection(None, f"massive_{capture.result.posture}")
        snapshots = self._stock_snapshots(capture.records)
        snapshot = snapshots.get(symbol.upper())
        if snapshot is None:
            return InstrumentSelection(None, "trusted_quote_unavailable")
        quote, liquidity = snapshot
        quantity = (self.max_notional / quote.ask).to_integral_value(
            rounding=ROUND_DOWN
        )
        if quantity <= 0:
            return InstrumentSelection(None, "position_budget_too_small")
        return InstrumentSelection(
            MarketInstrument(
                kind=kind,
                symbol=quote.symbol,
                underlying_symbol=underlying_symbol or quote.symbol,
                quote=quote,
                quantity=quantity,
                metadata={
                    "notional_limit": str(self.max_notional),
                    **liquidity,
                    **(metadata or {}),
                },
            ),
            "validated_equity_snapshot",
        )

    def option(
        self,
        underlying_symbol: str,
        direction: Literal["positive", "negative", "neutral"] | None,
        horizon_days: int,
    ) -> InstrumentSelection:
        if direction not in ("positive", "negative"):
            return InstrumentSelection(None, "option_requires_direction")
        now = self.clock()
        target_dte = min(max(horizon_days + 7, 14), 120)
        target_expiration = now.date() + timedelta(days=target_dte)
        expiration_from = max(
            now.date() + timedelta(days=1),
            target_expiration - timedelta(days=14),
        )
        expiration_to = target_expiration + timedelta(days=14)
        contract_type = "call" if direction == "positive" else "put"
        underlying = self.equity("stock", underlying_symbol)
        if underlying.instrument is None:
            return InstrumentSelection(None, "underlying_quote_unavailable")
        underlying_midpoint = (
            underlying.instrument.quote.bid + underlying.instrument.quote.ask
        ) / Decimal(2)
        capture = self.adapter.capture_option_chain(
            OptionChainQuery(
                underlying_symbol=underlying_symbol,
                contract_type=contract_type,
                expiration_from=expiration_from,
                expiration_to=expiration_to,
                strike_from=(underlying_midpoint * Decimal("0.80")),
                strike_to=(underlying_midpoint * Decimal("1.20")),
            )
        )
        if capture.result.posture != "healthy":
            return InstrumentSelection(None, f"massive_{capture.result.posture}")
        eligible = []
        for record in capture.records:
            parsed = self._option_candidate(
                record,
                target_expiration=target_expiration,
                expected_contract_type=contract_type,
            )
            if parsed is not None:
                eligible.append(parsed)
        if not eligible:
            return InstrumentSelection(None, "liquid_option_contract_unavailable")
        eligible.sort(key=lambda item: item[0])
        _, quote, details, open_interest, delta = eligible[0]
        contract_cost = quote.ask * Decimal(100)
        contracts = min(
            int(
                (self.max_notional / contract_cost).to_integral_value(
                    rounding=ROUND_DOWN
                )
            ),
            self.max_option_contracts,
        )
        if contracts <= 0:
            return InstrumentSelection(None, "position_budget_too_small")
        return InstrumentSelection(
            MarketInstrument(
                kind="option",
                symbol=quote.symbol,
                underlying_symbol=underlying_symbol.upper(),
                quote=quote,
                quantity=Decimal(contracts * 100),
                metadata={
                    "contracts": contracts,
                    "contract_multiplier": 100,
                    "contract_type": contract_type,
                    "expiration_date": details["expiration_date"],
                    "strike_price": details["strike_price"],
                    "delta": str(delta),
                    "open_interest": str(open_interest),
                    "target_dte": target_dte,
                },
            ),
            "validated_liquid_option_snapshot",
        )

    def quote(
        self,
        kind: Literal["stock", "etf", "option"],
        symbol: str,
        *,
        underlying_symbol: str | None = None,
    ) -> QuoteSnapshot | None:
        if kind == "option":
            if underlying_symbol is None:
                return None
            capture = self.adapter.capture_option_snapshot(underlying_symbol, symbol)
            if capture.result.posture != "healthy" or not capture.records:
                return None
            return self._option_quote(capture.records[0])
        capture = self.adapter.capture(MassiveDataset.STOCK_SNAPSHOTS, (symbol,))
        if capture.result.posture != "healthy":
            return None
        return self._stock_quotes(capture.records).get(symbol.upper())

    def forward_quote(
        self,
        kind: Literal["stock", "etf", "option"],
        symbol: str,
        *,
        committed_at: datetime,
        frozen_latency_ms: int,
        underlying_symbol: str | None = None,
    ) -> QuoteSnapshot | None:
        """Polls a bounded number of times for a quote truly newer than an intent."""
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise ValueError("forward quote intent time must be timezone-aware")
        if not 0 <= frozen_latency_ms <= 60_000:
            raise ValueError("forward quote latency must be between 0 and 60000 ms")
        eligible_known_at = committed_at + timedelta(milliseconds=frozen_latency_ms)
        attempts = max(
            1,
            math.ceil(
                self.forward_quote_timeout_seconds / self.forward_quote_poll_seconds
            )
            + 1,
        )
        latest = None
        for attempt in range(attempts):
            quote = self.quote(
                kind,
                symbol,
                underlying_symbol=underlying_symbol,
            )
            if quote is not None:
                latest = quote
                if quote.known_at > eligible_known_at and quote.as_of > committed_at:
                    return quote
            if attempt + 1 < attempts:
                self.sleeper(self.forward_quote_poll_seconds)
        return latest

    @staticmethod
    def _stock_quotes(records) -> dict[str, QuoteSnapshot]:
        return {
            symbol: quote
            for symbol, (quote, _liquidity) in MassiveMarketData._stock_snapshots(
                records
            ).items()
        }

    @staticmethod
    def _stock_snapshots(
        records,
    ) -> dict[str, tuple[QuoteSnapshot, dict[str, str]]]:
        result: dict[str, tuple[QuoteSnapshot, dict[str, str]]] = {}
        for record in records:
            payload = record.envelope.payload
            symbol = str(payload.get("symbol") or "").upper()
            snapshot = payload.get("snapshot") or {}
            quote = _value(snapshot, "last_quote", "lastQuote") or {}
            bid = _decimal(_value(quote, "bid_price", "bidPrice", "p"))
            ask = _decimal(_value(quote, "ask_price", "askPrice", "P"))
            as_of = record.envelope.semantic_event_at
            if not symbol or bid is None or ask is None or as_of is None:
                continue
            try:
                parsed_quote = QuoteSnapshot(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    as_of=as_of,
                    known_at=record.known_at,
                    raw_id=record.raw_id,
                    raw_version=record.raw_version,
                    content_hash=record.content_hash,
                )
            except ValueError:
                continue
            day = _value(snapshot, "day", "session") or {}
            day_volume = _decimal(_value(day, "volume", "v"))
            liquidity = {}
            if day_volume is not None and day_volume > 0:
                midpoint = (bid + ask) / Decimal(2)
                liquidity = {
                    "observed_day_volume": str(day_volume),
                    "observed_day_dollar_volume": str(day_volume * midpoint),
                }
            result[symbol] = parsed_quote, liquidity
        return result

    def _option_candidate(
        self,
        record,
        *,
        target_expiration: date,
        expected_contract_type: str,
    ):
        snapshot = record.envelope.payload.get("option_snapshot") or {}
        details = _value(snapshot, "details") or {}
        quote_value = _value(snapshot, "last_quote", "lastQuote") or {}
        greeks = _value(snapshot, "greeks") or {}
        symbol = str(_value(details, "ticker") or "").upper()
        expiration_text = _value(details, "expiration_date", "expirationDate")
        contract_type = _value(details, "contract_type", "contractType")
        bid = _decimal(_value(quote_value, "bid"))
        ask = _decimal(_value(quote_value, "ask"))
        delta = _decimal(_value(greeks, "delta"))
        open_interest = _decimal(_value(snapshot, "open_interest", "openInterest"))
        as_of = record.envelope.semantic_event_at
        try:
            expiration = date.fromisoformat(str(expiration_text))
        except ValueError:
            return None
        if (
            not symbol
            or contract_type != expected_contract_type
            or bid is None
            or ask is None
            or delta is None
            or open_interest is None
            or as_of is None
            or bid <= 0
            or ask < bid
            or open_interest < self.min_option_open_interest
        ):
            return None
        midpoint = (bid + ask) / Decimal(2)
        spread_bps = (ask - bid) / midpoint * Decimal(10_000)
        if spread_bps > self.max_option_spread_bps:
            return None
        absolute_delta = abs(delta)
        if not Decimal("0.25") <= absolute_delta <= Decimal("0.75"):
            return None
        try:
            quote = QuoteSnapshot(
                symbol=symbol,
                bid=bid,
                ask=ask,
                as_of=as_of,
                known_at=record.known_at,
                raw_id=record.raw_id,
                raw_version=record.raw_version,
                content_hash=record.content_hash,
            )
        except ValueError:
            return None
        score = (
            abs((expiration - target_expiration).days),
            abs(absolute_delta - Decimal("0.50")),
            spread_bps,
            -open_interest,
            symbol,
        )
        return score, quote, details, open_interest, delta

    @staticmethod
    def _option_quote(record) -> QuoteSnapshot | None:
        snapshot = record.envelope.payload.get("option_snapshot") or {}
        details = _value(snapshot, "details") or {}
        quote_value = _value(snapshot, "last_quote", "lastQuote") or {}
        symbol = str(_value(details, "ticker") or "").upper()
        bid = _decimal(_value(quote_value, "bid"))
        ask = _decimal(_value(quote_value, "ask"))
        as_of = record.envelope.semantic_event_at
        if not symbol or bid is None or ask is None or as_of is None:
            return None
        try:
            return QuoteSnapshot(
                symbol=symbol,
                bid=bid,
                ask=ask,
                as_of=as_of,
                known_at=record.known_at,
                raw_id=record.raw_id,
                raw_version=record.raw_version,
                content_hash=record.content_hash,
            )
        except ValueError:
            return None
