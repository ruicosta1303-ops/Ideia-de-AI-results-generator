import pytest

from sportsmodel.odds import expected_value, fair_probabilities, implied_probabilities, margin, overround

ODDS = [2.0, 3.5, 4.0]  # implied: 0.5 + 0.285714 + 0.25 = 1.035714


def test_overround_and_margin():
    assert overround(ODDS) == pytest.approx(0.035714, abs=1e-6)
    assert margin(ODDS) == pytest.approx(1 - 1 / 1.035714, abs=1e-6)


def test_fair_probabilities_sum_to_one():
    fair = fair_probabilities(ODDS)
    assert sum(fair) == pytest.approx(1.0)
    assert fair[0] == pytest.approx(0.5 / 1.035714, abs=1e-6)
    assert all(f < i for f, i in zip(fair, implied_probabilities(ODDS)))


def test_expected_value():
    assert expected_value(0.55, 2.0) == pytest.approx(0.10)
    assert expected_value(0.5, 2.0) == pytest.approx(0.0)


@pytest.mark.parametrize("bad", [[1.0, 2.0], [0.5, 3.0], [2.0]])
def test_rejects_invalid_odds(bad):
    with pytest.raises(ValueError):
        implied_probabilities(bad)
