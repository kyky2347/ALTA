import pytest

from alta_asterism.mind_usage import cumulative_thread_usage


def snapshot(scale=1):
    return {
        "input_tokens": 100 * scale,
        "cached_input_tokens": 80 * scale,
        "output_tokens": 60 * scale,
        "reasoning_output_tokens": 10 * scale,
        "total_tokens": 160 * scale,
    }


def test_thread_totals_are_not_added_again_after_finalization():
    assert cumulative_thread_usage([snapshot(), snapshot(2)]) == snapshot(2)
    assert cumulative_thread_usage([snapshot()]) == snapshot()


@pytest.mark.parametrize(
    "snapshots",
    [
        [],
        [None],
        [snapshot(), None],
        [None, snapshot()],
        [snapshot(2), snapshot()],
        [{**snapshot(), "input_tokens": -1}],
        [{**snapshot(), "total_tokens": True}],
        [{**snapshot(), "cached_input_tokens": 101}],
        [{**snapshot(), "input_tokens": 161}],
        [{**snapshot(), "output_tokens": 161}],
        [{}],
    ],
)
def test_unknown_or_invalid_cost_never_becomes_free(snapshots):
    assert cumulative_thread_usage(snapshots) is None
