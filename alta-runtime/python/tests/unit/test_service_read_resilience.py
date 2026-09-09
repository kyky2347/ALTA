import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

import psycopg
import pytest

from alta_asterism.contracts import Settings
from alta_asterism.freshness import MAX_CURRENT_SIGNAL_AGE
from alta_asterism.service import _handler


@pytest.fixture
def serve():
    servers = []

    def start(database, *, state=None, autonomous=False):
        settings = Settings(
            DATABASE_URL="postgresql://fixture:fixture@127.0.0.1:1/fixture",
            REDIS_URL="redis://127.0.0.1:1/0",
            ALTA_ENVIRONMENT="replay",
            ALTA_AUTONOMOUS_ENABLED=autonomous,
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler(database, settings, state)
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def read(url):
    try:
        response = urlopen(url, timeout=2)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def test_cached_status_rechecks_expiry_without_new_events(serve, monkeypatch):
    now = [datetime(2026, 9, 9, 15, tzinfo=UTC)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0]

    monkeypatch.setattr("alta_asterism.service.datetime", Clock)
    anchor = now[0] - MAX_CURRENT_SIGNAL_AGE
    stored = {
        "eventCursor": 42,
        "candidates": [{"id": "candidate", "freshnessAt": anchor}],
        "opportunities": [{"id": "opportunity", "freshnessAt": anchor}],
    }
    loads = []

    def status(*_args):
        loads.append(True)
        return stored

    base = serve(SimpleNamespace(event_cursor=lambda *_: 42, mvp_status=status))
    first_code, first = read(f"{base}/api/v1/mvp/status")
    now[0] += timedelta(seconds=1)
    second_code, second = read(f"{base}/api/v1/mvp/status")

    assert first_code == second_code == 200
    assert first["data"]["opportunities"][0]["actionableNow"] is True
    assert second["meta"]["cacheHit"] is True
    assert second["data"]["opportunities"][0]["actionableNow"] is False
    assert second["data"]["candidates"][0]["freshnessState"] == "expired"
    assert len(loads) == 1
    assert "freshnessState" not in stored["opportunities"][0]


def test_database_outage_is_sanitized_and_next_read_recovers(serve):
    unavailable = [True]

    def summary(*_args):
        if unavailable[0]:
            raise psycopg.OperationalError("driver-private-connection-detail")
        return {"run": 2}

    base = serve(SimpleNamespace(summary=summary))
    code, failure = read(f"{base}/api/v1/system/summary")
    assert code == 503
    assert failure["error"]["code"] == "database_unavailable"
    assert "driver-private" not in json.dumps(failure)
    assert read(f"{base}/health/live")[0] == 200
    unavailable[0] = False
    assert read(f"{base}/api/v1/system/summary")[1]["data"]["counts"] == {"run": 2}


@pytest.mark.parametrize(
    "heartbeat",
    ["not-a-date", "2026-09-09T15:00:00", "2999-01-01T00:00:00Z"],
)
def test_invalid_or_future_heartbeat_fails_readiness_cleanly(serve, heartbeat):
    base = serve(
        SimpleNamespace(ready=lambda: True),
        state={"autonomousStatus": "waiting", "lastHeartbeatAt": heartbeat},
        autonomous=True,
    )
    code, payload = read(f"{base}/health/ready")
    assert code == 503
    assert payload["heartbeatFresh"] is False
