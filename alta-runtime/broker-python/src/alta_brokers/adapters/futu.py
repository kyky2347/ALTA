"""Futu/moomoo OpenD: explicit security firm, account and trade environment."""

from ..contracts import Order, Position, Snapshot, dispatch_guard, now, require


class Futu:
    def __init__(self, profile, client=None):
        self.profile = profile
        self.account = int(profile.account.get_secret_value())
        # OpenD treats zero as "select by account index", not an exact binding.
        require(0 < self.account < 2**63, "broker_account_invalid")
        self.env = "SIMULATE" if profile.environment == "PAPER" else "REAL"
        if client is not None:
            self.client = client
            return
        from futu import OpenSecTradeContext, TrdMarket, SecurityFirm

        firm = profile.secret("security_firm")
        require(
            firm
            in ("FUTUSECURITIES", "FUTUINC", "FUTUSG", "FUTUAU", "FUTUCA", "FUTUJP"),
            "security_firm_invalid",
        )
        port = int(profile.secret("port"))
        require(1024 <= port <= 65535, "gateway_port_invalid")
        # OpenD remains operator-owned. ALTA never downloads/starts/unlocks it at login.
        self.client = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host="127.0.0.1",
            port=port,
            security_firm=getattr(SecurityFirm, firm),
        )

    @staticmethod
    def rows(response):
        code, data = response
        require(code == 0 and hasattr(data, "to_dict"), "opend_request_failed")
        return data.to_dict("records")

    @staticmethod
    def order(row):
        state = row["order_status"]
        return Order(
            order_id=str(row["order_id"]),
            client_id=row.get("remark", ""),
            symbol=row["code"].removeprefix("US."),
            side=row["trd_side"],
            quantity=row["qty"],
            filled=row["dealt_qty"],
            limit_price=row["price"],
            average_price=row["dealt_avg_price"] if row["dealt_qty"] else None,
            state="filled"
            if state == "FILLED_ALL"
            else "cancelled"
            if state in ("CANCELLED_ALL", "CANCELLED_PART", "DELETED")
            else "rejected"
            if state in ("FAILED", "DISABLED")
            else "working"
            if state
            in (
                "WAITING_SUBMIT",
                "SUBMITTING",
                "SUBMITTED",
                "FILLED_PART",
                "CANCELLING_ALL",
                "CANCELLING_PART",
            )
            else "unknown",
        )

    def snapshot(self):
        accounts = self.rows(self.client.get_acc_list())
        selected = [a for a in accounts if str(a["acc_id"]) == str(self.account)]
        require(
            len(selected) == 1 and selected[0]["trd_env"] == self.env,
            "account_environment_mismatch",
        )
        rows = self.rows(
            self.client.accinfo_query(
                trd_env=self.env,
                acc_id=self.account,
                refresh_cache=True,
                currency="USD",
            )
        )
        require(len(rows) == 1, "snapshot_incomplete")
        a = rows[0]
        positions = self.rows(
            self.client.position_list_query(
                trd_env=self.env, acc_id=self.account, refresh_cache=True
            )
        )
        orders = tuple(
            self.order(o)
            for o in self.rows(
                self.client.order_list_query(
                    trd_env=self.env, acc_id=self.account, refresh_cache=True
                )
            )
        )
        return Snapshot(
            binding=self.profile.binding,
            environment=self.profile.environment,
            verified_at=now(),
            currency="USD",
            equity=a["total_assets"],
            cash=a["cash"],
            buying_power=a["power"],
            positions=tuple(
                Position(
                    symbol=p["code"].removeprefix("US."),
                    quantity=p["qty"],
                    market_value=p["market_val"],
                    currency=p["currency"],
                )
                for p in positions
            ),
            orders=tuple(o for o in orders if o.state in ("working", "unknown")),
            account_verified=True,
            environment_verified=True,
            trading_permitted="US" in selected[0]["trdmarket_auth"],
        )

    def submit(self, intent):
        dispatch_guard(intent)
        if self.env == "REAL":
            code, _ = self.client.unlock_trade(
                password=self.profile.secret("trade_password")
            )
            require(code == 0, "opend_unlock_failed")
        dispatch_guard(intent)
        rows = self.rows(
            self.client.place_order(
                price=float(intent.limit_price),
                qty=int(intent.quantity),
                code=f"US.{intent.symbol}",
                trd_side=intent.side,
                order_type="NORMAL",
                trd_env=self.env,
                acc_id=self.account,
                remark=intent.client_id,
                time_in_force="DAY",
                fill_outside_rth=False,
                session="RTH",
            )
        )
        require(len(rows) == 1, "submission_outcome_unknown")
        return self.order(rows[0])

    def lookup(self, client_id, order_id):
        rows = self.rows(
            self.client.order_list_query(
                order_id=order_id or "",
                trd_env=self.env,
                acc_id=self.account,
                refresh_cache=True,
            )
        )
        results = [self.order(row) for row in rows if row.get("remark") == client_id]
        require(len(results) <= 1, "duplicate_client_order")
        if order_id and rows:
            require(len(results) == 1, "order_identity_mismatch")
        return results[0] if results else None

    def cancel(self, order_id):
        code, _ = self.client.modify_order(
            "CANCEL", order_id, 0, 0, trd_env=self.env, acc_id=self.account
        )
        require(code == 0, "cancel_outcome_unknown")

    def close(self):
        self.client.close()
