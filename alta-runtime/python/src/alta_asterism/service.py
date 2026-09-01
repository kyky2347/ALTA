import json
import hmac
import ipaddress
import os
import re
import signal
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .alpha_feedback import (
    ALPHA_FEEDBACK_MODE,
    ALPHA_LOWER_BOUND_Z,
    MIN_MIND_BENCHMARKED_POSITIONS,
    MIN_SLICE_BENCHMARKED_POSITIONS,
    AlphaFeedbackProjector,
)
from .autonomous import AutonomousRunner
from .contracts import Environment, Settings
from .database import Database, event_json
from .forward_evaluation import ForwardEvaluationReader
from .implementation import PortfolioRiskPolicy
from .projection_cache import ProjectionCache
from .paper_intent import PaperIntentStore
from .research_incentive import (
    MAX_REWARD_TOKENS,
    MAX_REWARD_TOOL_CALLS,
    RESEARCH_INCENTIVE_MODE,
)
from .scouts import SCOUT_PROMPT_VERSION, SCOUT_TOOL_CATALOG_VERSION
from .scout_repository import ScoutRepository
from .trader_mind import (
    CORE_ACTIVE_RESEARCH_TOOLS,
    PRODUCTION_ACTIVE_RESEARCH_REQUIRED,
    SCOUTS,
    TRADER_MIND_MEMORY_MODE,
)
from .version import __version__


def _json_bytes(value) -> bytes:
    return json.dumps(value, separators=(",", ":"), default=str).encode()


def _write_json_response(handler, status: int, value) -> None:
    body = _json_bytes(value)
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        handler.close_connection = True


def _write_sse(stream, events: list[dict]) -> None:
    try:
        if not events:
            stream.write(b": heartbeat\n\n")
        for event in events:
            payload = event_json(event)
            block = (
                f"id: {event['cursor']}\n"
                f"event: {event['event_type']}\n"
                f"data: {payload}\n\n"
            )
            stream.write(block.encode())
        stream.flush()
    except (BrokenPipeError, ConnectionResetError):
        return


