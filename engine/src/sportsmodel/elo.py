"""Elo team ratings for football (World Football Elo style margin factor)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


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
