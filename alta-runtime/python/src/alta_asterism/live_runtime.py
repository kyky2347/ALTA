import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from .agentic_deliberation import AgenticDeliberator
from .agentic_expression import AgenticExpressionFlow
from .agentic_roles import StructuredRoleRunner
from .contracts import Environment, Settings
from .database import Database
from .finlight import FinlightAdapter, PostgresSourceCursorStore, PostgresSourceOwner
from .ingest import RawStore
from .implementation import PortfolioRiskPolicy
from .live_source_flow import DatabaseSourceFlow, IngestingSourceFlow
from .market_data import MassiveMarketData
from .massive import (
    MassiveAccessCoordinator,
    MassiveAccessEvidence,
    MassiveAccessMode,
    MassiveRequestBudget,
    MassiveRestAdapter,
)
from .mind_worker import SdkAppServerMindClient
from .mind_pool import MindClientPool
from .mvp_fixture import MvpFixture
from .mvp_orchestrator import MvpOrchestrator
from .mvp_research_flow import ResearchRuntimeConfig
from .official_sources import (
    build_official_finlight_transport,
    build_official_massive_transport,
)
from .paper_execution import TigerPaperExecutor
from .scouts import FrozenScoutInput
from .trader_mind import PRODUCTION_ACTIVE_RESEARCH_REQUIRED

PRODUCTION_SCOUT_MAX_TOTAL_TOKENS = 88_000


