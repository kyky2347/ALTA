"""Durable, restartable lifecycle for a trusted, independently audited plan.

The caller supplies trusted audit and realtime quote ports, never model-declared
approval or quote JSON from a browser. This kernel does not select accounts,
authorize an account, launch a service or own credentials. Admission and broker
mutations remain in BrokerEngine. Production research handoff is a separate port.
"""

import hashlib
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Protocol

from pydantic import Field, model_validator

from .contracts import Contract, Intent, Positive, Quote, now, require
from .storage import owner


class ApprovedPlan(Contract):
    plan_id: str = Field(pattern=r"^plan-[a-f0-9]{32}$")
    binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    audit_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,128}$")
    audited_at: datetime
    entry: Intent
    exit_at: datetime
    stop_price: Positive
    target_price: Positive

    @model_validator(mode="after")
    def validate_plan(self):
        require(self.entry.side == "BUY", "plan_entry_must_buy")
        require(
            self.audited_at.tzinfo is not None and self.exit_at.tzinfo is not None,
            "timestamp_requires_timezone",
        )
        require(
            self.audited_at
            < self.entry.expires_at
            <= self.audited_at + timedelta(minutes=5)
            and self.entry.expires_at
            < self.exit_at
            <= self.audited_at + timedelta(days=90),
            "plan_deadlines_invalid",
        )
        require(
            self.stop_price < self.entry.limit_price < self.target_price,
            "plan_exit_prices_invalid",
        )
        return self


class AuditPort(Protocol):
    def verify(self, plan: ApprovedPlan) -> bool:
        """Verify the exact plan against durable independent audit evidence."""
        ...


class QuotePort(Protocol):
    def quote(self, symbol: str) -> Quote:
        """Read entitled realtime prices; never synthesize a live timestamp."""
        ...


