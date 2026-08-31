import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CachedProjection(Generic[T]):
    value: T
    age_ms: int
    hit: bool


class ProjectionCache(Generic[T]):
    """Small stampede-safe cache for read-only operator projections."""

    def __init__(
        self,
        ttl_seconds: float,
        *,
        max_entries: int = 64,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("projection cache TTL must be positive")
        if max_entries <= 0:
            raise ValueError("projection cache max_entries must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._entries: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()

    def get(self, key: Hashable, loader: Callable[[], T]) -> CachedProjection[T]:
        with self._lock:
            now = self.monotonic()
            existing = self._entries.get(key)
            if existing is not None and now - existing[0] < self.ttl_seconds:
                self._entries.move_to_end(key)
                return CachedProjection(
                    value=existing[1],
                    age_ms=max(0, round((now - existing[0]) * 1000)),
                    hit=True,
                )
            value = loader()
            loaded_at = self.monotonic()
            self._entries[key] = (loaded_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return CachedProjection(value=value, age_ms=0, hit=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
