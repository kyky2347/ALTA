"""Translate durable, independently audited research into a broker plan.

No broker credential or mutation belongs to a research Agent. The trusted
application verifies the exact event and role artifact before using its private
execution pipe. This is intentionally separate from Shadow/Paper fill models.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_UP

from .agentic_roles import canonical_hash
from .broker_process import BrokerExecutionError


def require(value, code):
    if not value:
        raise BrokerExecutionError(code)


def prepare_handoff(database, route, cycle_id, proposal):
    require(
        proposal.kind in ("stock", "etf") and proposal.side == "long",
        "broker_instrument_not_supported",
    )
    implementation = proposal.implementation_plan
    require(
        implementation is not None and implementation.status == "ready",
        "broker_implementation_not_ready",
    )
    execution = implementation.execution_plan
    clock = implementation.alpha_clock
    require(
        execution is not None and execution.status == "ready" and clock is not None,
        "broker_execution_plan_incomplete",
    )
    require(
        implementation.gross_replacement_credit == 0, "broker_rotation_not_supported"
    )
    require(
        proposal.quantity == proposal.quantity.to_integral_value(),
        "broker_whole_shares_required",
    )
    with database.connect() as connection:
        event = connection.execute(
            """SELECT payload FROM ops.event WHERE aggregate_id=%s
            AND event_type='expression.validated' ORDER BY sequence DESC LIMIT 1""",
            (proposal.expression_id,),
        ).fetchone()
        require(
            event is not None
            and canonical_hash(event[0]["expression"]) == proposal.hash(),
            "broker_expression_not_durable",
        )
        rows = connection.execute(
            """SELECT r.id, r.frozen_input, a.content, a.content_hash, a.known_at
            FROM research.run r JOIN research.run_artifact a ON a.run_id=r.id
            AND a.artifact_kind='role_output'
            WHERE r.cycle_id=%s AND r.role='expression_auditor' AND r.status='succeeded'
            ORDER BY a.known_at DESC LIMIT 32""",
            (cycle_id,),
        ).fetchall()
    rationale = json.loads(proposal.rationale)
    selected = rationale.get("selected_hypothesis_id")
    matches = []
    for run_id, frozen, content, artifact_hash, audited_at in rows:
        audit = content.get("output", {})
        opportunity = frozen.get("opportunity", {})
        candidates = [
            candidate
            for candidate in frozen.get("proposed_expression", {}).get(
                "expression_slate", []
            )
            if candidate.get("hypothesis", {}).get("hypothesis_id") == selected
        ]
        instrument = (
            candidates[0].get("instrument") or {} if len(candidates) == 1 else {}
        )
        # The audit must belong to this opportunity and select this exact slate
        # candidate. A different successful audit in the same cycle is not proof.
        if (
            opportunity.get("opportunity_id") == proposal.binding.opportunity_id
            and audit.get("decision") == "approve"
            and audit.get("selected_hypothesis_id") == selected
            and canonical_hash(content) == artifact_hash
            and frozen.get("broker_execution")
            == {
                key: route[key]
                for key in (
                    "provider",
                    "environment",
                    "binding",
                    "revision",
                    "profile_revision",
                )
            }
            and frozen.get("broker_opportunity_binding")
            == {
                "version": proposal.binding.opportunity_version,
                "snapshot_hash": proposal.binding.opportunity_snapshot_hash,
            }
            and instrument.get("symbol") == proposal.symbol
            and instrument.get("kind") == proposal.kind
            and Decimal(str(instrument.get("quantity", "0"))) >= proposal.quantity
        ):
            matches.append((run_id, artifact_hash, audited_at))
    require(len(matches) == 1 and bool(selected), "broker_independent_audit_not_proven")
    audit_id, artifact_hash, audited_at = matches[0]
    now = datetime.now(UTC)
    require(
        0 <= (now - proposal.decision_known_at).total_seconds() <= 300,
        "broker_expression_expired",
    )
    require(
        audited_at <= proposal.decision_known_at
        and 0 <= (now - audited_at).total_seconds() <= 300,
        "broker_independent_audit_expired",
    )
    quantity = proposal.quantity
    limit = execution.entry_limit_price
    require(
        limit is not None and limit > 0 and quantity > 0, "broker_entry_terms_invalid"
    )
    # The portfolio-wide allowance can exceed a small position's entire value.
    # Use this position's audited stress allocation, capped by that allowance;
    # treating unused account risk capacity as a stop distance is incorrect.
    loss_allocation = min(
        implementation.loss_budget, implementation.estimated_stress_loss
    )
    require(loss_allocation > 0, "broker_exit_terms_invalid")
    stop = limit - loss_allocation / quantity
    edge = implementation.expected_net_alpha_bps
    require(stop > 0 and edge is not None and edge > 0, "broker_exit_terms_invalid")
    expiry = audited_at + timedelta(minutes=5)
    exit_at = min(
        clock.known_at + timedelta(seconds=clock.remaining_seconds),
        audited_at + timedelta(days=90),
    )
    require(exit_at > expiry, "broker_alpha_horizon_expired")
    identity = canonical_hash([route["binding"], route["revision"], proposal.hash()])[
        :32
    ]

    def stamp(value):
        return value.isoformat().replace("+00:00", "Z")

    plan = {
        "plan_id": "plan-" + identity,
        "binding": route["binding"],
        "revision": route["profile_revision"],
        "audit_id": audit_id,
        "audited_at": stamp(audited_at),
        "entry": {
            "client_id": "alta-" + identity,
            "symbol": proposal.symbol,
            "side": "BUY",
            "quantity": str(quantity),
            "limit_price": str(limit),
            "reference_id": proposal.expression_id,
            "expires_at": stamp(expiry),
        },
        "exit_at": stamp(exit_at),
        "stop_price": str(stop),
        "target_price": str(
            (limit * (1 + edge / Decimal(10000))).quantize(
                Decimal("0.01"), rounding=ROUND_UP
            )
        ),
    }
    return plan, {
        "audit_id": audit_id,
        "expression_hash": proposal.hash(),
        "artifact_hash": artifact_hash,
        "plan_hash": canonical_hash(plan),
    }
