import argparse
import json
import signal
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from .contracts import Settings
from .autonomous import AutonomousRunner
from .database import Database
from .mvp_demo import replay_demo, run_demo, run_market_session_soak
from .service import serve
from .service_supervisor import supervise
from .version import __version__


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="alta_asterism")
    value.add_argument("--version", action="version", version=__version__)
    commands = value.add_subparsers(dest="command", required=True)

    migrate = commands.add_parser("migrate")
    migrate.add_argument("action", choices=["upgrade", "downgrade", "current"])

    opportunityd = commands.add_parser("opportunityd")
    opportunityd.add_argument("--host", default=None)
    opportunityd.add_argument("--port", type=int, default=None)

    supervisor = commands.add_parser("supervisor")
    supervisor.add_argument("--host", default=None)
    supervisor.add_argument("--port", type=int, default=None)
    supervisor.add_argument("--state-file", type=Path, required=True)
    supervisor.add_argument(
        "--max-restarts",
        type=int,
        default=None,
        help="Optional terminal restart limit; omitted means keep recovering.",
    )
    supervisor.add_argument("--backoff-seconds", type=float, default=5)

    status = commands.add_parser("status")
    status.add_argument("--state-file", type=Path, required=True)

    for name in ("demo", "replay"):
        demo = commands.add_parser(name)
        demo.add_argument("--demo-id", default="b6-one-click-demo")
        demo.add_argument("--wake-at", default="2026-08-24T13:30:00+00:00")

    soak = commands.add_parser("soak")
    soak.add_argument("--session-id", default="b6-market-session")
    soak.add_argument("--session-start", default="2026-08-24T13:30:00+00:00")
    soak.add_argument("--session-end", default="2026-08-24T20:00:00+00:00")
    soak.add_argument("--cadence-minutes", type=int, default=30)
    autonomous = commands.add_parser("autonomous")
    autonomous.add_argument("--once", action="store_true")
    acceptance = commands.add_parser("acceptance")
    acceptance.add_argument(
        "--cycle-id",
        default=None,
        help="Bounded acceptance cycle ID; defaults to a UTC timestamp.",
    )
    commands.add_parser("doctor")
    return value


def _aware_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("time arguments must be timezone-aware")
    return parsed.astimezone(UTC)


def _doctor(settings: Settings) -> int:
    database = Database(settings.database_dsn)
    checks = {
        "databaseReady": database.ready(),
        "shadowEnvironment": settings.environment.value == "shadow",
        "massiveEnabled": settings.massive_enabled,
        "massiveConfigured": settings.massive_api_key is not None,
        "finlightConfigured": settings.finlight_api_key is not None,
        "capitalMode": "disabled",
        "tigerLiveAllowed": False,
    }
    ready = (
        checks["databaseReady"]
        and checks["shadowEnvironment"]
        and (not checks["massiveEnabled"] or checks["massiveConfigured"])
    )
    print(json.dumps({"ready": ready, "checks": checks}, separators=(",", ":")))
    return 0 if ready else 1


def _migrate(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    revision = getattr(database, args.action)()
    print(json.dumps({"revision": revision}, separators=(",", ":")))
    return 0


def _demo(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    database.upgrade()
    result = run_demo(database, args.demo_id, _aware_time(args.wake_at))
    print(result.model_dump_json())
    return 0


def _replay(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    if not database.ready():
        raise RuntimeError("replay requires an already migrated ready database")
    result = replay_demo(database, args.demo_id)
    print(result.model_dump_json())
    return 0


def _soak(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    database.upgrade()
    result = run_market_session_soak(
        database,
        args.session_id,
        _aware_time(args.session_start),
        _aware_time(args.session_end),
        args.cadence_minutes,
    )
    print(result.model_dump_json())
    return 0 if result.status == "PASS" else 1


def _autonomous(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    database.upgrade()
    stop = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    previous = {
        item: signal.signal(item, request_stop)
        for item in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        return AutonomousRunner(database, settings).run(stop, once=args.once)
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def _acceptance(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_dsn)
    database.upgrade()
    cycle_id = args.cycle_id or (
        "paper-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    )
    from .live_runtime import LiveRuntime

    with LiveRuntime(database, settings) as runtime:
        result = runtime.run_acceptance(cycle_id)
    print(json.dumps(result, separators=(",", ":"), default=str))
    return 0 if result["lifecycleComplete"] else 2


def _service(args: argparse.Namespace, settings: Settings) -> int:
    host = args.host or settings.service_host
    port = settings.service_port if args.port is None else args.port
    if args.command == "opportunityd":
        return serve(settings, host, port)
    return supervise(
        settings,
        host,
        port,
        args.state_file,
        args.max_restarts,
        max(args.backoff_seconds, 0),
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "status":
        print(args.state_file.read_text().strip())
        return 0
    settings = Settings()
    handlers = {
        "doctor": lambda: _doctor(settings),
        "migrate": lambda: _migrate(args, settings),
        "demo": lambda: _demo(args, settings),
        "replay": lambda: _replay(args, settings),
        "soak": lambda: _soak(args, settings),
        "autonomous": lambda: _autonomous(args, settings),
        "acceptance": lambda: _acceptance(args, settings),
        "opportunityd": lambda: _service(args, settings),
        "supervisor": lambda: _service(args, settings),
    }
    return handlers[args.command]()


def opportunityd_main() -> int:
    return main(["opportunityd", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
