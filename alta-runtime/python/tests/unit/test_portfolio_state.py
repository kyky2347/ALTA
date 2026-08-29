from decimal import Decimal

from alta_asterism.portfolio_state import project_portfolio_state


def test_portfolio_state_scales_durable_entry_risk_to_current_notional() -> None:
    state = project_portfolio_state(
        (
            (
                Decimal("1200"),
                {
                    "implementation_plan": {
                        "alpha_source": "event",
                        "systematic_exposures": ["event_gap", "market_beta"],
                        "target_notional": "1000",
                        "estimated_stress_loss": "250",
                    }
                },
                "shared-policy-reset",
            ),
            (Decimal("800"), {"implementation_plan": None}, None),
        ),
        max_open_positions=2,
    )

    assert state.gross_notional == Decimal("2000")
    assert state.aggregate_stress_loss == Decimal("1100")
    assert state.prospective_replacement_credit == Decimal("800")
    assert state.prospective_replacement_stress_credit == Decimal("300")
    assert state.alpha_source_buckets[0].source == "event"
    assert state.alpha_source_buckets[0].estimated_stress_loss == Decimal("300")
    assert state.alpha_source_buckets[1].source == "legacy_unclassified"
    assert state.alpha_source_buckets[1].estimated_stress_loss == Decimal("800")
    assert state.catalyst_buckets[0].catalyst_key == "legacy-unclassified"
    assert state.catalyst_buckets[1].catalyst_key == "shared-policy-reset"
    assert state.catalyst_buckets[1].estimated_stress_loss == Decimal("300")
    assert {item.tag for item in state.exposure_buckets} == {
        "event_gap",
        "market_beta",
        "unknown",
    }


def test_malformed_legacy_risk_is_charged_full_notional_instead_of_zero() -> None:
    state = project_portfolio_state(
        (
            (
                Decimal("750"),
                {
                    "implementation_plan": {
                        "target_notional": "not-a-number",
                        "estimated_stress_loss": None,
                    }
                },
                None,
            ),
        ),
        max_open_positions=8,
    )

    assert state.aggregate_stress_loss == Decimal("750")
    assert state.alpha_source_buckets[0].estimated_stress_loss == Decimal("750")
