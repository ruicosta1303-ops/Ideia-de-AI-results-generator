from datetime import date, timedelta

import numpy as np

from sportsmodel.backtest import MatchRecord
from sportsmodel.cross_league import CupMatch, fit_cup, log_loss_gain, walk_forward_cup


def simulate(seed=1, seasons=4, gap=0.6):
    """Two domestic leagues of 10 teams; league A is `gap` (log goal rate) stronger than B.
    Cup matches pair A and B teams every few weeks."""
    rng = np.random.default_rng(seed)
    strength = {f"A{i}": gap / 2 + rng.normal(0, 0.25) for i in range(10)}
    strength |= {f"B{i}": -gap / 2 + rng.normal(0, 0.25) for i in range(10)}

    def play(h, a):
        return int(rng.poisson(np.exp(0.25 + 0.2 + strength[h] - strength[a]) * 0.6)), \
               int(rng.poisson(np.exp(0.2 + strength[a] - strength[h]) * 0.6))

    domestic, cup, key = [], [], 0
    start = date(2020, 8, 1)
    for s in range(seasons):
        day0 = start + timedelta(days=365 * s)
        for lg in "AB":
            teams = [f"{lg}{i}" for i in range(10)]
            rnd = 0
            for h in teams:
                for a in teams:
                    if h == a:
                        continue
                    d = day0 + timedelta(days=(rnd % 38) * 7)
                    rnd += 1
                    hg, ag = play(h, a)
                    key += 1
                    domestic.append(MatchRecord(key, lg, d, h, a, hg, ag))
        for wk in range(0, 34, 2):
            d = day0 + timedelta(days=wk * 7 + 3)
            for _ in range(6):
                h, a = rng.choice([f"A{i}" for i in range(10)]), rng.choice([f"B{i}" for i in range(10)])
                if rng.random() < 0.5:
                    h, a = a, h
                hg, ag = play(h, a)
                key += 1
                cup.append(CupMatch(key, d, str(h), str(a), hg, ag))
    return domestic, cup


def test_cross_league_learns_league_gap_and_beats_same_level():
    domestic, cup = simulate()
    bt, live = walk_forward_cup(cup, domestic, date(2022, 7, 1), "CL")
    by = {}
    for f in bt:
        by.setdefault(f.run.model, []).append(f)
    assert set(by) == {"base_rate", "same_level_elo", "cross_league_elo"}
    for fs in by.values():
        for f in fs:
            p = f.probs
            assert abs(p.home_win + p.draw + p.away_win - 1) < 1e-9
    last = by["cross_league_elo"][-1].run.params["offsets"]
    assert last["A"] - last["B"] > 100  # A is the stronger league
    gain = log_loss_gain(by["cross_league_elo"], by["same_level_elo"])
    assert gain["mean"] < 0 and gain["clearly_better"]
    assert log_loss_gain(by["cross_league_elo"], by["base_rate"])["clearly_better"]


def test_forecasts_use_only_earlier_matches():
    domestic, cup = simulate(seasons=3)
    cutoff = date(2022, 3, 1)
    bt_full, _ = walk_forward_cup(cup, domestic, date(2021, 9, 1), "CL")
    # removing every match from the cutoff on must not change forecasts before it
    cup_cut = [m for m in cup if m.played_on < cutoff]
    dom_cut = [m for m in domestic if m.played_on < cutoff]
    bt_changed, _ = walk_forward_cup(cup_cut, dom_cut, date(2021, 9, 1), "CL")
    before = lambda bt: [(f.run.model, f.match.key, f.probs) for f in bt if f.match.played_on < cutoff]
    assert before(bt_full) == before(bt_changed) and before(bt_full)


def test_unknown_league_team_and_neutral_final():
    domestic, cup = simulate(seasons=3)
    upcoming = [CupMatch("x", date(2023, 5, 1), "Z Club", "A1"), CupMatch("y", date(2023, 5, 1), "A1", "B1", neutral=True),
                CupMatch("z", date(2023, 5, 1), "A1", "B1")]
    _, live = walk_forward_cup(cup + upcoming, domestic, date(2023, 1, 1), "CL", live_cutoff=date(2023, 4, 1))
    cross = {f.match.key: f for f in live if f.run.model == "cross_league_elo"}
    assert set(cross) == {"x", "y", "z"}
    assert cross["y"].probs.home_win < cross["z"].probs.home_win  # no home advantage at a neutral final
    assert cross["x"].probs.away_win > 0  # a club from an uncovered league still gets a forecast


def test_fit_cup_prior_keeps_unseen_offsets_small():
    rows = [(("A", 0.0), ("B", 0.0), False, 0, 1.0)] * 3
    fit = fit_cup(rows, (-1.0, 0.3, 300.0))
    assert all(abs(v) < 300 for v in fit.offsets.values())
