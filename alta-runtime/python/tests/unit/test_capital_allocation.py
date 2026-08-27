from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alta_asterism.alpha_lifecycle import build_alpha_clock
from alta_asterism.capital_allocation import IncumbentAlpha, allocate_capital
from alta_asterism.implementation import TradeImplementationPlan


NOW = datetime(2026, 8, 26, 14, tzinfo=UTC)


def plan(expected_net_alpha_bps: Decimal) -> TradeImplementationPlan:
    clock = build_alpha_clock(
        known_at=NOW,
        evidence_freshness_at=NOW,
        horizon_days=30,
        raw_expected_net_alpha_bps=expected_net_alpha_bps,
        catalyst_clarity=Decimal("0.8"),
        next_pricing_facts=("Next operating KPI update.",),
    )
    return TradeImplementationPlan(
        status="ready",
        policy_version="test-policy-v1",
        intended_alpha="Issuer-specific expectation revision.",
        retained_exposure="Residual issuer exposure.",
        reference_nav=Decimal("1000000"),
        expected_net_alpha_bps=expected_net_alpha_bps,
        alpha_clock=clock,
        loss_budget=Decimal("2500"),
        position_notional_limit=Decimal("10000"),
        gross_notional_before=Decimal("10000"),
        gross_notional_limit=Decimal("80000"),
        gross_notional_after=Decimal("11000"),
        target_notional=Decimal("1000"),
        target_quantity=Decimal("10"),
        estimated_stress_loss=Decimal("250"),
        binding_constraint="stress_loss_budget",
    )


def incumbent(
    position_id: str,
    expected_net_alpha_bps: Decimal | None,
    *,
    elapsed_days: int = 15,
) -> IncumbentAlpha:
    return IncumbentAlpha(
        position_id=position_id,
        entered_at=NOW - timedelta(days=elapsed_days),
        time_exit_at=NOW + timedelta(days=30 - elapsed_days),
        expected_net_alpha_bps_at_entry=expected_net_alpha_bps,
        replacement_hurdle_bps=Decimal("75"),
    )


def test_free_capacity_admits_without_manufacturing_a_rotation() -> None:
    decision = allocate_capital(
        plan=plan(Decimal("180")),
        incumbents=(incumbent("position_one", Decimal("200")),),
        max_open_positions=2,
        known_at=NOW,
    )

    assert decision.status == "admit"
    assert decision.reason_code == "portfolio_capacity_available"
    assert decision.incumbent_position_id is None


def test_full_book_rotates_only_when_residual_alpha_hurdle_is_cleared() -> None:
    decision = allocate_capital(
        plan=plan(Decimal("180")),
        incumbents=(incumbent("position_one", Decimal("200")),),
        max_open_positions=1,
        known_at=NOW,
    )

    assert decision.status == "rotate"
    assert decision.incumbent_remaining_alpha_bps == Decimal("100.0000")
    assert decision.advantage_bps == Decimal("80.0000")
    assert decision.reason_code == "superior_audited_opportunity"


def test_full_book_waits_when_edge_or_incumbent_underwriting_is_insufficient() -> None:
    hurdle = allocate_capital(
        plan=plan(Decimal("160")),
        incumbents=(incumbent("position_one", Decimal("200")),),
        max_open_positions=1,
        known_at=NOW,
    )
    unknown = allocate_capital(
        plan=plan(Decimal("300")),
        incumbents=(incumbent("legacy_position", None),),
        max_open_positions=1,
        known_at=NOW,
    )

    assert (hurdle.status, hurdle.reason_code) == (
        "wait",
        "portfolio_alpha_hurdle_not_cleared",
    )
    assert (unknown.status, unknown.reason_code) == (
        "wait",
        "incumbent_alpha_unavailable",
    )


def test_alpha_clock_never_uses_future_evidence_and_expires_to_zero() -> None:
    expired = build_alpha_clock(
        known_at=NOW,
        evidence_freshness_at=NOW - timedelta(days=31),
        horizon_days=30,
        raw_expected_net_alpha_bps=Decimal("250"),
        catalyst_clarity=Decimal("0.4"),
        next_pricing_facts=("Unconfirmed monitoring window.",),
    )

    assert expired.stage == "expired"
    assert expired.retention_fraction == 0
    assert expired.time_adjusted_expected_net_alpha_bps == 0
