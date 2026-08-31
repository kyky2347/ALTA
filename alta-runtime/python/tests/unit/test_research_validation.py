from decimal import Decimal

import pytest

from alta_asterism.research_validation import selection_adjusted_alpha_evidence


def test_single_trial_matches_the_conventional_lower_bound() -> None:
    result = selection_adjusted_alpha_evidence(
        sample_size=30,
        mean_alpha_bps=Decimal("25"),
        standard_error_bps=Decimal("10"),
        research_trials=30,
    )

    assert result.research_trials == 30
    assert result.critical_z is not None
    assert result.critical_z > Decimal("3")
    assert result.adjusted_lower_alpha_bps < 0


def test_selection_evidence_requires_trials_to_cover_observations() -> None:
    with pytest.raises(ValueError, match="research trials"):
        selection_adjusted_alpha_evidence(
            sample_size=10,
            mean_alpha_bps=Decimal("25"),
            standard_error_bps=Decimal("10"),
            research_trials=9,
        )
