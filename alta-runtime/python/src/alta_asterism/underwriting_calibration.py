from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .research_validation import selection_adjusted_alpha_evidence


@dataclass(frozen=True)
class CalibrationObservation:
    position_id: str
    expected_alpha_bps: Decimal
    realized_alpha_bps: Decimal


@dataclass(frozen=True)
class AlphaPerformanceObservation:
    position_id: str
    realized_alpha_bps: Decimal


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _serialized(value: Decimal | None) -> str | None:
    return str(value.quantize(Decimal("0.01"))) if value is not None else None


def _sample_standard_deviation(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    assert mean is not None
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(
        len(values) - 1
    )
    return variance.sqrt()


def _median(values: tuple[Decimal, ...]) -> Decimal | None:
    ordered = sorted(values)
    sample_size = len(ordered)
    if not ordered:
        return None
    if sample_size % 2:
        return ordered[sample_size // 2]
    middle = sample_size // 2
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _confidence_interval(
    values: tuple[Decimal, ...],
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    standard_deviation = _sample_standard_deviation(values)
    if standard_deviation is None:
        return standard_deviation, None, None, None
    standard_error = standard_deviation / Decimal(len(values)).sqrt()
    radius = standard_error * Decimal("1.96")
    mean = _mean(values)
    assert mean is not None
    return standard_deviation, standard_error, mean - radius, mean + radius


def _alpha_posture(
    *,
    sample_size: int,
    minimum_sample: int,
    lower: Decimal | None,
    upper: Decimal | None,
    selection_adjusted_lower: Decimal | None,
) -> str:
    if sample_size < minimum_sample:
        return "insufficient_sample"
    if selection_adjusted_lower is not None and selection_adjusted_lower > 0:
        return "positive_signal_requires_external_validation"
    if lower is not None and lower > 0:
        return "positive_unadjusted_selection_risk"
    if upper is not None and upper < 0:
        return "negative_signal"
    return "inconclusive"


def frozen_expected_net_alpha_bps(position_thesis: object) -> Decimal | None:
    """Read the entry-frozen, cost-adjusted forecast used by capital admission."""

    if not isinstance(position_thesis, dict):
        return None
    implementation = position_thesis.get("implementation_plan")
    if not isinstance(implementation, dict):
        return None
    alpha_clock = implementation.get("alpha_clock")
    value = (
        alpha_clock.get("time_adjusted_expected_net_alpha_bps")
        if isinstance(alpha_clock, dict)
        else implementation.get("expected_net_alpha_bps")
    )
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def summarize_alpha_evidence(
    observations: tuple[AlphaPerformanceObservation, ...],
    *,
    minimum_sample: int = 30,
    research_trials: int | None = None,
) -> dict[str, object]:
    """Describe forward Shadow Alpha without promoting a small sample to proof."""

    if minimum_sample < 1:
        raise ValueError("minimum_sample must be positive")
    realized = tuple(item.realized_alpha_bps for item in observations)
    sample_size = len(realized)
    research_trials = sample_size if research_trials is None else research_trials
    if research_trials < sample_size:
        raise ValueError("research trials cannot be smaller than the Alpha sample")
    mean = _mean(realized)
    standard_deviation, standard_error, lower, upper = _confidence_interval(realized)
    selection = selection_adjusted_alpha_evidence(
        sample_size=sample_size,
        mean_alpha_bps=mean,
        standard_error_bps=standard_error,
        research_trials=research_trials,
    )
    posture = _alpha_posture(
        sample_size=sample_size,
        minimum_sample=minimum_sample,
        lower=lower,
        upper=upper,
        selection_adjusted_lower=selection.adjusted_lower_alpha_bps,
    )
    if sample_size < minimum_sample:
        warning = "Alpha is unproven: the forward Shadow sample is below the minimum."
    elif posture == "positive_unadjusted_selection_risk":
        warning = (
            "The unadjusted Alpha interval is positive, but it does not survive "
            "the opportunity-search selection correction."
        )
    else:
        warning = (
            "The selection-adjusted confidence bound remains forward Shadow evidence; "
            "regime dependence and non-normal returns still require external validation."
        )
    return {
        "scope": "cost_adjusted_spy_relative_closed_shadow",
        "posture": posture,
        "sampleSize": sample_size,
        "minimumSample": minimum_sample,
        "meanAlphaBps": _serialized(mean),
        "medianAlphaBps": _serialized(_median(realized)),
        "sampleStdDevAlphaBps": _serialized(standard_deviation),
        "standardErrorBps": _serialized(standard_error),
        "confidence95LowerBps": _serialized(lower),
        "confidence95UpperBps": _serialized(upper),
        "researchTrials": selection.research_trials,
        "selectionPolicyVersion": selection.version,
        "selectionCriticalZ": _serialized(selection.critical_z),
        "selectionAdjustedConfidence95LowerBps": _serialized(
            selection.adjusted_lower_alpha_bps
        ),
        "positiveAlphaRate": (
            str(Decimal(sum(value > 0 for value in realized)) / Decimal(sample_size))
            if sample_size
            else None
        ),
        "worstAlphaBps": _serialized(min(realized) if realized else None),
        "bestAlphaBps": _serialized(max(realized) if realized else None),
        "lowerBoundAboveZero": bool(lower is not None and lower > 0),
        "selectionAdjustedLowerBoundAboveZero": bool(
            selection.adjusted_lower_alpha_bps is not None
            and selection.adjusted_lower_alpha_bps > 0
        ),
        "warning": warning,
    }


def summarize_underwriting_calibration(
    observations: tuple[CalibrationObservation, ...],
    *,
    minimum_sample: int = 30,
) -> dict[str, object]:
    """Compare frozen ex-ante underwriting with forward realized Shadow Alpha."""

    if minimum_sample < 1:
        raise ValueError("minimum_sample must be positive")
    expected = tuple(item.expected_alpha_bps for item in observations)
    realized = tuple(item.realized_alpha_bps for item in observations)
    errors = tuple(
        item.realized_alpha_bps - item.expected_alpha_bps for item in observations
    )
    absolute_errors = tuple(abs(value) for value in errors)
    directional_hits = sum(
        (item.expected_alpha_bps > 0) == (item.realized_alpha_bps > 0)
        for item in observations
        if item.expected_alpha_bps != 0 and item.realized_alpha_bps != 0
    )
    directional_sample = sum(
        item.expected_alpha_bps != 0 and item.realized_alpha_bps != 0
        for item in observations
    )
    sample_size = len(observations)
    return {
        "scope": "entry_frozen_cost_adjusted_direct_stock_only",
        "posture": (
            "minimum_sample_reached"
            if sample_size >= minimum_sample
            else "exploratory_only"
        ),
        "sampleSize": sample_size,
        "minimumSample": minimum_sample,
        "meanExpectedAlphaBps": _serialized(_mean(expected)),
        "meanRealizedAlphaBps": _serialized(_mean(realized)),
        "meanForecastErrorBps": _serialized(_mean(errors)),
        "meanAbsoluteErrorBps": _serialized(_mean(absolute_errors)),
        "directionalHitRate": (
            str(Decimal(directional_hits) / Decimal(directional_sample))
            if directional_sample
            else None
        ),
        "warning": (
            None
            if sample_size >= minimum_sample
            else "Underwriting calibration is exploratory; do not tune prompts or weights from this sample."
        ),
    }
