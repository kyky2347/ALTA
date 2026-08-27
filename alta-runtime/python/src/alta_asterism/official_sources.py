import hashlib
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .ingest import RateLimited, SourceEnvelope
from .massive import MassiveDataset, OptionChainQuery


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    return str(value)


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json", by_alias=True)
        return _json_safe(result)
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return _json_safe(value)
    if hasattr(value, "__dict__"):
        return _json_safe(
            {
                key: child
                for key, child in vars(value).items()
                if not key.startswith("_")
            }
        )
    raise ValueError("official source returned an unsupported record type")


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _epoch_time(value: Any) -> datetime | None:
    if value is None:
        return None
    numeric = float(value)
    divisor = 1
    if numeric >= 1e18:
        divisor = 1_000_000_000
    elif numeric >= 1e15:
        divisor = 1_000_000
    elif numeric >= 1e12:
        divisor = 1_000
    return datetime.fromtimestamp(numeric / divisor, UTC)


def _raise_rate_limit(error: Exception) -> None:
    status = getattr(error, "status_code", None) or getattr(
        getattr(error, "response", None), "status_code", None
    )
    if status != 429:
        return
    headers = getattr(getattr(error, "response", None), "headers", {})
    try:
        retry_after = float(headers.get("Retry-After", 60))
    except (AttributeError, TypeError, ValueError):
        retry_after = 60
    raise RateLimited(max(retry_after, 1)) from error


class OfficialFinlightRestTransport:
    """Bounded REST polling using Finlight's official Python client."""

    websocket_available = False

    def __init__(
        self,
        client: Any,
        params_type: Callable[..., Any],
        universe: tuple[str, ...],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        page_size: int = 100,
    ) -> None:
        if not 1 <= page_size <= 100:
            raise ValueError("Finlight polling page_size must be between 1 and 100")
        self.client = client
        self.params_type = params_type
        self.universe = universe
        self.clock = clock
        self.page_size = page_size

    def stream(self, _cursor: str | None) -> Iterable[SourceEnvelope]:
        return ()

    def rest_gap(self, cursor: str | None) -> Iterable[SourceEnvelope]:
        return self.poll_rest(cursor)

    def poll_rest(self, cursor: str | None) -> Iterable[SourceEnvelope]:
        from_value = cursor.split("|", 1)[0] if cursor else None
        params = self.params_type(
            tickers=list(self.universe),
            language="en",
            from_=from_value,
            orderBy="createdAt",
            order="ASC",
            page=1,
            pageSize=self.page_size,
            includeContent=False,
            includeEntities=False,
        )
        try:
            response = self.client.articles.fetch_articles(params=params)
        except Exception as error:
            _raise_rate_limit(error)
            raise
        articles = _field(response, "articles") or ()
        envelopes = [self._envelope(article) for article in articles]
        envelopes.sort(key=lambda item: item.source_cursor or "")
        return tuple(envelopes)

    def _envelope(self, article: Any) -> SourceEnvelope:
        payload = _json_value(article)
        link = str(_field(article, "link") or "")
        if not link.startswith("https://"):
            raise ValueError("Finlight article is missing a canonical HTTPS link")
        created_at = _time(_field(article, "createdAt", "created_at"))
        published_at = _time(_field(article, "publishDate", "publish_date"))
        revised_at = _time(_field(article, "revisedDate", "revised_date"))
        indexed_at = created_at or published_at
        if indexed_at is None:
            raise ValueError("Finlight article is missing publication/index time")
        identity = hashlib.sha256(link.encode()).hexdigest()
        cursor = f"{indexed_at.isoformat()}|{identity[:16]}"
        return SourceEnvelope(
            source_id="finlight",
            source_record_id=f"article:{identity}",
            channel="rest",
            source_cursor=cursor,
            payload=payload,
            received_at=self.clock(),
            source_url=link,
            semantic_event_at=revised_at or published_at,
            published_at=published_at,
            source_revision=(
                revised_at.isoformat() if revised_at else indexed_at.isoformat()
            ),
            media_type="application/json",
            parser_version="finlight-client-2-v1",
        )


