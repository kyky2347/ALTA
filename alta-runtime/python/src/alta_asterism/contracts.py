import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from .scout_limits import (
    DEFAULT_SCOUT_DEADLINE_SECONDS,
    DEFAULT_SCOUT_TOKEN_BUDGET,
    MAX_SCOUT_TOKEN_BUDGET,
)

AgentProvider = Literal["openai", "deepseek", "grok", "kimi"]
MODEL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$"


class AgentModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: AgentProvider
    model: str = Field(pattern=MODEL_ID_PATTERN)

    @model_validator(mode="after")
    def matching_provider(self) -> "AgentModelRoute":
        prefix = {
            "openai": "gpt-",
            "deepseek": "deepseek-",
            "grok": "grok-",
            "kimi": "kimi-",
        }
        if not self.model.lower().startswith(prefix[self.provider]):
            raise ValueError("model does not belong to provider")
        return self


class Environment(StrEnum):
    REPLAY = "replay"
    SHADOW = "shadow"
    PAPER = "paper"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    redis_url: SecretStr = Field(validation_alias="REDIS_URL")
    environment: Environment = Field(
        default=Environment.REPLAY, validation_alias="ALTA_ENVIRONMENT"
    )
    service_host: str = Field(default="127.0.0.1", validation_alias="ALTA_SERVICE_HOST")
    service_port: int = Field(
        default=8765, ge=0, le=65535, validation_alias="ALTA_SERVICE_PORT"
    )
    api_token: SecretStr | None = Field(default=None, validation_alias="ALTA_API_TOKEN")
    credential_revision: str = Field(
        default="unmanaged",
        pattern=r"^(?:unmanaged|[a-f0-9]{16})$",
        validation_alias="ALTA_CREDENTIAL_REVISION",
    )
    credential_slots_csv: str = Field(
        default="", validation_alias="ALTA_CREDENTIAL_SLOTS"
    )
    finlight_api_key: SecretStr | None = Field(
        default=None, validation_alias="FINLIGHT_API_KEY"
    )
    massive_api_key: SecretStr | None = Field(
        default=None, validation_alias="MASSIVE_API_KEY"
    )
    massive_base_url: SecretStr = Field(
        default=SecretStr("https://api.massive.com"),
        validation_alias="ALTA_MASSIVE_BASE_URL",
    )
    massive_allow_insecure_http: bool = Field(
        default=False,
        validation_alias="ALTA_MASSIVE_ALLOW_INSECURE_HTTP",
    )
    massive_auth_mode: Literal["bearer", "x_api_key", "x_proxy_key"] = Field(
        default="bearer",
        validation_alias="ALTA_MASSIVE_AUTH_MODE",
    )
    massive_enabled: bool = Field(default=True, validation_alias="ALTA_MASSIVE_ENABLED")
    massive_discovery_enabled: bool = Field(
        default=False,
        validation_alias="ALTA_MASSIVE_DISCOVERY_ENABLED",
    )
    massive_max_requests_per_cycle: int = Field(
        default=8,
        ge=2,
        le=20,
        validation_alias="ALTA_MASSIVE_MAX_REQUESTS_PER_CYCLE",
    )
    shadow_max_position_notional: Decimal = Field(
        default=Decimal("10000"),
        gt=0,
        le=Decimal("1000000"),
        validation_alias="ALTA_SHADOW_MAX_POSITION_NOTIONAL",
    )
    shadow_reference_nav: Decimal = Field(
        default=Decimal("1000000"),
        gt=0,
        validation_alias="ALTA_SHADOW_REFERENCE_NAV",
    )
    shadow_trade_loss_budget_bps: Decimal = Field(
        default=Decimal("25"),
        gt=0,
        validation_alias="ALTA_SHADOW_TRADE_LOSS_BUDGET_BPS",
    )
    shadow_max_position_nav_bps: Decimal = Field(
        default=Decimal("100"),
        gt=0,
        validation_alias="ALTA_SHADOW_MAX_POSITION_NAV_BPS",
    )
    shadow_max_gross_nav_bps: Decimal = Field(
        default=Decimal("800"),
        gt=0,
        validation_alias="ALTA_SHADOW_MAX_GROSS_NAV_BPS",
    )
    shadow_max_underlying_nav_bps: Decimal = Field(
        default=Decimal("150"),
        gt=0,
        validation_alias="ALTA_SHADOW_MAX_UNDERLYING_NAV_BPS",
    )
    shadow_equity_stress_floor_bps: Decimal = Field(
        default=Decimal("2500"),
        gt=0,
        le=Decimal("10000"),
        validation_alias="ALTA_SHADOW_EQUITY_STRESS_FLOOR_BPS",
    )
    shadow_max_exit_days: int = Field(
        default=2,
        ge=1,
        le=20,
        validation_alias="ALTA_SHADOW_MAX_EXIT_DAYS",
    )
    shadow_adv_participation_bps: Decimal = Field(
        default=Decimal("500"),
        gt=0,
        le=Decimal("2000"),
        validation_alias="ALTA_SHADOW_ADV_PARTICIPATION_BPS",
    )
    shadow_min_net_alpha_bps: Decimal = Field(
        default=Decimal("50"),
        ge=0,
        validation_alias="ALTA_SHADOW_MIN_NET_ALPHA_BPS",
    )
    autonomous_enabled: bool = Field(
        default=False, validation_alias="ALTA_AUTONOMOUS_ENABLED"
    )
    autonomous_interval_seconds: int = Field(
        default=1_800,
        ge=60,
        le=86_400,
        validation_alias="ALTA_AUTONOMOUS_INTERVAL_SECONDS",
    )
    autonomous_follow_up_interval_seconds: int = Field(
        default=900,
        ge=60,
        le=86_400,
        validation_alias="ALTA_AUTONOMOUS_FOLLOW_UP_INTERVAL_SECONDS",
    )
    autonomous_position_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=86_400,
        validation_alias="ALTA_AUTONOMOUS_POSITION_INTERVAL_SECONDS",
    )
    autonomous_heartbeat_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        validation_alias="ALTA_AUTONOMOUS_HEARTBEAT_SECONDS",
    )
    autonomous_failure_backoff_seconds: int = Field(
        default=60,
        ge=1,
        le=3_600,
        validation_alias="ALTA_AUTONOMOUS_FAILURE_BACKOFF_SECONDS",
    )
    autonomous_failure_backoff_max_seconds: int = Field(
        default=1_800,
        ge=1,
        le=21_600,
        validation_alias="ALTA_AUTONOMOUS_FAILURE_BACKOFF_MAX_SECONDS",
    )
    autonomous_cycle_timeout_seconds: int = Field(
        default=3_600,
        ge=60,
        le=21_600,
        validation_alias="ALTA_AUTONOMOUS_CYCLE_TIMEOUT_SECONDS",
    )
    evaluation_cohort_id: str = Field(
        default="exploratory-v1",
        pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$",
        validation_alias="ALTA_EVALUATION_COHORT_ID",
    )
    evaluation_min_closed_positions: int = Field(
        default=30,
        ge=10,
        le=1_000,
        validation_alias="ALTA_EVALUATION_MIN_CLOSED_POSITIONS",
    )
    supervisor_restart_max_seconds: int = Field(
        default=300,
        ge=1,
        le=3_600,
        validation_alias="ALTA_SUPERVISOR_RESTART_MAX_SECONDS",
    )
    supervisor_stable_uptime_seconds: int = Field(
        default=600,
        ge=10,
        le=86_400,
        validation_alias="ALTA_SUPERVISOR_STABLE_UPTIME_SECONDS",
    )
    supervisor_probe_seconds: float = Field(
        default=5,
        ge=0.1,
        le=60,
        validation_alias="ALTA_SUPERVISOR_PROBE_SECONDS",
    )
    supervisor_unhealthy_grace_seconds: int = Field(
        default=120,
        ge=1,
        le=3_600,
        validation_alias="ALTA_SUPERVISOR_UNHEALTHY_GRACE_SECONDS",
    )
    supervisor_unresponsive_grace_seconds: int = Field(
        default=15,
        ge=1,
        le=300,
        validation_alias="ALTA_SUPERVISOR_UNRESPONSIVE_GRACE_SECONDS",
    )
    supervisor_shutdown_grace_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        validation_alias="ALTA_SUPERVISOR_SHUTDOWN_GRACE_SECONDS",
    )
    agent_provider: AgentProvider = Field(
        default="deepseek",
        validation_alias="ALTA_AGENT_PROVIDER",
    )
    agent_model: str = Field(
        default="deepseek-v4-flash",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_AGENT_MODEL",
    )
    agent_reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="high", validation_alias="ALTA_AGENT_REASONING_EFFORT"
    )
    scout_model_overrides: dict[
        Literal[
            "change_event_scout",
            "market_dislocation_scout",
            "causal_policy_scout",
            "expectation_gap_scout",
        ],
        AgentModelRoute,
    ] = Field(default_factory=dict, validation_alias="ALTA_SCOUT_MODEL_OVERRIDES")
    position_provider: AgentProvider | None = Field(
        default=None, validation_alias="ALTA_POSITION_PROVIDER"
    )
    position_model: str | None = Field(
        default=None, pattern=MODEL_ID_PATTERN, validation_alias="ALTA_POSITION_MODEL"
    )
    thesis_provider: AgentProvider = Field(
        default="deepseek", validation_alias="ALTA_THESIS_PROVIDER"
    )
    thesis_model: str = Field(
        default="deepseek-v4-pro",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_THESIS_MODEL",
    )
    disconfirming_provider: AgentProvider = Field(
        default="grok", validation_alias="ALTA_DISCONFIRMING_PROVIDER"
    )
    disconfirming_model: str = Field(
        default="grok-4.6",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_DISCONFIRMING_MODEL",
    )
    moderator_provider: AgentProvider = Field(
        default="kimi", validation_alias="ALTA_MODERATOR_PROVIDER"
    )
    moderator_model: str = Field(
        default="kimi-k3",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_MODERATOR_MODEL",
    )
    expression_provider: AgentProvider = Field(
        default="deepseek", validation_alias="ALTA_EXPRESSION_PROVIDER"
    )
    expression_model: str = Field(
        default="deepseek-v4-pro",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_EXPRESSION_MODEL",
    )
    audit_provider: AgentProvider = Field(
        default="grok", validation_alias="ALTA_AUDIT_PROVIDER"
    )
    audit_model: str = Field(
        default="grok-4.6",
        pattern=MODEL_ID_PATTERN,
        validation_alias="ALTA_AUDIT_MODEL",
    )
    agent_deadline_seconds: int = Field(
        default=DEFAULT_SCOUT_DEADLINE_SECONDS,
        ge=15,
        le=600,
        validation_alias="ALTA_AGENT_DEADLINE_SECONDS",
    )
    reasoning_agent_deadline_seconds: int = Field(
        default=300,
        ge=30,
        le=900,
        validation_alias="ALTA_REASONING_AGENT_DEADLINE_SECONDS",
    )
    scout_concurrency: int = Field(
        default=4,
        ge=1,
        le=4,
        validation_alias="ALTA_SCOUT_CONCURRENCY",
    )
    agent_workspace: Path = Field(
        default=Path(".alta/agent-workspace"),
        validation_alias="ALTA_AGENT_WORKSPACE",
    )
    scout_max_tool_calls: int = Field(
        default=11, ge=1, le=12, validation_alias="ALTA_SCOUT_MAX_TOOL_CALLS"
    )
    scout_max_total_tokens: int = Field(
        default=DEFAULT_SCOUT_TOKEN_BUDGET,
        ge=1_000,
        le=MAX_SCOUT_TOKEN_BUDGET,
        validation_alias="ALTA_SCOUT_MAX_TOTAL_TOKENS",
    )
    universe_csv: str = Field(
        default="SPY,QQQ,IWM,DIA,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,JPM,XOM,LLY,UNH",
        validation_alias="ALTA_UNIVERSE",
    )
    tiger_paper_enabled: bool = Field(
        default=False,
        validation_alias="ALTA_TIGER_PAPER_ENABLED",
    )
    tiger_config_path: Path | None = Field(
        default=None,
        validation_alias="ALTA_TIGER_CONFIG_PATH",
    )
    tiger_paper_account_sha256: SecretStr | None = Field(
        default=None,
        validation_alias="ALTA_TIGER_PAPER_ACCOUNT_SHA256",
    )
    tiger_order_timeout_seconds: int = Field(
        default=20,
        ge=5,
        le=60,
        validation_alias="ALTA_TIGER_ORDER_TIMEOUT_SECONDS",
    )
    tiger_paper_max_order_notional: Decimal = Field(
        default=Decimal("10000"),
        gt=0,
        le=Decimal("1000000"),
        validation_alias="ALTA_TIGER_PAPER_MAX_ORDER_NOTIONAL",
    )
    tiger_paper_max_open_positions: int = Field(
        default=4,
        ge=1,
        le=8,
        validation_alias="ALTA_TIGER_PAPER_MAX_OPEN_POSITIONS",
    )
    tiger_paper_max_dispatch_quote_age_seconds: int = Field(
        default=10,
        ge=1,
        le=30,
        validation_alias="ALTA_TIGER_PAPER_MAX_DISPATCH_QUOTE_AGE_SECONDS",
    )
    tiger_paper_authorization_path: Path | None = Field(
        default=None,
        validation_alias="ALTA_TIGER_PAPER_AUTHORIZATION_PATH",
    )
    tiger_paper_authorization_generation: int | None = Field(
        default=None,
        ge=1,
        validation_alias="ALTA_TIGER_PAPER_AUTHORIZATION_GENERATION",
    )
    tiger_paper_owner_lease_path: Path | None = Field(
        default=None,
        validation_alias="ALTA_TIGER_PAPER_OWNER_LEASE_PATH",
    )
    tiger_paper_mutation_lease_path: Path | None = Field(
        default=None,
        validation_alias="ALTA_TIGER_PAPER_MUTATION_LEASE_PATH",
    )
    acceptance_hold_seconds: int | None = Field(
        default=None,
        ge=2,
        le=60,
        validation_alias="ALTA_ACCEPTANCE_HOLD_SECONDS",
    )

    @model_validator(mode="after")
    def runtime_configuration_is_consistent(self) -> "Settings":
        if (
            self.autonomous_failure_backoff_max_seconds
            < self.autonomous_failure_backoff_seconds
        ):
            raise ValueError(
                "autonomous failure backoff max must be at least the base backoff"
            )
        longest_agent_deadline = max(
            self.agent_deadline_seconds,
            self.reasoning_agent_deadline_seconds,
        )
        if self.autonomous_cycle_timeout_seconds < longest_agent_deadline * 4:
            raise ValueError(
                "autonomous cycle timeout must cover at least four Agent deadlines"
            )
        routes = {
            "thesis": (self.thesis_provider, self.thesis_model),
            "disconfirming": (
                self.disconfirming_provider,
                self.disconfirming_model,
            ),
            "moderator": (self.moderator_provider, self.moderator_model),
            "expression": (self.expression_provider, self.expression_model),
            "audit": (self.audit_provider, self.audit_model),
        }
        prefixes = {
            "openai": "gpt-",
            "deepseek": "deepseek-",
            "grok": "grok-",
            "kimi": "kimi-",
        }
        if not self.agent_model.lower().startswith(prefixes[self.agent_provider]):
            raise ValueError("Scout model does not belong to Scout provider")
        for role, (provider, model) in routes.items():
            if not model.lower().startswith(prefixes[provider]):
                raise ValueError(f"{role} model does not belong to {provider}")
        if routes["thesis"] == routes["disconfirming"]:
            raise ValueError("private debate requires two different models")
        if routes["expression"] == routes["audit"]:
            raise ValueError("expression and audit require two different models")
        if (self.position_provider is None) != (self.position_model is None):
            raise ValueError("position provider and model must be configured together")
        if self.position_model is not None:
            AgentModelRoute(provider=self.position_provider, model=self.position_model)
        if self.shadow_max_position_nav_bps > self.shadow_max_gross_nav_bps:
            raise ValueError("Shadow position NAV limit cannot exceed gross NAV limit")
        if self.shadow_max_underlying_nav_bps < self.shadow_max_position_nav_bps:
            raise ValueError(
                "Shadow underlying NAV limit cannot be below position NAV limit"
            )
        if self.shadow_max_underlying_nav_bps > self.shadow_max_gross_nav_bps:
            raise ValueError(
                "Shadow underlying NAV limit cannot exceed gross NAV limit"
            )
        configured_position_limit = (
            self.shadow_reference_nav
            * self.shadow_max_position_nav_bps
            / Decimal(10_000)
        )
        if self.shadow_max_position_notional > configured_position_limit:
            raise ValueError(
                "ALTA_SHADOW_MAX_POSITION_NOTIONAL cannot exceed the NAV position limit"
            )
        if not self.tiger_paper_enabled:
            return self
        if self.tiger_paper_max_order_notional > self.shadow_max_position_notional:
            raise ValueError(
                "Tiger Paper max order notional cannot exceed the audited Shadow position limit"
            )
        if self.environment is not Environment.SHADOW:
            raise ValueError("Tiger Paper mirroring requires ALTA_ENVIRONMENT=shadow")
        if self.tiger_config_path is None or not self.tiger_config_path.is_absolute():
            raise ValueError("Tiger Paper mirroring requires an absolute config path")
        required_paths = (
            self.tiger_paper_authorization_path,
            self.tiger_paper_owner_lease_path,
            self.tiger_paper_mutation_lease_path,
        )
        if any(path is None or not path.is_absolute() for path in required_paths):
            raise ValueError(
                "Tiger Paper mirroring requires absolute authorization and lease paths"
            )
        if self.tiger_paper_authorization_generation is None:
            raise ValueError(
                "Tiger Paper mirroring requires an authorization generation"
            )
        account_hash = (
            self.tiger_paper_account_sha256.get_secret_value()
            if self.tiger_paper_account_sha256 is not None
            else ""
        )
        if len(account_hash) != 64 or any(
            character not in "0123456789abcdef" for character in account_hash
        ):
            raise ValueError("Tiger Paper mirroring requires an account SHA-256")
        return self

    @property
    def database_dsn(self) -> str:
        return self.database_url.get_secret_value()

    @property
    def universe(self) -> tuple[str, ...]:
        values = tuple(
            dict.fromkeys(
                item.strip().upper()
                for item in self.universe_csv.split(",")
                if item.strip()
            )
        )
        if not 1 <= len(values) <= 50 or any(
            len(item) > 15 or not item.replace(".", "").replace("-", "").isalnum()
            for item in values
        ):
            raise ValueError("ALTA_UNIVERSE must contain 1..50 explicit symbols")
        return values

    @property
    def credential_slots(self) -> tuple[str, ...]:
        allowed = {
            "deepseek",
            "xai",
            "kimi",
            "massive",
            "finlight",
            "finnhub",
            "brave",
            "jina",
            "openalex",
        }
        values = tuple(
            dict.fromkeys(
                item.strip().lower()
                for item in self.credential_slots_csv.split(",")
                if item.strip()
            )
        )
        if len(values) > len(allowed) or any(item not in allowed for item in values):
            raise ValueError("ALTA_CREDENTIAL_SLOTS contains an unknown slot")
        return values

    def safe_dump(self) -> dict[str, Any]:
        return {
            "database_url": "**********",
            "redis_url": "**********",
            "environment": self.environment.value,
            "service_host": self.service_host,
            "service_port": self.service_port,
            "credential_revision": self.credential_revision,
            "credential_slots": self.credential_slots,
            "autonomous_enabled": self.autonomous_enabled,
            "autonomous_interval_seconds": self.autonomous_interval_seconds,
            "autonomous_follow_up_interval_seconds": (
                self.autonomous_follow_up_interval_seconds
            ),
            "autonomous_position_interval_seconds": (
                self.autonomous_position_interval_seconds
            ),
            "autonomous_heartbeat_seconds": self.autonomous_heartbeat_seconds,
            "autonomous_failure_backoff_seconds": (
                self.autonomous_failure_backoff_seconds
            ),
            "autonomous_failure_backoff_max_seconds": (
                self.autonomous_failure_backoff_max_seconds
            ),
            "autonomous_cycle_timeout_seconds": (self.autonomous_cycle_timeout_seconds),
            "evaluation_cohort_id": self.evaluation_cohort_id,
            "evaluation_min_closed_positions": (self.evaluation_min_closed_positions),
            "supervisor_restart_max_seconds": (self.supervisor_restart_max_seconds),
            "supervisor_stable_uptime_seconds": (self.supervisor_stable_uptime_seconds),
            "supervisor_probe_seconds": self.supervisor_probe_seconds,
            "supervisor_unhealthy_grace_seconds": (
                self.supervisor_unhealthy_grace_seconds
            ),
            "supervisor_unresponsive_grace_seconds": (
                self.supervisor_unresponsive_grace_seconds
            ),
            "supervisor_shutdown_grace_seconds": (
                self.supervisor_shutdown_grace_seconds
            ),
            "massive_enabled": self.massive_enabled,
            "massive_discovery_enabled": self.massive_discovery_enabled,
            "massive_max_requests_per_cycle": self.massive_max_requests_per_cycle,
            "massive_configured": self.massive_api_key is not None,
            "massive_custom_base": (
                self.massive_base_url.get_secret_value().rstrip("/")
                != "https://api.massive.com"
            ),
            "massive_insecure_http_allowed": self.massive_allow_insecure_http,
            "massive_auth_mode": self.massive_auth_mode,
            "shadow_max_position_notional": str(self.shadow_max_position_notional),
            "shadow_portfolio_policy": {
                "reference_nav": str(self.shadow_reference_nav),
                "trade_loss_budget_bps": str(self.shadow_trade_loss_budget_bps),
                "max_position_nav_bps": str(self.shadow_max_position_nav_bps),
                "max_gross_nav_bps": str(self.shadow_max_gross_nav_bps),
                "max_underlying_nav_bps": str(self.shadow_max_underlying_nav_bps),
                "equity_stress_floor_bps": str(self.shadow_equity_stress_floor_bps),
                "max_exit_days": self.shadow_max_exit_days,
                "adv_participation_bps": str(self.shadow_adv_participation_bps),
                "min_net_alpha_bps": str(self.shadow_min_net_alpha_bps),
            },
            "agent_provider": self.agent_provider,
            "agent_model": self.agent_model,
            "agent_reasoning_effort": self.agent_reasoning_effort,
            "scout_model_overrides": {
                key: value.model_dump()
                for key, value in self.scout_model_overrides.items()
            },
            "role_models": {
                "position_reviewer": {
                    "provider": self.position_provider or self.agent_provider,
                    "model": self.position_model or self.agent_model,
                },
                "thesis_assessor": {
                    "provider": self.thesis_provider,
                    "model": self.thesis_model,
                },
                "disconfirming_assessor": {
                    "provider": self.disconfirming_provider,
                    "model": self.disconfirming_model,
                },
                "discussion_moderator": {
                    "provider": self.moderator_provider,
                    "model": self.moderator_model,
                },
                "expression_agent": {
                    "provider": self.expression_provider,
                    "model": self.expression_model,
                },
                "expression_auditor": {
                    "provider": self.audit_provider,
                    "model": self.audit_model,
                },
            },
            "agent_deadline_seconds": self.agent_deadline_seconds,
            "reasoning_agent_deadline_seconds": (self.reasoning_agent_deadline_seconds),
            "scout_concurrency": self.scout_concurrency,
            "agent_workspace": str(self.agent_workspace),
            "universe": self.universe,
            "scout_max_tool_calls": self.scout_max_tool_calls,
            "scout_max_total_tokens": self.scout_max_total_tokens,
            "tiger_paper_enabled": self.tiger_paper_enabled,
            "tiger_paper_configured": (
                self.tiger_config_path is not None
                and self.tiger_paper_account_sha256 is not None
            ),
            "tiger_order_timeout_seconds": self.tiger_order_timeout_seconds,
            "tiger_paper_max_order_notional": str(self.tiger_paper_max_order_notional),
            "tiger_paper_max_open_positions": self.tiger_paper_max_open_positions,
            "tiger_paper_max_dispatch_quote_age_seconds": (
                self.tiger_paper_max_dispatch_quote_age_seconds
            ),
            "acceptance_hold_seconds": self.acceptance_hold_seconds,
        }


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=3, max_length=128)
    environment: Environment
    version: int = Field(ge=1)
    known_at: datetime

    @field_validator("known_at")
    @classmethod
    def known_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("known_at must be timezone-aware")
        return value


