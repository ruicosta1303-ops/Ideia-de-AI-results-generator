"""Walk-forward tests on SYNTHETIC simulated seasons (test-only data)."""
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from sportsmodel.backtest import MatchRecord, walk_forward
from sportsmodel.evaluate import report


def league(seasons=4, n_teams=12, seed=3):
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(n_teams)]
    att = rng.normal(0, 0.35, n_teams)
    de = rng.normal(0, 0.3, n_teams)
    out, key = [], 0
    for s in range(seasons):
        start = date(2018 + s, 8, 10)
        pairs = [(h, a) for h in range(n_teams) for a in range(n_teams) if h != a]
        rng.shuffle(pairs)
        for i, (h, a) in enumerate(pairs):
            lam, mu = np.exp(0.25 + att[h] + de[a]), np.exp(att[a] + de[h])
            out.append(MatchRecord(key, "XX", start + timedelta(days=(i // (n_teams // 2)) * 3), teams[h], teams[a],
                                   int(rng.poisson(lam)), int(rng.poisson(mu)), (2.0, 3.4, 3.8)))
            key += 1
    return out


TEST_FROM = date(2020, 8, 1)


@pytest.fixture(scope="module")
def run():
    ms = league()
    return ms, walk_forward(ms, TEST_FROM)[0]


def test_every_test_match_is_forecast_by_every_model(run):
    ms, fc = run
    test_keys = {m.key for m in ms if m.played_on >= TEST_FROM}
    for model in ("base_rate", "elo", "dixon_coles"):
        assert {f.match.key for f in fc if f.run.model == model} == test_keys


def test_cutoffs_precede_matches_and_probabilities_sum_to_one(run):
    _, fc = run
    for f in fc:
        assert f.run.cutoff <= f.match.played_on
        assert f.match.played_on - f.run.cutoff < timedelta(days=7)
        assert f.probs.home_win + f.probs.draw + f.probs.away_win == pytest.approx(1.0)


def test_changing_a_future_result_never_changes_earlier_forecasts(run):
    ms, fc = run
    pivot = date(2021, 3, 1)
    altered = [replace(m, home_goals=9, away_goals=0) if m.played_on >= pivot else m for m in ms]
    fc2 = walk_forward(altered, TEST_FROM)[0]
    before = lambda fs: {(f.run.model, f.match.key): f.probs.home_win for f in fs if f.match.played_on < pivot}
    assert before(fc) == before(fc2)


def test_models_beat_base_rate_on_synthetic_league(run):
    _, fc = run
    r = report(fc, [])["ALL"]
    assert r["dixon_coles"]["rps"] < r["base_rate"]["rps"]
    assert r["elo"]["rps"] < r["base_rate"]["rps"]
    assert r["dixon_coles"]["n"] == r["base_rate"]["n"]


def test_live_forecasts_for_upcoming_and_promoted_team():
    ms = league(seasons=3)
    last = max(m.played_on for m in ms)
    upcoming = [MatchRecord("u1", "XX", last + timedelta(days=5), "T0", "T1"),
                MatchRecord("u2", "XX", last + timedelta(days=5), "Promoted FC", "T2")]
    _, live = walk_forward(ms + upcoming, TEST_FROM, live_cutoff=last + timedelta(days=1))
    assert {f.match.key for f in live} == {"u1", "u2"}
    promoted = [f for f in live if f.match.key == "u2" and f.run.model == "dixon_coles"][0]
    assert promoted.probs.away_win > promoted.probs.home_win * 0.5  # weak prior, still a valid forecast
    assert all(f.run.cutoff == last + timedelta(days=1) for f in live)


def test_rejects_mixed_competitions():
    ms = league(seasons=1)
    with pytest.raises(ValueError):
        walk_forward(ms + [replace(ms[0], competition="YY", key="z")], TEST_FROM)