def _handler(
    database: Database,
    settings: Settings,
    runtime_state: dict[str, object] | None = None,
    runtime_state_lock=None,
):
    if runtime_state is None:
        runtime_state = {"autonomousStatus": "disabled"}
    runtime_state_lock = runtime_state_lock or threading.RLock()
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
    # The event cursor is the durable invalidation signal. This keeps idle reads
    # cheap without hiding newly committed research behind a time-only TTL.
    mvp_projection: ProjectionCache[dict[str, object]] = ProjectionCache(
        300.0, max_entries=32
    )
    runtime_projection: ProjectionCache[dict[str, object]] = ProjectionCache(10.0)

    def runtime_snapshot() -> dict[str, object]:
        with runtime_state_lock:
            return dict(runtime_state)

    class Handler(BaseHTTPRequestHandler):
        server_version = "opportunityd"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            # Persistent loopback clients may reuse a connection, but an
            # abandoned socket must not retain a server thread indefinitely.
            self.connection.settimeout(30)

        def log_message(self, _format, *_args) -> None:
            return

        def json_response(self, status: int, value) -> None:
            _write_json_response(self, status, value)

        def do_GET(self) -> None:  # noqa: N802
            request = urlsplit(self.path)
            if request.path == "/health/live":
                return self.json_response(
                    200,
                    {
                        "status": "live",
                        "version": __version__,
                        "processId": os.getpid(),
                    },
                )
            if request.path == "/health/ready":
                state = runtime_snapshot()
                heartbeat = state.get("lastHeartbeatAt")
                heartbeat_fresh = not settings.autonomous_enabled
                if settings.autonomous_enabled and isinstance(heartbeat, str):
                    try:
                        age = (
                            datetime.now(UTC)
                            - datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                        ).total_seconds()
                        heartbeat_limit = (
                            settings.autonomous_cycle_timeout_seconds
                            if state.get("autonomousStatus") == "running"
                            else max(settings.autonomous_heartbeat_seconds * 3, 60)
                        )
                        heartbeat_fresh = age <= heartbeat_limit
                    except ValueError:
                        heartbeat_fresh = False
                autonomous_ready = not settings.autonomous_enabled or (
                    state.get("autonomousStatus") in ("running", "waiting", "degraded")
                    and isinstance(heartbeat, str)
                    and heartbeat_fresh
                )
                database_ready = database.ready()
                capital_ready = not settings.tiger_paper_enabled or (
                    database_ready and not PaperIntentStore.circuit_open(database)
                )
                ready = database_ready and autonomous_ready and capital_ready
                response = {"ready": ready}
                if settings.autonomous_enabled:
                    response["autonomousStatus"] = state.get("autonomousStatus")
                    response["heartbeatFresh"] = heartbeat_fresh
                if settings.tiger_paper_enabled:
                    response["capitalCircuitClosed"] = capital_ready
                return self.json_response(
                    200 if ready else 503,
                    response,
                )
            if request.path.startswith("/api/v1/") and not self.authorized():
                return self.json_response(401, {"error": {"code": "unauthorized"}})
            query = parse_qs(request.query)
            try:
                limit = min(max(int(query.get("limit", ["20"])[0]), 1), 100)
            except ValueError:
                return self.json_response(400, {"error": {"code": "invalid_limit"}})
            generated_at = datetime.now(UTC).isoformat()
            meta = {
                "environment": settings.environment.value,
                "version": __version__,
                "knownAt": generated_at,
                "generatedAt": generated_at,
                "asOf": generated_at,
                "freshnessMs": 0,
                "sourcePosture": "database",
                "traceId": None,
                "nextCursor": None,
            }
            if request.path == "/api/v1/system/summary":
                return self.json_response(
                    200,
                    {
                        "data": {
                            "counts": database.summary(settings.environment.value)
                        },
                        "meta": meta,
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/mvp/status":
                event_cursor = database.event_cursor(settings.environment.value)
                cached = mvp_projection.get(
                    (limit, event_cursor),
                    lambda: database.mvp_status(settings.environment.value, limit),
                )
                status = cached.value
                return self.json_response(
                    200,
                    {
                        "data": status,
                        "meta": {
                            **meta,
                            "nextCursor": status["eventCursor"],
                            "freshnessMs": cached.age_ms,
                            "cacheHit": cached.hit,
                        },
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/system/runtime":
                state = runtime_snapshot()
                cached = runtime_projection.get(
                    "runtime",
                    lambda: database.runtime_detail(
                        settings.environment.value,
                        portfolio_policy,
                        settings.universe,
                    ),
                )
                return self.json_response(
                    200,
                    {
                        "data": {
                            **cached.value,
                            "config": {
                                "autonomousEnabled": settings.autonomous_enabled,
                                "autonomousIntervalSeconds": (
                                    settings.autonomous_interval_seconds
                                ),
                                "autonomousFollowUpIntervalSeconds": (
                                    settings.autonomous_follow_up_interval_seconds
                                ),
                                "autonomousPositionIntervalSeconds": (
                                    settings.autonomous_position_interval_seconds
                                ),
                                "autonomousHeartbeatSeconds": (
                                    settings.autonomous_heartbeat_seconds
                                ),
                                "autonomousCycleTimeoutSeconds": (
                                    settings.autonomous_cycle_timeout_seconds
                                ),
                                "evaluationCohortId": settings.evaluation_cohort_id,
                                "evaluationMinClosedPositions": (
                                    settings.evaluation_min_closed_positions
                                ),
                                "autonomousFailureBackoffSeconds": (
                                    settings.autonomous_failure_backoff_seconds
                                ),
                                "autonomousFailureBackoffMaxSeconds": (
                                    settings.autonomous_failure_backoff_max_seconds
                                ),
                                "supervisorUnresponsiveGraceSeconds": (
                                    settings.supervisor_unresponsive_grace_seconds
                                ),
                                "agentProvider": settings.agent_provider,
                                "agentModel": settings.agent_model,
                                "agentReasoningEffort": (
                                    settings.agent_reasoning_effort
                                ),
                                "agentDeadlineSeconds": (
                                    settings.agent_deadline_seconds
                                ),
                                "reasoningAgentDeadlineSeconds": (
                                    settings.reasoning_agent_deadline_seconds
                                ),
                                "scoutConcurrency": settings.scout_concurrency,
                                "credentials": {
                                    "revision": settings.credential_revision,
                                    "configuredSlots": list(settings.credential_slots),
                                    "reloadMode": "atomic_replace_then_restart",
                                    "valuesExposed": False,
                                },
                                "traderMinds": {
                                    "count": len(SCOUTS),
                                    "promptVersion": SCOUT_PROMPT_VERSION,
                                    "toolCatalogVersion": (SCOUT_TOOL_CATALOG_VERSION),
                                    "activeResearchRequired": (
                                        PRODUCTION_ACTIVE_RESEARCH_REQUIRED
                                    ),
                                    "memoryMode": TRADER_MIND_MEMORY_MODE,
                                    "coreActiveTools": list(CORE_ACTIVE_RESEARCH_TOOLS),
                                    "alphaFeedback": {
                                        "mode": ALPHA_FEEDBACK_MODE,
                                        "minimumMindBenchmarkedPositions": (
                                            MIN_MIND_BENCHMARKED_POSITIONS
                                        ),
                                        "minimumSliceBenchmarkedPositions": (
                                            MIN_SLICE_BENCHMARKED_POSITIONS
                                        ),
                                        "automaticPolicyChanges": False,
                                        "automaticResearchBudgetChanges": True,
                                        "researchIncentive": {
                                            "mode": RESEARCH_INCENTIVE_MODE,
                                            "alphaLowerBoundZ": str(
                                                ALPHA_LOWER_BOUND_Z
                                            ),
                                            "maximumBonusToolCalls": (
                                                MAX_REWARD_TOOL_CALLS
                                            ),
                                            "maximumBonusTokens": MAX_REWARD_TOKENS,
                                            "capitalInfluence": False,
                                            "rankingInfluence": False,
                                            "brokerInfluence": False,
                                        },
                                    },
                                },
                                "massiveEnabled": settings.massive_enabled,
                                "massiveConfigured": (
                                    settings.massive_api_key is not None
                                ),
                                "shadowMaxPositionNotional": str(
                                    settings.shadow_max_position_notional
                                ),
                                "shadowPortfolioPolicy": {
                                    "referenceNav": str(settings.shadow_reference_nav),
                                    "tradeLossBudgetBps": str(
                                        settings.shadow_trade_loss_budget_bps
                                    ),
                                    "maxPositionNavBps": str(
                                        settings.shadow_max_position_nav_bps
                                    ),
                                    "maxGrossNavBps": str(
                                        settings.shadow_max_gross_nav_bps
                                    ),
                                    "maxUnderlyingNavBps": str(
                                        settings.shadow_max_underlying_nav_bps
                                    ),
                                    "equityStressFloorBps": str(
                                        settings.shadow_equity_stress_floor_bps
                                    ),
                                    "maxExitDays": settings.shadow_max_exit_days,
                                    "advParticipationBps": str(
                                        settings.shadow_adv_participation_bps
                                    ),
                                    "minNetAlphaBps": str(
                                        settings.shadow_min_net_alpha_bps
                                    ),
                                    "navSource": "synthetic_shadow_reference",
                                },
                                "universe": settings.universe,
                                "capitalMode": "disabled",
                                **state,
                            },
                        },
                        "meta": {
                            **meta,
                            "freshnessMs": cached.age_ms,
                            "cacheHit": cached.hit,
                        },
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/alpha/summary":
                return self.json_response(
                    200,
                    {
                        "data": database.alpha_summary(
                            settings.environment.value, portfolio_policy
                        ),
                        "meta": meta,
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/alpha/feedback":
                return self.json_response(
                    200,
                    {
                        "data": AlphaFeedbackProjector(database).public_summary(
                            settings.environment
                        ),
                        "meta": meta,
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/evaluation/summary":
                return self.json_response(
                    200,
                    {
                        "data": ForwardEvaluationReader(database).summary(
                            settings.environment.value,
                            settings.evaluation_cohort_id,
                            settings.evaluation_min_closed_positions,
                        ),
                        "meta": meta,
                        "warnings": [],
                    },
                )
            if request.path == "/api/v1/events":
                raw_cursor = query.get("cursor", ["0"])[0]
                try:
                    cursor = int(raw_cursor)
                    if cursor < 0:
                        raise ValueError
                except ValueError:
                    return self.json_response(
                        400, {"error": {"code": "invalid_cursor"}}
                    )
                raw_before = query.get("before", [None])[0]
                if raw_before is not None:
                    try:
                        before = int(raw_before)
                        if before <= 0:
                            raise ValueError
                    except ValueError:
                        return self.json_response(
                            400, {"error": {"code": "invalid_before"}}
                        )
                    events = database.events_before(
                        before, limit, environment=settings.environment.value
                    )
                else:
                    events = database.events_after(
                        cursor, limit, environment=settings.environment.value
                    )
                serialized = [json.loads(event_json(event)) for event in events]
                next_cursor = serialized[-1]["cursor"] if serialized else cursor
                return self.json_response(
                    200,
                    {
                        "data": {"events": serialized},
                        "meta": {**meta, "nextCursor": next_cursor},
                        "warnings": [],
                    },
                )
            detail_routes = (
                ("/api/v1/runs/", database.run_detail),
                ("/api/v1/opportunities/", database.opportunity_detail),
                ("/api/v1/expressions/", database.expression_detail),
            )
            for prefix, loader in detail_routes:
                if request.path.startswith(prefix):
                    record_id = request.path.removeprefix(prefix)
                    if re.fullmatch(r"[A-Za-z0-9_.:-]{3,128}", record_id) is None:
                        return self.json_response(
                            400, {"error": {"code": "invalid_id"}}
                        )
                    detail = loader(record_id, settings.environment.value)
                    if detail is None:
                        return self.json_response(404, {"error": {"code": "not_found"}})
                    return self.json_response(
                        200, {"data": detail, "meta": meta, "warnings": []}
                    )
            if request.path == "/api/v1/stream":
                return self.stream(query, limit)
            self.json_response(404, {"error": {"code": "not_found"}})

        def authorized(self) -> bool:
            if settings.api_token is None:
                return True
            expected = f"Bearer {settings.api_token.get_secret_value()}"
            return hmac.compare_digest(self.headers.get("Authorization", ""), expected)

        def stream(self, query: dict[str, list[str]], limit: int) -> None:
            raw_cursor = (
                self.headers.get("Last-Event-ID") or query.get("cursor", ["0"])[0]
            )
            try:
                cursor = int(raw_cursor)
                if cursor < 0:
                    raise ValueError
            except ValueError:
                return self.json_response(400, {"error": {"code": "invalid_cursor"}})
            events = database.events_after(
                cursor, limit, environment=settings.environment.value
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            _write_sse(self.wfile, events)

    return Handler


def serve(settings: Settings, host: str, port: int) -> int:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback and settings.api_token is None:
        raise ValueError("non-loopback opportunityd requires ALTA_API_TOKEN")
    if settings.autonomous_enabled and settings.environment is not Environment.SHADOW:
        raise ValueError("autonomous opportunityd requires ALTA_ENVIRONMENT=shadow")
    if (
        settings.autonomous_enabled
        and settings.massive_enabled
        and settings.massive_api_key is None
    ):
        raise ValueError(
            "autonomous opportunityd requires MASSIVE_API_KEY when Massive is enabled"
        )
    database = Database(settings.database_dsn, pool_size=8)
    if settings.autonomous_enabled and not database.ready():
        raise ValueError(
            "autonomous opportunityd requires the latest database migration"
        )
    runtime_state: dict[str, object] = {
        "autonomousStatus": ("starting" if settings.autonomous_enabled else "disabled"),
        "autonomousFailureType": None,
        "lastHeartbeatAt": None,
        "currentCycleId": None,
        "lastCycleResult": None,
        "lastCycleCompletedAt": None,
        "nextCycleAt": None,
        "nextIntervalSeconds": None,
        "cadenceReason": None,
        "retryInSeconds": None,
        "failureRecorded": None,
        "consecutiveFailures": 0,
    }
    runtime_state_lock = threading.RLock()
    server = ThreadingHTTPServer(
        (host, port),
        _handler(database, settings, runtime_state, runtime_state_lock),
    )
    server.daemon_threads = True
    server.block_on_close = False
    autonomous_stop = threading.Event()
    autonomous_thread = None
    exit_code = 0
    if settings.autonomous_enabled:

        def update_runtime_state(status: str, detail: dict) -> None:
            with runtime_state_lock:
                runtime_state.update(
                    {
                        "autonomousStatus": status,
                        "lastHeartbeatAt": detail.get("heartbeat_at"),
                        "currentCycleId": detail.get("cycle_id"),
                        "lastCycleResult": detail.get("cycle_result"),
                        "lastCycleCompletedAt": detail.get("cycle_completed_at"),
                        "nextCycleAt": detail.get("next_cycle_at"),
                        "nextIntervalSeconds": detail.get("next_interval_seconds"),
                        "cadenceReason": detail.get("cadence_reason"),
                        "retryInSeconds": detail.get("retry_in_seconds"),
                        "failureRecorded": detail.get("failure_recorded"),
                        "consecutiveFailures": detail.get("consecutive_failures", 0),
                        "autonomousFailureType": detail.get("failure_type"),
                    }
                )

        runner = AutonomousRunner(
            database, settings, state_callback=update_runtime_state
        )

        def run_autonomous() -> None:
            nonlocal exit_code
            with runtime_state_lock:
                runtime_state["autonomousStatus"] = "starting"
            try:
                result = runner.run(autonomous_stop)
            except Exception as error:
                result = 1
                with runtime_state_lock:
                    runtime_state["autonomousFailureType"] = type(error).__name__
            if not autonomous_stop.is_set() and result != 0:
                with runtime_state_lock:
                    runtime_state["autonomousStatus"] = "failed"
                exit_code = 1
                server.shutdown()

        autonomous_thread = threading.Thread(
            target=run_autonomous,
            daemon=True,
            name="alta-autonomous-runner",
        )
        autonomous_thread.start()

    def stop(_signum, _frame) -> None:
        autonomous_stop.set()
        with runtime_state_lock:
            runtime_state["autonomousStatus"] = "stopping"
            cycle_id = runtime_state.get("currentCycleId")

        def cancel_and_shutdown() -> None:
            try:
                if isinstance(cycle_id, str) and cycle_id:
                    ScoutRepository(database).cancel_cycle(cycle_id)
            finally:
                server.shutdown()

        threading.Thread(target=cancel_and_shutdown, daemon=True).start()

    previous = {
        item: signal.signal(item, stop) for item in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        autonomous_stop.set()
        if autonomous_thread is not None:
            autonomous_thread.join(timeout=settings.supervisor_shutdown_grace_seconds)
            if autonomous_thread.is_alive():
                exit_code = 1
                with runtime_state_lock:
                    runtime_state["autonomousStatus"] = "failed"
                    runtime_state["autonomousFailureType"] = "AutonomousShutdownTimeout"
        server.server_close()
        database.close()
        for item, handler in previous.items():
            signal.signal(item, handler)
    return exit_code
