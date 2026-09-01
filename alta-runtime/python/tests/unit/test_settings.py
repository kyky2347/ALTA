import pytest
from pydantic import ValidationError

from alta_asterism.contracts import Environment, Settings
from alta_asterism.service import _write_json_response, _write_sse, serve


class _DisconnectedStream:
    def write(self, _body: bytes) -> None:
        raise BrokenPipeError

    def flush(self) -> None:
        raise AssertionError("flush must not follow a disconnected write")


class _DisconnectedHandler:
    close_connection = False
    wfile = _DisconnectedStream()

    def send_response(self, _status: int) -> None:
        return

    def send_header(self, _name: str, _value: str) -> None:
        return

    def end_headers(self) -> None:
        return


def test_settings_redact_runtime_urls_and_default_to_replay() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://user:database-secret@127.0.0.1/alta",
        REDIS_URL="redis://:redis-secret@127.0.0.1/0",
    )

    assert settings.environment is Environment.REPLAY
    assert settings.safe_dump() == {
        "database_url": "**********",
        "redis_url": "**********",
        "environment": "replay",
        "service_host": "127.0.0.1",
        "service_port": 8765,
        "credential_revision": "unmanaged",
        "credential_slots": (),
        "autonomous_enabled": False,
        "autonomous_interval_seconds": 1_800,
        "autonomous_follow_up_interval_seconds": 900,
        "autonomous_position_interval_seconds": 300,
        "autonomous_heartbeat_seconds": 30,
        "autonomous_failure_backoff_seconds": 60,
        "autonomous_failure_backoff_max_seconds": 1_800,
        "autonomous_cycle_timeout_seconds": 3_600,
        "evaluation_cohort_id": "exploratory-v1",
        "evaluation_min_closed_positions": 30,
        "supervisor_restart_max_seconds": 300,
        "supervisor_stable_uptime_seconds": 600,
        "supervisor_probe_seconds": 5,
        "supervisor_unhealthy_grace_seconds": 120,
        "supervisor_unresponsive_grace_seconds": 15,
        "supervisor_shutdown_grace_seconds": 30,
        "massive_enabled": True,
        "massive_discovery_enabled": False,
        "massive_max_requests_per_cycle": 8,
        "massive_configured": False,
        "massive_custom_base": False,
        "massive_insecure_http_allowed": False,
        "massive_auth_mode": "bearer",
        "shadow_max_position_notional": "10000",
        "shadow_portfolio_policy": {
            "reference_nav": "1000000",
            "trade_loss_budget_bps": "25",
            "max_position_nav_bps": "100",
            "max_gross_nav_bps": "800",
            "max_underlying_nav_bps": "150",
            "equity_stress_floor_bps": "2500",
            "max_exit_days": 2,
            "adv_participation_bps": "500",
            "min_net_alpha_bps": "50",
        },
        "agent_provider": "deepseek",
        "agent_model": "deepseek-v4-flash",
        "agent_reasoning_effort": "high",
        "role_models": {
            "thesis_assessor": {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            },
            "disconfirming_assessor": {
                "provider": "grok",
                "model": "grok-4.6",
            },
            "discussion_moderator": {"provider": "kimi", "model": "kimi-k3"},
            "expression_agent": {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            },
            "expression_auditor": {"provider": "grok", "model": "grok-4.6"},
        },
        "agent_deadline_seconds": 180,
        "reasoning_agent_deadline_seconds": 300,
        "scout_concurrency": 4,
        "agent_workspace": ".alta/agent-workspace",
        "universe": (
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "META",
            "TSLA",
            "AVGO",
            "JPM",
            "XOM",
            "LLY",
            "UNH",
        ),
        "tiger_paper_enabled": False,
        "tiger_paper_configured": False,
        "tiger_order_timeout_seconds": 20,
        "acceptance_hold_seconds": None,
    }
    assert "database-secret" not in repr(settings)
    assert "redis-secret" not in repr(settings)


def test_settings_accept_the_complete_gateway_credential_inventory() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://fixture.invalid/alta",
        REDIS_URL="redis://fixture.invalid/0",
        ALTA_CREDENTIAL_SLOTS=(
            "deepseek,xai,kimi,massive,finlight,finnhub,brave,jina,openalex"
        ),
    )

    assert settings.credential_slots == (
        "deepseek",
        "xai",
        "kimi",
        "massive",
        "finlight",
        "finnhub",
        "brave",
        "jina",
        "openalex",
    )


def test_agent_deadline_is_bounded_and_configurable() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }

    settings = Settings(
        **baseline,
        ALTA_AGENT_DEADLINE_SECONDS=30,
        ALTA_REASONING_AGENT_DEADLINE_SECONDS=240,
    )

    assert settings.agent_deadline_seconds == 30
    assert settings.reasoning_agent_deadline_seconds == 240
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_AGENT_DEADLINE_SECONDS=14)
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_AGENT_DEADLINE_SECONDS=601)
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_REASONING_AGENT_DEADLINE_SECONDS=29)
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_REASONING_AGENT_DEADLINE_SECONDS=901)


