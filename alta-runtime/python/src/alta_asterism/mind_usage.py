"""Validate cumulative App Server usage for one fresh, non-resumed thread."""

from collections.abc import Sequence

USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def cumulative_thread_usage(
    snapshots: Sequence[dict[str, int] | None],
) -> dict[str, int] | None:
    """Use the final cumulative snapshot, never sum thread totals across turns.

    Missing, negative, or regressing counters are unknown usage and fail closed
    at the existing budget admission boundary. No estimation hides missing cost.
    """
    previous = dict.fromkeys(USAGE_FIELDS, 0)
    if not snapshots:
        return None
    for snapshot in snapshots:
        if snapshot is None or any(
            type(snapshot.get(field)) is not int or snapshot[field] < previous[field]
            for field in USAGE_FIELDS
        ):
            return None
        if (
            snapshot["cached_input_tokens"] > snapshot["input_tokens"]
            or snapshot["input_tokens"] > snapshot["total_tokens"]
            or snapshot["output_tokens"] > snapshot["total_tokens"]
        ):
            return None
        previous = {field: snapshot[field] for field in USAGE_FIELDS}
    return previous
