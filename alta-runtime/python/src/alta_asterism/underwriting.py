from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UNDERWRITING_POLICY_VERSION = "alta-underwriting-uncertainty-v1"
FORECAST_DISPERSION_RESERVE_FRACTION = Decimal("0.25")


class ScenarioCase(BaseModel):
    """One direction-normalized, benchmark-relative outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    probability: float = Field(gt=0, lt=1)
    relative_alpha_bps: int = Field(ge=-10_000, le=10_000)
    trigger: str = Field(min_length=1, max_length=600)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)


class DecisionIntelligence(BaseModel):
    """PM judgment that separates a company view from a tradable security view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    what_is_priced_in: str = Field(min_length=1, max_length=500)
    variant_view: str = Field(min_length=1, max_length=500)
    reference_class: str = Field(min_length=1, max_length=240)
    base_rate_probability: float = Field(ge=0, le=1)
    inside_view_probability: float = Field(ge=0, le=1)
    must_be_true: tuple[str, ...] = Field(min_length=1, max_length=4)
    company_thesis_status: Literal[
        "strengthening",
        "intact",
        "watch",
        "impaired",
        "broken",
        "untested",
    ]
    security_thesis_readiness: Literal[
        "ready", "conditional", "re_underwrite", "not_decision_grade"
    ]
    edge_half_life_days: int = Field(ge=1, le=365)
    dominant_uncertainty: str = Field(min_length=1, max_length=300)
    action_trigger: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_decision(self) -> "DecisionIntelligence":
        if self.what_is_priced_in.casefold() == self.variant_view.casefold():
            raise ValueError("variant view must differ from what is priced in")
        if len(set(self.must_be_true)) != len(self.must_be_true):
            raise ValueError("must-be-true conditions must be unique")
        if (
            self.company_thesis_status == "broken"
            and self.security_thesis_readiness == "ready"
        ):
            raise ValueError("a broken company thesis cannot be security-ready")
        return self


class ScenarioUnderwriting(BaseModel):
    """A falsifiable payoff distribution used for research prioritization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_symbol: Literal["SPY"] = "SPY"
    bull: ScenarioCase
    base: ScenarioCase
    bear: ScenarioCase
    catalyst_clarity: float = Field(ge=0, le=1)
    crowding_risk: float = Field(ge=0, le=1)
    liquidity_risk: float = Field(ge=0, le=1)
    next_pricing_fact: str = Field(min_length=1, max_length=600)
    decision: DecisionIntelligence | None = None

    @model_validator(mode="after")
    def validate_distribution(self) -> "ScenarioUnderwriting":
        probability = sum(
            (Decimal(str(case.probability)) for case in self.ordered_cases),
            Decimal(0),
        )
        if abs(probability - Decimal(1)) > Decimal("0.000001"):
            raise ValueError("scenario probabilities must sum to one")
        if not (
            self.bull.relative_alpha_bps
            > self.base.relative_alpha_bps
            > self.bear.relative_alpha_bps
        ):
            raise ValueError(
                "scenario alpha must be strictly ordered bull > base > bear"
            )
        if self.bull.relative_alpha_bps <= 0:
            raise ValueError("bull scenario must have positive relative alpha")
        if self.bear.relative_alpha_bps >= 0:
            raise ValueError("bear scenario must have negative relative alpha")
        if self.decision is not None and (
            abs(
                Decimal(str(self.decision.inside_view_probability))
                - self.positive_alpha_probability
            )
            > Decimal("0.25")
        ):
            raise ValueError(
                "inside-view probability conflicts with the scenario distribution"
            )
        return self

    @property
    def ordered_cases(self) -> tuple[ScenarioCase, ScenarioCase, ScenarioCase]:
        return (self.bull, self.base, self.bear)

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                evidence_id
                for case in self.ordered_cases
                for evidence_id in case.evidence_ids
            )
        )

    @property
    def positive_alpha_probability(self) -> Decimal:
        return sum(
            (
                Decimal(str(case.probability))
                for case in self.ordered_cases
                if case.relative_alpha_bps > 0
            ),
            Decimal(0),
        )

    @property
    def expected_alpha_bps(self) -> Decimal:
        return sum(
            (
                Decimal(str(case.probability)) * Decimal(case.relative_alpha_bps)
                for case in self.ordered_cases
            ),
            Decimal(0),
        )

    @property
    def expected_upside_bps(self) -> Decimal:
        return sum(
            (
                Decimal(str(case.probability)) * Decimal(case.relative_alpha_bps)
                for case in self.ordered_cases
                if case.relative_alpha_bps > 0
            ),
            Decimal(0),
        )

    @property
    def expected_downside_bps(self) -> Decimal:
        return sum(
            (
                Decimal(str(case.probability)) * abs(Decimal(case.relative_alpha_bps))
                for case in self.ordered_cases
                if case.relative_alpha_bps < 0
            ),
            Decimal(0),
        )


def _unit_interval(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(1), value))


class DecisionConsensus(BaseModel):
    """Deterministic synthesis of two locked decisions without erasing disagreement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "conditional", "wait"]
    company_thesis_statuses: tuple[str, str]
    security_thesis_readinesses: tuple[str, str]
    edge_half_life_days: int = Field(ge=1, le=365)
    base_rate_probability_range: tuple[float, float]
    inside_view_probability_range: tuple[float, float]
    reference_classes: tuple[str, ...] = Field(default=(), max_length=2)
    must_be_true: tuple[str, ...] = Field(default=(), max_length=8)
    dominant_uncertainties: tuple[str, ...] = Field(default=(), max_length=2)
    action_triggers: tuple[str, ...] = Field(default=(), max_length=2)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=4)


