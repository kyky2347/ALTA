from datetime import UTC, datetime, timedelta

from alta_asterism.freshness import (
    MAX_CURRENT_SIGNAL_AGE,
    classify_signal_freshness,
    signal_age_seconds,
    signal_is_current,
)


def test_signal_freshness_uses_event_time_not_retrieval_time() -> None:
    known_at = datetime(2026, 9, 9, 15, tzinfo=UTC)

    assert classify_signal_freshness(known_at - timedelta(minutes=5), known_at) == (
        "live"
    )
    assert classify_signal_freshness(known_at - timedelta(days=2), known_at) == (
        "current"
    )
    expired = known_at - MAX_CURRENT_SIGNAL_AGE - timedelta(seconds=1)
    assert classify_signal_freshness(expired, known_at) == "expired"
    assert signal_is_current(expired, known_at) is False
    assert signal_age_seconds(expired, known_at) == int(
        (MAX_CURRENT_SIGNAL_AGE + timedelta(seconds=1)).total_seconds()
    )


def test_unknown_and_future_signal_times_fail_closed() -> None:
    known_at = datetime(2026, 9, 9, 15, tzinfo=UTC)

    assert classify_signal_freshness(None, known_at) == "unknown"
    assert signal_is_current(None, known_at) is False
    assert classify_signal_freshness(known_at + timedelta(seconds=1), known_at) == (
        "invalid"
    )