def build_official_finlight_transport(
    api_key: str, universe: tuple[str, ...]
) -> OfficialFinlightRestTransport:
    if not api_key:
        raise ValueError("Finlight API key is empty")
    from finlight_client import ApiConfig, FinlightApi
    from finlight_client.models import GetArticlesParams

    client = FinlightApi(config=ApiConfig(api_key=api_key))
    return OfficialFinlightRestTransport(client, GetArticlesParams, universe)


class OfficialMassiveRestTransport:
    """Official bounded REST client; admission is owned by the adapter."""

    def __init__(
        self,
        client: Any,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lookback_days: int = 7,
    ) -> None:
        if not 1 <= lookback_days <= 30:
            raise ValueError("Massive lookback_days must be between 1 and 30")
        self.client = client
        self.clock = clock
        self.lookback_days = lookback_days

    def fetch(
        self, dataset: MassiveDataset, symbols: tuple[str, ...]
    ) -> Iterable[SourceEnvelope]:
        try:
            if dataset is MassiveDataset.DAILY_BARS:
                return tuple(self._daily_bars(symbols))
            if dataset is MassiveDataset.TICKER_REFERENCE:
                return tuple(self._ticker_reference(symbols))
            if dataset is MassiveDataset.STOCK_SNAPSHOTS:
                return tuple(self._stock_snapshots(symbols))
            raise ValueError(f"unsupported Massive dataset: {dataset}")
        except Exception as error:
            _raise_rate_limit(error)
            raise

    def fetch_option_chain(self, query: OptionChainQuery) -> Iterable[SourceEnvelope]:
        params = {
            "contract_type": query.contract_type,
            "expiration_date.gte": query.expiration_from.isoformat(),
            "expiration_date.lte": query.expiration_to.isoformat(),
            "limit": 250,
        }
        if query.strike_from is not None:
            params["strike_price.gte"] = str(query.strike_from)
        if query.strike_to is not None:
            params["strike_price.lte"] = str(query.strike_to)
        try:
            records = self.client.list_snapshot_options_chain(
                query.underlying_symbol, params=params
            )
            return tuple(self._option_envelope(query, record) for record in records)
        except Exception as error:
            _raise_rate_limit(error)
            raise

    def fetch_option_snapshot(
        self, underlying_symbol: str, contract_symbol: str
    ) -> SourceEnvelope:
        try:
            record = self.client.get_snapshot_option(underlying_symbol, contract_symbol)
            return self._option_envelope(
                OptionChainQuery(
                    underlying_symbol=underlying_symbol,
                    contract_type="call",
                    expiration_from=self.clock().date(),
                    expiration_to=self.clock().date(),
                ),
                record,
            )
        except Exception as error:
            _raise_rate_limit(error)
            raise

    def _stock_snapshots(self, symbols: tuple[str, ...]) -> Iterable[SourceEnvelope]:
        received_at = self.clock()
        for requested_symbol in symbols:
            record = self.client.get_snapshot_ticker("stocks", requested_symbol)
            symbol = str(_field(record, "ticker") or requested_symbol).upper()
            if symbol != requested_symbol:
                raise ValueError("Massive snapshot returned a different ticker")
            quote = _field(record, "last_quote", "lastQuote")
            quote_at = _epoch_time(
                _field(quote, "sip_timestamp", "sipTimestamp")
                or _field(record, "updated")
            )
            if quote is None or quote_at is None:
                continue
            payload = _json_value(record)
            revision = str(
                _field(quote, "sequence_number", "sequenceNumber")
                or _field(quote, "sip_timestamp", "sipTimestamp")
                or _field(record, "updated")
            )
            yield SourceEnvelope(
                source_id="massive",
                source_record_id=f"stock-snapshot:{symbol}:{revision}",
                channel="rest",
                payload={"symbol": symbol, "snapshot": payload},
                received_at=received_at,
                source_url=f"https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}",
                semantic_event_at=quote_at,
                effective_at=quote_at,
                source_revision=revision,
                parser_version="massive-client-2-v2",
            )

    def _option_envelope(self, query: OptionChainQuery, record: Any) -> SourceEnvelope:
        received_at = self.clock()
        details = _field(record, "details")
        quote = _field(record, "last_quote", "lastQuote")
        contract = str(_field(details, "ticker") or "").upper()
        quote_at = _epoch_time(_field(quote, "last_updated", "lastUpdated"))
        if not contract or quote is None or quote_at is None:
            raise ValueError(
                "Massive option snapshot is missing contract quote identity"
            )
        revision = str(_field(quote, "last_updated", "lastUpdated"))
        return SourceEnvelope(
            source_id="massive",
            source_record_id=f"option-snapshot:{contract}:{revision}",
            channel="rest",
            payload={
                "underlying_symbol": query.underlying_symbol,
                "option_snapshot": _json_value(record),
            },
            received_at=received_at,
            source_url=(
                "https://api.massive.com/v3/snapshot/options/"
                f"{query.underlying_symbol}/{contract}"
            ),
            semantic_event_at=quote_at,
            effective_at=quote_at,
            source_revision=revision,
            parser_version="massive-client-2-v2",
        )

    def _daily_bars(self, symbols: tuple[str, ...]) -> Iterable[SourceEnvelope]:
        received_at = self.clock()
        end = received_at.date()
        start = end - timedelta(days=self.lookback_days)
        for symbol in symbols:
            records = self.client.list_aggs(
                ticker=symbol,
                multiplier=1,
                timespan="day",
                from_=start.isoformat(),
                to=end.isoformat(),
                adjusted=True,
                sort="asc",
                limit=min(self.lookback_days + 5, 50),
            )
            for record in records:
                timestamp = _field(record, "timestamp")
                if timestamp is None:
                    raise ValueError("Massive aggregate is missing timestamp")
                bar_at = datetime.fromtimestamp(float(timestamp) / 1_000, UTC)
                payload = _json_value(record)
                yield SourceEnvelope(
                    source_id="massive",
                    source_record_id=f"daily:{symbol}:{int(float(timestamp))}",
                    channel="rest",
                    payload={"symbol": symbol, "aggregate": payload},
                    received_at=received_at,
                    source_url=(
                        "https://api.massive.com/v2/aggs/ticker/"
                        f"{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
                    ),
                    semantic_event_at=bar_at,
                    effective_at=bar_at,
                    source_revision=str(int(float(timestamp))),
                    parser_version="massive-client-2-v1",
                )

    def _ticker_reference(self, symbols: tuple[str, ...]) -> Iterable[SourceEnvelope]:
        received_at = self.clock()
        for symbol in symbols:
            record = self.client.get_ticker_details(symbol)
            updated_at = _time(_field(record, "last_updated_utc", "lastUpdatedUtc"))
            payload = _json_value(record)
            revision = updated_at.isoformat() if updated_at else "current"
            yield SourceEnvelope(
                source_id="massive",
                source_record_id=f"ticker:{symbol}:{revision}",
                channel="rest",
                payload={"symbol": symbol, "details": payload},
                received_at=received_at,
                source_url=f"https://api.massive.com/v3/reference/tickers/{symbol}",
                semantic_event_at=updated_at,
                source_revision=revision,
                parser_version="massive-client-2-v1",
            )


