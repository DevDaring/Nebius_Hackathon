"""Mechanistic ODE layer (twin/model.py): steady state, gut mass balance, meal recovery."""

from __future__ import annotations

import numpy as np
import pytest

from nemotwins.twin import model as M

TH = M.GENERIC_PRIOR_MEDIAN[None, :].copy()


def _run(th: np.ndarray, x0: np.ndarray, inputs: list[M.StepInputs]) -> np.ndarray:
    """All states after each step: (len(inputs), n, N_STATE)."""
    x = x0.copy()
    out = []
    for u in inputs:
        x = M.rk4_step(x, th, u)
        out.append(x.copy())
    return np.array(out)


@pytest.mark.parametrize("gb", [90.0, 110.0, 160.0])
def test_steady_state_stays_at_basal(gb: float) -> None:
    th = TH.copy()
    th[0, 4] = gb
    x0 = M.steady_state(th)
    xs = _run(th, x0, [M.StepInputs(0.0, 1.0, M.REST_METS, (6 + k * M.DT / 60) % 24) for k in range(288 * 2)])
    g = xs[:, 0, 0]
    assert np.max(np.abs(g - gb)) < 1e-6
    # no insulin action, no gut content, no exercise, no drift
    assert np.allclose(xs[:, 0, 1:], 0.0)


@pytest.mark.parametrize("carbs,slow", [(30.0, 1.0), (75.0, 1.0), (75.0, 1.6), (120.0, 1.2)])
def test_gut_mass_balance(carbs: float, slow: float) -> None:
    """Integrated rate of appearance equals F_BIO x carbs (within 2%)."""
    th = TH.copy()
    x0 = M.steady_state(th)
    steps = 288  # 24 h, gut is empty long before
    inputs = [M.StepInputs(carbs if k == 0 else 0.0, slow, M.REST_METS, 12.0) for k in range(steps)]
    xs = _run(th, x0, inputs)
    kabs = th[0, 3] / slow
    q2 = np.concatenate([[0.0], xs[:, 0, 4]])  # Q2 at step boundaries (0 before the meal)
    ra = M.F_BIO * 1000.0 * kabs * q2 / M.VG_DL  # mg/dL/min
    appeared_g = np.trapezoid(ra, dx=M.DT) * M.VG_DL / 1000.0
    assert appeared_g == pytest.approx(M.F_BIO * carbs, rel=0.02)
    assert xs[-1, 0, 3] + xs[-1, 0, 4] < 1e-3 * carbs  # gut emptied


def test_glucose_returns_near_basal_after_meal() -> None:
    th = TH.copy()
    gb = float(th[0, 4])
    x0 = M.steady_state(th)
    inputs = [M.StepInputs(60.0 if k == 0 else 0.0, 1.2, M.REST_METS, (13 + k * M.DT / 60) % 24) for k in range(96)]
    g = _run(th, x0, inputs)[:, 0, 0]
    assert g.max() > gb + 20  # a real excursion
    assert int(np.argmax(g)) * M.DT <= 150  # peaks within 2.5 h
    assert abs(g[-1] - gb) < 10  # back near basal after 8 h


def test_exercise_lowers_glucose() -> None:
    th = TH.copy()
    x0 = M.steady_state(th)
    rest = [M.StepInputs(50.0 if k == 0 else 0.0, 1.0, M.REST_METS, 13.0) for k in range(36)]
    walk = [M.StepInputs(50.0 if k == 0 else 0.0, 1.0, 3.5 if 3 <= k < 9 else M.REST_METS, 13.0) for k in range(36)]
    assert _run(th, x0, walk)[:, 0, 0].max() < _run(th, x0, rest)[:, 0, 0].max()