def consensus_decision(
    underwritings: tuple[ScenarioUnderwriting, ScenarioUnderwriting],
) -> DecisionConsensus:
    """Require independent security readiness while preserving both PM views."""

    if any(item.decision is None for item in underwritings):
        return DecisionConsensus(
            status="wait",
            company_thesis_statuses=("unknown", "unknown"),
            security_thesis_readinesses=("unknown", "unknown"),
            edge_half_life_days=1,
            base_rate_probability_range=(0, 0),
            inside_view_probability_range=(0, 0),
            reason_codes=("decision_intelligence_missing",),
        )
    decisions = (underwritings[0].decision, underwritings[1].decision)
    assert decisions[0] is not None and decisions[1] is not None
    company_statuses = tuple(item.company_thesis_status for item in decisions)
    readinesses = tuple(item.security_thesis_readiness for item in decisions)
    reasons: list[str] = []
    if "broken" in company_statuses:
        reasons.append("company_thesis_broken")
    if "not_decision_grade" in readinesses:
        reasons.append("security_not_decision_grade")
    if "re_underwrite" in readinesses:
        reasons.append("security_reunderwrite_required")
    if "ready" not in readinesses:
        reasons.append("independent_security_readiness_unavailable")
    status: Literal["ready", "conditional", "wait"]
    if reasons:
        status = "wait"
    elif readinesses == ("ready", "ready"):
        status = "ready"
    else:
        status = "conditional"
    base_rates = sorted(item.base_rate_probability for item in decisions)
    inside_views = sorted(item.inside_view_probability for item in decisions)
    return DecisionConsensus(
        status=status,
        company_thesis_statuses=company_statuses,  # type: ignore[arg-type]
        security_thesis_readinesses=readinesses,  # type: ignore[arg-type]
        edge_half_life_days=min(item.edge_half_life_days for item in decisions),
        base_rate_probability_range=(base_rates[0], base_rates[1]),
        inside_view_probability_range=(inside_views[0], inside_views[1]),
        reference_classes=tuple(
            dict.fromkeys(item.reference_class for item in decisions)
        ),
        must_be_true=tuple(
            dict.fromkeys(
                condition for item in decisions for condition in item.must_be_true
            )
        )[:8],
        dominant_uncertainties=tuple(
            dict.fromkeys(item.dominant_uncertainty for item in decisions)
        ),
        action_triggers=tuple(dict.fromkeys(item.action_trigger for item in decisions)),
        reason_codes=tuple(reasons),
    )


def consensus_underwriting(
    underwritings: tuple[ScenarioUnderwriting, ScenarioUnderwriting],
) -> dict[str, Decimal]:
    """Materialize deterministic, bounded ranking inputs from two locked views."""

    expected = tuple(item.expected_alpha_bps for item in underwritings)
    expected_alpha = sum(expected, Decimal(0)) / Decimal(2)
    conservative_expected_alpha = min(expected)
    forecast_dispersion = abs(expected[0] - expected[1])
    forecast_uncertainty_reserve = (
        forecast_dispersion * FORECAST_DISPERSION_RESERVE_FRACTION
    )
    uncertainty_adjusted_expected_alpha = (
        conservative_expected_alpha - forecast_uncertainty_reserve
    )
    expected_upside = sum(
        (item.expected_upside_bps for item in underwritings), Decimal(0)
    ) / Decimal(2)
    expected_downside = sum(
        (item.expected_downside_bps for item in underwritings), Decimal(0)
    ) / Decimal(2)
    payoff_ratio = (
        expected_upside / expected_downside if expected_downside > 0 else Decimal(10)
    )
    catalyst_clarity = sum(
        (Decimal(str(item.catalyst_clarity)) for item in underwritings), Decimal(0)
    ) / Decimal(2)
    crowding_risk = sum(
        (Decimal(str(item.crowding_risk)) for item in underwritings), Decimal(0)
    ) / Decimal(2)
    liquidity_risk = sum(
        (Decimal(str(item.liquidity_risk)) for item in underwritings), Decimal(0)
    ) / Decimal(2)
    return {
        "consensus_expected_alpha_bps": expected_alpha,
        "conservative_expected_alpha_bps": conservative_expected_alpha,
        "forecast_dispersion_bps": forecast_dispersion,
        "forecast_uncertainty_reserve_bps": forecast_uncertainty_reserve,
        "uncertainty_adjusted_expected_alpha_bps": (
            uncertainty_adjusted_expected_alpha
        ),
        "expected_alpha_score": _unit_interval(
            Decimal("0.5") + uncertainty_adjusted_expected_alpha / Decimal(2_000)
        ),
        "downside_resilience": _unit_interval(
            Decimal(1) - expected_downside / Decimal(1_500)
        ),
        "payoff_asymmetry": _unit_interval(payoff_ratio / (payoff_ratio + Decimal(1))),
        "catalyst_clarity": catalyst_clarity,
        "crowding_risk": crowding_risk,
        "liquidity_risk": liquidity_risk,
        "scenario_disagreement": _unit_interval(forecast_dispersion / Decimal(2_000)),
    }
