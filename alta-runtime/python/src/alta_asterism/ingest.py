import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import Environment
from .database import Database

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "accesskey",
    "accesstoken",
    "apikey",
    "authorization",
    "clientsecret",
    "cookie",
    "credentials",
    "password",
    "privatekey",
    "proxyauthorization",
    "refreshtoken",
    "secret",
    "sessiontoken",
    "setcookie",
    "signature",
    "token",
    "xapikey",
}
_AUTH_PATTERN = re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]+")
_URL_PATTERN = re.compile(r"(?i)https?://[^\s\"'<>]+")


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _sensitive_query_key(value: str) -> bool:
    normalized = _normalized_key(value)
    return (
        normalized in _SENSITIVE_KEYS
        or normalized in {"auth", "code", "credential", "key", "sig"}
        or value.casefold().replace("_", "-").startswith("x-amz-")
    )


def _redact_url(value: str) -> str:
    """Remove URL credentials/fragments and redact authentication query values."""

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if parsed.scheme not in {"http", "https"} or hostname is None:
            return value
        host = f"[{hostname}]" if ":" in hostname else hostname
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{host}:{port}" if port is not None else host
        query = urlencode(
            [
                (key, REDACTED if _sensitive_query_key(key) else item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            doseq=True,
            safe="[]",
        )
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))
    except (TypeError, ValueError):
        return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                REDACTED
                if _normalized_key(str(key)) in _SENSITIVE_KEYS
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _AUTH_PATTERN.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
        return _URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), value)
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class SourceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Literal["finlight", "massive"]
    source_record_id: str = Field(min_length=1, max_length=256)
    channel: Literal["websocket", "rest"]
    source_cursor: str | None = Field(default=None, max_length=2_048)
    payload: dict[str, Any]
    received_at: datetime
    source_url: str | None = Field(default=None, max_length=2_048)
    semantic_event_at: datetime | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None
    period_end: datetime | None = None
    source_revision: str | None = Field(default=None, max_length=128)
    supersedes_id: str | None = Field(default=None, max_length=256)
    media_type: str = Field(default="application/json", max_length=128)
    parser_version: str = Field(default="fixture-v1", max_length=64)

    @field_validator(
        "received_at",
        "semantic_event_at",
        "published_at",
        "effective_at",
        "period_end",
    )
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("source timestamps must be timezone-aware")
        return value

    @field_validator("payload")
    @classmethod
    def payload_is_json_and_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        if len(encoded) > 60_000:
            raise ValueError("source payload exceeds 60000 bytes")
        return value

    def raw_body(self) -> dict[str, Any]:
        return redact(
            {
                "source": {
                    "id": self.source_id,
                    "recordId": self.source_record_id,
                    "url": self.source_url,
                },
                "transport": {
                    "channel": self.channel,
                    "sourceCursor": self.source_cursor,
                },
                "semanticTimes": {
                    "eventAt": _iso(self.semantic_event_at),
                    "publishedAt": _iso(self.published_at),
                    "effectiveAt": _iso(self.effective_at),
                    "periodEnd": _iso(self.period_end),
                },
                "receivedAt": _iso(self.received_at),
                "revision": {
                    "sourceRevision": self.source_revision,
                    "supersedesId": self.supersedes_id,
                },
                "mediaType": self.media_type,
                "parserVersion": self.parser_version,
                "payload": self.payload,
            }
        )

    def content_hash(self) -> str:
        body = self.raw_body()
        body.pop("receivedAt")
        body.pop("transport")
        encoded = json.dumps(
            body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RawReceipt:
    id: str
    content_hash: str
    known_at: datetime
    inserted: bool


class RawSink(Protocol):
    def save(self, envelope: SourceEnvelope) -> RawReceipt: ...


class RawStore:
    def __init__(
        self,
        database: Database,
        environment: Environment = Environment.REPLAY,
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.database = database
        self.environment = environment
        self.clock = clock

    def save(self, envelope: SourceEnvelope) -> RawReceipt:
        known_at = self.clock()
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise ValueError("RawStore clock must return a timezone-aware datetime")
        content_hash = envelope.content_hash()
        raw_id = (
            "raw_"
            + hashlib.sha256(
                (
                    f"{self.environment.value}\0{envelope.source_id}\0"
                    f"{envelope.source_record_id}\0{content_hash}"
                ).encode()
            ).hexdigest()
        )
        body = envelope.raw_body()
        with self.database.connect() as connection:
            row = connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body)
                VALUES (%s,%s,1,%s,%s,%s,%s,%s)
                ON CONFLICT (environment, source, source_key, content_hash) DO NOTHING
                RETURNING id, known_at""",
                (
                    raw_id,
                    self.environment.value,
                    known_at,
                    envelope.source_id,
                    envelope.source_record_id,
                    content_hash,
                    Jsonb(body),
                ),
            ).fetchone()
            inserted = row is not None
            if row is None:
                row = connection.execute(
                    """SELECT id, known_at FROM research.raw
                    WHERE environment = %s AND source = %s
                    AND source_key = %s AND content_hash = %s""",
                    (
                        self.environment.value,
                        envelope.source_id,
                        envelope.source_record_id,
                        content_hash,
                    ),
                ).fetchone()
        return RawReceipt(
            id=row[0], content_hash=content_hash, known_at=row[1], inserted=inserted
        )


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        if retry_after <= 0:
            raise ValueError("retry_after must be positive")
        self.retry_after = retry_after
        super().__init__(f"rate limited for {retry_after:g} seconds")


class Cooldown:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._blocked_until = 0.0
        self._lock = threading.Lock()

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - self._monotonic())

    def record(self, retry_after: float) -> None:
        if retry_after <= 0:
            raise ValueError("retry_after must be positive")
        with self._lock:
            self._blocked_until = max(
                self._blocked_until, self._monotonic() + retry_after
            )
