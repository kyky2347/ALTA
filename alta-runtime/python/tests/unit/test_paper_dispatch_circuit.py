from types import SimpleNamespace

import pytest

from alta_asterism.agentic_position import AgenticPositionBook
from alta_asterism.paper_execution import (
    PaperCapitalCircuitOpen,
    PaperExecutionResult,
)


class _IntentStore:
    def __init__(self) -> None:
        self.states: list[str] = []

    def mark_dispatching(self, _intent_id: str) -> None:
        self.states.append("dispatching")

    def record_result(self, _intent_id: str, result: PaperExecutionResult):
        self.states.append(result.status)
        return SimpleNamespace(intent_id="intent_one", state="broker_filled")

    def mark_manual_review(self, _intent_id: str, code: str) -> None:
        self.states.append(f"manual_review:{code}")


@pytest.mark.parametrize(
    "action,before,after",
    [("BUY", "0", "1"), ("SELL", "1", "0")],
)
def test_post_dispatch_exception_reconciles_late_fill_before_returning(
    action: str, before: str, after: str
) -> None:
    book = object.__new__(AgenticPositionBook)
    store = _IntentStore()
    result = PaperExecutionResult(
        status="filled",
        action=action,
        symbol="SPY",
        quantity="1",
        position_before=before,
        position_after=after,
        average_fill_price="500",
        broker_order_hash="a" * 64,
    )
    executor = SimpleNamespace(reconcile=lambda _durable: result)
    book.paper_intents = store
    book.paper_executor = executor
    durable = SimpleNamespace(intent_id="intent_one")

    persisted, observed = book._dispatch_and_persist(
        durable, lambda: (_ for _ in ()).throw(TimeoutError("kill point"))
    )

    assert observed == result
    assert persisted.state == "broker_filled"
    assert store.states == ["dispatching", "filled"]


def test_post_dispatch_unresolved_result_opens_global_capital_circuit() -> None:
    book = object.__new__(AgenticPositionBook)
    store = _IntentStore()
    result = PaperExecutionResult(
        status="unresolved",
        action="BUY",
        symbol="SPY",
        quantity="1",
        position_before="0",
        position_after="0",
        average_fill_price=None,
        broker_order_hash=None,
    )
    book.paper_intents = store
    book.paper_executor = SimpleNamespace(reconcile=lambda _durable: result)

    with pytest.raises(PaperCapitalCircuitOpen, match="unresolved"):
        book._dispatch_and_persist(
            SimpleNamespace(intent_id="intent_one"),
            lambda: (_ for _ in ()).throw(TimeoutError("kill point")),
        )

    assert store.states == [
        "dispatching",
        "manual_review:broker_history_unresolved",
    ]