class LiveRuntime:
    """Wires the durable database, real App Server minds, and safe Shadow gates."""

    def __init__(self, database: Database, settings: Settings) -> None:
        if settings.environment is not Environment.SHADOW:
            raise ValueError("live autonomous runtime requires ALTA_ENVIRONMENT=shadow")
        repo_root = Path(__file__).resolve().parents[4]
        self.database = database
        self.settings = settings
        workspace = settings.agent_workspace
        if not workspace.is_absolute():
            workspace = repo_root / workspace
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.client = MindClientPool(
            tuple(
                SdkAppServerMindClient(
                    repo_root=repo_root,
                    provider=settings.agent_provider,
                    model_id=settings.agent_model,
                    agent_cwd=workspace,
                    reasoning_effort=settings.agent_reasoning_effort,
                )
                for _ in range(settings.scout_concurrency)
            )
        )
        scout_route = (settings.agent_provider, settings.agent_model)
        role_clients: dict[tuple[str, str], MindClientPool] = {}
        role_runners: dict[tuple[str, str], StructuredRoleRunner] = {}

        def runner_for(provider: str, model_id: str) -> StructuredRoleRunner:
            route = (provider, model_id)
            existing = role_runners.get(route)
            if existing is not None:
                return existing
            client = self.client
            if route != scout_route:
                client = MindClientPool(
                    (
                        SdkAppServerMindClient(
                            repo_root=repo_root,
                            provider=provider,
                            model_id=model_id,
                            agent_cwd=workspace,
                            reasoning_effort=settings.agent_reasoning_effort,
                        ),
                    )
                )
                role_clients[route] = client
            runner = StructuredRoleRunner(
                database,
                client,
                model_provider=provider,
                model_id=model_id,
                max_total_tokens=30_000,
                max_output_bytes=8_000,
                deadline_seconds=settings.reasoning_agent_deadline_seconds,
            )
            role_runners[route] = runner
            return runner

        thesis_runner = runner_for(settings.thesis_provider, settings.thesis_model)
        disconfirming_runner = runner_for(
            settings.disconfirming_provider, settings.disconfirming_model
        )
        moderator_runner = runner_for(
            settings.moderator_provider, settings.moderator_model
        )
        expression_runner = runner_for(
            settings.expression_provider, settings.expression_model
        )
        audit_runner = runner_for(settings.audit_provider, settings.audit_model)
        position_runner = runner_for(*scout_route)
        self._role_clients = tuple(role_clients.values())
        deliberator = AgenticDeliberator(
            database,
            thesis_runner,
            disconfirming_runner=disconfirming_runner,
            moderator_runner=moderator_runner,
        )
        fixture = MvpFixture.default()
        raw_store = RawStore(database, Environment.SHADOW)
        finlight_adapter = None
        if settings.finlight_api_key is not None:
            finlight_adapter = FinlightAdapter(
                build_official_finlight_transport(
                    settings.finlight_api_key.get_secret_value(), settings.universe
                ),
                raw_store,
                PostgresSourceOwner(database),
                cursor_store=PostgresSourceCursorStore(database, Environment.SHADOW),
            )
        massive_adapter = None
        market_data = None
        self.massive_budget = None
        if settings.massive_enabled and settings.massive_api_key is not None:
            massive_key = settings.massive_api_key.get_secret_value()
            credential_slot_id = (
                "massive-" + hashlib.sha256(massive_key.encode()).hexdigest()[:24]
            )
            self.massive_budget = MassiveRequestBudget(
                settings.massive_max_requests_per_cycle
            )
            massive_adapter = MassiveRestAdapter(
                build_official_massive_transport(
                    massive_key,
                    base_url=settings.massive_base_url.get_secret_value(),
                    allow_insecure_http=settings.massive_allow_insecure_http,
                    auth_mode=settings.massive_auth_mode,
                ),
                raw_store,
                MassiveAccessCoordinator(
                    MassiveAccessEvidence(
                        requested_mode=MassiveAccessMode.DEDICATED,
                        credential_slot_id=credential_slot_id,
                        dedicated_key_confirmed=True,
                    )
                ),
                request_budget=self.massive_budget,
            )
            market_data = MassiveMarketData(
                massive_adapter,
                max_notional=settings.shadow_max_position_notional,
            )
        portfolio_policy = PortfolioRiskPolicy(
            reference_nav=settings.shadow_reference_nav,
            per_trade_loss_budget_bps=settings.shadow_trade_loss_budget_bps,
            max_position_nav_bps=settings.shadow_max_position_nav_bps,
            max_gross_nav_bps=settings.shadow_max_gross_nav_bps,
            max_underlying_nav_bps=settings.shadow_max_underlying_nav_bps,
            equity_stress_floor_bps=settings.shadow_equity_stress_floor_bps,
            max_exit_days=settings.shadow_max_exit_days,
            adv_participation_bps=settings.shadow_adv_participation_bps,
            min_net_alpha_bps=settings.shadow_min_net_alpha_bps,
        )
        source_flow = IngestingSourceFlow(
            DatabaseSourceFlow(
                database,
                settings.universe,
                portfolio_policy=portfolio_policy,
            ),
            finlight_adapter,
            massive_adapter,
            PostgresSourceCursorStore(
                database, Environment.SHADOW, source="massive_daily"
            ),
            massive_discovery_enabled=settings.massive_discovery_enabled,
        )
        paper_executor = None
        if settings.tiger_paper_enabled:
            if (
                settings.tiger_config_path is None
                or settings.tiger_paper_account_sha256 is None
            ):
                raise ValueError("Tiger Paper configuration is incomplete")
            paper_executor = TigerPaperExecutor(
                repo_root=repo_root,
                config_path=settings.tiger_config_path,
                account_sha256=(settings.tiger_paper_account_sha256.get_secret_value()),
                timeout_seconds=settings.tiger_order_timeout_seconds,
            )
            preflight = paper_executor.preflight()
            if preflight.get("paper") is not True:
                raise ValueError("Tiger Paper preflight did not prove Paper mode")
            if (
                preflight.get("positionCount") != 0
                or preflight.get("openOrderCount") != 0
            ):
                raise ValueError(
                    "Tiger Paper acceptance requires an empty account and no open orders"
                )
        self.paper_executor = paper_executor
        self.market_data = market_data
        self.orchestrator = MvpOrchestrator(
            database,
            fixture,
            self.client,
            source_flow=source_flow,
            shadow_flow=AgenticExpressionFlow(
                database,
                expression_runner,
                settings.universe,
                market_data,
                audit_runner=audit_runner,
                position_runner=position_runner,
                max_open_positions=1 if paper_executor else 8,
                paper_executor=paper_executor,
                acceptance_hold_seconds=settings.acceptance_hold_seconds,
                portfolio_policy=portfolio_policy,
            ),
            research_config=ResearchRuntimeConfig(
                model_provider=settings.agent_provider,
                model_id=settings.agent_model,
                max_tool_calls=5,
                # Five-stage internet research can charge about 80k new
                # (non-cached) tokens once independent Evidence is folded back
                # into the Scout context. Keep the bound finite and below the
                # 100k global contract, but avoid rejecting a completed turn
                # after it has already paid the retrieval latency and cost.
                max_total_tokens=PRODUCTION_SCOUT_MAX_TOTAL_TOKENS,
                max_output_bytes=8_000,
                deadline_seconds=settings.agent_deadline_seconds,
                max_concurrency=settings.scout_concurrency,
                use_wall_clock=True,
                require_active_research=PRODUCTION_ACTIVE_RESEARCH_REQUIRED,
            ),
            deliberator=deliberator,
        )

    def run_acceptance(self, cycle_id: str) -> dict[str, object]:
        """Runs discovery once, then performs one bounded Paper exit observation."""
        if self.paper_executor is None:
            raise ValueError("acceptance requires Tiger Paper mirroring")
        if self.settings.acceptance_hold_seconds is None:
            raise ValueError("acceptance requires ALTA_ACCEPTANCE_HOLD_SECONDS")
        if self.massive_budget is not None:
            self.massive_budget.reset(cycle_id)
        wake_at = datetime.now(UTC)
        result = None
        monitored: tuple[str, ...] = ()
        paper_flattened: tuple[str, ...] = ()
        try:
            result = self.orchestrator.run(cycle_id, wake_at)
            if result.shadow_position_id is not None:
                time.sleep(self.settings.acceptance_hold_seconds + 1)
                observation_at = datetime.now(UTC)
                frozen = FrozenScoutInput(
                    wake_id=f"{cycle_id}-acceptance-exit",
                    environment=Environment.SHADOW,
                    known_at=observation_at,
                    universe=self.settings.universe,
                    evidence=(),
                    expectation_posture="unavailable",
                )
                monitored = self.orchestrator.shadow.monitor_existing(
                    f"{cycle_id}-acceptance-exit",
                    observation_at,
                    frozen,
                )
        finally:
            flatten_error = None
            try:
                paper_flattened = (
                    self.orchestrator.shadow.positions.ensure_cycle_paper_flat(cycle_id)
                )
            except Exception as error:
                flatten_error = error
            finally:
                final_preflight = self.paper_executor.preflight()
                if (
                    final_preflight.get("positionCount") != 0
                    or final_preflight.get("openOrderCount") != 0
                ):
                    raise ValueError(
                        "Tiger Paper account is not flat and order-free after acceptance"
                    )
            if flatten_error is not None:
                raise RuntimeError(
                    "Tiger Paper safety flatten failed"
                ) from flatten_error
        if result is None:
            raise RuntimeError("acceptance cycle did not produce a result")
        position_status = None
        paper_fills = 0
        if result.shadow_position_id is not None:
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT status FROM research.shadow_position WHERE id = %s",
                    (result.shadow_position_id,),
                ).fetchone()
                position_status = row[0] if row is not None else None
                paper_fills = connection.execute(
                    """SELECT count(*) FROM ops.event
                    WHERE aggregate_id = %s
                      AND event_type = 'paper.order.filled'""",
                    (result.shadow_position_id,),
                ).fetchone()[0]
        budget = (
            self.massive_budget.snapshot() if self.massive_budget is not None else None
        )
        return {
            "cycleId": cycle_id,
            "pipelineStatus": result.status,
            "opportunityFound": result.top_opportunity_id is not None,
            "topOpportunityId": result.top_opportunity_id,
            "selectedOpportunityId": result.selected_opportunity_id,
            "expressionId": result.expression_id,
            "shadowPositionId": result.shadow_position_id,
            "monitoredPositionIds": monitored,
            "positionStatus": position_status,
            "paperFillCount": paper_fills,
            "paperFlatSafety": True,
            "paperFlattenedPositionIds": paper_flattened,
            "lifecycleComplete": (
                result.shadow_position_id is not None
                and position_status == "closed"
                and paper_fills == 2
            ),
            "capitalMode": self.orchestrator.shadow.capital_mode,
            "massiveRequests": (
                {"used": budget[1], "maximum": budget[2]} if budget else None
            ),
        }

    def close(self) -> None:
        try:
            self.client.close()
        finally:
            for client in self._role_clients:
                client.close()

    def __enter__(self) -> "LiveRuntime":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()
