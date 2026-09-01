from typing import Literal

from psycopg.types.json import Jsonb

from .contracts import Environment, Event
from .database import Database
from .expression import (
    EvidenceVersion,
    ExpressionProposal,
    ExpressionValidation,
    VersionBinding,
    contract_hash,
)
from .paper_execution import PaperExecutionResult
from .paper_intent import PaperIntentStore
from .shadow import (
    ExitDecision,
    LedgerTransaction,
    MonitorObservation,
    PositionThesis,
    ShadowFill,
    ShadowIntent,
)


def _append_event(connection, event: Event) -> None:
    normalized_payload = event.model_dump(mode="json")["payload"]
    row = connection.execute(
        """INSERT INTO ops.event
        (id, environment, version, known_at, aggregate_type, aggregate_id,
         event_type, payload, correlation_id, causation_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO NOTHING RETURNING id""",
        (
            event.id,
            event.environment.value,
            event.version,
            event.known_at,
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            Jsonb(normalized_payload),
            event.correlation_id,
            event.causation_id,
        ),
    ).fetchone()
    if row is not None:
        return
    existing = connection.execute(
        """SELECT environment::text, version, known_at, aggregate_type,
        aggregate_id, event_type, payload, correlation_id, causation_id
        FROM ops.event WHERE id = %s""",
        (event.id,),
    ).fetchone()
    expected = (
        event.environment.value,
        event.version,
        event.known_at,
        event.aggregate_type,
        event.aggregate_id,
        event.event_type,
        normalized_payload,
        event.correlation_id,
        event.causation_id,
    )
    if existing != expected:
        raise ValueError("event ID already contains different immutable content")


