"""Mechanistic glucose-insulin layer (spec section 4.1).

A compact minimal-model-style ODE, vectorised over particles (every array has
shape ``(N,)``) and integrated with fixed-step RK4 at 5-minute resolution.

States (index into ``x[:, k]``)::

    0 G   plasma glucose                        mg/dL
    1 X   remote insulin action                 1/min
    2 I   endogenous insulin above basal        uU/mL
    3 Q1  gut compartment 1                     g carbohydrate
    4 Q2  gut compartment 2                     g carbohydrate
    5 E   exercise-induced extra uptake         1/min
    6 D   slow unexplained drift (disturbance)  mg/dL/min

Personal parameters (log-space in the particle filter)::

    SI    insulin sensitivity            (1/min per uU/mL)
    SG    glucose effectiveness          1/min
    GAM   secretion gain                 uU/mL/min per mg/dL above basal
    KABS  gut absorption rate            1/min
    GB    basal glucose                  mg/dL
    KEX   exercise gain                  1/min per MET above rest, per min
    CAMP  circadian amplitude on SI      unitless, 0..0.6 (dawn effect)

T2D patients mostly still secrete insulin, so insulin comes from the secretion
term, not from external doses.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DT = 5.0  # minutes
STATE_NAMES = ("G", "X", "I", "Q1", "Q2", "E", "D")
N_STATE = len(STATE_NAMES)
PARAM_NAMES = ("SI", "SG", "GAM", "KABS", "GB", "KEX", "CAMP")
N_PARAM = len(PARAM_NAMES)

# Fixed physiology constants
P2 = 0.025  # 1/min, remote insulin action decay
N_CLEAR = 0.1  # 1/min, insulin clearance
VG_DL = 1.6 * 75.0  # glucose distribution volume, dL (1.6 dL/kg x 75 kg)
F_BIO = 0.9  # carbohydrate bioavailability
TAU_EX = 60.0  # min, exercise effect decay
REST_METS = 1.5
TAU_D = 180.0  # min, decay of the unexplained drift state

# Generic (population-agnostic) log-normal prior: median, log-sd
GENERIC_PRIOR_MEDIAN = np.array([4.0e-4, 0.010, 0.040, 0.030, 110.0, 1.0e-4, 0.15])
GENERIC_PRIOR_LOGSD = np.array([0.8, 0.5, 0.7, 0.45, 0.2, 0.8, 0.6])
PARAM_BOUNDS = np.array(
    [
        [2e-5, 3e-3],
        [1e-3, 0.05],
        [2e-3, 0.4],
        [0.008, 0.12],
        [60.0, 250.0],
        [5e-6, 2e-3],
        [0.0, 0.6],
    ]
)


@dataclass
class StepInputs:
    """Exogenous inputs for one 5-minute step.

    Each field is a scalar shared by all particles, or an ``(N,)`` array when many
    forecasts with different inputs are batched together.
    """

    carbs: float | np.ndarray = 0.0  # g eaten at the start of this step
    slow: float | np.ndarray = 1.0  # composition slow-down divisor (>=1) of latest meal
    mets: float | np.ndarray = REST_METS
    hour: float | np.ndarray = 12.0  # local clock hour (float)


def meal_slow_factor(fat: float, protein: float, fibre: float) -> float:
    """Fat, protein and fibre slow gastric emptying; returns a divisor for KABS."""
    return 1.0 + 0.010 * max(fat, 0) + 0.006 * max(protein, 0) + 0.025 * max(fibre, 0)


def clip_params(theta: np.ndarray) -> np.ndarray:
    return np.clip(theta, PARAM_BOUNDS[:, 0], PARAM_BOUNDS[:, 1])


def _deriv(x: np.ndarray, th: np.ndarray, u: StepInputs) -> np.ndarray:
    G, X, Ins, Q1, Q2, E, D = (x[:, k] for k in range(N_STATE))
    SI, SG, GAM, KABS, GB, KEX, CAMP = (th[:, k] for k in range(N_PARAM))
    # Dawn effect: insulin sensitivity lowest around 06:00, highest around 18:00.
    si_eff = SI * (1.0 - CAMP * np.cos(2 * np.pi * (u.hour - 6.0) / 24.0))
    kabs = KABS / u.slow
    ra = F_BIO * 1000.0 * kabs * Q2 / VG_DL  # mg/dL/min
    dG = -(SG + X + E) * G + SG * GB + ra + D
    dX = -P2 * X + P2 * si_eff * Ins
    dI = -N_CLEAR * Ins + GAM * np.maximum(G - GB, 0.0)
    dQ1 = -kabs * Q1
    dQ2 = kabs * (Q1 - Q2)
    dE = -E / TAU_EX + KEX * np.maximum(u.mets - REST_METS, 0.0)
    dD = -D / TAU_D
    return np.stack([dG, dX, dI, dQ1, dQ2, dE, dD], axis=1)


def rk4_step(x: np.ndarray, th: np.ndarray, u: StepInputs, dt: float = DT) -> np.ndarray:
    """Advance all particles by one step. Meal carbs enter Q1 as an impulse."""
    x = x.copy()
    if np.any(u.carbs):
        x[:, 3] += u.carbs
    k1 = _deriv(x, th, u)
    k2 = _deriv(x + 0.5 * dt * k1, th, u)
    k3 = _deriv(x + 0.5 * dt * k2, th, u)
    k4 = _deriv(x + dt * k3, th, u)
    out = x + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
    out[:, 0] = np.clip(out[:, 0], 30.0, 600.0)
    out[:, 1:6] = np.maximum(out[:, 1:6], 0.0)
    return out


def steady_state(th: np.ndarray, g0: np.ndarray | None = None) -> np.ndarray:
    """Fasting steady state (G = GB unless an initial glucose is given)."""
    n = th.shape[0]
    x = np.zeros((n, N_STATE))
    x[:, 0] = th[:, 4] if g0 is None else g0
    return x


def simulate(
    x0: np.ndarray, th: np.ndarray, inputs: list[StepInputs], process_sd: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Simulate trajectories; returns glucose array of shape (len(inputs), N)."""
    rng = rng or np.random.default_rng(0)
    x = x0.copy()
    out = np.empty((len(inputs), x.shape[0]))
    for i, u in enumerate(inputs):
        x = rk4_step(x, th, u)
        if process_sd > 0:
            x[:, 6] += rng.normal(0.0, process_sd, x.shape[0])
        out[i] = x[:, 0]
    return out
