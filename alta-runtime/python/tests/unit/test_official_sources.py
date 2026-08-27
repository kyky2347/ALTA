from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from alta_asterism.ingest import RateLimited
from alta_asterism.massive import MassiveDataset, OptionChainQuery
from alta_asterism.official_sources import (
    OfficialFinlightRestTransport,
    OfficialMassiveRestTransport,
    build_official_massive_transport,
)


NOW = datetime(2026, 8, 23, 15, tzinfo=UTC)


class CapturingParams:
    latest: dict | None = None

    def __init__(self, **values) -> None:
        type(self).latest = values


def test_official_finlight_transport_is_bounded_and_cursor_driven() -> None:
    article = {
        "link": "https://news.example/item/1",
        "createdAt": "2026-08-23T14:00:00Z",
        "publishDate": "2026-08-23T13:58:00Z",
        "title": "A bounded fixture article",
    }
    client = SimpleNamespace(
        articles=SimpleNamespace(
            fetch_articles=lambda *, params: SimpleNamespace(articles=[article])
        )
    )
    transport = OfficialFinlightRestTransport(
        client,
        CapturingParams,
        ("SPY", "NVDA"),
        clock=lambda: NOW,
        page_size=25,
    )

    envelopes = tuple(transport.poll_rest("2026-08-23T12:00:00+00:00|prior-record"))

    assert CapturingParams.latest == {
        "tickers": ["SPY", "NVDA"],
        "language": "en",
        "from_": "2026-08-23T12:00:00+00:00",
        "orderBy": "createdAt",
        "order": "ASC",
        "page": 1,
        "pageSize": 25,
        "includeContent": False,
        "includeEntities": False,
    }
    assert len(envelopes) == 1
    assert envelopes[0].source_id == "finlight"
    assert envelopes[0].source_cursor.startswith("2026-08-23T14:00:00+00:00|")
    assert envelopes[0].source_url == "https://news.example/item/1"


def test_official_finlight_transport_converts_429_to_cooldown() -> None:
    class UpstreamError(Exception):
        status_code = 429
        response = SimpleNamespace(status_code=429, headers={"Retry-After": "7"})

    def fail(*, params) -> None:
        raise UpstreamError

    client = SimpleNamespace(articles=SimpleNamespace(fetch_articles=fail))
    transport = OfficialFinlightRestTransport(
        client, CapturingParams, ("SPY",), clock=lambda: NOW
    )

    with pytest.raises(RateLimited, match="7") as captured:
        tuple(transport.poll_rest(None))

    assert captured.value.retry_after == 7


def test_official_massive_transport_creates_versioned_daily_envelopes() -> None:
    class Client:
        requested: dict | None = None

        def list_aggs(self, **values):
            self.requested = values
            return [
                SimpleNamespace(
                    timestamp=1_777_248_000_000,
                    open=100.0,
                    high=102.0,
                    low=99.5,
                    close=101.0,
                    volume=1234,
                )
            ]

    client = Client()
    transport = OfficialMassiveRestTransport(client, clock=lambda: NOW, lookback_days=7)

    envelopes = tuple(transport.fetch(MassiveDataset.DAILY_BARS, ("SPY",)))

    assert client.requested == {
        "ticker": "SPY",
        "multiplier": 1,
        "timespan": "day",
        "from_": "2026-08-16",
        "to": "2026-08-23",
        "adjusted": True,
        "sort": "asc",
        "limit": 12,
    }
    assert len(envelopes) == 1
    assert envelopes[0].source_record_id == "daily:SPY:1777248000000"
    assert envelopes[0].payload["aggregate"]["close"] == 101.0
    assert "apiKey" not in envelopes[0].source_url


def test_official_massive_transport_serializes_reference_datetimes() -> None:
    class Client:
        def get_ticker_details(self, symbol: str):
            return SimpleNamespace(
                ticker=symbol,
                name="Fixture ETF",
                last_updated_utc=NOW,
            )

    transport = OfficialMassiveRestTransport(Client(), clock=lambda: NOW)

    envelope = tuple(transport.fetch(MassiveDataset.TICKER_REFERENCE, ("SPY",)))[0]

    assert envelope.payload["details"]["last_updated_utc"] == NOW.isoformat()
    assert envelope.source_revision == NOW.isoformat()


def test_official_massive_transport_builds_stock_and_option_snapshots() -> None:
    class Client:
        option_params = None

        def get_snapshot_ticker(self, market_type, ticker):
            assert (market_type, ticker) == ("stocks", "SPY")
            return {
                "ticker": "SPY",
                "updated": 1_777_248_000_000_000_000,
                "last_quote": {
                    "bid_price": 500.0,
                    "ask_price": 500.1,
                    "sip_timestamp": 1_777_248_000_000_000_000,
                    "sequence_number": 7,
                },
            }

        def list_snapshot_options_chain(self, symbol, params):
            assert symbol == "SPY"
            self.option_params = params
            return [
                {
                    "details": {
                        "ticker": "O:SPY260918C00500000",
                        "contract_type": "call",
                        "expiration_date": "2026-09-18",
                        "strike_price": 500,
                    },
                    "last_quote": {
                        "bid": 10.0,
                        "ask": 10.5,
                        "last_updated": 1_777_248_000_000_000_000,
                    },
                    "greeks": {"delta": 0.5},
                    "open_interest": 1000,
                }
            ]

    client = Client()
    transport = OfficialMassiveRestTransport(client, clock=lambda: NOW)

    stock = tuple(transport.fetch(MassiveDataset.STOCK_SNAPSHOTS, ("SPY",)))[0]
    option = tuple(
        transport.fetch_option_chain(
            OptionChainQuery(
                underlying_symbol="SPY",
                contract_type="call",
                expiration_from=NOW.date(),
                expiration_to=NOW.date(),
            )
        )
    )[0]

    assert stock.source_record_id == "stock-snapshot:SPY:7"
    assert stock.semantic_event_at is not None
    assert option.source_record_id.startswith("option-snapshot:O:SPY")
    assert client.option_params["contract_type"] == "call"


def test_massive_builder_requires_explicit_insecure_http(monkeypatch) -> None:
    captured = {}

    class Client:
        def __init__(self, **values):
            captured.update(values)
            self.headers = {"Authorization": "Bearer fixture-key"}
            self.client = SimpleNamespace(headers=self.headers)

    monkeypatch.setattr("massive.RESTClient", Client)

    with pytest.raises(ValueError, match="must use HTTPS"):
        build_official_massive_transport(
            "fixture-key", base_url="http://market-data.invalid:8081"
        )
    build_official_massive_transport(
        "fixture-key",
        base_url="http://market-data.invalid:8081/",
        allow_insecure_http=True,
    )

    assert captured["base"] == "http://market-data.invalid:8081"

    transport = build_official_massive_transport("fixture-key", auth_mode="x_api_key")
    assert "Authorization" not in transport.client.headers
    assert transport.client.headers["X-API-Key"] == "fixture-key"

    transport = build_official_massive_transport("fixture-key", auth_mode="x_proxy_key")
    assert "Authorization" not in transport.client.headers
    assert transport.client.headers["X-Proxy-Key"] == "fixture-key"
