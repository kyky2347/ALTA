"""Selected-broker handoff and monitoring independent of slow LLM turns."""

import threading
from datetime import UTC, datetime

from .b5_runtime import _append_event, _contract_event
from .broker_handoff import prepare_handoff, require
from .broker_process import BrokerExecutionError, BrokerProcess, selected_broker
from .contracts import Environment
from .market_data import MassiveMarketData
from .massive import MassiveRequestBudget, MassiveRestAdapter


class BrokerResearchBridge:
    def __init__(self, database, process, route, market_data):
        self.database, self.process, self.route, self.market_data = (
            database,
            process,
            route,
            market_data,
        )
        self.stop = threading.Event()
        self.thread = None
        self._monitor_lock = threading.Lock()
        self._last_event = {}

    @classmethod
    def configured(cls, database, root, market_data, *, paper_enabled):
        process = BrokerProcess(root)
        route = selected_broker(process)
        if route is None:
            return None
        require(not paper_enabled, "broker_and_tiger_paper_conflict")
        require(market_data is not None, "broker_realtime_market_data_required")
        source = market_data.adapter
        monitor_data = MassiveMarketData(
            MassiveRestAdapter(
                source.transport,
                source.raw_store,
                source.coordinator,
                request_budget=MassiveRequestBudget(4),
            )
        )
        return cls(database, process, route, monitor_data)

    def call(self, action, **payload):
        request = {
            "action": action,
            "provider": self.route["provider"],
            "revision": self.route["profile_revision"],
            "route_revision": self.route["revision"],
            **payload,
        }
        if action in ("stage", "tick"):
            with self.database.autonomous_external_operation():
                require(not self.stop.is_set(), "broker_monitor_stopping")
                return self.process.request(request, research=True)
        return self.process.request(request, research=True)

    def snapshot(self):
        return self.process.request(
            {"action": "verify", "provider": self.route["provider"]}
        )

    def handoff(self, cycle_id, proposal):
        self.database.assert_autonomous_fence()
        plan_id = proposal.expression_id
        try:
            require(not self.stop.is_set(), "broker_monitor_stopping")
            plan, receipt = prepare_handoff(
                self.database, self.route, cycle_id, proposal
            )
            plan_id = plan["plan_id"]
            result = self.call("stage", plan=plan, receipt=receipt)
        except BrokerExecutionError as error:
            result = {"state": "blocked", "reason": str(error)}
        self._record(plan_id, result, cycle_id)
        return result

    def monitor_once(self):
        if not self._monitor_lock.acquire(blocking=False):
            return ()
        try:
            self.database.assert_autonomous_fence()
            active = self.call("active")
            # Exit observation has its own four-reads/minute allowance. A slow
            # research cycle exhausting its budget must not starve held positions.
            if hasattr(self.market_data, "adapter"):
                self.market_data.adapter.reset_budget(
                    datetime.now(UTC).strftime("broker-monitor-%Y%m%d%H%M")
                )
            observed = []
            for plan in active["plans"]:
                if self.stop.is_set():
                    break
                try:
                    require(
                        plan["state"] != "manual_review",
                        "broker_manual_review_required",
                    )
                    quote = self._quote(plan["symbol"])
                    self.database.assert_autonomous_fence()
                    if self.stop.is_set():
                        break
                    result = self.call(
                        "tick",
                        plan_id=plan["plan_id"],
                        quote=quote,
                    )
                except BrokerExecutionError as error:
                    result = {"state": "blocked", "reason": str(error)}
                self._record(plan["plan_id"], result)
                observed.append(plan["plan_id"])
            return tuple(observed)
        finally:
            self._monitor_lock.release()

    def _quote(self, symbol):
        try:
            selection = self.market_data.equity("stock", symbol)
            if selection.instrument is None:
                return None
            quote = selection.instrument.quote
            # Provider time, not retrieval time. Missing prices still allow
            # reconciliation and cancellation, but cannot authorize a new order.
            if not 0 <= (datetime.now(UTC) - quote.as_of).total_seconds() <= 10:
                return None
            return {
                "symbol": quote.symbol,
                "bid": str(quote.bid),
                "ask": str(quote.ask),
                "observed_at": quote.as_of.isoformat(),
                "realtime": True,
            }
        except Exception:
            return None

    def _record(self, plan_id, result, cycle_id=None):
        signature = (result.get("state"), result.get("reason"))
        if self._last_event.get(plan_id) == signature:
            return
        observed = datetime.now(UTC)
        payload = {
            "plan_id": plan_id,
            "provider": self.route["provider"],
            "broker_environment": self.route["environment"],
            "account_binding": self.route["binding"],
            "state": signature[0],
            "reason": signature[1],
            "observed_at": observed.isoformat(),
        }
        with self.database.connect() as connection:
            _append_event(
                connection,
                _contract_event(
                    event_type="broker.lifecycle.updated",
                    aggregate_type="broker_plan",
                    aggregate_id=plan_id,
                    environment=Environment.SHADOW,
                    known_at=observed,
                    payload=payload,
                    correlation_id=cycle_id,
                ),
            )
        if len(self._last_event) >= 512 and plan_id not in self._last_event:
            self._last_event.pop(next(iter(self._last_event)))
        self._last_event[plan_id] = signature

    def start(self):
        require(self.thread is None, "broker_monitor_already_started")

        def run():
            while not self.stop.is_set():
                try:
                    self.monitor_once()
                except Exception:
                    # No raw SDK/DB response belongs in logs. Preserve the lane;
                    # failure does not select another broker or repeat a POST.
                    try:
                        self._record(
                            "broker-monitor",
                            {
                                "state": "blocked",
                                "reason": "broker_monitor_unavailable",
                            },
                        )
                    except Exception:
                        pass
                self.stop.wait(15)

        self.thread = threading.Thread(
            target=run, name="alta-broker-monitor", daemon=True
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=55)
            require(not self.thread.is_alive(), "broker_monitor_stop_unconfirmed")
