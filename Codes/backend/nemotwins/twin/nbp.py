"""Next best prick - active sensing (spec section 4.4, feature M3).

For every candidate time c on a 30-minute grid in the next 24 h (sleep skipped) we
estimate the expected reduction in forecast variance over the following 12 h if a
finger-prick were taken at c.

The particle cloud is simulated forward once; reading at c with glucometer noise R
reweights the particles. Under the linear-Gaussian (ensemble Kalman) approximation
the expected posterior variance at a later time s is

    Var(G_s) - Cov(G_s, G_c)^2 / (Var(G_c) + R_c)

so the expected gain is the summed variance drop over [c, c + 12 h] divided by the
summed prior variance. This is exact for Gaussian clouds and fast enough (< 0.5 s)
to run on every request.
"""

from __future__ import annotations

import numpy as np

from nemotwins.twin import filter as PF
from nemotwins.twin import model as M

WINDOW_STEPS = int(12 * 60 / M.DT)
GRID_STEPS = int(30 / M.DT)


def gain_profile(traj: np.ndarray, cand_steps: np.ndarray, window: int = WINDOW_STEPS) -> np.ndarray:
    """traj: (m, T) glucose trajectories. Returns fractional gain per candidate step."""
    m, t_len = traj.shape
    centred = traj - traj.mean(axis=0, keepdims=True)
    var = (centred**2).mean(axis=0)
    gains = np.zeros(len(cand_steps))
    for k, c in enumerate(cand_steps):
        end = min(t_len, c + window)
        if end <= c:
            continue
        cov = (centred[:, c:end] * centred[:, c][:, None]).mean(axis=0)
        r = PF.noise_sd(traj[:, c].mean(), "prick") ** 2
        drop = cov**2 / (var[c] + r)
        gains[k] = drop.sum() / max(var[c:end].sum(), 1e-9)
    return gains


def awake(hour: np.ndarray, sleep_start: float = 23.0, sleep_end: float = 6.5) -> np.ndarray:
    if sleep_start > sleep_end:
        return ~((hour >= sleep_start) | (hour < sleep_end))
    return ~((hour >= sleep_start) & (hour < sleep_end))


def expected_inputs(
    hour0: float, steps: int, meal_profile: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Future inputs (steps,) from a habitual meal profile.

    ``meal_profile``: expected carbs per 30-min clock bin (48,), learnt from the
    patient's own logged meals; the future is otherwise assumed at rest.
    """
    hours = (hour0 + np.arange(steps) * M.DT / 60.0) % 24.0
    carbs = np.zeros(steps)
    if meal_profile is not None:
        bins = (hours * 2).astype(int) % 48
        first_in_bin = np.r_[True, bins[1:] != bins[:-1]]
        carbs = np.where(first_in_bin, meal_profile[bins], 0.0)
    return carbs, np.full(steps, 1.4), np.full(steps, M.REST_METS), hours


def recommend(
    snap: PF.Snapshot,
    hour0: float,
    meal_profile: np.ndarray | None,
    horizon_h: float = 24.0,
    sleep: tuple[float, float] = (23.0, 6.5),
    rng: np.random.Generator | None = None,
    exclude_steps: list[int] | None = None,
    min_sep_steps: int = 36,
) -> dict:
    rng = rng or np.random.default_rng(0)
    snap = inflate_for_planning(snap, rng)
    steps = int((horizon_h + 12) * 60 / M.DT)
    carbs, slow, mets, hours = expected_inputs(hour0, steps, meal_profile)
    traj = PF.forecast_batch([snap], carbs[:, None], slow[:, None], mets[:, None], hours[:, None], rng)[0]
    cand = np.arange(GRID_STEPS, int(horizon_h * 60 / M.DT), GRID_STEPS)
    cand = cand[awake(hours[cand], *sleep)]
    if exclude_steps:
        for e in exclude_steps:
            cand = cand[np.abs(cand - e) >= min_sep_steps]
    gains = gain_profile(traj, cand)
    best = int(np.argmax(gains)) if len(gains) else 0
    return {
        "cand_steps": cand,
        "gains": gains,
        "best_step": int(cand[best]) if len(cand) else None,
        "best_gain": float(gains[best]) if len(gains) else 0.0,
        "traj": traj,
    }


# Persistent model-misspecification spread (log-sd) used only for planning. The filter's
# own cloud under-represents slowly varying bias (the conformal layer has to widen it
# ~2-3x); without this the planner chases short-lived post-meal variance.
PLAN_EXTRA_LOGSD = {"GB": 0.12, "SI": 0.30}


def inflate_for_planning(snap: PF.Snapshot, rng: np.random.Generator) -> PF.Snapshot:
    lt = snap.logth.copy()
    for name, sd in PLAN_EXTRA_LOGSD.items():
        k = M.PARAM_NAMES.index(name)
        lt[:, k] += rng.normal(0.0, sd, lt.shape[0])
    x = snap.x.copy()
    x[:, 0] *= np.exp(rng.normal(0.0, 0.08, x.shape[0]))
    return PF.Snapshot(x, lt)


def condition_on(traj: np.ndarray, c: int) -> np.ndarray:
    """Expected ensemble after observing glucose at step ``c`` (EnSRF, mean unchanged).

    Anomalies shrink by the deterministic square-root Kalman update, so later picks
    are chosen knowing what earlier picks will already have taught the twin.
    """
    mean = traj.mean(axis=0, keepdims=True)
    a = traj - mean
    var_c = float((a[:, c] ** 2).mean())
    r = PF.noise_sd(float(mean[0, c]), "prick") ** 2
    gain = (a * a[:, c][:, None]).mean(axis=0) / (var_c + r)
    alpha = 1.0 / (1.0 + np.sqrt(r / (var_c + r)))
    return mean + a - alpha * gain[None, :] * a[:, c][:, None]


def plan(
    snap: PF.Snapshot,
    hour0: float,
    meal_profile: np.ndarray | None,
    k: int,
    last_hour: float = 23.0,
    window_h: float = 24.0,
    sleep: tuple[float, float] = (23.0, 6.5),
    rng: np.random.Generator | None = None,
) -> list[float]:
    """Greedy joint plan of ``k`` readings for today (clock hours), 24-h objective."""
    rng = rng or np.random.default_rng(0)
    snap = inflate_for_planning(snap, rng)
    steps = int((max(last_hour - hour0, 0.5) + window_h) * 60 / M.DT)
    carbs, slow, mets, hours = expected_inputs(hour0, steps, meal_profile)
    traj = PF.forecast_batch([snap], carbs[:, None], slow[:, None], mets[:, None], hours[:, None], rng)[0]
    cand = np.arange(GRID_STEPS // 2, int(max(last_hour - hour0, 0.5) * 60 / M.DT) + 1, GRID_STEPS // 2)
    cand = cand[awake(hours[cand], *sleep)]
    window = int(window_h * 60 / M.DT)
    chosen: list[int] = []
    for _ in range(k):
        rest = np.array([c for c in cand if all(abs(c - x) >= 12 for x in chosen)])
        if len(rest) == 0:
            break
        g = gain_profile(traj, rest, window)
        c = int(rest[int(np.argmax(g))])
        chosen.append(c)
        traj = condition_on(traj, c)
    return [float((hour0 + c * M.DT / 60.0) % 24) for c in sorted(chosen)]
