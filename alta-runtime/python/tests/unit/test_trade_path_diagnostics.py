from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alta_asterism.trade_path_diagnostics import (
    ExecutablePathObservation,
    PositionPathDiagnostics,
    build_position_path_diagnostics,
    summarize_path_diagnostics,
)


OPENED = datetime(2026, 8, 24, 14, tzinfo=UTC)


def observation(day: int, price: str) -> ExecutablePathObservation:
    return ExecutablePathObservation(
        known_at=OPENED + timedelta(days=day),
        executable_price=Decimal(price),
    )


def test_path_diagnostics_measure_only_observed_executable_prices() -> None:
    result = build_position_path_diagnostics(
        entry_price=Decimal("100"),
        opened_at=OPENED,
        observations=(
            observation(1, "105"),
            observation(2, "95"),
            observation(3, "110"),
        ),
        exit_price=Decimal("108"),
        closed_at=OPENED + timedelta(days=4),
        net_return_bps=Decimal("750"),
    )

    assert result.price_observations == 4
    assert result.maximum_favorable_excursion_bps == Decimal("1000.00")
    assert result.maximum_adverse_excursion_bps == Decimal("-500.00")
    assert result.maximum_drawdown_bps == Decimal("1000.00")
    assert result.exit_capture_ratio == Decimal("0.7500")
    assert result.time_to_best_seconds == 3 * 86_400
    assert result.holding_seconds == 4 * 86_400


def test_path_diagnostics_ignore_prices_outside_the_holding_interval() -> None:
    result = build_position_path_diagnostics(
        entry_price=Decimal("100"),
        opened_at=OPENED,
        observations=(
            ExecutablePathObservation(
                known_at=OPENED - timedelta(seconds=1),
                executable_price=Decimal("200"),
            ),
            observation(1, "102"),
            observation(3, "300"),
        ),
        exit_price=Decimal("101"),
        closed_at=OPENED + timedelta(days=2),
        net_return_bps=Decimal("90"),
    )

    assert result.price_observations == 2
    assert result.maximum_favorable_excursion_bps == Decimal("200.00")
    assert result.maximum_adverse_excursion_bps == 0


def test_path_diagnostics_reject_invalid_time_or_price() -> None:
    with pytest.raises(ValueError, match="prices must be positive"):
        build_position_path_diagnostics(
            entry_price=Decimal(0),
            opened_at=OPENED,
            observations=(),
            exit_price=Decimal("100"),
            closed_at=OPENED,
            net_return_bps=Decimal(0),
        )
    with pytest.raises(ValueError, match="close cannot precede open"):
        build_position_path_diagnostics(
            entry_price=Decimal("100"),
            opened_at=OPENED,
            observations=(),
            exit_price=Decimal("100"),
            closed_at=OPENED - timedelta(seconds=1),
            net_return_bps=Decimal(0),
        )


def test_path_summary_stays_descriptive_and_reports_exit_leakage() -> None:
    captured = build_position_path_diagnostics(
        entry_price=Decimal("100"),
        opened_at=OPENED,
        observations=(observation(1, "110"),),
        exit_price=Decimal("108"),
        closed_at=OPENED + timedelta(days=2),
        net_return_bps=Decimal("750"),
    )
    missed = captured.model_copy(
        update={
            "net_return_bps": Decimal("-50"),
            "exit_capture_ratio": Decimal("-0.0500"),
        }
    )

    summary = summarize_path_diagnostics((captured, missed))

    assert summary["posture"] == "collecting"
    assert summary["measuredPositions"] == 2
    assert summary["meanMaximumFavorableExcursionBps"] == "1000.00"
    assert summary["meanExitCaptureRatio"] == "0.3500"
    assert summary["positiveExcursionMissRate"] == "0.5000"
    assert "not intraday backtest" in str(summary["warning"])


def test_path_summary_handles_legacy_rows_without_diagnostics() -> None:
    assert summarize_path_diagnostics(()) == {
        "posture": "unmeasured",
        "measuredPositions": 0,
        "minimumSample": 30,
        "meanMaximumFavorableExcursionBps": None,
        "meanMaximumAdverseExcursionBps": None,
        "meanMaximumDrawdownBps": None,
        "meanExitCaptureRatio": None,
        "positiveExcursionMissRate": None,
        "warning": (
            "Path diagnostics are unavailable until a position has an observed exit."
        ),
    }


def test_path_contract_rejects_a_best_time_outside_the_holding_period() -> None:
    with pytest.raises(ValueError, match="best observation"):
        PositionPathDiagnostics(
            price_observations=1,
            opened_at=OPENED,
            closed_at=OPENED + timedelta(seconds=10),
            maximum_favorable_excursion_bps=Decimal(0),
            maximum_adverse_excursion_bps=Decimal(0),
            maximum_drawdown_bps=Decimal(0),
            net_return_bps=Decimal(0),
            time_to_best_seconds=11,
            holding_seconds=10,
        )
