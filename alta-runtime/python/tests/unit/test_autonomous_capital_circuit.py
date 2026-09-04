import threading
from types import SimpleNamespace

from alta_asterism.autonomous import AutonomousRunner
from alta_asterism.contracts import Environment
from alta_asterism.paper_execution import PaperCapitalCircuitOpen


def test_capital_circuit_terminates_runner_without_retry(monkeypatch) -> None:
    notifications: list[tuple[str, dict]] = []
    recorded: list[bool] = []
    closed: list[bool] = []
    runtime = SimpleNamespace(
        orchestrator=SimpleNamespace(
            run=lambda *_args: (_ for _ in ()).throw(
                PaperCapitalCircuitOpen("uncertain broker mutation")
            )
        ),
        close=lambda: closed.append(True),
    )
    runner = object.__new__(AutonomousRunner)
    runner.database = SimpleNamespace(assert_autonomous_fence=lambda: None)
    runner.settings = SimpleNamespace(environment=Environment.SHADOW)
    runner.runtime_factory = lambda *_args: runtime
    runner.state_callback = lambda state, detail: notifications.append((state, detail))
    runner.evaluation = SimpleNamespace(
        bind_cycle=lambda *_args: None,
        incomplete_cycles=lambda: (),
    )
    runner._record_failure = lambda *_args, **kwargs: recorded.append(
        kwargs["retry_scheduled"]
    )
    monkeypatch.setattr(
        "alta_asterism.autonomous.acquire_autonomous_owner", lambda _database: object()
    )
    monkeypatch.setattr(
        "alta_asterism.autonomous.release_autonomous_owner", lambda _owner: None
    )
    monkeypatch.setattr(
        "alta_asterism.autonomous.ScoutRepository",
        lambda _database: SimpleNamespace(reconcile_expired_activity=lambda _at: None),
    )

    assert runner.run(threading.Event(), once=False) == 1
    assert recorded == [False]
    assert notifications[-1][1]["cycle_result"] == "capital_circuit_open"
    assert closed == [True]
