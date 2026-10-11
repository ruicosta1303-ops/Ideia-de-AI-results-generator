"""Scoring rules and calibration for probabilistic forecasts.

`probs` is an (n, k) array of forecasts; `outcomes` holds the index of the
outcome that happened (for 1X2: 0 = home, 1 = draw, 2 = away).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EPS = 1e-15


def _check(probs, outcomes):
    p = np.asarray(probs, dtype=float)
    o = np.asarray(outcomes, dtype=int)
    if p.ndim != 2 or len(p) != len(o) or len(p) == 0:
        raise ValueError("probs must be (n, k) with n == len(outcomes) > 0")
    if not np.allclose(p.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("each forecast must sum to 1")
    return p, o


def log_loss(probs, outcomes) -> float:
    p, o = _check(probs, outcomes)
    return float(-np.mean(np.log(np.clip(p[np.arange(len(o)), o], EPS, 1.0))))


def brier(probs, outcomes) -> float:
    """Multi-class Brier score: mean over matches of sum of squared errors (0 = perfect, 2 = worst)."""
    p, o = _check(probs, outcomes)
    onehot = np.eye(p.shape[1])[o]
    return float(np.mean(((p - onehot) ** 2).sum(axis=1)))


def rps(probs, outcomes) -> float:
    """Ranked probability score for ordered outcomes (0 = perfect)."""
    p, o = _check(probs, outcomes)
    onehot = np.eye(p.shape[1])[o]
    cum_diff = np.cumsum(p, axis=1) - np.cumsum(onehot, axis=1)
    return float(np.mean((cum_diff[:, :-1] ** 2).sum(axis=1) / (p.shape[1] - 1)))


def accuracy(probs, outcomes) -> float:
    p, o = _check(probs, outcomes)
    return float(np.mean(np.argmax(p, axis=1) == o))


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float | None
    observed_rate: float | None


def calibration(predicted, happened, n_bins: int = 10) -> tuple[list[CalibrationBin], float]:
    """Reliability bins for binary events and expected calibration error (ECE).

    predicted: probabilities for an event; happened: 0/1 whether it occurred.
    Empty bins are reported with count 0 and None rates, never dropped.
    """
    p = np.asarray(predicted, dtype=float)
    y = np.asarray(happened, dtype=float)
    if len(p) != len(y) or len(p) == 0:
        raise ValueError("predicted and happened must be non-empty and the same length")
    edges = np.linspace(0, 1, n_bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    bins, ece = [], 0.0
    for b in range(n_bins):
        mask = which == b
        c = int(mask.sum())
        if c:
            mp, obs = float(p[mask].mean()), float(y[mask].mean())
            ece += c / len(p) * abs(mp - obs)
            bins.append(CalibrationBin(edges[b], edges[b + 1], c, mp, obs))
        else:
            bins.append(CalibrationBin(edges[b], edges[b + 1], 0, None, None))
    return bins, float(ece)
