import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from .contracts import Settings
from .version import __version__


def _write_state(file: Path, value: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = file.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(file)


def _health(
    host: str,
    port: int,
    path: str,
    timeout_seconds: float,
    *,
    expected_process_id: int | None = None,
) -> bool:
    try:
        with urllib_request.urlopen(
            f"http://{host}:{port}{path}", timeout=timeout_seconds
        ) as response:
            payload = json.load(response)
        expected = payload.get("ready") if path == "/health/ready" else True
        process_matches = (
            expected_process_id is None
            or payload.get("processId") == expected_process_id
        )
        return response.status == 200 and expected is True and process_matches
    except (OSError, ValueError, urllib_error.URLError):
        return False


def _wait_for_child_live(
    child: subprocess.Popen,
    host: str,
    port: int,
    stop: threading.Event,
    timeout_seconds: float = 30,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and not stop.is_set():
        if child.poll() is not None:
            return False
        if _health(
            host,
            port,
            "/health/live",
            0.5,
            expected_process_id=child.pid,
        ):
            return True
        stop.wait(0.1)
    return False


def _terminate_child(child: subprocess.Popen, grace_seconds: float) -> None:
    if child.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(child.pid, signal.SIGTERM)
    else:
        child.terminate()
    try:
        child.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
        child.wait()


def _monitor_child(
    child: subprocess.Popen,
    host: str,
    port: int,
    state_file: Path,
    stop: threading.Event,
    settings: Settings,
    *,
    restarts: int,
) -> str:
    unhealthy_since: float | None = None
    unresponsive_since: float | None = None
    last_healthy_at: str | None = None
    last_state_write = 0.0
    while child.poll() is None and not stop.is_set():
        now = time.monotonic()
        live = _health(
            host,
            port,
            "/health/live",
            settings.supervisor_probe_seconds,
            expected_process_id=child.pid,
        )
        if not live:
            if unresponsive_since is None:
                unresponsive_since = now
                _write_state(
                    state_file,
                    {
                        "state": "degraded",
                        "version": __version__,
                        "supervisorPid": os.getpid(),
                        "childPid": child.pid,
                        "restarts": restarts,
                        "lastHealthyAt": last_healthy_at,
                        "failure": "liveness_unavailable",
                    },
                )
            elif (
                now - unresponsive_since
                >= settings.supervisor_unresponsive_grace_seconds
            ):
                _terminate_child(child, settings.supervisor_shutdown_grace_seconds)
                return "liveness_timeout"
        elif _health(host, port, "/health/ready", settings.supervisor_probe_seconds):
            unresponsive_since = None
            last_healthy_at = datetime.now(UTC).isoformat()
            if unhealthy_since is not None or now - last_state_write >= 60:
                unhealthy_since = None
                _write_state(
                    state_file,
                    {
                        "state": "running",
                        "version": __version__,
                        "supervisorPid": os.getpid(),
                        "childPid": child.pid,
                        "restarts": restarts,
                        "lastHealthyAt": last_healthy_at,
                    },
                )
                last_state_write = now
        else:
            unresponsive_since = None
            if unhealthy_since is None:
                unhealthy_since = now
                _write_state(
                    state_file,
                    {
                        "state": "degraded",
                        "version": __version__,
                        "supervisorPid": os.getpid(),
                        "childPid": child.pid,
                        "restarts": restarts,
                        "lastHealthyAt": last_healthy_at,
                        "failure": "readiness_unavailable",
                    },
                )
            elif now - unhealthy_since >= settings.supervisor_unhealthy_grace_seconds:
                _terminate_child(child, settings.supervisor_shutdown_grace_seconds)
                return "readiness_timeout"
        try:
            child.wait(timeout=settings.supervisor_probe_seconds)
        except subprocess.TimeoutExpired:
            pass
    if stop.is_set():
        _terminate_child(child, settings.supervisor_shutdown_grace_seconds)
        return "stopped"
    return "unexpected_exit"


def supervise(
    settings: Settings,
    host: str,
    port: int,
    state_file: Path,
    max_restarts: int | None,
    backoff_seconds: float,
) -> int:
    if port == 0:
        raise ValueError("supervised opportunityd requires an explicit port")
    if max_restarts is not None and max_restarts < 0:
        raise ValueError("max_restarts must be non-negative or unlimited")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")
    stop = threading.Event()
    child: subprocess.Popen | None = None
    restarts = 0
    consecutive_failures = 0
    terminal_failure = False

    def request_stop(_signum, _frame) -> None:
        stop.set()

    previous = {
        item: signal.signal(item, request_stop)
        for item in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        while not stop.is_set():
            started_at = time.monotonic()
            command = [
                sys.executable,
                "-m",
                "alta_asterism",
                "opportunityd",
                "--host",
                host,
                "--port",
                str(port),
            ]
            child = subprocess.Popen(
                command,
                env=os.environ.copy(),
                start_new_session=os.name == "posix",
            )
            _write_state(
                state_file,
                {
                    "state": "starting",
                    "version": __version__,
                    "supervisorPid": os.getpid(),
                    "childPid": child.pid,
                    "restarts": restarts,
                    "consecutiveFailures": consecutive_failures,
                },
            )
            if _wait_for_child_live(child, host, port, stop):
                _write_state(
                    state_file,
                    {
                        "state": "running",
                        "version": __version__,
                        "supervisorPid": os.getpid(),
                        "childPid": child.pid,
                        "restarts": restarts,
                        "consecutiveFailures": consecutive_failures,
                    },
                )
                failure = _monitor_child(
                    child,
                    host,
                    port,
                    state_file,
                    stop,
                    settings,
                    restarts=restarts,
                )
            else:
                failure = "startup_timeout"
                _terminate_child(child, settings.supervisor_shutdown_grace_seconds)
            code = child.wait()
            if stop.is_set():
                break
            uptime_seconds = time.monotonic() - started_at
            if uptime_seconds >= settings.supervisor_stable_uptime_seconds:
                consecutive_failures = 0
            consecutive_failures += 1
            restarts += 1
            if max_restarts is not None and restarts > max_restarts:
                terminal_failure = True
                _write_state(
                    state_file,
                    {
                        "state": "failed",
                        "version": __version__,
                        "supervisorPid": os.getpid(),
                        "childPid": None,
                        "restarts": restarts,
                        "consecutiveFailures": consecutive_failures,
                        "lastExitCode": code,
                        "failure": failure,
                    },
                )
                return 1
            delay_seconds = min(
                backoff_seconds * 2 ** min(consecutive_failures - 1, 12),
                settings.supervisor_restart_max_seconds,
            )
            _write_state(
                state_file,
                {
                    "state": "backoff",
                    "version": __version__,
                    "supervisorPid": os.getpid(),
                    "childPid": None,
                    "restarts": restarts,
                    "consecutiveFailures": consecutive_failures,
                    "lastExitCode": code,
                    "failure": failure,
                    "restartAt": (
                        datetime.now(UTC) + timedelta(seconds=delay_seconds)
                    ).isoformat(),
                    "restartInSeconds": delay_seconds,
                },
            )
            stop.wait(delay_seconds)
        return 0
    finally:
        if child is not None:
            _terminate_child(child, settings.supervisor_shutdown_grace_seconds)
        if not terminal_failure:
            _write_state(
                state_file,
                {
                    "state": "stopped",
                    "version": __version__,
                    "supervisorPid": os.getpid(),
                    "childPid": None,
                    "restarts": restarts,
                },
            )
        for item, handler in previous.items():
            signal.signal(item, handler)
