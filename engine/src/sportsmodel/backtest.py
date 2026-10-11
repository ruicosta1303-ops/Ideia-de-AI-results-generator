"""Walk-forward forecasting: every forecast uses only matches played before it.

Models are refitted every `refit_days`; all matches until the next refit are
forecast with that frozen fit, exactly as a weekly live schedule would.

Models
  base_rate    league home/draw/away frequencies over the training window
  elo          Elo ratings (frozen at the cut-off) mapped to 1X2 by an ordered logit
  dixon_coles  Dixon-Coles Poisson with time decay; also gives goals markets
Benchmark (not a model, needs closing odds known only at kickoff)
  market       bookmaker closing odds with the margin removed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import groupby

from . import dixon_coles
from .elo import Elo, fit_ordered_logit, ordered_logit_probs
from .markets import MatchMarkets
from .odds import fair_probabilities

MODEL_VERSION = "0.1.0"
BURN_IN_DAYS = 300  # Elo ratings start equal; ignore their first season when fitting the logit
PROMOTED_PRIOR_TEAMS = 3


@dataclass(frozen=True)
class MatchRecord:
    key: object
    competition: str
    played_on: date
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    closing_odds: tuple[float, float, float] | None = None

    @property
    def finished(self) -> bool:
        return self.home_goals is not None

    @property
    def outcome(self) -> int:
        return 0 if self.home_goals > self.away_goals else 1 if self.home_goals == self.away_goals else 2


@dataclass(frozen=True)
class Probs:
    home_win: float
    draw: float
    away_win: float


@dataclass
class Run:
    model: str
    cutoff: date
    n_train: int
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Forecast:
    run: Run
    match: MatchRecord
    probs: Probs | MatchMarkets


@dataclass
class Settings:
    refit_days: int = 7
    window_days: int = 3 * 365
    xi: float = 0.0019
    elo_k: float = 20.0
    elo_home_adv: float = 60.0


class _EloTracker:
    """Elo ratings updated day by day, with a rating rule for teams appearing later."""

    def __init__(self, s: Settings):
        self.elo = Elo(k=s.elo_k, home_adv=s.elo_home_adv)
        self.first_day: date | None = None
        self.last_played: dict[str, date] = {}
        self.history: list[tuple[date, float, int]] = []  # (date, pre-match diff, outcome)

    def _enter(self, team: str, day: date) -> None:
        if team not in self.elo.ratings:
            self.elo.ratings[team] = self.promoted_rating(day)

    def snapshot_diff(self, ratings: dict[str, float], recent_low: float, m: MatchRecord) -> float:
        return ratings.get(m.home, recent_low) + self.elo.home_adv - ratings.get(m.away, recent_low)

    def promoted_rating(self, day: date) -> float:
        recent = [t for t, d in self.last_played.items() if (day - d).days <= 365]
        if self.first_day is None or (day - self.first_day).days <= BURN_IN_DAYS or len(recent) < 3:
            return self.elo.initial
        lowest = sorted(self.elo.ratings[t] for t in recent)[:PROMOTED_PRIOR_TEAMS]
        return sum(lowest) / len(lowest)

    def play_day(self, day: date, matches: list[MatchRecord]) -> None:
        if self.first_day is None:
            self.first_day = day
        for m in matches:
            self._enter(m.home, day)
            self._enter(m.away, day)
        diffs = [self.elo.diff(m.home, m.away) for m in matches]  # all before any update that day
        for m, d in zip(matches, diffs):
            self.history.append((day, d, m.outcome))
        for m in matches:
            self.elo.update(m.home, m.away, m.home_goals, m.away_goals)
            self.last_played[m.home] = self.last_played[m.away] = day


class _Fitted:
    def __init__(self, finished_before: list[MatchRecord], cutoff: date, tracker: _EloTracker, s: Settings):
        train = [m for m in finished_before if (cutoff - m.played_on).days <= s.window_days]
        self.cutoff = cutoff
        n = len(train)

        counts = [0, 0, 0]
        for m in train:
            counts[m.outcome] += 1
        self.base = Probs(*(c / n for c in counts))
        self.base_run = Run("base_rate", cutoff, n, {"window_days": s.window_days})

        self.dc = dixon_coles.fit(
            [dixon_coles.Match(m.played_on, m.home, m.away, m.home_goals, m.away_goals) for m in train],
            cutoff, s.xi)
        self.dc_run = Run("dixon_coles", cutoff, n, {
            "xi": s.xi, "window_days": s.window_days, "home_adv": self.dc.home_adv, "rho": self.dc.rho,
            "promoted_prior_teams": PROMOTED_PRIOR_TEAMS})

        start = tracker.first_day + timedelta(days=BURN_IN_DAYS)
        pairs = [(d, o) for day, d, o in tracker.history
                 if day >= start and (cutoff - day).days <= s.window_days]
        self.logit = fit_ordered_logit([p[0] for p in pairs], [p[1] for p in pairs])
        self.ratings = dict(tracker.elo.ratings)
        self.promoted = tracker.promoted_rating(cutoff)
        self.elo_run = Run("elo", cutoff, len(pairs), {
            "k": s.elo_k, "home_adv": s.elo_home_adv, "cut_low": self.logit[0], "cut_high": self.logit[1],
            "scale": self.logit[2]})

    def forecasts(self, m: MatchRecord, tracker: _EloTracker) -> list[Forecast]:
        diff = tracker.snapshot_diff(self.ratings, self.promoted, m)
        return [
            Forecast(self.base_run, m, self.base),
            Forecast(self.elo_run, m, Probs(*ordered_logit_probs(diff, *self.logit))),
            Forecast(self.dc_run, m, self.dc.predict(m.home, m.away, PROMOTED_PRIOR_TEAMS)),
        ]


def market_forecast(m: MatchRecord) -> Probs | None:
    return Probs(*fair_probabilities(m.closing_odds)) if m.closing_odds else None


def walk_forward(matches: list[MatchRecord], test_from: date, s: Settings | None = None,
                 live_cutoff: date | None = None) -> tuple[list[Forecast], list[Forecast]]:
    """Returns (backtest forecasts for finished matches on/after test_from,
    live forecasts for unfinished matches on/after live_cutoff)."""
    s = s or Settings()
    comps = {m.competition for m in matches}
    if len(comps) > 1:
        raise ValueError("walk_forward works on one competition at a time")
    finished = sorted((m for m in matches if m.finished), key=lambda m: m.played_on)
    tracker = _EloTracker(s)
    done: list[MatchRecord] = []
    fitted: _Fitted | None = None
    backtest: list[Forecast] = []

    for day, group in groupby(finished, key=lambda m: m.played_on):
        group = list(group)
        if day >= test_from:
            if fitted is None or (day - fitted.cutoff).days >= s.refit_days:
                fitted = _Fitted(done, day, tracker, s)
            for m in group:
                backtest.extend(fitted.forecasts(m, tracker))
        tracker.play_day(day, group)
        done.extend(group)

    live: list[Forecast] = []
    if live_cutoff is not None:
        upcoming = [m for m in matches if not m.finished and m.played_on >= live_cutoff]
        if upcoming:
            fitted = _Fitted([m for m in done if m.played_on < live_cutoff], live_cutoff, tracker, s)
            for m in sorted(upcoming, key=lambda m: m.played_on):
                live.extend(fitted.forecasts(m, tracker))
    return backtest, live
