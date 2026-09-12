"""Write-only operator RPC over stdin. This entrypoint never places orders.

The execution engine is a separate library boundary pending research-runner
integration and real-account acceptance. A dashboard button cannot bypass that.
"""

import json
import logging
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from .adapters import connect
from .catalog import CATALOG, validate_credentials
from .contracts import BrokerError, Profile, require
from .engine import BrokerEngine
from .storage import Profiles, owner


def handle(request, profiles):
    require(isinstance(request, dict), "broker_request_invalid")
    action = request.get("action")
    require(
        action in ("catalog", "save", "verify", "state"), "broker_action_unavailable"
    )
    allowed = (
        {"action"}
        if action == "catalog"
        else {"action", "profile", "revision"}
        if action == "save"
        else {"action", "provider"}
    )
    require(set(request) == allowed, "broker_request_invalid")
    if action == "catalog":
        rows = []
        for entry in CATALOG:
            configured = profiles.file(entry["provider"]).exists()
            row = {
                **entry,
                "configured": configured,
                "revision": "new",
                "autonomous_execution": False,
                "acceptance": "not_verified",
            }
            if configured:
                try:
                    profile = profiles.load(entry["provider"])
                    row.update(
                        revision=profile.revision,
                        environment=profile.environment,
                        binding=profile.binding,
                    )
                except (OSError, ValueError, BrokerError):
                    # One damaged account must not hide every connector. Do not
                    # overwrite it or expose its file path / validation payload.
                    row.update(
                        revision="unavailable",
                        profile_error="broker_profile_unreadable",
                    )
            rows.append(row)
        return {"brokers": rows}
    if action == "save":
        profile = Profile.model_validate(request["profile"])
        validate_credentials(profile)
        profiles.save(profile, request["revision"])
        return {
            "provider": profile.provider,
            "revision": profile.revision,
            "binding": profile.binding,
            "saved": True,
        }
    profile = profiles.load(request["provider"])
    # Isolated process plus per-account lock bounds all SDK sessions. No raw
    # provider log, account response, or credential is returned on failure.
    with owner(profiles.account_dir(profile) / "connection.lock"):
        adapter = connect(profile)
        engine = BrokerEngine(profile, adapter, profiles.account_dir(profile))
        try:
            return engine.verify() if action == "verify" else engine.state()
        finally:
            engine.close()


def main():
    logging.disable(logging.CRITICAL)
    os.umask(0o077)
    project = Path(__file__).resolve().parents[4]
    credentials = Path(
        os.environ.get(
            "ALTA_CREDENTIALS_DIR", str(Path.home() / ".config/alta/credentials")
        )
    )
    state = Path.home() / ".local/state/alta/brokers"
    # SDK output is discarded at the OS descriptor level (some native SDKs do
    # not use Python's logging). Only our explicit allowlisted JSON crosses out.
    stdout = os.dup(1)
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 1)
        os.dup2(null.fileno(), 2)
    try:
        raw = sys.stdin.buffer.read(65537)
        require(len(raw) <= 65536, "broker_request_too_large")
        result = {
            "data": handle(json.loads(raw), Profiles(credentials, state, project))
        }
    except (ValidationError, ValueError, TypeError, KeyError):
        result = {"error": {"code": "broker_input_or_response_invalid"}}
    except FileNotFoundError:
        result = {"error": {"code": "broker_profile_not_configured"}}
    except BrokerError as error:
        result = {"error": {"code": str(error)}}
    except Exception:
        result = {"error": {"code": "broker_operation_failed"}}
    os.write(stdout, (json.dumps(result) + "\n").encode())
    os.close(stdout)


if __name__ == "__main__":
    main()
