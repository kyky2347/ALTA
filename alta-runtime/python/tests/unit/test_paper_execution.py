import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from alta_asterism.live_runtime import LiveRuntime
from alta_asterism.paper_execution import TigerPaperExecutor


def test_executor_uses_frozen_isolated_process_and_secret_allowlist(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def run(command, **kwargs):
        captured.update({"command": command, **kwargs})
        result = {
            "status": "filled",
            "action": "BUY",
            "symbol": "SPY",
            "quantity": "1",
            "position_before": "0",
            "position_after": "1",
            "average_fill_price": "100.50",
            "broker_order_hash": "a" * 64,
        }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "result": result}),
        )

    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )
    monkeypatch.setattr("alta_asterism.paper_execution.subprocess.run", run)
    monkeypatch.setenv("MASSIVE_API_KEY", "must-not-cross")
    monkeypatch.setenv("FINLIGHT_API_KEY", "must-not-cross")
    monkeypatch.setenv("TIGER_SECRET", "must-not-cross")
    executor = TigerPaperExecutor(
        repo_root=tmp_path,
        config_path=tmp_path / "paper.properties",
        account_sha256="a" * 64,
        timeout_seconds=20,
    )

    result = executor.open(
        "SPY",
        Decimal("100"),
        "paper-cycle",
        limit_offset_bps=Decimal("10"),
    )

    assert (result.status, result.position_after) == ("filled", "1")
    assert captured["command"][0:3] == ["/uv", "run", "--frozen"]
    assert captured["command"][-4:] == [
        "--symbol",
        "SPY",
        "--limit-price",
        "100.10",
    ]
    assert captured["cwd"] == tmp_path
    assert captured["timeout"] == 50
    assert "MASSIVE_API_KEY" not in captured["env"]
    assert "FINLIGHT_API_KEY" not in captured["env"]
    assert "TIGER_SECRET" not in captured["env"]
    assert captured["env"]["UV_PROJECT_ENVIRONMENT"].endswith("/.alta/capital/venv")


def test_acceptance_always_runs_final_preflight_when_flatten_fails() -> None:
    class Executor:
        def __init__(self) -> None:
            self.preflight_calls = 0

        def preflight(self):
            self.preflight_calls += 1
            return {"positionCount": 0, "openOrderCount": 0}

    class Positions:
        def ensure_cycle_paper_flat(self, _cycle_id):
            raise ValueError("synthetic flatten failure")

    class Orchestrator:
        shadow = SimpleNamespace(positions=Positions())

        def run(self, _cycle_id, _wake_at):
            raise ValueError("synthetic pipeline failure")

    executor = Executor()
    runtime = object.__new__(LiveRuntime)
    runtime.paper_executor = executor
    runtime.settings = SimpleNamespace(acceptance_hold_seconds=2)
    runtime.massive_budget = None
    runtime.orchestrator = Orchestrator()

    with pytest.raises(RuntimeError, match="safety flatten failed"):
        runtime.run_acceptance("paper-acceptance-test")

    assert executor.preflight_calls == 1


def test_executor_uses_the_frozen_absolute_limit_instead_of_repricing(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        result = {
            "status": "not_filled",
            "action": "BUY",
            "symbol": "SPY",
            "quantity": "1",
            "position_before": "0",
            "position_after": "0",
            "average_fill_price": None,
            "broker_order_hash": "b" * 64,
        }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "result": result}),
        )

    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )
    monkeypatch.setattr("alta_asterism.paper_execution.subprocess.run", run)
    executor = TigerPaperExecutor(
        repo_root=tmp_path,
        config_path=tmp_path / "paper.properties",
        account_sha256="a" * 64,
        timeout_seconds=20,
    )

    executor.open(
        "SPY",
        Decimal("102"),
        "paper-frozen-limit",
        limit_offset_bps=Decimal("25"),
        absolute_limit_price=Decimal("100.07"),
    )

    assert captured["command"][-1] == "100.07"


def test_acceptance_rejects_a_remaining_open_order() -> None:
    class Executor:
        def preflight(self):
            return {"positionCount": 0, "openOrderCount": 1}

    class Positions:
        def ensure_cycle_paper_flat(self, _cycle_id):
            return ()

    class Orchestrator:
        shadow = SimpleNamespace(positions=Positions())

        def run(self, _cycle_id, _wake_at):
            raise ValueError("synthetic pipeline failure")

    runtime = object.__new__(LiveRuntime)
    runtime.paper_executor = Executor()
    runtime.settings = SimpleNamespace(acceptance_hold_seconds=2)
    runtime.massive_budget = None
    runtime.orchestrator = Orchestrator()

    with pytest.raises(ValueError, match="order-free"):
        runtime.run_acceptance("paper-acceptance-test")
