from datetime import UTC, datetime, timedelta

import pytest

from alta_asterism.freshness import (
    MAX_CURRENT_SIGNAL_AGE,
    classify_signal_freshness,
    current_signal_window,
    signal_age_seconds,
    signal_is_current,
)


def test_prompt_window_matches_inclusive_admission_boundaries() -> None:
    now = datetime(2026, 9, 12, 18, 30, tzinfo=UTC)
    window = current_signal_window(now)
    earliest = datetime.fromisoformat(window["earliest_event_at"])
    latest = datetime.fromisoformat(window["latest_event_at"])
    assert earliest == now - MAX_CURRENT_SIGNAL_AGE
    assert latest == now
    assert signal_is_current(earliest, now)
    assert signal_is_current(latest, now)
    assert not signal_is_current(earliest - timedelta(microseconds=1), now)
    assert not signal_is_current(latest + timedelta(microseconds=1), now)
    with pytest.raises(ValueError, match="timezone-aware"):
        current_signal_window(now.replace(tzinfo=None))


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
