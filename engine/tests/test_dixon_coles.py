"""Parameter-recovery tests on SYNTHETIC simulated seasons (test-only data)."""
from datetime import date, timedelta

import numpy as np
import pytest

from sportsmodel.dixon_coles import Match, fit


def simulate(n_teams=20, seasons=3, home_adv=0.27, seed=1):
    rng = np.random.default_rng(seed)
    teams = [f"Team{i:02d}" for i in range(n_teams)]
    attack = rng.normal(0, 0.3, n_teams)
    attack -= attack.mean()
    defence = rng.normal(0, 0.25, n_teams)
    start = date(2020, 8, 1)
    matches = []
    day = 0
    for _ in range(seasons):
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a:
                    continue
                lam = np.exp(home_adv + attack[h] + defence[a])
                mu = np.exp(attack[a] + defence[h])
                matches.append(Match(start + timedelta(days=day // 10), teams[h], teams[a],
                                     int(rng.poisson(lam)), int(rng.poisson(mu))))
                day += 1
    return teams, attack, defence, matches


def test_recovers_known_parameters():
    teams, attack, defence, matches = simulate(seasons=8)
    ref = max(m.played_on for m in matches) + timedelta(days=1)
    model = fit(matches, ref, xi=0.0)
    order = [model.teams.index(t) for t in teams]
    assert np.corrcoef(model.attack[order], attack)[0, 1] > 0.9
    assert np.corrcoef(model.defence[order], defence)[0, 1] > 0.85
    assert model.home_adv == pytest.approx(0.27, abs=0.08)
    assert abs(model.attack.sum()) < 1e-9
    assert abs(model.rho) < 0.15  # simulated with rho = 0


def test_predictions_are_valid_distributions():
    _, _, _, matches = simulate(n_teams=8, seasons=2)
    ref = max(m.played_on for m in matches) + timedelta(days=1)
    mk = fit(matches, ref).predict("Team00", "Team01")
    assert mk.home_win + mk.draw + mk.away_win == pytest.approx(1.0)


def test_refuses_future_matches():
    _, _, _, matches = simulate(n_teams=6, seasons=1)
    with pytest.raises(ValueError):
        fit(matches, matches[len(matches) // 2].played_on)


def test_unknown_team_raises():
    _, _, _, matches = simulate(n_teams=6, seasons=1)
    model = fit(matches, max(m.played_on for m in matches) + timedelta(days=1))
    with pytest.raises(KeyError):
        model.predict("Team00", "Nobody FC")


def test_predict_clips_rho_for_high_scoring_pairings():
    from sportsmodel.dixon_coles import DixonColesModel

    m = DixonColesModel(("A", "B"), np.array([1.0, -1.0]), np.array([1.0, 1.0]), 0.3, 0.2, date(2025, 1, 1), 10)
    lam, mu = m.expected_goals("A", "B")
    assert 0.2 > 1 / (lam * mu)  # rho would make P(0-0) negative without clipping
    mk = m.predict("A", "B")
    assert mk.home_win + mk.draw + mk.away_win == pytest.approx(1.0)
