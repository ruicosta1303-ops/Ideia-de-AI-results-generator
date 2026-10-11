"""Turn expected goals into a scoreline matrix and derive every market from it.

All market probabilities (1X2, over/under, BTTS) are read off the *same*
normalised matrix, so they are mutually consistent and each set sums to 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import poisson

DEFAULT_MAX_GOALS = 10
DEFAULT_LINES = (1.5, 2.5, 3.5)


def rho_bounds(lam: float, mu: float) -> tuple[float, float]:
    """Range of the Dixon-Coles rho that keeps every probability non-negative."""
    return max(-1.0 / lam, -1.0 / mu), min(1.0 / (lam * mu), 1.0)


def score_matrix(
    lam: float, mu: float, rho: float = 0.0, max_goals: int = DEFAULT_MAX_GOALS
) -> np.ndarray:
    """P(home scores i, away scores j) for i, j in 0..max_goals.

    lam / mu are the expected goals of the home / away team. rho applies the
    Dixon-Coles adjustment to the four low scores (0-0, 1-0, 0-1, 1-1);
    rho = 0 gives two independent Poisson distributions. The matrix is
    renormalised so the tiny mass beyond max_goals is redistributed and the
    total is exactly 1.
    """
    if not (lam > 0 and mu > 0):
        raise ValueError(f"expected goals must be positive, got lam={lam}, mu={mu}")
    lo, hi = rho_bounds(lam, mu)
    if not lo <= rho <= hi:
        raise ValueError(f"rho={rho} outside valid range [{lo:.4f}, {hi:.4f}]")

    goals = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
    m[0, 0] *= 1 - lam * mu * rho
    m[0, 1] *= 1 + lam * rho
    m[1, 0] *= 1 + mu * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()


@dataclass(frozen=True)
class MatchMarkets:
    home_win: float
    draw: float
    away_win: float
    expected_home_goals: float
    expected_away_goals: float
    over: dict[float, float] = field(default_factory=dict)
    under: dict[float, float] = field(default_factory=dict)
    btts_yes: float = 0.0
    btts_no: float = 0.0
    most_likely_score: tuple[int, int] = (0, 0)
    most_likely_score_prob: float = 0.0


def markets_from_matrix(m: np.ndarray, lines: tuple[float, ...] = DEFAULT_LINES) -> MatchMarkets:
    if not np.isclose(m.sum(), 1.0):
        raise ValueError("score matrix must sum to 1")
    n = m.shape[0]
    goals = np.arange(n)
    home = float(np.tril(m, -1).sum())
    draw = float(np.trace(m))
    away = float(np.triu(m, 1).sum())

    total = goals[:, None] + goals[None, :]
    over = {line: float(m[total > line].sum()) for line in lines}
    under = {line: 1.0 - over[line] for line in lines}

    btts_yes = float(m[1:, 1:].sum())
    i, j = np.unravel_index(int(np.argmax(m)), m.shape)

    return MatchMarkets(
        home_win=home,
        draw=draw,
        away_win=away,
        expected_home_goals=float((m.sum(axis=1) * goals).sum()),
        expected_away_goals=float((m.sum(axis=0) * goals).sum()),
        over=over,
        under=under,
        btts_yes=btts_yes,
        btts_no=1.0 - btts_yes,
        most_likely_score=(int(i), int(j)),
        most_likely_score_prob=float(m[i, j]),
    )


def match_markets(lam: float, mu: float, rho: float = 0.0, **kwargs) -> MatchMarkets:
    return markets_from_matrix(score_matrix(lam, mu, rho, **kwargs))