class ExecutionLifecycle:
    def __init__(self, engine, audit: AuditPort, quotes: QuotePort):
        self.engine, self.audit, self.quotes = engine, audit, quotes
        self.db = engine.ledger.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS broker_plans (
            plan_id TEXT PRIMARY KEY, entry_id TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
            exit_request TEXT, reason TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.db.commit()

    def stage(self, plan: ApprovedPlan):
        with owner(self.engine.directory / "lifecycle.lock"):
            self._binding(plan)
            payload = plan.model_dump_json()
            digest = hashlib.sha256(payload.encode()).hexdigest()
            current = self._row(plan.plan_id)
            if current:
                require(current["digest"] == digest, "plan_identity_conflict")
                return self.state(plan.plan_id)
            require(
                self.engine._authority()["mode"] == "entries",
                "broker_trading_not_authorized",
            )
            require(now() < plan.entry.expires_at, "plan_expired")
            require(
                0 <= (now() - plan.audited_at).total_seconds() <= 300,
                "plan_audit_stale",
            )
            require(self.audit.verify(plan) is True, "independent_audit_not_proven")
            require(
                self.engine.ledger.get(plan.entry.client_id) is None,
                "entry_identity_already_owned",
            )
            # One position owner per account in this initial kernel. Multiple
            # simultaneous research proposals cannot reserve the same capital.
            active = self.db.execute(
                "SELECT count(*) FROM broker_plans WHERE state NOT IN ('closed','expired','unfilled')"
            ).fetchone()[0]
            require(active == 0, "active_plan_requires_monitoring")
            with self.db:
                self.db.execute(
                    "INSERT INTO broker_plans(plan_id,entry_id,payload,digest,state) VALUES(?,?,?,?,?)",
                    (plan.plan_id, plan.entry.client_id, payload, digest, "staged"),
                )
            return self.state(plan.plan_id)

    def _binding(self, plan):
        require(
            plan.binding == self.engine.profile.binding
            and plan.revision == self.engine.profile.revision,
            "plan_account_revision_mismatch",
        )

    def _row(self, plan_id):
        return self.db.execute(
            "SELECT * FROM broker_plans WHERE plan_id=?", (plan_id,)
        ).fetchone()

    def state(self, plan_id):
        row = self._row(plan_id)
        require(row is not None, "plan_not_found")
        return {
            "plan_id": plan_id,
            "state": row["state"],
            "reason": row["reason"],
            "updated_at": row["updated_at"],
        }

    def _save(self, plan_id, state, reason=None, exit_request=None):
        with self.db:
            self.db.execute(
                "UPDATE broker_plans SET state=?,reason=?,exit_request=COALESCE(?,exit_request),updated_at=CURRENT_TIMESTAMP WHERE plan_id=?",
                (
                    state,
                    reason,
                    exit_request.model_dump_json() if exit_request else None,
                    plan_id,
                ),
            )
        return self.state(plan_id)

    def _quote(self, symbol):
        quote = self.quotes.quote(symbol)
        require(isinstance(quote, Quote), "quote_contract_required")
        require(
            quote.symbol == symbol
            and quote.realtime
            and 0
            <= (now() - quote.observed_at).total_seconds()
            <= self.engine.profile.max_quote_age_seconds,
            "dispatch_quote_stale_or_delayed",
        )
        return quote

    def tick(self, plan_id):
        """One bounded step; callers schedule retries, never rerun an uncertain POST."""
        with owner(self.engine.directory / "lifecycle.lock"):
            row = self._row(plan_id)
            require(row is not None, "plan_not_found")
            if row["state"] in ("closed", "expired", "unfilled", "manual_review"):
                return self.state(plan_id)
            plan = ApprovedPlan.model_validate_json(row["payload"])
            self._binding(plan)
            if row["exit_request"]:
                return self._exit(plan, Intent.model_validate_json(row["exit_request"]))
            existing = self.engine.ledger.get(plan.entry.client_id)
            mode = self.engine._authority()["mode"]
            if existing is None:
                if now() >= plan.entry.expires_at or mode != "entries":
                    return self._save(plan_id, "expired", "entry_expired_or_revoked")
                require(self.audit.verify(plan) is True, "independent_audit_not_proven")
                result = self.engine.submit(plan.entry, self._quote(plan.entry.symbol))
            else:
                result = self.engine.reconcile_order(plan.entry.client_id)
            if result.state in ("working", "unknown"):
                if now() >= plan.entry.expires_at or mode != "entries":
                    result = self.engine.cancel(plan.entry.client_id)
                if result.state in ("working", "unknown"):
                    return self._save(plan_id, "entry_working")
            if result.filled == 0:
                return self._save(plan_id, "unfilled")
            quote = self._quote(plan.entry.symbol)
            reason = (
                "authority_revoked"
                if mode != "entries"
                else "time_exit"
                if now() >= plan.exit_at
                else "stop_exit"
                if quote.bid <= plan.stop_price
                else "target_exit"
                if quote.bid >= plan.target_price
                else None
            )
            if reason is None:
                return self._save(plan_id, "monitoring")
            # Freeze identity and terms before the first call to the engine.
            # After a crash, a new quote may not rewrite an uncertain exit.
            exit_request = Intent(
                client_id="alta-"
                + hashlib.sha256((plan_id + ":exit:1").encode()).hexdigest()[:32],
                symbol=plan.entry.symbol,
                side="SELL",
                quantity=result.filled,
                limit_price=(quote.bid * Decimal("0.9975")).quantize(
                    Decimal("0.01"), rounding=ROUND_FLOOR
                ),
                reference_id=plan.audit_id,
                expires_at=min(
                    now() + timedelta(seconds=10),
                    quote.observed_at
                    + timedelta(seconds=self.engine.profile.max_quote_age_seconds),
                ),
            )
            self._save(plan_id, "exit_prepared", reason, exit_request)
            return self._exit(plan, exit_request)

    def _exit(self, plan, request):
        existing = self.engine.ledger.get(request.client_id)
        if existing is None:
            if now() >= request.expires_at:
                return self._save(
                    plan.plan_id, "manual_review", "unsubmitted_exit_expired"
                )
            result = self.engine.submit(request, self._quote(request.symbol))
        else:
            result = self.engine.reconcile_order(request.client_id)
        if result.state == "filled":
            self.engine.reconcile()  # Broker positions must agree before declaring closure.
            require(self.engine.ledger.flat_and_settled(), "broker_position_drift")
            return self._save(plan.plan_id, "closed")
        if result.state in ("cancelled", "rejected"):
            return self._save(plan.plan_id, "manual_review", "exit_incomplete")
        if now() >= request.expires_at:
            result = self.engine.cancel(request.client_id)
            if result.state == "filled":
                self.engine.reconcile()
                require(self.engine.ledger.flat_and_settled(), "broker_position_drift")
                return self._save(plan.plan_id, "closed")
            if result.state in ("cancelled", "rejected"):
                return self._save(plan.plan_id, "manual_review", "exit_incomplete")
        return self._save(plan.plan_id, "exit_working")
