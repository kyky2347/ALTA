from datetime import datetime, timedelta
from typing import Any, Literal


# Four calendar days keeps the last completed US session usable across a long
# weekend while preventing a newly ingested old article or an abandoned cycle
# from masquerading as current research.
MAX_CURRENT_SIGNAL_AGE = timedelta(days=4)
LIVE_SIGNAL_AGE = timedelta(minutes=15)

FreshnessState = Literal["live", "current", "expired", "unknown", "invalid"]


def current_signal_window(known_at: datetime) -> dict[str, str]:
    """Expose the exact validator interval to research and finalization prompts."""
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    return {
        "earliest_event_at": (known_at - MAX_CURRENT_SIGNAL_AGE).isoformat(),
        "latest_event_at": known_at.isoformat(),
        "basis": "thesis-changing source event, not retrieval time; inclusive bounds",
    }


def signal_age_seconds(anchor: datetime | None, known_at: datetime) -> int | None:
    if anchor is None:
        return None
    for value, name in ((anchor, "signal anchor"), (known_at, "known_at")):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
    return max(0, int((known_at - anchor).total_seconds()))


def classify_signal_freshness(
    anchor: datetime | None,
    known_at: datetime,
) -> FreshnessState:
    if anchor is None:
        return "unknown"
    if anchor > known_at:
        return "invalid"
    age = known_at - anchor
    if age <= LIVE_SIGNAL_AGE:
        return "live"
    if age <= MAX_CURRENT_SIGNAL_AGE:
        return "current"
    return "expired"


def signal_is_current(anchor: datetime | None, known_at: datetime) -> bool:
    return classify_signal_freshness(anchor, known_at) in {"live", "current"}


def signal_freshness_fields(
    anchor: datetime | None, known_at: datetime, *, actionable: bool = False
) -> dict[str, Any]:
    state = classify_signal_freshness(anchor, known_at)
    fields = {
        "freshnessState": state,
        "freshnessAgeSeconds": signal_age_seconds(anchor, known_at),
    }
    if actionable:
        fields["actionableNow"] = state in {"live", "current"}
    return fields


def refresh_status_freshness(
    status: dict[str, Any], known_at: datetime
) -> dict[str, Any]:
    """Reproject wall-clock fields without mutating the shared database cache."""
    return {
        **status,
        **{
            collection: [
                {
                    **row,
                    **signal_freshness_fields(
                        row.get("freshnessAt"),
                        known_at,
                        actionable=collection == "opportunities",
                    ),
                }
                for row in status.get(collection, [])
            ]
            for collection in ("candidates", "opportunities")
        },
    }
