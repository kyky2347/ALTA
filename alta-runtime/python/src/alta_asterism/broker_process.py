"""Bounded private pipe to the selected broker's isolated runtime."""

import json
import os
import re
import signal
import subprocess
from pathlib import Path


class BrokerExecutionError(RuntimeError):
    pass


class BrokerProcess:
    def __init__(self, root: Path):
        self.root = root
        self.python = root / "alta-runtime/broker-python/.venv/bin/python"

    def request(self, body: dict, *, research: bool = False) -> dict:
        if not self.python.is_file():
            raise BrokerExecutionError("broker_dependencies_not_installed")
        module = "alta_brokers.research_rpc" if research else "alta_brokers"
        environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(Path.home()),
            "PYTHONUNBUFFERED": "1",
            "ALTA_BROKER_PARENT_PID": str(os.getpid()),
        }
        if os.environ.get("ALTA_CREDENTIALS_DIR"):
            environment["ALTA_CREDENTIALS_DIR"] = os.environ["ALTA_CREDENTIALS_DIR"]
        child = subprocess.Popen(
            [str(self.python), "-m", module],
            cwd=self.root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            output, _ = child.communicate(json.dumps(body).encode(), timeout=45)
        except BaseException as error:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
            if not isinstance(error, Exception):
                raise
            raise BrokerExecutionError("broker_process_interrupted") from None
        if child.returncode != 0 or len(output) > 4 * 1024 * 1024:
            raise BrokerExecutionError("broker_process_unavailable")
        try:
            result = json.loads(output)
            if "error" in result:
                code = result["error"].get("code", "")
                raise BrokerExecutionError(
                    code
                    if re.fullmatch(r"[a-z_]{4,80}", code)
                    else "broker_operation_failed"
                )
            if not isinstance(result["data"], dict):
                raise ValueError()
            return result["data"]
        except (ValueError, KeyError, TypeError):
            raise BrokerExecutionError("broker_response_invalid") from None


def selected_broker(process):
    # Missing selection means ordinary Shadow, not an automatic Tiger choice.
    # An existing but invalid route must raise, never fall back to Shadow.
    if not (Path.home() / ".local/state/alta/brokers/execution-route.json").exists():
        return None
    route = process.request({"action": "route"})
    return route if route.get("provider") is not None else None
