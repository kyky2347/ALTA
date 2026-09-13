"""One explicit execution destination. Never fall back to another broker."""

import hashlib
import json
from uuid import uuid4

from .contracts import require
from .engine import BrokerEngine
from .storage import atomic_private, owner, read_private


class ExecutionRoute:
    def __init__(self, profiles):
        self.profiles = profiles
        self.path = profiles.state / "execution-route.json"
        self.lock = profiles.state / "route.lock"

    def state(self):
        value = (
            read_private(self.path)
            if self.path.exists()
            else {
                "provider": None,
                "binding": None,
                "profile_revision": None,
                "environment": None,
                "generation": "initial",
            }
        )
        require(
            isinstance(value, dict)
            and set(value)
            == {"provider", "binding", "profile_revision", "environment", "generation"},
            "execution_route_invalid",
        )
        if value["provider"] is not None:
            profile = self.profiles.load(value["provider"])
            require(
                value["binding"] == profile.binding
                and value["profile_revision"] == profile.revision
                and value["environment"] == profile.environment,
                "execution_route_configuration_changed",
            )
        else:
            require(
                all(
                    value[k] is None
                    for k in ("binding", "profile_revision", "environment")
                ),
                "execution_route_invalid",
            )
        revision = hashlib.sha256(
            json.dumps(value, sort_keys=True).encode()
        ).hexdigest()
        return {**value, "revision": revision}

    def selected(self, provider, revision):
        route = self.state()
        require(route["provider"] == provider, "execution_broker_not_selected")
        require(route["profile_revision"] == revision, "broker_profile_conflict")
        return route

    def select(self, provider, revision, profile_revision):
        with owner(self.lock), owner(self.profiles.state / "profiles.lock"):
            current = self.state()
            require(current["revision"] == revision, "execution_route_conflict")
            profile = self.profiles.load(provider) if provider is not None else None
            require(
                profile_revision == (profile.revision if profile else None),
                "broker_profile_conflict",
            )
            # Inspect every configured lane, not just the visible account. A
            # hidden old authorization must not survive selecting another lane.
            from .catalog import CATALOG

            for entry in CATALOG:
                if not self.profiles.file(entry["provider"]).exists():
                    continue
                previous = self.profiles.load(entry["provider"])
                directory = self.profiles.account_dir(previous)
                with owner(directory / "connection.lock"):
                    engine = BrokerEngine(previous, None, directory)
                    try:
                        require(
                            engine._authority()["mode"] == "off",
                            "revoke_before_broker_switch",
                        )
                        require(
                            engine.ledger.flat_and_settled(),
                            "reconcile_before_broker_switch",
                        )
                    finally:
                        engine.close()
            atomic_private(
                self.path,
                {
                    "provider": provider,
                    "binding": profile.binding if profile else None,
                    "profile_revision": profile.revision if profile else None,
                    "environment": profile.environment if profile else None,
                    "generation": uuid4().hex,
                },
            )
            return self.state()