def _massive_base_url(base_url: str, allow_insecure_http: bool) -> str:
    parsed = urlsplit(base_url.strip())
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Massive base URL must be a credential-free origin or path")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and allow_insecure_http
    ):
        raise ValueError(
            "Massive base URL must use HTTPS unless insecure HTTP is explicitly allowed"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def build_official_massive_transport(
    api_key: str,
    *,
    base_url: str = "https://api.massive.com",
    allow_insecure_http: bool = False,
    auth_mode: str = "bearer",
) -> OfficialMassiveRestTransport:
    """Builds a transport only; it cannot bypass MassiveAccessCoordinator."""
    if not api_key:
        raise ValueError("Massive API key is empty")
    from massive import RESTClient

    if auth_mode not in {"bearer", "x_api_key", "x_proxy_key"}:
        raise ValueError("Massive auth mode must be bearer, x_api_key, or x_proxy_key")
    validated_base = _massive_base_url(base_url, allow_insecure_http)
    client = RESTClient(
        api_key=api_key,
        base=validated_base,
        connect_timeout=10,
        read_timeout=10,
        num_pools=1,
        retries=0,
        pagination=False,
        trace=False,
        verbose=False,
    )
    if auth_mode in {"x_api_key", "x_proxy_key"}:
        client.headers.pop("Authorization", None)
        header = "X-API-Key" if auth_mode == "x_api_key" else "X-Proxy-Key"
        client.headers[header] = api_key
        client.client.headers = client.headers
    return OfficialMassiveRestTransport(client)
