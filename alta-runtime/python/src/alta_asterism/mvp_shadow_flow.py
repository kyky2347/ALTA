from datetime import datetime, timedelta
from decimal import Decimal

from psycopg.types.json import Jsonb

from .alpha_feedback import load_alpha_contributors
from .b5_runtime import B5Runtime
from .database import Database
from .expression import (
    ExpressionPolicy,
    ExpressionProposal,
    QuoteSnapshot,
    contract_hash,
    validate_expression,
)
from .foundry import OpportunityDraft
from .mvp_fixture import MvpFixture
from .shadow import (
    LedgerTransaction,
    MonitorObservation,
    MonitorPolicy,
    PositionThesis,
    ShadowFillPolicy,
    ShadowIntent,
    close_ledger_transaction,
    evaluate_shadow_fill,
    monitor_position,
    open_ledger_transaction,
)


class MvpShadowFlow:
    def __init__(self, database: Database, fixture: MvpFixture) -> None:
        self.database = database
        self.fixture = fixture
        self.runtime = B5Runtime(database, capital_mode="disabled")

    @property
    def capital_mode(self) -> str:
        return self.runtime.capital_mode

    def express(
        self, demo_id: str, opportunity: OpportunityDraft, wake_at: datetime
    ) -> ExpressionProposal:
        binding = self.runtime.expressions.binding_for(opportunity.opportunity_id)
        quote = self._quote(demo_id, "validation", wake_at, 14, 15)
        proposal = ExpressionProposal(
            expression_id="expression_"
            + contract_hash([demo_id, opportunity.opportunity_id, "stock"])[:32],
            binding=binding,
            kind="stock",
            symbol=self.fixture.symbol,
            side="long",
            quantity=Decimal("10"),
            rationale="Top-ranked fixed B6 Stock expression.",
            decision_known_at=wake_at + timedelta(seconds=16),
            quote=quote,
            thesis_pillar_ids=tuple(
                item.pillar_id for item in opportunity.thesis_pillars[:1]
            ),
        )
        validation = validate_expression(proposal, ExpressionPolicy())
        if validation.status != "validated":
            raise ValueError("B6 fixture Expression failed deterministic validation")
        self.runtime.expressions.persist(proposal, validation)
        return proposal

    def open_shadow(
        self,
        demo_id: str,
        opportunity: OpportunityDraft,
        proposal: ExpressionProposal,
        wake_at: datetime,
    ) -> tuple[PositionThesis, LedgerTransaction]:
        fill_policy = ShadowFillPolicy()
        with self.database.connect() as connection:
            alpha_contributors = load_alpha_contributors(
                connection, opportunity.member_candidate_ids
            )
        if not alpha_contributors:
            raise ValueError("fixture Opportunity is missing frozen Alpha contributors")
        position_id = f"shadow_{contract_hash([demo_id, proposal.expression_id])[:32]}"
        intent = ShadowIntent(
            intent_id=f"intent_{contract_hash([demo_id, 'open'])[:32]}",
            position_id=position_id,
            action="open",
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=proposal.hash(),
            binding=proposal.binding,
            symbol=self.fixture.symbol,
            quantity=proposal.quantity,
            committed_at=wake_at + timedelta(seconds=17),
            policy_version=fill_policy.version,
        )
        fill = evaluate_shadow_fill(
            intent, self._quote(demo_id, "entry", wake_at, 18, 19), fill_policy
        )
        ledger = open_ledger_transaction(fill)
        thesis = PositionThesis(
            thesis_id=f"thesis_{contract_hash([demo_id, position_id])[:32]}",
            position_id=position_id,
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=proposal.hash(),
            binding=proposal.binding,
            known_at=fill.known_at,
            entry_expectation=(
                opportunity.expectation or "Frozen fixture expectation."
            ),
            why_now=opportunity.why_now or "Frozen fixture why-now.",
            invalidation_condition=(opportunity.falsifier or "Fixture falsifier."),
            time_exit_at=wake_at + timedelta(seconds=30),
            next_catalyst="Next versioned fixture update.",
            better_opportunity_min_bps=Decimal("75"),
            alpha_contributors=alpha_contributors,
            thesis_pillars=tuple(
                item
                for item in opportunity.thesis_pillars
                if item.pillar_id in proposal.thesis_pillar_ids
            ),
        )
        self.runtime.shadow.open(intent, fill, ledger, thesis)
        return thesis, ledger

    def monitor_and_exit(
        self,
        demo_id: str,
        proposal: ExpressionProposal,
        thesis: PositionThesis,
        open_ledger: LedgerTransaction,
        wake_at: datetime,
    ) -> LedgerTransaction:
        monitor_policy = MonitorPolicy()
        hold_observation = MonitorObservation(
            observation_id=(f"observation_{contract_hash([demo_id, 'hold'])[:32]}"),
            position_id=thesis.position_id,
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            thesis_hash=thesis.hash(),
            binding=proposal.binding,
            known_at=wake_at + timedelta(seconds=24),
            quote=self._quote(demo_id, "hold", wake_at, 22, 23),
        )
        hold = monitor_position(thesis, hold_observation, monitor_policy)
        if hold.action != "hold":
            raise ValueError("B6 fixture hold monitor exited unexpectedly")
        self.runtime.shadow.record_monitor(hold_observation, hold)

        exit_observation = MonitorObservation(
            observation_id=(f"observation_{contract_hash([demo_id, 'exit'])[:32]}"),
            position_id=thesis.position_id,
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            thesis_hash=thesis.hash(),
            binding=proposal.binding,
            known_at=wake_at + timedelta(seconds=32),
            quote=self._quote(demo_id, "exit_monitor", wake_at, 30, 31),
        )
        decision = monitor_position(thesis, exit_observation, monitor_policy)
        if (decision.action, decision.reason_code) != ("exit", "time_exit"):
            raise ValueError("B6 fixture time exit did not trigger")
        self.runtime.shadow.record_monitor(exit_observation, decision)

        fill_policy = ShadowFillPolicy()
        close_intent = ShadowIntent(
            intent_id=f"intent_{contract_hash([demo_id, 'close'])[:32]}",
            position_id=thesis.position_id,
            action="close",
            expression_id=proposal.expression_id,
            expression_version=proposal.version,
            expression_hash=proposal.hash(),
            binding=proposal.binding,
            symbol=self.fixture.symbol,
            quantity=proposal.quantity,
            committed_at=wake_at + timedelta(seconds=33),
            policy_version=fill_policy.version,
        )
        close_fill = evaluate_shadow_fill(
            close_intent,
            self._quote(demo_id, "exit_fill", wake_at, 34, 35),
            fill_policy,
        )
        cost_basis = next(
            line.debit for line in open_ledger.lines if line.account == "position"
        )
        close_ledger = close_ledger_transaction(
            close_fill, position_cost_basis=cost_basis
        )
        self.runtime.shadow.close(close_intent, close_fill, close_ledger, decision)
        return close_ledger

    def _quote(
        self,
        demo_id: str,
        label: str,
        wake_at: datetime,
        as_of_seconds: int,
        known_seconds: int,
    ) -> QuoteSnapshot:
        price = self.fixture.prices[label]
        as_of = wake_at + timedelta(seconds=as_of_seconds)
        known_at = wake_at + timedelta(seconds=known_seconds)
        body = {
            "fixture": True,
            "demo_id": demo_id,
            "label": label,
            "symbol": self.fixture.symbol,
            "bid": price.bid,
            "ask": price.ask,
            "as_of": as_of.isoformat(),
        }
        content_hash = contract_hash(body)
        raw_id = f"raw_{contract_hash([demo_id, label, 'quote'])[:32]}"
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO research.raw
                (id, environment, version, known_at, source, source_key,
                 content_hash, body) VALUES (%s,'shadow',1,%s,'b6_price_fixture',
                 %s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (
                    raw_id,
                    known_at,
                    f"{demo_id}:{label}",
                    content_hash,
                    Jsonb(body),
                ),
            )
        return QuoteSnapshot(
            symbol=self.fixture.symbol,
            bid=Decimal(price.bid),
            ask=Decimal(price.ask),
            as_of=as_of,
            known_at=known_at,
            raw_id=raw_id,
            raw_version=1,
            content_hash=content_hash,
        )
