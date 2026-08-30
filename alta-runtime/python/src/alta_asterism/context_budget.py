"""Shared byte budgets for durable Agent hand-offs.

The limits live together so a new role cannot silently choose a larger context
than PostgreSQL, the App Server prompt, or the replay contract can preserve.
All measurements use the same canonical UTF-8 JSON representation.
"""

import json
from typing import Any

MAX_FROZEN_SCOUT_INPUT_BYTES = 16_000
MAX_PERSISTED_SCOUT_SNAPSHOT_BYTES = 7_000
MAX_SCOUT_PROMPT_BYTES = 12_000
MAX_ROLE_FROZEN_INPUT_BYTES = 8_000
MAX_ROLE_PROMPT_BYTES = 16_000


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode()


def json_size(value: Any) -> int:
    # PostgreSQL's ``jsonb::text`` renders separators with spaces.  The durable
    # run constraint measures that representation rather than the compact JSON
    # used for hashes and model prompts, so size hand-offs the same way here.
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode()
    )


def require_json_budget(value: Any, maximum_bytes: int, message: str) -> None:
    if json_size(value) > maximum_bytes:
        raise ValueError(message)


def bounded_utf8(value: str | None, maximum_bytes: int) -> str | None:
    if value is None:
        return None
    encoded = value.encode()
    if len(encoded) <= maximum_bytes:
        return value
    return encoded[:maximum_bytes].decode(errors="ignore").rstrip()
