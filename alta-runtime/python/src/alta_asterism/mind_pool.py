from __future__ import annotations

import threading
from collections.abc import Sequence
from queue import Queue
from typing import TYPE_CHECKING

from .scouts import ScoutRunSpec

if TYPE_CHECKING:
    from .mind_worker import MindClient, ModelTurn


class MindClientPool:
    """Leases independent App Server clients to concurrent agent runs."""

    def __init__(self, clients: Sequence[MindClient]) -> None:
        if not clients:
            raise ValueError("mind client pool requires at least one client")
        self._clients = tuple(clients)
        self._available: Queue[MindClient] = Queue(maxsize=len(self._clients))
        for client in self._clients:
            self._available.put_nowait(client)
        self._close_lock = threading.Lock()
        self._closed = False

    def run(
        self, spec: ScoutRunSpec, prompt: str, schema: dict[str, object]
    ) -> ModelTurn:
        if self._closed:
            raise RuntimeError("mind client pool is closed")
        client = self._available.get()
        try:
            return client.run(spec, prompt, schema)
        finally:
            self._available.put_nowait(client)

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            for client in self._clients:
                client.close()

    def __enter__(self) -> MindClientPool:
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()
