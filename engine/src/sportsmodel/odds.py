"""Bookmaker odds maths (decimal odds). Used to benchmark the model and, later,
for the optional odds module. Statistical probability is not betting value:
a positive expected value is an estimate under the model, not a promise.
"""

from __future__ import annotations

from collections.abc import Sequence


def _validate(odds: Sequence[float]) -> None:
    if len(odds) < 2 or any(o <= 1.0 for o in odds):
        raise ValueError("need at least two decimal odds, each > 1.0")


def implied_probabilities(odds: Sequence[float]) -> list[float]:
    """Raw 1/odds; these sum to more than 1 because of the bookmaker margin."""
    _validate(odds)
    return [1.0 / o for o in odds]


def overround(odds: Sequence[float]) -> float:
    """Sum of implied probabilities minus 1 (e.g. 0.05 = 5 %)."""
    return sum(implied_probabilities(odds)) - 1.0


def margin(odds: Sequence[float]) -> float:
    """Bookmaker margin as share of stakes kept on a balanced book: 1 - 1/sum(1/odds)."""
    return 1.0 - 1.0 / sum(implied_probabilities(odds))


def fair_probabilities(odds: Sequence[float]) -> list[float]:
    """Remove the margin proportionally so probabilities sum to 1.

    Proportional normalisation is the simplest method; it slightly overstates
    longshots. Alternatives (power, Shin) can be compared in Phase 4.
    """
    imp = implied_probabilities(odds)
    s = sum(imp)
    return [p / s for p in imp]


def expected_value(model_probability: float, decimal_odds: float) -> float:
    """Expected profit per 1 unit staked if the model probability were correct."""
    if not 0.0 <= model_probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    if decimal_odds <= 1.0:
        raise ValueError("decimal odds must be > 1.0")
    return model_probability * decimal_odds - 1.0
