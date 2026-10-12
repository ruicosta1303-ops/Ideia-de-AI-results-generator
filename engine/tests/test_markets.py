import math

import numpy as np
import pytest

from sportsmodel.markets import match_markets, rho_bounds, score_matrix


@pytest.mark.parametrize("lam,mu,rho", [(1.0, 1.0, 0.0), (2.4, 0.6, -0.1), (0.3, 3.1, 0.05), (1.45, 1.2, -0.13)])
def test_every_market_sums_to_one(lam, mu, rho):
    mk = match_markets(lam, mu, rho)
    assert mk.home_win + mk.draw + mk.away_win == pytest.approx(1.0, abs=1e-12)
    for line in (1.5, 2.5, 3.5):
        assert mk.over[line] + mk.under[line] == pytest.approx(1.0, abs=1e-12)
    assert mk.btts_yes + mk.btts_no == pytest.approx(1.0, abs=1e-12)


def test_independent_poisson_closed_form():
    m = score_matrix(1.0, 1.0, max_goals=20)
    assert m[0, 0] == pytest.approx(math.exp(-2), rel=1e-9)
    mk = match_markets(1.0, 1.0, max_goals=20)
    # total goals ~ Poisson(2): P(total <= 1) = 3 e^-2
    assert mk.under[1.5] == pytest.approx(3 * math.exp(-2), rel=1e-9)
    assert mk.btts_yes == pytest.approx((1 - math.exp(-1)) ** 2, rel=1e-9)
    assert mk.home_win == pytest.approx(mk.away_win)
    assert mk.expected_home_goals == pytest.approx(1.0, rel=1e-6)


def test_stronger_home_team_is_favoured():
    mk = match_markets(2.2, 0.7)
    assert mk.home_win > mk.away_win
    assert mk.expected_home_goals > mk.expected_away_goals


def test_negative_rho_raises_draw_probability():
    assert match_markets(1.2, 1.1, -0.1).draw > match_markets(1.2, 1.1, 0.0).draw


@pytest.mark.parametrize("lam,mu", [(0, 1), (-1, 1), (1, 0)])
def test_rejects_non_positive_goals(lam, mu):
    with pytest.raises(ValueError):
        score_matrix(lam, mu)


def test_rejects_rho_outside_valid_range():
    lo, hi = rho_bounds(2.0, 2.0)
    with pytest.raises(ValueError):
        score_matrix(2.0, 2.0, rho=hi + 0.01)
    assert np.all(score_matrix(2.0, 2.0, rho=hi) >= 0)
