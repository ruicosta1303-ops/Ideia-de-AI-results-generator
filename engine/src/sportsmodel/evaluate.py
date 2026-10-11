"""Score forecasts against what happened. Every finished match counts."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import metrics


def _probs(f) -> list[float]:
    return [f.probs.home_win, f.probs.draw, f.probs.away_win]


def summarize(forecasts, extra: dict | None = None) -> dict:
    """Metrics for one group of forecasts of the same model."""
    p = np.array([_probs(f) for f in forecasts])
    o = np.array([f.match.outcome for f in forecasts])
    bins, ece = metrics.calibration(p.ravel(), (np.eye(3)[o]).ravel(), n_bins=10)
    out = {
        "n": len(forecasts),
        "log_loss": metrics.log_loss(p, o),
        "brier": metrics.brier(p, o),
        "rps": metrics.rps(p, o),
        "accuracy": metrics.accuracy(p, o),
        "ece_1x2": ece,
        "calibration_1x2": [b.__dict__ for b in bins],
        "observed": {k: float((o == i).mean()) for i, k in enumerate(("home", "draw", "away"))},
        "mean_predicted": dict(zip(("home", "draw", "away"), p.mean(axis=0).tolist())),
    }
    if forecasts and hasattr(forecasts[0].probs, "over"):
        for name, pred, happened in (
            ("over_2_5", [f.probs.over[2.5] for f in forecasts],
             [f.match.home_goals + f.match.away_goals > 2.5 for f in forecasts]),
            ("btts", [f.probs.btts_yes for f in forecasts],
             [f.match.home_goals > 0 and f.match.away_goals > 0 for f in forecasts]),
        ):
            pp = np.array(pred)
            yy = np.array(happened, dtype=int)
            two = np.stack([pp, 1 - pp], axis=1)
            _, e = metrics.calibration(pp, yy)
            out[name] = {"log_loss": metrics.log_loss(two, 1 - yy), "brier": metrics.brier(two, 1 - yy) / 2,
                         "ece": e, "observed_rate": float(yy.mean()), "mean_predicted": float(pp.mean())}
    if extra:
        out.update(extra)
    return out


def report(forecasts, market) -> dict:
    """forecasts: model Forecasts; market: Forecast-like benchmark items (may cover fewer matches).

    Returns {competition|'ALL': {model: metrics}}. Models are compared on the same
    matches; the market benchmark is also scored on the subset of matches that have
    closing odds, alongside each model restricted to that same subset.
    """
    groups = defaultdict(list)
    for f in forecasts:
        groups[(f.match.competition, f.run.model)].append(f)
        groups[("ALL", f.run.model)].append(f)
    mkt = defaultdict(list)
    for f in market:
        mkt[f.match.competition].append(f)
        mkt["ALL"].append(f)

    out: dict = defaultdict(dict)
    for (comp, model), fs in sorted(groups.items()):
        out[comp][model] = summarize(fs)
    for comp, ms in mkt.items():
        keys = {f.match.key for f in ms}
        out[comp]["market_closing (benchmark)"] = summarize(ms)
        for model in [m for (c, m) in groups if c == comp]:
            same = [f for f in groups[(comp, model)] if f.match.key in keys]
            out[comp][model]["on_market_subset"] = {
                "n": len(same), "log_loss": metrics.log_loss([_probs(f) for f in same], [f.match.outcome for f in same]),
                "rps": metrics.rps([_probs(f) for f in same], [f.match.outcome for f in same])}
    return dict(out)
