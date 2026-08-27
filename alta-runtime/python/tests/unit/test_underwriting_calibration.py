from decimal import Decimal

from alta_asterism.underwriting_calibration import (
    AlphaPerformanceObservation,
    CalibrationObservation,
    frozen_expected_net_alpha_bps,
    summarize_alpha_evidence,
    summarize_underwriting_calibration,
)


def test_underwriting_calibration_reports_error_without_claiming_readiness() -> None:
    summary = summarize_underwriting_calibration(
        (
            CalibrationObservation("position_a", Decimal(200), Decimal(100)),
            CalibrationObservation("position_b", Decimal(-50), Decimal(50)),
        )
    )

    assert summary == {
        "scope": "entry_frozen_cost_adjusted_direct_stock_only",
        "posture": "exploratory_only",
        "sampleSize": 2,
        "minimumSample": 30,
        "meanExpectedAlphaBps": "75.00",
        "meanRealizedAlphaBps": "75.00",
        "meanForecastErrorBps": "0.00",
        "meanAbsoluteErrorBps": "100.00",
        "directionalHitRate": "0.5",
        "warning": "Underwriting calibration is exploratory; do not tune prompts or weights from this sample.",
    }


def test_underwriting_calibration_handles_an_empty_sample() -> None:
    summary = summarize_underwriting_calibration(())

    assert summary["sampleSize"] == 0
    assert summary["meanForecastErrorBps"] is None
    assert summary["directionalHitRate"] is None


def test_alpha_evidence_reports_uncertainty_without_promoting_small_samples() -> None:
    summary = summarize_alpha_evidence(
        (
            AlphaPerformanceObservation("position_a", Decimal("120")),
            AlphaPerformanceObservation("position_b", Decimal("-20")),
            AlphaPerformanceObservation("position_c", Decimal("80")),
        )
    )

    assert summary["posture"] == "insufficient_sample"
    assert summary["sampleSize"] == 3
    assert summary["meanAlphaBps"] == "60.00"
    assert summary["medianAlphaBps"] == "80.00"
    assert summary["sampleStdDevAlphaBps"] is not None
    assert summary["confidence95LowerBps"] is not None
    assert summary["confidence95UpperBps"] is not None
    assert summary["positiveAlphaRate"] == str(Decimal(2) / Decimal(3))
    assert summary["lowerBoundAboveZero"] is False


def test_alpha_evidence_requires_a_positive_lower_bound_after_maturity() -> None:
    positive = tuple(
        AlphaPerformanceObservation(f"position_{index}", Decimal(100 + index % 3))
        for index in range(30)
    )
    inconclusive = tuple(
        AlphaPerformanceObservation(
            f"mixed_{index}", Decimal(100 if index % 2 else -100)
        )
        for index in range(30)
    )

    assert (
        summarize_alpha_evidence(positive)["posture"]
        == "positive_signal_requires_external_validation"
    )
    assert summarize_alpha_evidence(positive)["lowerBoundAboveZero"] is True
    assert summarize_alpha_evidence(inconclusive)["posture"] == "inconclusive"


def test_calibration_reads_the_entry_frozen_cost_adjusted_forecast() -> None:
    thesis = {
        "implementation_plan": {
            "expected_net_alpha_bps": "140",
            "alpha_clock": {"time_adjusted_expected_net_alpha_bps": "87.50"},
        }
    }

    assert frozen_expected_net_alpha_bps(thesis) == Decimal("87.50")
    assert frozen_expected_net_alpha_bps({"implementation_plan": {}}) is None
    assert frozen_expected_net_alpha_bps({"implementation_plan": "invalid"}) is None