class Job(Record):
    kind: str = Field(min_length=1, max_length=64)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    subject_id: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=0, ge=-100, le=100)


class Run(Record):
    job_id: str | None = None
    role: str = Field(min_length=1, max_length=64)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None = Field(default=None, max_length=64)


class Raw(Record):
    source: str = Field(min_length=1, max_length=64)
    source_key: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    body: dict[str, Any]

    @field_validator("body")
    @classmethod
    def body_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, separators=(",", ":")).encode()) > 65_536:
            raise ValueError("raw body exceeds 65536 bytes")
        return value


class Evidence(Record):
    raw_id: str
    stance: Literal["support", "oppose", "unknown"]
    summary: str = Field(min_length=1, max_length=2_000)
    event_time: datetime | None = None


class Candidate(Record):
    run_id: str
    title: str = Field(min_length=1, max_length=256)
    why_now: str = Field(min_length=1, max_length=2_000)
    expectation: str = Field(min_length=1, max_length=2_000)
    variant_wedge: str = Field(min_length=1, max_length=2_000)
    falsifier: str = Field(min_length=1, max_length=2_000)
    horizon_days: int = Field(ge=1, le=365)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20)


class Opportunity(Record):
    candidate_id: str
    status: Literal["forming", "ranked", "shadow", "closed", "rejected"]
    title: str = Field(min_length=1, max_length=256)
    thesis: str = Field(min_length=1, max_length=4_000)
    falsifier: str = Field(min_length=1, max_length=2_000)
    horizon_days: int = Field(ge=1, le=365)


class Assessment(Record):
    opportunity_id: str
    run_id: str
    assessor: str = Field(min_length=1, max_length=64)
    verdict: Literal["advance", "hold", "reject"]
    score: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4_000)


class Rank(Record):
    opportunity_id: str
    book: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=1)
    score: float = Field(ge=0, le=1)


class Expression(Record):
    opportunity_id: str
    opportunity_version: int = Field(ge=1)
    kind: Literal["stock", "etf", "option", "wait"]
    status: Literal["proposed", "validated", "rejected", "active", "closed"]
    rationale: str = Field(min_length=1, max_length=4_000)


class ShadowPosition(Record):
    expression_id: str
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.:-]{0,31}$")
    side: Literal["long", "short"]
    quantity: float = Field(gt=0)
    status: Literal["open", "closed"]


class Event(Record):
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)

    @field_validator("payload")
    @classmethod
    def payload_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, separators=(",", ":")).encode()) > 16_384:
            raise ValueError("event payload exceeds 16384 bytes")
        return value
