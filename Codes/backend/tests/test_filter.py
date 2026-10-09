"""Calibration (CEM) + particle filter on a synthetic patient with known parameters."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nemotwins.twin import filter as PF
from nemotwins.twin import model as M
from nemotwins.twin.calibrate import cem_fit
from nemotwins.twin.runner import build_timeline

TRUE = np.array([3.0e-4, 0.012, 0.030, 0.025, 140.0, 1.0e-4, 0.10])  # SI SG GAM KABS GB KEX CAMP
DAYS = 3
MEALS = ((8.0, 50.0), (13.0, 75.0), (20.0, 60.0))  # (clock hour, carbs g)
CGM_SD = 5.0


def _synthetic_patient(seed: int = 3) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = DAYS * 288
    t = pd.date_range("2026-01-05 00:00", periods=n, freq="5min")
    hour = (t.hour + t.minute / 60.0).to_numpy(float)
    carbs = np.zeros(n)
    for h, c in MEALS:
        carbs[np.isclose(hour, h)] = c
    mets = np.full(n, M.REST_METS)
    walk = (hour >= 18.0) & (hour < 18.5)
    mets[walk] = 3.5
    th = TRUE[None, :]
    x = M.steady_state(th)
    truth = np.empty(n)
    for i in range(n):
        if i > 0:
            u = M.StepInputs(carbs[i - 1], 1.2 if carbs[: i].any() else 1.0, mets[i - 1], hour[i - 1])
            x = M.rk4_step(x, th, u)
            x[:, 6] += rng.normal(0.0, 0.02)  # small unexplained drift
        truth[i] = x[0, 0]
    cgm = truth + rng.normal(0.0, CGM_SD, n)
    df = pd.DataFrame({
        "pid": "synthetic", "t": t, "cgm": cgm, "cgm_native": True, "cbg": np.nan, "carbs": carbs,
        "protein": np.where(carbs > 0, 12.0, 0.0), "fat": np.where(carbs > 0, 8.0, 0.0),
        "fibre": np.where(carbs > 0, 3.0, 0.0), "mets": mets,
    })
    return df, truth


@pytest.fixture(scope="module")
def patient():
    df, truth = _synthetic_patient()
    return build_timeline(df), truth


@pytest.fixture(scope="module")
def calibrated(patient):
    tl, _ = patient
    end = len(tl.t)
    cm, cs = cem_fit(tl, end, np.log(M.GENERIC_PRIOR_MEDIAN), M.GENERIC_PRIOR_LOGSD, seed=1)
    return cm, cs


def _run_filter(tl, cm, cs, obs_mask: np.ndarray, kind: str = "cgm", seed: int = 2):
    pf = PF.ParticleFilter(1000, np.exp(cm), cs, seed=seed, g0=float(tl.cgm[0]))
    rec = np.zeros((len(tl.t), 4))
    for i in range(len(tl.t)):
        if i > 0:
            pf.predict(M.StepInputs(tl.carbs[i - 1], tl.slow[i - 1], tl.mets[i - 1], tl.hour[i - 1]),
                       observed_next=bool(obs_mask[i]))
        if obs_mask[i]:
            pf.update(float(tl.cgm[i]), kind if i >= 288 * 2 else "cgm")
        rec[i] = pf.glucose_summary()
    return pf, rec


def test_cem_recovers_basal_glucose(calibrated) -> None:
    cm, _ = calibrated
    gb = float(np.exp(cm[M.PARAM_NAMES.index("GB")]))
    assert gb == pytest.approx(TRUE[4], rel=0.10), gb


def test_filter_recovers_gb_and_reconstructs(patient, calibrated) -> None:
    tl, truth = patient
    cm, cs = calibrated
    pf, rec = _run_filter(tl, cm, cs, np.ones(len(tl.t), bool))
    th = pf.theta
    w = pf.weights
    gb_post = float(np.sum(w * th[:, M.PARAM_NAMES.index("GB")]))
    assert gb_post == pytest.approx(TRUE[4], rel=0.10), gb_post
    rmse = float(np.sqrt(np.mean((rec[:, 0] - truth) ** 2)))
    assert rmse < 15.0, rmse
    # the 90% band should contain the truth most of the time
    cover = float(np.mean((truth >= rec[:, 2]) & (truth <= rec[:, 3])))
    assert cover > 0.6, cover


def test_band_widens_with_time_since_observation(patient, calibrated) -> None:
    """Sparse mode: dense CGM for 2 days, then 2 finger-pricks on day 3 (07:00, 22:00)."""
    tl, _ = patient
    cm, cs = calibrated
    n = len(tl.t)
    obs = np.zeros(n, bool)
    obs[: 288 * 2] = True
    day3 = np.arange(288 * 2, n)
    for h in (7.0, 22.0):
        obs[day3[np.isclose(tl.hour[day3], h)]] = True
    _, rec = _run_filter(tl, cm, cs, obs, kind="prick")
    width = rec[:, 3] - rec[:, 2]
    i7 = int(day3[np.isclose(tl.hour[day3], 7.0)][0])
    # a reading narrows the band ...
    assert width[i7] < 0.7 * width[i7 - 1], (width[i7 - 1], width[i7])
    # ... which then widens again as hours pass without one
    later = width[i7 + 4 * 12: i7 + 8 * 12].mean()  # 4-8 h after the reading
    assert later > 1.3 * width[i7], (width[i7], later)
    last = np.maximum.accumulate(np.where(obs, np.arange(n), 0))
    hs = (np.arange(n) - last)[day3] * M.DT / 60.0
    rho = pd.Series(hs).corr(pd.Series(width[day3]), method="spearman")
    assert rho > 0.3, rho
    # dense CGM keeps the band much tighter than sparse pricks
    assert width[288: 288 * 2].mean() < 0.6 * width[day3].mean()
