import math

import numpy as np
import pytest

from sportsmodel.metrics import accuracy, brier, calibration, log_loss, rps

UNIFORM = [[1 / 3] * 3] * 3
OUTCOMES = [0, 1, 2]


def test_uniform_forecast_values():
    assert log_loss(UNIFORM, OUTCOMES) == pytest.approx(math.log(3))
    assert brier(UNIFORM, OUTCOMES) == pytest.approx(2 / 3)


def test_perfect_forecast_scores_zero():
    perfect = np.eye(3)
    assert rps(perfect, OUTCOMES) == pytest.approx(0)
    assert brier(perfect, OUTCOMES) == pytest.approx(0)
    assert accuracy(perfect, OUTCOMES) == 1.0


def test_rps_hand_computed():
    # forecast (0.5, 0.3, 0.2), home win: ((0.5-1)^2 + (0.8-1)^2) / 2 = 0.145
    assert rps([[0.5, 0.3, 0.2]], [0]) == pytest.approx(0.145)


def test_rps_penalises_distant_misses_more():
    near = rps([[0.1, 0.8, 0.1]], [0])
    far = rps([[0.1, 0.1, 0.8]], [0])
    assert far > near


def test_rejects_forecasts_not_summing_to_one():
    with pytest.raises(ValueError):
        log_loss([[0.5, 0.5, 0.5]], [0])


def test_calibration_keeps_empty_bins_and_counts_everything():
    p = [0.05, 0.15, 0.95, 0.95]
    y = [0, 0, 1, 1]
    bins, ece = calibration(p, y, n_bins=10)
    assert len(bins) == 10
    assert sum(b.count for b in bins) == 4
    assert bins[5].count == 0 and bins[5].observed_rate is None
    assert ece == pytest.approx((0.05 + 0.15 + 0.05 * 2) / 4)
