import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .paper_execution import PaperExecutionResult


class PaperIntentError(RuntimeError):
    pass


class DurablePaperDrain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    drain_id: str = Field(min_length=3, max_length=128)
    account_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization_generation: int = Field(gt=0)
    state: Literal["requested", "draining", "completed", "manual_review"]


class DurablePaperIntent(BaseModel):
    """Crash-recoverable broker mutation prepared before any SDK call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_id: str = Field(min_length=3, max_length=128)
    account_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    client_order_id: str = Field(pattern=r"^alta-[a-f0-9]{32}$")
    cycle_id: str = Field(min_length=3, max_length=256)
    position_id: str = Field(min_length=3, max_length=128)
    expression_id: str = Field(min_length=3, max_length=128)
    operation: Literal["open", "close"]
    action: Literal["BUY", "SELL"]
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    quantity: Decimal
    limit_price: Decimal
    expected_position_before: Decimal
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: Literal[
        "prepared",
        "dispatching",
        "broker_filled",
        "broker_not_filled",
        "local_committed",
        "abandoned",
        "manual_review",
    ]
    local_commit: dict[str, object]
    broker_result: dict[str, object] | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def request_is_one_share_and_directionally_bound(self) -> "DurablePaperIntent":
        expected = (
            ("BUY", Decimal(0)) if self.operation == "open" else ("SELL", Decimal(1))
        )
        if (self.action, self.expected_position_before) != expected:
            raise ValueError("Paper intent operation is not directionally bound")
        if self.quantity != 1 or self.limit_price <= 0:
            raise ValueError("Paper intent violates one-share limit policy")
        return self


class PaperIntentStore:
    """Durable outbox for broker-first Paper mutations.

    A `prepared` row proves the broker was not called. `dispatching` is committed
    immediately before crossing the isolated-process boundary and is therefore
    never retried after a crash; startup must reconcile it by client identity.
    """

    _ACTIVE_STATES = ("prepared", "dispatching", "broker_filled", "manual_review")

    def __init__(self, database, account_sha256: str) -> None:
        if re.fullmatch(r"[a-f0-9]{64}", account_sha256) is None:
            raise PaperIntentError("Paper account approval hash is invalid")
        self.database = database
        self.account_sha256 = account_sha256

    @staticmethod
    def _hash(value: object) -> str:
        import hashlib

        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def prepare(
        self,
        *,
        cycle_id: str,
        position_id: str,
        expression_id: str,
        operation: Literal["open", "close"],
        symbol: str,
        limit_price: Decimal,
        local_commit: dict[str, object],
    ) -> DurablePaperIntent:
        action = "BUY" if operation == "open" else "SELL"
        expected_before = Decimal(0) if operation == "open" else Decimal(1)
        request = {
            "account_sha256": self.account_sha256,
            "operation": operation,
            "action": action,
            "symbol": symbol,
            "quantity": "1",
            "limit_price": format(limit_price, "f"),
            "expected_position_before": format(expected_before, "f"),
            "position_id": position_id,
            "expression_id": expression_id,
        }
        request_hash = self._hash(request)
        identity_hash = self._hash([cycle_id, request_hash, local_commit])
        intent_id = "paper_intent_" + identity_hash[:32]
        client_order_id = "alta-" + identity_hash[:32]
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            inserted = connection.execute(
                """INSERT INTO ops.paper_intent
                (id, environment, version, known_at, updated_at, account_sha256,
                 client_order_id, cycle_id, position_id, expression_id, operation,
                 action, symbol, quantity, limit_price, expected_position_before,
                 request_hash, state, local_commit)
                VALUES (%s,'shadow',1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,
                        'prepared',%s)
                ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    intent_id,
                    now,
                    now,
                    self.account_sha256,
                    client_order_id,
                    cycle_id,
                    position_id,
                    expression_id,
                    operation,
                    action,
                    symbol,
                    limit_price,
                    expected_before,
                    request_hash,
                    Jsonb(local_commit),
                ),
            ).fetchone()
            row = connection.execute(
                """SELECT id, account_sha256, client_order_id, cycle_id,
                position_id, expression_id, operation, action, symbol, quantity,
                limit_price, expected_position_before, request_hash, state,
                local_commit, broker_result, failure_code
                FROM ops.paper_intent WHERE id = %s""",
                (intent_id,),
            ).fetchone()
        durable = self._row(row)
        expected = DurablePaperIntent(
            intent_id=intent_id,
            account_sha256=self.account_sha256,
            client_order_id=client_order_id,
            cycle_id=cycle_id,
            position_id=position_id,
            expression_id=expression_id,
            operation=operation,
            action=action,
            symbol=symbol,
            quantity=Decimal(1),
            limit_price=limit_price,
            expected_position_before=expected_before,
            request_hash=request_hash,
            state="prepared",
            local_commit=local_commit,
        )
        if (
            inserted is None
            and durable.model_copy(
                update={
                    "state": "prepared",
                    "broker_result": None,
                    "failure_code": None,
                }
            )
            != expected
        ):
            raise PaperIntentError("Paper intent identity collision")
        if inserted is None and durable.state != "prepared":
            raise PaperIntentError(
                "Paper intent already crossed dispatch and requires recovery"
            )
        return durable

    def mark_dispatching(self, intent_id: str) -> DurablePaperIntent:
        return self._transition(
            intent_id,
            expected=("prepared",),
            state="dispatching",
        )

    def record_result(
        self, intent_id: str, result: PaperExecutionResult
    ) -> DurablePaperIntent:
        state = (
            "broker_filled"
            if result.status in ("filled", "already_flat")
            else "broker_not_filled"
        )
        return self._transition(
            intent_id,
            expected=("dispatching",),
            state=state,
            broker_result=result.model_dump(mode="json"),
        )

    def abandon_prepared(self, intent_id: str) -> DurablePaperIntent:
        return self._transition(
            intent_id,
            expected=("prepared",),
            state="abandoned",
            failure_code="restart_before_dispatch",
        )

    def mark_manual_review(self, intent_id: str, code: str) -> DurablePaperIntent:
        return self._transition(
            intent_id,
            expected=("dispatching",),
            state="manual_review",
            failure_code=code,
        )

    def unresolved(self) -> tuple[DurablePaperIntent, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, account_sha256, client_order_id, cycle_id,
                position_id, expression_id, operation, action, symbol, quantity,
                limit_price, expected_position_before, request_hash, state,
                local_commit, broker_result, failure_code
                FROM ops.paper_intent
                WHERE account_sha256 = %s
                  AND state = ANY(%s)
                ORDER BY known_at, id""",
                (self.account_sha256, list(self._ACTIVE_STATES)),
            ).fetchall()
        return tuple(self._row(row) for row in rows)

    @staticmethod
    def circuit_open(database) -> bool:
        with database.connect() as connection:
            return (
                connection.execute(
                    """SELECT EXISTS (
                    SELECT 1 FROM ops.paper_intent
                    WHERE environment = 'shadow' AND state = 'manual_review'
                    )"""
                ).fetchone()[0]
                is True
            )

    def ensure_drain(self, authorization_generation: int) -> DurablePaperDrain:
        if authorization_generation < 1:
            raise PaperIntentError("Paper drain authorization generation is invalid")
        drain_id = (
            "paper_drain_"
            + self._hash([self.account_sha256, authorization_generation])[:32]
        )
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO ops.paper_drain
                (id, environment, version, known_at, updated_at, account_sha256,
                 authorization_generation, state)
                VALUES (%s,'shadow',1,%s,%s,%s,%s,'requested')
                ON CONFLICT (account_sha256, authorization_generation) DO NOTHING""",
                (
                    drain_id,
                    now,
                    now,
                    self.account_sha256,
                    authorization_generation,
                ),
            )
            row = connection.execute(
                """SELECT id, account_sha256, authorization_generation, state
                FROM ops.paper_drain
                WHERE account_sha256 = %s
                  AND state IN ('requested','draining','manual_review')
                ORDER BY known_at, id LIMIT 1""",
                (self.account_sha256,),
            ).fetchone()
        if row is None or row[2] != authorization_generation:
            raise PaperIntentError("Paper drain conflicts with another generation")
        return DurablePaperDrain(
            drain_id=row[0],
            account_sha256=row[1],
            authorization_generation=row[2],
            state=row[3],
        )

    def mark_drain_draining(self, drain_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT state FROM ops.paper_drain WHERE id = %s FOR UPDATE",
                (drain_id,),
            ).fetchone()
            if row is None or row[0] not in ("requested", "draining"):
                raise PaperIntentError("Paper drain cannot enter draining state")
            if row[0] == "requested":
                connection.execute(
                    """UPDATE ops.paper_drain SET state = 'draining',
                    version = version + 1, updated_at = %s WHERE id = %s""",
                    (datetime.now(UTC), drain_id),
                )

    def complete_drain(self, drain_id: str, snapshot: dict[str, object]) -> None:
        if snapshot.get("positionCount") != 0 or snapshot.get("openOrderCount") != 0:
            raise PaperIntentError("Paper drain cannot complete before broker flat")
        with self.database.connect() as connection:
            local_open = connection.execute(
                """SELECT EXISTS (
                SELECT 1 FROM research.shadow_position
                WHERE environment = 'shadow' AND status = 'open'
                )"""
            ).fetchone()[0]
            if local_open:
                raise PaperIntentError("Paper drain cannot complete before local flat")
            updated = connection.execute(
                """UPDATE ops.paper_drain SET state = 'completed',
                version = version + 1, updated_at = %s, last_snapshot = %s
                WHERE id = %s AND state IN ('requested','draining')
                RETURNING id""",
                (datetime.now(UTC), Jsonb(snapshot), drain_id),
            ).fetchone()
            if updated is None:
                raise PaperIntentError("Paper drain completion transition failed")

    @staticmethod
    def commit_local(connection, intent_id: str) -> None:
        row = connection.execute(
            "SELECT state FROM ops.paper_intent WHERE id = %s FOR UPDATE",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise PaperIntentError("Paper intent is missing during local commit")
        if row[0] == "local_committed":
            return
        if row[0] != "broker_filled":
            raise PaperIntentError("Paper intent is not broker-filled")
        connection.execute(
            """UPDATE ops.paper_intent
            SET state = 'local_committed', version = version + 1,
                updated_at = %s
            WHERE id = %s""",
            (datetime.now(UTC), intent_id),
        )

    def _transition(
        self,
        intent_id: str,
        *,
        expected: tuple[str, ...],
        state: str,
        broker_result: dict[str, object] | None = None,
        failure_code: str | None = None,
    ) -> DurablePaperIntent:
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT state FROM ops.paper_intent WHERE id = %s FOR UPDATE",
                (intent_id,),
            ).fetchone()
            if row is None:
                raise PaperIntentError("Paper intent is missing")
            if row[0] == state:
                pass
            elif row[0] not in expected:
                raise PaperIntentError(
                    f"Paper intent transition {row[0]} -> {state} is forbidden"
                )
            else:
                connection.execute(
                    """UPDATE ops.paper_intent
                    SET state = %s, version = version + 1, updated_at = %s,
                        broker_result = COALESCE(%s, broker_result),
                        failure_code = COALESCE(%s, failure_code)
                    WHERE id = %s""",
                    (
                        state,
                        now,
                        Jsonb(broker_result) if broker_result is not None else None,
                        failure_code,
                        intent_id,
                    ),
                )
            durable_row = connection.execute(
                """SELECT id, account_sha256, client_order_id, cycle_id,
                position_id, expression_id, operation, action, symbol, quantity,
                limit_price, expected_position_before, request_hash, state,
                local_commit, broker_result, failure_code
                FROM ops.paper_intent WHERE id = %s""",
                (intent_id,),
            ).fetchone()
        return self._row(durable_row)

    @staticmethod
    def _row(row) -> DurablePaperIntent:
        if row is None:
            raise PaperIntentError("Paper intent row is unavailable")
        return DurablePaperIntent(
            intent_id=row[0],
            account_sha256=row[1],
            client_order_id=row[2],
            cycle_id=row[3],
            position_id=row[4],
            expression_id=row[5],
            operation=row[6],
            action=row[7],
            symbol=row[8],
            quantity=row[9],
            limit_price=row[10],
            expected_position_before=row[11],
            request_hash=row[12],
            state=row[13],
            local_commit=row[14],
            broker_result=row[15],
            failure_code=row[16],
        )
