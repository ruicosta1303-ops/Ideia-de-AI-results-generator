"""Dixon-Coles (1997) Poisson model with exponential time decay.

Model: home goals ~ Poisson(lam), away goals ~ Poisson(mu) with
    log(lam) = home_adv + attack[home] + defence[away]
    log(mu)  =            attack[away] + defence[home]
plus the low-score correction rho. Older matches are down-weighted by
exp(-xi * days_before_reference_date). Attack ratings are constrained to sum
to zero so the parameters are identifiable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from .markets import MatchMarkets, match_markets, rho_bounds


@dataclass(frozen=True)
class Match:
    played_on: date
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class DixonColesModel:
    teams: tuple[str, ...]
    attack: np.ndarray
    defence: np.ndarray
    home_adv: float
    rho: float
    fitted_until: date
    n_matches: int

    def ratings(self, team: str, unknown_as_weakest: int = 0) -> tuple[float, float]:
        """(attack, defence) of a team.

        A team absent from the training data (e.g. newly promoted) raises KeyError,
        unless unknown_as_weakest > 0: it then gets the average ratings of that many
        weakest teams, a common prior for promoted clubs.
        """
        if team in self.teams:
            i = self.teams.index(team)
            return float(self.attack[i]), float(self.defence[i])
        if unknown_as_weakest <= 0:
            raise KeyError(f"team {team!r} has no rating in this model")
        weakest = np.argsort(self.attack - self.defence)[:unknown_as_weakest]
        return float(self.attack[weakest].mean()), float(self.defence[weakest].mean())

    def expected_goals(self, home: str, away: str, unknown_as_weakest: int = 0) -> tuple[float, float]:
        ah, dh = self.ratings(home, unknown_as_weakest)
        aa, da = self.ratings(away, unknown_as_weakest)
        return float(np.exp(self.home_adv + ah + da)), float(np.exp(aa + dh))

    def predict(self, home: str, away: str, unknown_as_weakest: int = 0) -> MatchMarkets:
        lam, mu = self.expected_goals(home, away, unknown_as_weakest)
        # rho was valid for the training matches; clip it to this match's valid range
        lo, hi = rho_bounds(lam, mu)
        return match_markets(lam, mu, min(max(self.rho, lo), hi))


def time_weights(dates: list[date], reference: date, xi: float) -> np.ndarray:
    days = np.array([(reference - d).days for d in dates], dtype=float)
    if (days < 0).any():
        raise ValueError("training data contains matches after the reference date")
    return np.exp(-xi * days)


def _tau(x, y, lam, mu, rho):
    t = np.ones_like(lam)
    t = np.where((x == 0) & (y == 0), 1 - lam * mu * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lam * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + mu * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


def fit(matches: list[Match], reference: date, xi: float = 0.0019) -> DixonColesModel:
    """Fit by weighted maximum likelihood using only matches before `reference`.

    xi = 0.0019/day (half-life ~ 1 year) is the value Dixon & Coles found
    reasonable; it should be re-tuned by backtesting.
    """
    if any(m.played_on >= reference for m in matches):
        raise ValueError("fit() only accepts matches played before the reference date")
    if not matches:
        raise ValueError("no matches to fit")

    teams = tuple(sorted({m.home for m in matches} | {m.away for m in matches}))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([idx[m.home] for m in matches])
    ai = np.array([idx[m.away] for m in matches])
    x = np.array([m.home_goals for m in matches])
    y = np.array([m.away_goals for m in matches])
    w = time_weights([m.played_on for m in matches], reference, xi)
    const = gammaln(x + 1) + gammaln(y + 1)

    def unpack(p):
        attack = np.append(p[: n - 1], -p[: n - 1].sum())
        defence = p[n - 1 : 2 * n - 1]
        return attack, defence, p[-2], p[-1]

    def neg_loglik(p):
        attack, defence, home_adv, rho = unpack(p)
        log_lam = home_adv + attack[hi] + defence[ai]
        log_mu = attack[ai] + defence[hi]
        lam, mu = np.exp(log_lam), np.exp(log_mu)
        tau = _tau(x, y, lam, mu, rho)
        if (tau <= 0).any():
            return 1e12
        ll = np.log(tau) + x * log_lam - lam + y * log_mu - mu - const
        return -(w * ll).sum()

    p0 = np.zeros(2 * n + 1)
    p0[-2] = 0.25
    bounds = [(None, None)] * (2 * n - 1) + [(-1, 1), (-0.3, 0.3)]
    res = minimize(neg_loglik, p0, method="L-BFGS-B", bounds=bounds)
    if not res.success:
        raise RuntimeError(f"Dixon-Coles fit did not converge: {res.message}")

    attack, defence, home_adv, rho = unpack(res.x)
    return DixonColesModel(
        teams=teams,
        attack=attack,
        defence=defence,
        home_adv=float(home_adv),
        rho=float(rho),
        fitted_until=reference,
        n_matches=len(matches),
    )