def test_shadow_portfolio_limits_are_internally_consistent() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }

    settings = Settings(**baseline)

    assert settings.shadow_reference_nav == 1_000_000
    assert settings.shadow_trade_loss_budget_bps == 25
    assert settings.shadow_max_underlying_nav_bps == 150
    with pytest.raises(ValidationError, match="position NAV limit"):
        Settings(**baseline, ALTA_SHADOW_MAX_POSITION_NAV_BPS=900)
    with pytest.raises(ValidationError, match="underlying NAV limit"):
        Settings(**baseline, ALTA_SHADOW_MAX_UNDERLYING_NAV_BPS=50)
    with pytest.raises(ValidationError, match="cannot exceed the NAV position limit"):
        Settings(**baseline, ALTA_SHADOW_REFERENCE_NAV=100_000)


def test_scouts_default_to_flash_but_allow_a_validated_provider_fallback() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }

    settings = Settings(**baseline)

    assert (settings.agent_provider, settings.agent_model) == (
        "deepseek",
        "deepseek-v4-flash",
    )
    openai = Settings(
        **baseline,
        ALTA_AGENT_PROVIDER="openai",
        ALTA_AGENT_MODEL="gpt-5.6-terra",
    )
    assert (openai.agent_provider, openai.agent_model) == (
        "openai",
        "gpt-5.6-terra",
    )
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_AGENT_PROVIDER="anthropic")
    kimi = Settings(
        **baseline,
        ALTA_AGENT_PROVIDER="kimi",
        ALTA_AGENT_MODEL="kimi-k3",
    )
    assert (kimi.agent_provider, kimi.agent_model) == ("kimi", "kimi-k3")
    with pytest.raises(ValidationError, match="Scout model does not belong"):
        Settings(
            **baseline,
            ALTA_AGENT_PROVIDER="kimi",
            ALTA_AGENT_MODEL="deepseek-v4-pro",
        )

    with pytest.raises(ValidationError, match="private debate"):
        Settings(
            **baseline,
            ALTA_DISCONFIRMING_PROVIDER="deepseek",
            ALTA_DISCONFIRMING_MODEL="deepseek-v4-pro",
        )
    with pytest.raises(ValidationError, match="expression and audit"):
        Settings(
            **baseline,
            ALTA_AUDIT_PROVIDER="deepseek",
            ALTA_AUDIT_MODEL="deepseek-v4-pro",
        )
    with pytest.raises(ValidationError, match="does not belong"):
        Settings(
            **baseline,
            ALTA_MODERATOR_PROVIDER="kimi",
            ALTA_MODERATOR_MODEL="grok-4.6",
        )


def test_scout_concurrency_is_bounded_by_the_fixed_scout_team() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }

    settings = Settings(**baseline, ALTA_SCOUT_CONCURRENCY=2)

    assert settings.scout_concurrency == 2
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_SCOUT_CONCURRENCY=0)
    with pytest.raises(ValidationError):
        Settings(**baseline, ALTA_SCOUT_CONCURRENCY=5)


def test_autonomous_recovery_windows_are_consistent() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }

    settings = Settings(
        **baseline,
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS=10,
        ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS=40,
        ALTA_AUTONOMOUS_CYCLE_TIMEOUT_SECONDS=300,
        ALTA_AGENT_DEADLINE_SECONDS=60,
        ALTA_REASONING_AGENT_DEADLINE_SECONDS=60,
    )

    assert (
        settings.autonomous_failure_backoff_seconds,
        settings.autonomous_failure_backoff_max_seconds,
        settings.autonomous_cycle_timeout_seconds,
    ) == (10, 40, 300)
    with pytest.raises(ValidationError, match="backoff max"):
        Settings(
            **baseline,
            ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS=60,
            ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS=30,
        )
    with pytest.raises(ValidationError, match="four Agent deadlines"):
        Settings(
            **baseline,
            ALTA_AUTONOMOUS_CYCLE_TIMEOUT_SECONDS=180,
            ALTA_AGENT_DEADLINE_SECONDS=180,
            ALTA_REASONING_AGENT_DEADLINE_SECONDS=180,
        )


def test_live_environment_is_not_a_valid_contract() -> None:
    try:
        Settings(
            DATABASE_URL="postgresql://fixture.invalid/alta",
            REDIS_URL="redis://fixture.invalid/0",
            ALTA_ENVIRONMENT="live",
        )
    except ValidationError as error:
        assert "live" in str(error)
    else:
        raise AssertionError("live environment was accepted")


def test_service_fails_closed_for_remote_unauthenticated_or_autonomous_replay() -> None:
    baseline = {
        "DATABASE_URL": "postgresql://fixture.invalid/alta",
        "REDIS_URL": "redis://fixture.invalid/0",
    }
    with pytest.raises(ValueError, match="ALTA_API_TOKEN"):
        serve(Settings(**baseline), "0.0.0.0", 0)
    with pytest.raises(ValueError, match="ALTA_ENVIRONMENT=shadow"):
        serve(
            Settings(**baseline, ALTA_AUTONOMOUS_ENABLED=True),
            "127.0.0.1",
            0,
        )


def test_sse_client_disconnect_is_a_normal_transport_outcome() -> None:
    _write_sse(_DisconnectedStream(), [])


def test_json_client_disconnect_is_a_normal_transport_outcome() -> None:
    handler = _DisconnectedHandler()

    _write_json_response(handler, 200, {"status": "live"})

    assert handler.close_connection is True
