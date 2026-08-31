import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from alta_asterism.projection_cache import ProjectionCache


def test_projection_cache_expires_and_reports_age() -> None:
    now = [10.0]
    cache: ProjectionCache[dict[str, int]] = ProjectionCache(
        5, monotonic=lambda: now[0]
    )
    calls = 0

    def load() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"version": calls}

    first = cache.get("runtime", load)
    now[0] = 12.25
    second = cache.get("runtime", load)
    now[0] = 15.01
    third = cache.get("runtime", load)

    assert (first.value, first.hit, first.age_ms) == ({"version": 1}, False, 0)
    assert (second.value, second.hit, second.age_ms) == (
        {"version": 1},
        True,
        2250,
    )
    assert (third.value, third.hit, third.age_ms) == ({"version": 2}, False, 0)
    assert calls == 2


def test_projection_cache_coalesces_concurrent_misses() -> None:
    cache: ProjectionCache[int] = ProjectionCache(5)
    calls = 0
    gate = threading.Event()

    def load() -> int:
        nonlocal calls
        calls += 1
        gate.wait(1)
        return 7

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(cache.get, "status", load) for _ in range(4)]
        time.sleep(0.02)
        gate.set()
        results = [future.result(timeout=1) for future in futures]

    assert [item.value for item in results] == [7, 7, 7, 7]
    assert sum(not item.hit for item in results) == 1
    assert calls == 1


def test_projection_cache_rejects_invalid_ttl() -> None:
    with pytest.raises(ValueError, match="TTL"):
        ProjectionCache(0)


def test_projection_cache_bounds_entries_with_lru_eviction() -> None:
    cache: ProjectionCache[int] = ProjectionCache(5, max_entries=2)

    cache.get("one", lambda: 1)
    cache.get("two", lambda: 2)
    assert cache.get("one", lambda: 10).hit is True
    cache.get("three", lambda: 3)

    assert cache.get("one", lambda: 10).hit is True
    assert cache.get("two", lambda: 20).value == 20


def test_projection_cache_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        ProjectionCache(1, max_entries=0)
