import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

from alta_asterism.__main__ import parser
from alta_asterism.contracts import Settings
from alta_asterism.service_supervisor import _monitor_child
from alta_asterism.version import __version__


def _free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return value.getsockname()[1]


def test_supervisor_defaults_to_continuous_recovery() -> None:
    args = parser().parse_args(
        ["supervisor", "--state-file", "/tmp/alta-supervisor-state.json"]
    )

    assert args.max_restarts is None
    assert args.backoff_seconds == 5


def test_supervisor_restarts_a_live_but_persistently_unready_child(
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "watchdog.json"
    env = {
        **os.environ,
        "DATABASE_URL": (
            "postgresql://alta:unavailable@127.0.0.1:1/alta?connect_timeout=1"
        ),
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "ALTA_ENVIRONMENT": "replay",
        "ALTA_SUPERVISOR_PROBE_SECONDS": "0.1",
        "ALTA_SUPERVISOR_UNHEALTHY_GRACE_SECONDS": "1",
        "ALTA_SUPERVISOR_SHUTDOWN_GRACE_SECONDS": "1",
        "ALTA_SUPERVISOR_RESTART_MAX_SECONDS": "1",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alta_asterism",
            "supervisor",
            "--host",
            "127.0.0.1",
            "--port",
            str(_free_port()),
            "--state-file",
            str(state_file),
            "--max-restarts",
            "1",
            "--backoff-seconds",
            "0.1",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    state = json.loads(state_file.read_text())
    assert state.pop("supervisorPid") > 0
    assert state == {
        "childPid": None,
        "consecutiveFailures": 2,
        "failure": "readiness_timeout",
        "lastExitCode": 0,
        "restarts": 2,
        "state": "failed",
        "version": __version__,
    }


def test_supervisor_reaps_an_unresponsive_child_process_group(tmp_path: Path) -> None:
    state_file = tmp_path / "unresponsive.json"
    settings = Settings(
        DATABASE_URL="postgresql://alta:fixture@127.0.0.1:1/alta",
        REDIS_URL="redis://127.0.0.1:1/0",
        ALTA_SUPERVISOR_PROBE_SECONDS="0.1",
        ALTA_SUPERVISOR_UNRESPONSIVE_GRACE_SECONDS="1",
        ALTA_SUPERVISOR_SHUTDOWN_GRACE_SECONDS="1",
    )
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=os.name == "posix",
    )

    failure = _monitor_child(
        child,
        "127.0.0.1",
        _free_port(),
        state_file,
        threading.Event(),
        settings,
        restarts=0,
    )

    assert failure == "liveness_timeout"
    assert child.poll() is not None
    state = json.loads(state_file.read_text())
    assert state["failure"] == "liveness_unavailable"
