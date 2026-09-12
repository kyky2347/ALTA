import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from alta_asterism.contracts import Settings
from alta_asterism.scout_model_router import ScoutModelRouter
from alta_asterism.scout_batch import MindWorker
from alta_asterism.scouts import SCOUTS, FrozenScoutInput, RunBudget


def settings(**kwargs):
    return Settings(
        DATABASE_URL="postgresql://localhost/alta",
        REDIS_URL="redis://localhost/0",
        **kwargs,
    )


def test_model_overrides_are_validated_and_reported(monkeypatch):
    monkeypatch.setenv(
        "ALTA_SCOUT_MODEL_OVERRIDES",
        '{"change_event_scout":{"provider":"kimi","model":"kimi-k3"}}',
    )
    value = settings(ALTA_POSITION_PROVIDER="grok", ALTA_POSITION_MODEL="grok-4.6")
    assert value.scout_model_overrides["change_event_scout"].model == "kimi-k3"
    assert value.safe_dump()["role_models"]["position_reviewer"]["model"] == "grok-4.6"
    for bad in [
        '{"unknown":{"provider":"kimi","model":"kimi-k3"}}',
        '{"change_event_scout":{"provider":"kimi","model":"grok-4.6"}}',
        '{"change_event_scout":{"provider":"kimi","model":"kimi-k3","secret":"not-allowed"}}',
    ]:
        with pytest.raises(ValidationError):
            settings(ALTA_SCOUT_MODEL_OVERRIDES=json.loads(bad))
    with pytest.raises(ValidationError):
        settings(ALTA_POSITION_PROVIDER="kimi")


def test_dispatch_uses_the_persisted_route_and_never_falls_back():
    calls = []

    def client(label):
        return SimpleNamespace(
            run=lambda spec, prompt, schema: calls.append(
                (label, spec.model_id, prompt)
            )
        )

    router = ScoutModelRouter(
        {
            ("deepseek", "deepseek-v4-flash"): client("default"),
            ("kimi", "kimi-k3"): client("override"),
        }
    )
    router.run(
        SimpleNamespace(model_provider="kimi", model_id="kimi-k3"), "evidence", {}
    )
    assert calls == [("override", "kimi-k3", "evidence")]
    with pytest.raises(ValueError, match="refusing silent fallback"):
        router.run(
            SimpleNamespace(model_provider="grok", model_id="grok-unknown"),
            "evidence",
            {},
        )


def test_worker_freezes_individual_model_before_dispatch():
    now = datetime(2026, 9, 12, tzinfo=UTC)
    frozen = FrozenScoutInput(
        wake_id="routing-check",
        environment="replay",
        known_at=now,
        universe=("DEMO",),
        evidence=(),
        expectation_posture="available",
    )
    worker = MindWorker(
        repository=SimpleNamespace(),
        client=SimpleNamespace(),
        model_provider="deepseek",
        model_id="deepseek-v4-flash",
        model_overrides={SCOUTS[0].scout_id: ("kimi", "kimi-k3")},
        budget=RunBudget(
            max_tool_calls=2, max_total_tokens=2000, max_output_bytes=8192
        ),
        deadline_seconds=60,
    )
    override = worker._build_run_spec(
        "batch", frozen, SCOUTS[0], now + timedelta(seconds=60)
    )
    inherited = worker._build_run_spec(
        "batch", frozen, SCOUTS[1], now + timedelta(seconds=60)
    )
    assert (override.model_provider, override.model_id) == ("kimi", "kimi-k3")
    assert (inherited.model_provider, inherited.model_id) == (
        "deepseek",
        "deepseek-v4-flash",
    )
