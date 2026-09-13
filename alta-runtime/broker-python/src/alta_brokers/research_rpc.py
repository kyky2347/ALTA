"""Private research-process pipe, deliberately absent from the operator HTTP RPC.

The trusted application verifies PostgreSQL audit artifacts and persisted market
data before using this pipe. Browser/model-declared approvals are not inputs to
the operator API. Credentials remain in this child process.
"""

import hashlib
import json

from .adapters import connect
from .contracts import Quote, require
from .engine import BrokerEngine
from .lifecycle import ApprovedPlan, ExecutionLifecycle
from .routing import ExecutionRoute
from .storage import owner


class StoredAudit:
    def __init__(self, db):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS broker_audits (
            plan_id TEXT PRIMARY KEY, digest TEXT NOT NULL, audit_id TEXT NOT NULL,
            expression_hash TEXT NOT NULL, artifact_hash TEXT NOT NULL)""")
        db.commit()

    def put(self, plan, receipt):
        import re

        require(
            isinstance(receipt, dict)
            and set(receipt)
            == {"audit_id", "expression_hash", "artifact_hash", "plan_hash"},
            "audit_receipt_invalid",
        )
        digest = plan_hash(plan)
        require(
            receipt["audit_id"] == plan.audit_id and receipt["plan_hash"] == digest,
            "audit_plan_mismatch",
        )
        require(
            all(
                isinstance(receipt[k], str)
                and re.fullmatch(r"[a-f0-9]{64}", receipt[k])
                for k in ("expression_hash", "artifact_hash")
            ),
            "audit_receipt_invalid",
        )
        expected = (
            plan.plan_id,
            digest,
            plan.audit_id,
            receipt["expression_hash"],
            receipt["artifact_hash"],
        )
        previous = self.db.execute(
            "SELECT * FROM broker_audits WHERE plan_id=?", (plan.plan_id,)
        ).fetchone()
        if previous:
            require(tuple(previous) == expected, "audit_receipt_conflict")
        else:
            with self.db:
                self.db.execute("INSERT INTO broker_audits VALUES(?,?,?,?,?)", expected)

    def verify(self, plan):
        row = self.db.execute(
            "SELECT digest,audit_id FROM broker_audits WHERE plan_id=?", (plan.plan_id,)
        ).fetchone()
        return row is not None and tuple(row) == (plan_hash(plan), plan.audit_id)


def plan_hash(plan):
    return hashlib.sha256(
        json.dumps(
            plan.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


class InputQuote:
    def __init__(self, value):
        self.value = value

    def quote(self, symbol):
        require(self.value is not None, "broker_trusted_quote_unavailable")
        quote = Quote.model_validate(self.value)
        require(quote.symbol == symbol, "quote_symbol_mismatch")
        return quote


def handle_research(request, profiles):
    require(isinstance(request, dict), "broker_request_invalid")
    action = request.get("action")
    extra = {
        "stage": {"plan", "receipt"},
        "tick": {"plan_id", "quote"},
        "active": set(),
    }
    require(action in extra, "broker_action_unavailable")
    require(
        set(request)
        == {"action", "provider", "revision", "route_revision"} | extra[action],
        "broker_request_invalid",
    )
    route = ExecutionRoute(profiles)
    with owner(route.lock):
        selected = route.selected(request["provider"], request["revision"])
        require(
            selected["revision"] == request["route_revision"],
            "execution_route_conflict",
        )
        profile = profiles.load(request["provider"])
        directory = profiles.account_dir(profile)
        with owner(directory / "connection.lock"):
            adapter = connect(profile) if action == "tick" else None
            engine = BrokerEngine(profile, adapter, directory)
            try:
                audit = StoredAudit(engine.ledger.db)
                worker = ExecutionLifecycle(
                    engine, audit, InputQuote(request.get("quote"))
                )
                if action == "stage":
                    plan = ApprovedPlan.model_validate(request["plan"])
                    worker._binding(plan)
                    audit.put(plan, request["receipt"])
                    return worker.stage(plan)
                if action == "tick":
                    result = worker.tick(request["plan_id"])
                    engine.verify()
                    return result
                rows = engine.ledger.db.execute(
                    "SELECT plan_id,payload,state FROM broker_plans WHERE state NOT IN ('closed','expired','unfilled') ORDER BY rowid LIMIT 2"
                ).fetchall()
                require(len(rows) <= 1, "multiple_active_plans_require_review")
                return {
                    "authority": engine._authority()["mode"],
                    "plans": [
                        {
                            "plan_id": row["plan_id"],
                            "symbol": json.loads(row["payload"])["entry"]["symbol"],
                            "state": row["state"],
                        }
                        for row in rows
                    ],
                }
            finally:
                engine.close()


if __name__ == "__main__":
    from .__main__ import main

    main(handler=handle_research)
