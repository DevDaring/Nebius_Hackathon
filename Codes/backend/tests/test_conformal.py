"""Normalised split-conformal helper (twin/hybrid.py) on synthetic heteroscedastic data."""

from __future__ import annotations

import numpy as np
import pytest

from nemotwins.twin import hybrid as HY


def _data(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Truth y, point prediction yhat, and the model's (imperfect) spread estimate sd_hat."""
    x = rng.uniform(0, 1, n)
    sd_true = 4.0 + 40.0 * x**2  # strongly heteroscedastic
    yhat = 120 + 60 * x
    y = yhat + rng.standard_t(5, n) * sd_true  # heavy-ish tails
    sd_hat = sd_true * np.exp(rng.normal(0, 0.25, n))  # the particle spread is only roughly right
    return y, yhat, sd_hat


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_normalised_conformal_coverage(seed: int) -> None:
    rng = np.random.default_rng(seed)
    y, yhat, sd = _data(3000, rng)
    scores = np.abs(y - yhat) / (sd + HY.SD_FLOOR)
    q = HY._conformal_q(scores, alpha=HY.ALPHA)
    yt, yhat_t, sd_t = _data(20000, rng)
    half = q * (sd_t + HY.SD_FLOOR)
    covered = np.abs(yt - yhat_t) <= half
    cov = float(covered.mean())
    assert 0.85 <= cov <= 0.95, cov
    # normalisation keeps coverage roughly even across the spread range (not just on average)
    lo_sd, hi_sd = sd_t < np.quantile(sd_t, 0.33), sd_t > np.quantile(sd_t, 0.67)
    assert 0.80 <= covered[lo_sd].mean() <= 0.98
    assert 0.80 <= covered[hi_sd].mean() <= 0.98
    # and the bands adapt: wider where the data are noisier
    assert half[hi_sd].mean() > 3 * half[lo_sd].mean()


def test_conformal_quantile_finite_sample() -> None:
    """ceil((n+1)(1-alpha))/n quantile; empty input falls back to a Gaussian 90% z."""
    s = np.arange(1, 101, dtype=float)
    assert HY._conformal_q(s, 0.10) == pytest.approx(np.quantile(s, 91 / 100))
    assert HY._conformal_q(np.array([]), 0.10) == pytest.approx(1.645)


def test_hs_bins() -> None:
    import pandas as pd

    b = HY.hs_bin(np.array([0.5, 2.0, 6.0, 30.0, 3.0]), pd.Series(["2", "2", "2", "1", "full"]))
    assert b.tolist() == [0, 1, 2, 3, -1]
