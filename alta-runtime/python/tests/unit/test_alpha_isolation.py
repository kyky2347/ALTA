from decimal import Decimal

from alta_asterism.alpha_isolation import (
    audited_alpha_isolation,
    normalize_systematic_exposure,
    provisional_alpha_isolation,
)


def test_audited_isolation_uses_the_most_conservative_independent_score() -> None:
    result = audited_alpha_isolation(
        alpha_source="earnings_revision",
        proposed_exposures=("market_beta", "sector"),
        confirmed_exposures=("market_beta", "sector"),
        proposed_hedge_posture="size_down",
        audited_hedge_posture="size_down",
        thesis_purity=0.9,
        timing_fit=0.85,
        thesis_alignment=0.8,
        implementation_quality=0.75,
        auditor_score=0.7,
        basis_risk="Sector beta can dominate before the operating revision prices.",
        exposure_disagreements=(),
    )

    assert result.conservative_score == Decimal("0.7")
    assert result.sizing_multiplier == Decimal("0.5")
    assert result.reason_codes == ()


def test_exposure_disagreement_is_preserved_as_a_fail_closed_reason() -> None:
    result = audited_alpha_isolation(
        alpha_source="event",
        proposed_exposures=("event_gap",),
        confirmed_exposures=("event_gap", "market_beta"),
        proposed_hedge_posture="unhedged_intentional",
        audited_hedge_posture="size_down",
        thesis_purity=0.9,
        timing_fit=0.9,
        thesis_alignment=0.9,
        implementation_quality=0.9,
        auditor_score=0.9,
        basis_risk="The market move may swamp the event payoff.",
        exposure_disagreements=("Auditor identified broad beta contamination.",),
    )

    assert result.hedge_posture == "size_down"
    assert result.reason_codes == ("systematic_exposure_audit_disagreement",)
    assert "proposer_and_auditor_exposure_sets_differ" in (
        result.exposure_disagreements
    )


def test_unclassified_provisional_idea_can_reach_audit_but_cannot_claim_purity() -> (
    None
):
    result = provisional_alpha_isolation(
        alpha_source="legacy_unclassified",
        systematic_exposures=("unknown",),
        hedge_posture="not_applicable",
        thesis_purity=0.9,
        timing_fit=0.9,
        basis_risk="Unknown until independently audited.",
    )

    assert result.posture == "provisional"
    assert result.reason_codes == ("systematic_exposure_unclassified",)


def test_legacy_or_malformed_exposure_never_becomes_a_new_risk_tag() -> None:
    assert normalize_systematic_exposure("market_beta") == "market_beta"
    assert normalize_systematic_exposure("broad beta") == "unknown"
    assert normalize_systematic_exposure({"unexpected": "shape"}) == "unknown"
