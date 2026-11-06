"""Forecasts for cross-league cup matches (Champions League).

Domestic Elo ratings are only comparable inside one league: every league's ratings
are centred on its own average. A cup match between, say, the 5th best Belgian club
and the 10th best English club therefore needs one more number per league: how strong
its average team is. Those league offsets are learned from earlier cup matches.

Model (cross_league_elo)
    rel(team)  = domestic Elo rating - average rating of its league over the last year
    diff       = rel(home) + offset[league(home)] - rel(away) - offset[league(away)] + home_adv
    P(1, X, 2) = ordered logit of diff (same mapping as the domestic Elo model)
Offsets, home advantage and the logit are fitted by maximum likelihood on cup matches
played before the forecast, with a Gaussian prior (sd PRIOR_SD Elo points) on each
offset so leagues with few cup matches stay near the average. Clubs from leagues we do
not cover share one OTHER offset and count as an average team of it.

Baselines it must beat before it is shown
  base_rate        home/draw/away frequencies of earlier cup matches
  same_level_elo   the same model with every offset fixed at 0 (all leagues equal)
Only the 90-minute result is modelled (extra time and penalties are ignored).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby

import numpy as np
from scipy.optimize import minimize

from .backtest import BURN_IN_DAYS, Forecast, MatchRecord, Probs, Run, Settings, _EloTracker
from .elo import fit_ordered_logit, ordered_logit_probs

OTHER = "OTHER"
PRIOR_SD = 150.0  # Elo points; a league offset of +-300 is about 2 sd
MIN_TRAIN = 60  # cup matches needed before the cup-specific parameters are fitted
LEAGUE_MEMORY_DAYS = 365  # a team belongs to the league of its last domestic match within this window
REFIT_DAYS = 7
DEFAULT_LOGIT = (-0.94, 0.20, 250.0)  # about 45/27/28 % home/draw/away for equal teams


@dataclass(frozen=True)
class CupMatch:
    key: object
    played_on: date
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    neutral: bool = False  # final at a neutral ground: no home advantage

    @property
    def finished(self) -> bool:
        return self.home_goals is not None

    @property
    def outcome(self) -> int:
        return 0 if self.home_goals > self.away_goals else 1 if self.home_goals == self.away_goals else 2


class DomesticRatings:
    """Domestic Elo per league, advanced day by day, read as league-relative ratings."""

    def __init__(self, domestic: list[MatchRecord], s: Settings):
        self._days = [(d, list(g)) for d, g in groupby(
            sorted((m for m in domestic if m.finished), key=lambda m: m.played_on), key=lambda m: m.played_on)]
        self._i = 0
        self._trackers: dict[str, _EloTracker] = defaultdict(lambda: _EloTracker(s))
        self._last: dict[str, tuple[date, str]] = {}  # team -> (last domestic match, league)

    def advance_to(self, day: date) -> None:
        """Apply every domestic result played before `day`."""
        while self._i < len(self._days) and self._days[self._i][0] < day:
            d, ms = self._days[self._i]
            for comp, group in groupby(sorted(ms, key=lambda m: m.competition), key=lambda m: m.competition):
                group = list(group)
                self._trackers[comp].play_day(d, group)
                for m in group:
                    self._last[m.home] = self._last[m.away] = (d, comp)
            self._i += 1

    def relative(self, day: date) -> dict[str, tuple[str, float]]:
        """team -> (league, rating minus its league's average), for teams active in the last year."""
        out: dict[str, tuple[str, float]] = {}
        for comp, tr in self._trackers.items():
            active = [t for t, d in tr.last_played.items() if (day - d).days <= LEAGUE_MEMORY_DAYS]
            if not active:
                continue
            mean = sum(tr.elo.ratings[t] for t in active) / len(active)
            for t in active:
                if self._last[t][1] == comp:
                    out[t] = (comp, tr.elo.ratings[t] - mean)
        return out

    def domestic_logit(self) -> tuple[float, float, float]:
        """Ordered-logit mapping fitted on all domestic matches so far (fallback before cup data)."""
        diffs, outs = [], []
        for tr in self._trackers.values():
            start = tr.first_day + timedelta(days=BURN_IN_DAYS) if tr.first_day else None
            for day, d, o in tr.history:
                if day >= start:  # ratings all start equal; skip each league's first season
                    diffs.append(d)
                    outs.append(o)
        try:
            return fit_ordered_logit(diffs, outs)
        except (ValueError, RuntimeError):
            return DEFAULT_LOGIT


def _side(rel: dict[str, tuple[str, float]], team: str) -> tuple[str, float]:
    return rel.get(team, (OTHER, 0.0))


def _probs(diff: np.ndarray, c1: float, c2: float, beta: float) -> np.ndarray:
    z = beta * diff / 400.0
    p_away = 1 / (1 + np.exp(-(c1 - z)))
    p_not_home = 1 / (1 + np.exp(-(c2 - z)))
    return np.stack([1 - p_not_home, p_not_home - p_away, p_away], axis=1)


@dataclass
class CupFit:
    offsets: dict[str, float]
    home_adv: float
    cut_low: float
    cut_high: float
    scale: float

    def diff(self, home: tuple[str, float], away: tuple[str, float], neutral: bool) -> float:
        return (home[1] + self.offsets.get(home[0], 0.0) - away[1] - self.offsets.get(away[0], 0.0)
                + (0.0 if neutral else self.home_adv))

    def probs(self, home, away, neutral) -> Probs:
        return Probs(*ordered_logit_probs(self.diff(home, away, neutral), self.cut_low, self.cut_high, self.scale))

    def params(self) -> dict:
        return {"offsets": {k: round(v, 1) for k, v in sorted(self.offsets.items())}, "home_adv": self.home_adv,
                "cut_low": self.cut_low, "cut_high": self.cut_high, "scale": self.scale, "prior_sd": PRIOR_SD}


def fit_cup(rows: list[tuple[tuple[str, float], tuple[str, float], bool, int, float]],
            fallback: tuple[float, float, float], with_offsets: bool = True) -> CupFit:
    """rows: (home side, away side, neutral, outcome, weight). Maximum a posteriori fit."""
    leagues = sorted({r[0][0] for r in rows} | {r[1][0] for r in rows}) if with_offsets else []
    li = {lg: i for i, lg in enumerate(leagues)}
    nl = len(leagues)
    hrel = np.array([r[0][1] for r in rows])
    arel = np.array([r[1][1] for r in rows])
    hl = np.array([li.get(r[0][0], -1) for r in rows])
    al = np.array([li.get(r[1][0], -1) for r in rows])
    home = np.array([0.0 if r[2] else 1.0 for r in rows])
    out = np.array([r[3] for r in rows])
    w = np.array([r[4] for r in rows])

    def unpack(p):
        off = np.append(p[:nl], 0.0)  # index -1 -> 0
        return off, p[nl], p[nl + 1], p[nl + 1] + math.exp(p[nl + 2]), p[nl + 3]

    def nll(p):
        off, h, c1, c2, beta = unpack(p)
        diff = hrel + off[hl] - arel - off[al] + home * h
        pr = _probs(diff, c1, c2, beta)[np.arange(len(out)), out]
        return -(w * np.log(np.clip(pr, 1e-12, 1))).sum() + (off[:nl] ** 2).sum() / (2 * PRIOR_SD ** 2)

    c1, c2, scale = fallback
    p0 = np.concatenate([np.zeros(nl), [60.0, c1, math.log(c2 - c1), 400.0 / scale]])
    bounds = [(-600, 600)] * nl + [(-200, 300), (-5, 5), (-5, 3), (0.05, 10)]
    res = minimize(nll, p0, method="L-BFGS-B", bounds=bounds)
    off, h, c1, c2, beta = unpack(res.x)
    return CupFit({lg: float(off[li[lg]]) for lg in leagues}, float(h), float(c1), float(c2), float(400.0 / beta))


def walk_forward_cup(cup: list[CupMatch], domestic: list[MatchRecord], test_from: date, competition: str,
                     s: Settings | None = None, live_cutoff: date | None = None,
                     xi: float = 0.0019) -> tuple[list[Forecast], list[Forecast]]:
    """Backtest forecasts for finished cup matches on/after test_from, and live forecasts for
    unfinished ones on/after live_cutoff. Every forecast uses only matches played before its day."""
    s = s or Settings()
    ratings = DomesticRatings(domestic, s)
    seen: list[tuple[date, tuple, tuple, bool, int]] = []  # earlier finished cup matches with their sides
    fits: dict[str, tuple[Run, object]] = {}
    last_fit: date | None = None
    backtest: list[Forecast] = []

    def refit(day: date) -> None:
        nonlocal fits, last_fit
        last_fit = day
        fallback = ratings.domestic_logit()
        n = len(seen)
        counts = [sum(1 for r in seen if r[4] == k) for k in range(3)]
        base = Probs(*(c / n for c in counts)) if n >= MIN_TRAIN // 2 else Probs(*_domestic_base(domestic, day))
        rows = [(h, a, neu, o, math.exp(-xi * (day - d).days)) for d, h, a, neu, o in seen]
        if n >= MIN_TRAIN:
            full, flat = fit_cup(rows, fallback), fit_cup(rows, fallback, with_offsets=False)
        else:  # not enough cup matches yet: all leagues equal, domestic home advantage and mapping
            full = flat = CupFit({}, s.elo_home_adv, *fallback)
        fits = {"base_rate": (Run("base_rate", day, n), base),
                "same_level_elo": (Run("same_level_elo", day, n, flat.params()), flat),
                "cross_league_elo": (Run("cross_league_elo", day, n, full.params()), full)}

    def forecasts(m: CupMatch, rel) -> list[Forecast]:
        rec = MatchRecord(m.key, competition, m.played_on, m.home, m.away, m.home_goals, m.away_goals)
        h, a = _side(rel, m.home), _side(rel, m.away)
        out = []
        for name, (run, model) in fits.items():
            out.append(Forecast(run, rec, model if name == "base_rate" else model.probs(h, a, m.neutral)))
        return out

    finished = sorted((m for m in cup if m.finished), key=lambda m: m.played_on)
    for day, group in groupby(finished, key=lambda m: m.played_on):
        group = list(group)
        ratings.advance_to(day)
        rel = ratings.relative(day)
        if day >= test_from:
            if last_fit is None or (day - last_fit).days >= REFIT_DAYS:
                refit(day)
            for m in group:
                backtest.extend(forecasts(m, rel))
        for m in group:
            seen.append((day, _side(rel, m.home), _side(rel, m.away), m.neutral, m.outcome))

    live: list[Forecast] = []
    if live_cutoff is not None:
        upcoming = sorted((m for m in cup if not m.finished and m.played_on >= live_cutoff), key=lambda m: m.played_on)
        if upcoming:
            seen[:] = [r for r in seen if r[0] < live_cutoff]
            ratings.advance_to(live_cutoff)
            refit(live_cutoff)
            rel = ratings.relative(live_cutoff)
            for m in upcoming:
                live.extend(forecasts(m, rel))
    return backtest, live


def _domestic_base(domestic: list[MatchRecord], day: date) -> tuple[float, float, float]:
    recent = [m for m in domestic if m.finished and timedelta(0) < day - m.played_on <= timedelta(days=3 * 365)]
    counts = [0, 0, 0]
    for m in recent:
        counts[m.outcome] += 1
    n = sum(counts)
    return tuple(c / n for c in counts) if n else (0.45, 0.27, 0.28)


def log_loss_gain(model: list[Forecast], baseline: list[Forecast], n_boot: int = 2000, seed: int = 0) -> dict:
    """Paired comparison: mean log-loss difference (model - baseline) with a bootstrap 95% interval.
    Negative means the model is better; 'clearly better' means the whole interval is below 0."""
    by_key = {f.match.key: f for f in baseline}
    diffs = []
    for f in model:
        b = by_key.get(f.match.key)
        if b is None:
            continue
        o = f.match.outcome
        pm = (f.probs.home_win, f.probs.draw, f.probs.away_win)[o]
        pb = (b.probs.home_win, b.probs.draw, b.probs.away_win)[o]
        diffs.append(-math.log(max(pm, 1e-15)) + math.log(max(pb, 1e-15)))
    if not diffs:
        return {"n": 0, "mean": None, "low": None, "high": None, "clearly_better": False}
    d = np.array(diffs)
    rng = np.random.default_rng(seed)
    boot = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    low, high = np.percentile(boot, [2.5, 97.5])
    return {"n": len(d), "mean": float(d.mean()), "low": float(low), "high": float(high),
            "clearly_better": bool(high < 0)}
