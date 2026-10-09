"""Calibration-phase posterior approximation (spec section 4.2).

The particle filter alone learns parameters slowly because, with dense CGM, the
glucose state is re-anchored every few minutes and the parameters barely affect the
one-step likelihood. Here we approximate the personal posterior with the
cross-entropy method (CEM) on a multiple-shooting objective:

* simulate the calibration window with K candidate parameter vectors at once;
* every ``reset_min`` minutes the glucose state is reset to the observed CGM, so each
  error term is a 0..reset_min-ahead prediction error - exactly the regime of the
  sparse maintenance phase;
* add a Gaussian prior penalty in log space (population / EHR-conditioned prior).

The elite distribution (mean, sd in log space) seeds the particle cloud, which the
filter then keeps updating (Liu-West) through calibration and maintenance.
"""

from __future__ import annotations

import numpy as np

from nemotwins.twin import model as M
from nemotwins.twin.runner import Timeline


def multiple_shooting_loss(
    logth: np.ndarray, tl: Timeline, end_idx: int, reset_steps: int, obs_every: int = 3
) -> np.ndarray:
    k = logth.shape[0]
    th = np.exp(logth)
    y = np.where(tl.cgm_native[:end_idx], tl.cgm[:end_idx], np.nan)
    first = int(np.argmax(np.isfinite(y)))
    x = M.steady_state(th, np.full(k, y[first]))
    sse = np.zeros(k)
    cnt = 0
    for i in range(first, end_idx):
        if i > first:
            u = M.StepInputs(tl.carbs[i - 1], tl.slow[i - 1], tl.mets[i - 1], tl.hour[i - 1])
            x = M.rk4_step(x, th, u)
        yi = y[i]
        if not np.isfinite(yi):
            continue
        if (i - first) % obs_every == 0:
            r = (x[:, 0] - yi) / (4.0 + 0.06 * yi)
            # Huber, robust to CGM artefacts
            a = np.abs(r)
            sse += np.where(a < 2.0, 0.5 * r * r, 2.0 * a - 2.0)
            cnt += 1
        if (i - first) % reset_steps == 0:
            x[:, 0] = yi
    return sse / max(cnt, 1)


def cem_fit(
    tl: Timeline,
    end_idx: int,
    prior_mu: np.ndarray,
    prior_sd: np.ndarray,
    reset_min: int = 120,
    k: int = 192,
    iters: int = 10,
    elite_frac: float = 0.12,
    prior_weight: float = 1.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, sd) of the approximate posterior over log-parameters."""
    rng = np.random.default_rng(seed)
    reset_steps = max(1, int(reset_min // M.DT))
    m = prior_mu.copy()
    s = prior_sd.copy()
    n_obs_scale = max(1.0, np.isfinite(tl.cgm[:end_idx]).sum() / 3.0)
    lo = np.log(np.maximum(M.PARAM_BOUNDS[:, 0], 1e-3 * M.PARAM_BOUNDS[:, 1]))
    hi = np.log(M.PARAM_BOUNDS[:, 1])
    n_elite = max(4, int(k * elite_frac))
    best = None
    for _ in range(iters):
        cand = np.clip(m + rng.standard_normal((k, M.N_PARAM)) * s, lo, hi)
        if best is not None:
            cand[0] = best
        loss = multiple_shooting_loss(cand, tl, end_idx, reset_steps)
        # negative log posterior per observation
        pen = 0.5 * np.sum(((cand - prior_mu) / prior_sd) ** 2, axis=1) * prior_weight / n_obs_scale
        obj = loss + pen
        elite = cand[np.argsort(obj)[:n_elite]]
        best = elite[0]
        m = 0.3 * m + 0.7 * elite.mean(axis=0)
        s = 0.3 * s + 0.7 * np.maximum(elite.std(axis=0), 0.03)
    return m, np.maximum(s, 0.05)
