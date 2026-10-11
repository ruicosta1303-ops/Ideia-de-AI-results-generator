import pytest

from sportsmodel.elo import Elo, ordered_logit_probs


def test_update_is_zero_sum_and_directional():
    elo = Elo()
    delta = elo.update("A", "B", 2, 0)
    assert delta > 0
    assert elo.rating("A") + elo.rating("B") == pytest.approx(3000)


def test_bigger_margin_moves_ratings_more():
    assert Elo().update("A", "B", 4, 0) > Elo().update("A", "B", 1, 0)


def test_home_advantage_in_expectation():
    assert Elo().expected_score("A", "B") > 0.5


def test_ordered_logit_sums_to_one_and_is_monotonic():
    probs = [ordered_logit_probs(d, -0.6, 0.6, 200) for d in (-300, 0, 300)]
    for p in probs:
        assert sum(p) == pytest.approx(1.0)
        assert all(x > 0 for x in p)
    assert probs[0][0] < probs[1][0] < probs[2][0]
