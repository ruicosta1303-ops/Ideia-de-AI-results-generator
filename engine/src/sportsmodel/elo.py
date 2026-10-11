"""Elo team ratings for football (World Football Elo style margin factor)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize


def margin_multiplier(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


@dataclass
class Elo:
    k: float = 20.0
    home_adv: float = 60.0
    initial: float = 1500.0
    ratings: dict[str, float] = field(default_factory=dict)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self.initial)

    def diff(self, home: str, away: str) -> float:
        """Rating difference including home advantage (positive favours home)."""
        return self.rating(home) + self.home_adv - self.rating(away)

    def expected_score(self, home: str, away: str) -> float:
        """Expected points share of the home team (win=1, draw=0.5)."""
        return 1.0 / (1.0 + 10 ** (-self.diff(home, away) / 400))

    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> float:
        """Apply a result; returns the rating change of the home team."""
        actual = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        delta = self.k * margin_multiplier(home_goals - away_goals) * (
            actual - self.expected_score(home, away)
        )
        self.ratings[home] = self.rating(home) + delta
        self.ratings[away] = self.rating(away) - delta
        return delta


def ordered_logit_probs(diff: float, cut_low: float, cut_high: float, scale: float) -> tuple[float, float, float]:
    """Map an Elo difference to (home, draw, away) with an ordered logit.

    cut_low < cut_high and scale are fitted on historical data (Phase 3).
    The three values sum to 1 by construction.
    """
    if cut_low >= cut_high:
        raise ValueError("cut_low must be < cut_high")
    z = diff / scale
    p_away = 1 / (1 + math.exp(-(cut_low - z)))
    p_not_home = 1 / (1 + math.exp(-(cut_high - z)))
    return 1 - p_not_home, p_not_home - p_away, p_away


def fit_ordered_logit(diffs, outcomes) -> tuple[float, float, float]:
    """Maximum-likelihood cut points and scale for ordered_logit_probs.

    diffs: pre-match Elo differences; outcomes: 0 = home win, 1 = draw, 2 = away win.
    """
    d = np.asarray(diffs, dtype=float) / 400.0
    o = np.asarray(outcomes, dtype=int)
    if len(d) < 50 or len(set(o.tolist())) < 3:
        raise ValueError("need at least 50 matches with all three outcomes to fit")

    def nll(p):
        c1, gap, beta = p
        c2 = c1 + np.exp(gap)
        z = beta * d
        p_away = 1 / (1 + np.exp(-(c1 - z)))
        p_not_home = 1 / (1 + np.exp(-(c2 - z)))
        probs = np.stack([1 - p_not_home, p_not_home - p_away, p_away], axis=1)
        return -np.log(np.clip(probs[np.arange(len(o)), o], 1e-12, 1)).sum()

    res = minimize(nll, [-1.0, 0.0, 2.0], method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-8})
    c1, gap, beta = res.x
    if beta <= 0:
        raise RuntimeError("ordered logit fit gave a non-positive slope")
    return float(c1), float(c1 + np.exp(gap)), float(400.0 / beta)
