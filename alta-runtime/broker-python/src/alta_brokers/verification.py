"""Revision-bound connection evidence, distinct from permission to execute.

The operator can inspect real account responses without arming an account.
Neither a successful read nor a saved screenshot is an acceptance record.
"""

import hashlib
import re

from .contracts import Snapshot, now, require
from .storage import atomic_private, read_private


class Verification:
    def __init__(self, profile, directory):
        self.profile = profile
        self.path = directory / "verification.json"

    def save(self, snapshot):
        require(
            snapshot.binding == self.profile.binding
            and snapshot.environment == self.profile.environment,
            "account_environment_mismatch",
        )
        require(
            0 <= (now() - snapshot.verified_at).total_seconds() <= 30,
            "broker_snapshot_stale",
        )
        public = snapshot.model_dump(mode="json")
        for order in public["orders"]:
            order["order_id"] = hashlib.sha256(order["order_id"].encode()).hexdigest()[
                :16
            ]
            # Other applications' order remarks are not ALTA audit identifiers.
            if not re.fullmatch(r"alta-[a-f0-9]{32}", order["client_id"]):
                order["client_id"] = ""
        atomic_private(
            self.path,
            {
                "revision": self.profile.revision,
                "snapshot": public,
                "checked_at": now().isoformat(),
                "status": "verified",
            },
        )

    def failed(self):
        # An old success must not outlive a later failed authentication probe.
        atomic_private(
            self.path,
            {
                "revision": self.profile.revision,
                "checked_at": now().isoformat(),
                "status": "failed",
            },
        )

    def state(self):
        if not self.path.exists():
            return {"status": "not_checked", "fresh": False, "snapshot": None}
        try:
            record = read_private(self.path, max_bytes=2 * 1024 * 1024)
            require(isinstance(record, dict), "verification_record_invalid")
            if record.get("revision") != self.profile.revision:
                return {
                    "status": "configuration_changed",
                    "fresh": False,
                    "snapshot": None,
                }
            if record.get("status") == "failed":
                return {"status": "failed", "fresh": False, "snapshot": None}
            require(record.get("status") == "verified", "verification_record_invalid")
            snapshot = Snapshot.model_validate(record["snapshot"])
            require(
                snapshot.binding == self.profile.binding
                and snapshot.environment == self.profile.environment,
                "account_environment_mismatch",
            )
            fresh = 0 <= (now() - snapshot.verified_at).total_seconds() <= 30
            return {
                "status": "verified" if fresh else "stale",
                "fresh": fresh,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        except (OSError, ValueError, KeyError, RuntimeError):
            return {"status": "unavailable", "fresh": False, "snapshot": None}


def authorization_review(profile, verification, rows, *, flat_and_settled=None):
    """Expose the actual release gates, never a client-supplied readiness flag."""
    snapshot = verification.get("snapshot") or {}
    fresh = verification["fresh"]
    permission = snapshot.get("trading_permitted") is True or (
        profile.provider == "ibkr" and snapshot.get("order_preview_required") is True
    )
    checks = {
        "fresh_account": fresh,
        "account_identity": fresh and snapshot.get("account_verified") is True,
        "environment_identity": fresh and snapshot.get("environment_verified") is True,
        "trade_permission": fresh and permission,
        "empty_account": fresh
        and not snapshot.get("positions")
        and not snapshot.get("orders"),
        "clear_ledger": not rows if flat_and_settled is None else flat_and_settled,
        "runner_integration": True,
        # Read-only acceptance evidence, not a claim that a live order was tested.
        "account_acceptance": fresh
        and permission
        and all(
            snapshot.get(k) is True
            for k in ("account_verified", "environment_verified")
        ),
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "provider": profile.provider,
        "environment": profile.environment,
        "binding": profile.binding,
        "revision": profile.revision,
        "limits": {
            "max_order_notional": str(profile.max_order_notional),
            "max_gross_notional": str(profile.max_gross_notional),
            "max_quote_age_seconds": profile.max_quote_age_seconds,
        },
    }