def _contract_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    environment: Environment,
    known_at,
    payload: dict,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    event_id = "event_" + contract_hash([event_type, aggregate_id, payload])[:32]
    return Event(
        id=event_id,
        environment=environment,
        version=1,
        known_at=known_at,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


def _dump(contract) -> dict:
    return contract.model_dump(mode="json")


class ExpressionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def binding_for(self, opportunity_id: str) -> VersionBinding:
        with self.database.connect() as connection:
            opportunity = connection.execute(
                """SELECT environment::text, version, snapshot_hash, evidence_ids
                FROM research.opportunity WHERE id = %s""",
                (opportunity_id,),
            ).fetchone()
            if opportunity is None:
                raise ValueError("opportunity does not exist")
            evidence_rows = connection.execute(
                """SELECT id, version, known_at FROM research.evidence
                WHERE id = ANY(%s) ORDER BY id""",
                (opportunity[3],),
            ).fetchall()
        if len(evidence_rows) != len(opportunity[3]) or not evidence_rows:
            raise ValueError("opportunity must bind existing versioned evidence")
        evidence = tuple(
            EvidenceVersion(evidence_id=row[0], version=row[1], known_at=row[2])
            for row in evidence_rows
        )
        evidence_set_hash = contract_hash(
            [item.model_dump(mode="json") for item in evidence]
        )
        return VersionBinding(
            environment=Environment(opportunity[0]),
            opportunity_id=opportunity_id,
            opportunity_version=opportunity[1],
            opportunity_snapshot_hash=opportunity[2],
            evidence=evidence,
            evidence_set_hash=evidence_set_hash,
        )

    def persist(
        self,
        proposal: ExpressionProposal,
        validation: ExpressionValidation,
    ) -> None:
        expected = self.binding_for(proposal.binding.opportunity_id)
        if proposal.binding != expected or validation.binding != expected:
            raise ValueError(
                "expression changed the frozen Opportunity/Evidence binding"
            )
        if (
            validation.expression_id,
            validation.expression_version,
            validation.expression_hash,
        ) != (proposal.expression_id, proposal.version, proposal.hash()):
            raise ValueError("validation does not match the frozen expression")
        status = validation.status
        with self.database.connect() as connection:
            inserted = connection.execute(
                """INSERT INTO research.expression
                (id, environment, version, known_at, opportunity_id,
                 opportunity_version, kind, status, rationale,
                 opportunity_snapshot_hash, evidence_refs, evidence_set_hash,
                 binding_hash, symbol, side, decision_known_at, quote_snapshot,
                 validation, expression_hash, policy_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    proposal.expression_id,
                    proposal.binding.environment.value,
                    proposal.version,
                    proposal.decision_known_at,
                    proposal.binding.opportunity_id,
                    proposal.binding.opportunity_version,
                    proposal.kind,
                    status,
                    proposal.rationale,
                    proposal.binding.opportunity_snapshot_hash,
                    Jsonb([_dump(item) for item in proposal.binding.evidence]),
                    proposal.binding.evidence_set_hash,
                    proposal.binding.hash(),
                    proposal.symbol,
                    proposal.side,
                    proposal.decision_known_at,
                    Jsonb(_dump(proposal.quote)) if proposal.quote else None,
                    Jsonb(_dump(validation)),
                    proposal.hash(),
                    validation.policy_version,
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    """SELECT expression_hash, binding_hash, validation
                    FROM research.expression WHERE id = %s""",
                    (proposal.expression_id,),
                ).fetchone()
                if existing != (
                    proposal.hash(),
                    proposal.binding.hash(),
                    _dump(validation),
                ):
                    raise ValueError("expression ID already has different content")
            payload = {
                "expression": _dump(proposal),
                "validation": _dump(validation),
            }
            _append_event(
                connection,
                _contract_event(
                    event_type=f"expression.{status}",
                    aggregate_type="expression",
                    aggregate_id=proposal.expression_id,
                    environment=proposal.binding.environment,
                    known_at=validation.known_at,
                    payload=payload,
                    correlation_id=proposal.binding.opportunity_id,
                ),
            )


class ShadowRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _validate_open_contracts(
        intent: ShadowIntent,
        fill: ShadowFill,
        transaction: LedgerTransaction,
        thesis: PositionThesis,
    ) -> None:
        if intent.action != "open" or fill.action != "open" or fill.status != "filled":
            raise ValueError("opening a position requires a filled open intent")
        if (
            fill.intent_id != intent.intent_id
            or fill.position_id != intent.position_id
            or fill.binding != intent.binding
        ):
            raise ValueError("open fill does not match intent")
        if (
            transaction.fill_id != fill.fill_id
            or transaction.position_id != intent.position_id
            or transaction.binding != intent.binding
            or transaction.action != "open"
        ):
            raise ValueError("open ledger does not match fill")
        if (
            thesis.position_id != intent.position_id
            or thesis.expression_id != intent.expression_id
            or thesis.expression_version != intent.expression_version
            or thesis.expression_hash != intent.expression_hash
            or thesis.binding != intent.binding
        ):
            raise ValueError("PositionThesis does not match frozen intent versions")
        if thesis.known_at < fill.known_at:
            raise ValueError("PositionThesis cannot predate the fill")

    def open(
        self,
        intent: ShadowIntent,
        fill: ShadowFill,
        transaction: LedgerTransaction,
        thesis: PositionThesis,
        *,
        paper_intent_id: str | None = None,
        paper_cycle_id: str | None = None,
        paper_result: PaperExecutionResult | None = None,
    ) -> None:
        self._validate_open_contracts(intent, fill, transaction, thesis)
        if fill.fill_price is None or fill.commission is None:
            raise ValueError("open fill is incomplete")
        if (
            ExpressionRepository(self.database).binding_for(
                intent.binding.opportunity_id
            )
            != intent.binding
        ):
            raise ValueError("open intent no longer matches current frozen versions")
        with self.database.connect() as connection:
            expression = connection.execute(
                """SELECT version, expression_hash, binding_hash, status, kind,
                symbol FROM research.expression WHERE id = %s""",
                (intent.expression_id,),
            ).fetchone()
            expected = (
                intent.expression_version,
                intent.expression_hash,
                intent.binding.hash(),
            )
            if (
                expression is None
                or expression[:3] != expected
                or expression[3] not in ("validated", "active", "closed")
            ):
                raise ValueError("open intent is not bound to a validated expression")
            if expression[4] == "wait" or expression[5] != intent.symbol:
                raise ValueError("Wait or mismatched instrument cannot open a position")
            if expression[3] == "closed":
                existing = connection.execute(
                    """SELECT id, entry_transaction_id, thesis_hash
                    FROM research.shadow_position WHERE expression_id = %s""",
                    (intent.expression_id,),
                ).fetchone()
                if existing != (
                    intent.position_id,
                    transaction.transaction_id,
                    thesis.hash(),
                ):
                    raise ValueError(
                        "closed expression has a different Shadow position"
                    )
                self._append_open_events(connection, intent, fill, transaction, thesis)
                self._commit_paper(
                    connection,
                    paper_intent_id,
                    paper_cycle_id,
                    paper_result,
                    fill.known_at,
                    intent.position_id,
                )
                return
            inserted = connection.execute(
                """INSERT INTO research.shadow_position
                (id, environment, version, known_at, expression_id, symbol, side,
                 quantity, status, opportunity_id, opportunity_version,
                 opportunity_snapshot_hash, evidence_refs, evidence_set_hash,
                 binding_hash, expression_version, expression_hash,
                 entry_transaction_id, entry_price, entry_commission, opened_at,
                 position_thesis, thesis_hash, ledger_version)
                VALUES (%s,%s,1,%s,%s,%s,'long',%s,'open',%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (expression_id) DO NOTHING RETURNING id""",
                (
                    intent.position_id,
                    intent.binding.environment.value,
                    fill.known_at,
                    intent.expression_id,
                    intent.symbol,
                    intent.quantity,
                    intent.binding.opportunity_id,
                    intent.binding.opportunity_version,
                    intent.binding.opportunity_snapshot_hash,
                    Jsonb([_dump(item) for item in intent.binding.evidence]),
                    intent.binding.evidence_set_hash,
                    intent.binding.hash(),
                    intent.expression_version,
                    intent.expression_hash,
                    transaction.transaction_id,
                    fill.fill_price,
                    fill.commission,
                    fill.known_at,
                    Jsonb(_dump(thesis)),
                    thesis.hash(),
                    transaction.ledger_version,
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    """SELECT id, entry_transaction_id, thesis_hash
                    FROM research.shadow_position WHERE expression_id = %s""",
                    (intent.expression_id,),
                ).fetchone()
                if existing != (
                    intent.position_id,
                    transaction.transaction_id,
                    thesis.hash(),
                ):
                    raise ValueError(
                        "expression already has a different Shadow position"
                    )
            connection.execute(
                "UPDATE research.expression SET status = 'active' WHERE id = %s",
                (intent.expression_id,),
            )
            connection.execute(
                "UPDATE research.opportunity SET status = 'shadow' WHERE id = %s",
                (intent.binding.opportunity_id,),
            )
            self._append_open_events(connection, intent, fill, transaction, thesis)
            self._commit_paper(
                connection,
                paper_intent_id,
                paper_cycle_id,
                paper_result,
                fill.known_at,
                intent.position_id,
            )

    @staticmethod
    def _append_open_events(connection, intent, fill, transaction, thesis) -> None:
        contracts = (
            ("shadow.intent.committed", intent, intent.committed_at, intent.intent_id),
            ("shadow.fill.recorded", fill, fill.known_at, fill.fill_id),
            (
                "shadow.ledger.posted",
                transaction,
                transaction.known_at,
                transaction.transaction_id,
            ),
            ("position.thesis.opened", thesis, thesis.known_at, thesis.thesis_id),
        )
        for event_type, contract, known_at, causation_id in contracts:
            _append_event(
                connection,
                _contract_event(
                    event_type=event_type,
                    aggregate_type="shadow_position",
                    aggregate_id=intent.position_id,
                    environment=intent.binding.environment,
                    known_at=known_at,
                    payload=_dump(contract),
                    correlation_id=intent.expression_id,
                    causation_id=causation_id,
                ),
            )

    def record_monitor(
        self, observation: MonitorObservation, decision: ExitDecision
    ) -> None:
        if (
            decision.position_id != observation.position_id
            or decision.observation_id != observation.observation_id
            or decision.binding != observation.binding
        ):
            raise ValueError("exit decision does not match monitor observation")
        payload = {"observation": _dump(observation), "decision": _dump(decision)}
        event = _contract_event(
            event_type="position.monitored",
            aggregate_type="shadow_position",
            aggregate_id=observation.position_id,
            environment=observation.binding.environment,
            known_at=observation.known_at,
            payload=payload,
            correlation_id=observation.binding.opportunity_id,
            causation_id=observation.observation_id,
        )
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT thesis_hash, binding_hash, status
                FROM research.shadow_position
                WHERE id = %s""",
                (observation.position_id,),
            ).fetchone()
            expected = (observation.thesis_hash, observation.binding.hash())
            if row is None or row[:2] != expected:
                raise ValueError("monitor changed frozen position versions")
            if (
                row[2] == "closed"
                and connection.execute(
                    "SELECT 1 FROM ops.event WHERE id = %s", (event.id,)
                ).fetchone()
                is None
            ):
                raise ValueError("cannot add a new monitor after position close")
            _append_event(connection, event)

    def close(
        self,
        intent: ShadowIntent,
        fill: ShadowFill,
        transaction: LedgerTransaction,
        decision: ExitDecision,
        *,
        paper_intent_id: str | None = None,
        paper_cycle_id: str | None = None,
        paper_result: PaperExecutionResult | None = None,
    ) -> None:
        close_state = (intent.action, fill.action, fill.status, decision.action)
        if close_state != ("close", "close", "filled", "exit"):
            raise ValueError("closing requires an exit decision and filled close")
        contract_links = (
            intent.position_id,
            fill.intent_id,
            fill.binding,
            transaction.fill_id,
            transaction.binding,
            transaction.action,
            decision.binding,
        )
        expected_links = (
            decision.position_id,
            intent.intent_id,
            intent.binding,
            fill.fill_id,
            intent.binding,
            "close",
            intent.binding,
        )
        if contract_links != expected_links:
            raise ValueError("close contracts do not share frozen versions")
        if intent.committed_at < decision.known_at:
            raise ValueError("close intent cannot predate its ExitDecision")
        if fill.fill_price is None or fill.commission is None:
            raise ValueError("close fill is incomplete")
        with self.database.connect() as connection:
            position = connection.execute(
                """SELECT status, expression_id, expression_version,
                expression_hash, binding_hash, quantity, exit_transaction_id,
                thesis_hash
                FROM research.shadow_position WHERE id = %s FOR UPDATE""",
                (intent.position_id,),
            ).fetchone()
            if position is None or position[1:5] != (
                intent.expression_id,
                intent.expression_version,
                intent.expression_hash,
                intent.binding.hash(),
            ):
                raise ValueError("close intent changed frozen position versions")
            if position[5] != intent.quantity:
                raise ValueError("B5 closes the full Shadow quantity only")
            if position[7] != decision.thesis_hash:
                raise ValueError("exit decision changed frozen PositionThesis")
            if position[0] == "closed":
                if position[6] != transaction.transaction_id:
                    raise ValueError("position already has a different close")
            else:
                connection.execute(
                    """UPDATE research.shadow_position SET status = 'closed',
                    version = version + 1, known_at = %s, closed_at = %s,
                    exit_decision = %s, exit_transaction_id = %s,
                    exit_price = %s, exit_commission = %s WHERE id = %s""",
                    (
                        fill.known_at,
                        fill.known_at,
                        Jsonb(_dump(decision)),
                        transaction.transaction_id,
                        fill.fill_price,
                        fill.commission,
                        intent.position_id,
                    ),
                )
            connection.execute(
                "UPDATE research.expression SET status = 'closed' WHERE id = %s",
                (intent.expression_id,),
            )
            connection.execute(
                "UPDATE research.opportunity SET status = 'closed' WHERE id = %s",
                (intent.binding.opportunity_id,),
            )
            contracts = (
                ("shadow.exit_intent.committed", intent, intent.committed_at),
                ("shadow.exit_fill.recorded", fill, fill.known_at),
                ("shadow.ledger.posted", transaction, transaction.known_at),
                ("position.exit_decided", decision, decision.known_at),
            )
            for event_type, contract, known_at in contracts:
                _append_event(
                    connection,
                    _contract_event(
                        event_type=event_type,
                        aggregate_type="shadow_position",
                        aggregate_id=intent.position_id,
                        environment=intent.binding.environment,
                        known_at=known_at,
                        payload=_dump(contract),
                        correlation_id=intent.expression_id,
                    ),
                )
            self._commit_paper(
                connection,
                paper_intent_id,
                paper_cycle_id,
                paper_result,
                fill.known_at,
                intent.position_id,
            )

    @staticmethod
    def _commit_paper(
        connection,
        paper_intent_id: str | None,
        paper_cycle_id: str | None,
        paper_result: PaperExecutionResult | None,
        known_at,
        position_id: str,
    ) -> None:
        supplied = (
            paper_intent_id is not None,
            paper_cycle_id is not None,
            paper_result is not None,
        )
        if not any(supplied):
            return
        if not all(supplied):
            raise ValueError("Paper local commit binding is incomplete")
        if paper_result.status not in ("filled", "already_flat"):
            raise ValueError("Paper local commit requires broker completion")
        PaperIntentStore.commit_local(connection, paper_intent_id)
        event_type = (
            "paper.order.filled"
            if paper_result.status == "filled"
            else "paper.position.verified_flat"
        )
        _append_event(
            connection,
            _contract_event(
                event_type=event_type,
                aggregate_type="shadow_position",
                aggregate_id=position_id,
                environment=Environment.SHADOW,
                known_at=known_at,
                payload={
                    "cycle_id": paper_cycle_id,
                    "broker": "tiger_paper",
                    "paper_intent_id": paper_intent_id,
                    **paper_result.model_dump(mode="json"),
                },
                correlation_id=paper_cycle_id,
                causation_id=paper_intent_id,
            ),
        )

    def ledger(self, position_id: str) -> tuple[LedgerTransaction, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT payload FROM ops.event WHERE aggregate_id = %s
                AND event_type = 'shadow.ledger.posted' ORDER BY sequence""",
                (position_id,),
            ).fetchall()
        return tuple(LedgerTransaction.model_validate(row[0]) for row in rows)


class B5Runtime:
    def __init__(
        self, database: Database, capital_mode: Literal["disabled"] = "disabled"
    ) -> None:
        if capital_mode != "disabled":
            raise ValueError("the B5 main runtime requires capital mode disabled")
        self.capital_mode = capital_mode
        self.expressions = ExpressionRepository(database)
        self.shadow = ShadowRepository(database)
