"""Replayable starting lanes, not market facts, recommendations or quotas."""

import hashlib


def exploration_start(
    wake_id: str, scout_id: str, universe: tuple[str, ...]
) -> tuple[str, ...]:
    ordered = sorted(
        universe,
        key=lambda symbol: hashlib.sha256(
            f"{wake_id}:{scout_id}:{symbol}".encode()
        ).digest(),
    )
    return tuple(ordered[:3])
