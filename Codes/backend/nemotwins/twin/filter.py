"""Hierarchical Bayesian personalisation with a particle filter (spec section 4.2).

* Particles carry the 7 ODE states plus the 7 personal parameters (log space).
* Parameter learning uses the Liu-West kernel-shrinkage scheme at resampling.
* Observations: CGM (calibration phase) or finger-pricks (maintenance phase), with a
  Student-t likelihood (robust to CGM compression artefacts) whose scale grows with
  glucose (sensor/glucometer error is roughly proportional).
* Between observations the particles keep propagating with process noise, so the
  spread of the cloud is the "living uncertainty" shown in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nemotwins.twin import model as M

# Observation noise sd = a + b * glucose
CGM_NOISE = (4.0, 0.06)
PRICK_NOISE = (4.0, 0.07)  # ISO 15197: 95% of readings within +-15%
T_DF = 4.0

# Process noise (per 5-min step)
D_NOISE_SD = 0.12  # mg/dL/min on the drift state
G_NOISE_SD = 3.0  # mg/dL directly on glucose (model error per step)

LW_DELTA = 0.97  # Liu-West discount factor
_LW_H2 = 1.0 - ((3 * LW_DELTA - 1) / (2 * LW_DELTA)) ** 2
_LW_A = np.sqrt(1.0 - _LW_H2)


def noise_sd(g: np.ndarray | float, kind: str) -> np.ndarray | float:
    a, b = CGM_NOISE if kind == "cgm" else PRICK_NOISE
    return a + b * np.asarray(g)


# Prior spread of G before a finger-prick, by hours since the last observation. Anchored
# to the observed virtual-CGM error in sparse mode (~30 mg/dL RMSE hours after a reading).
PRICK_INFLATE_BASE = 6.0
PRICK_INFLATE_PER_H = 4.0
PRICK_INFLATE_MAX = 30.0


def prick_inflation_sd(hours_since_obs: float) -> float:
    return float(min(PRICK_INFLATE_MAX, PRICK_INFLATE_BASE + PRICK_INFLATE_PER_H * max(hours_since_obs, 0.0)))


def _student_t_logpdf(r: np.ndarray, df: float = T_DF) -> np.ndarray:
    return -0.5 * (df + 1.0) * np.log1p(r * r / df)


@dataclass
class Snapshot:
    """Equally-weighted particle subsample at a time point (for forecasting)."""

    x: np.ndarray
    logth: np.ndarray


@dataclass
class ParticleFilter:
    n: int
    prior_median: np.ndarray
    prior_logsd: np.ndarray
    seed: int = 0
    g0: float | None = None
    rng: np.random.Generator = field(init=False)
    x: np.ndarray = field(init=False)
    logth: np.ndarray = field(init=False)
    logw: np.ndarray = field(init=False)
    last_ess: float = field(init=False, default=1.0)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        z = self.rng.standard_normal((self.n, M.N_PARAM))
        self.logth = np.log(self.prior_median)[None, :] + z * self.prior_logsd[None, :]
        # CAMP lives in [0, 0.6]: sample it directly (log of a tiny value is unstable)
        self.logth = self._clip_log(self.logth)
        g0 = self.g0 if self.g0 is not None else None
        th = self.theta
        if g0 is None:
            self.x = M.steady_state(th)
        else:
            self.x = M.steady_state(th, g0 + self.rng.normal(0, 8.0, self.n))
        self.logw = np.full(self.n, -np.log(self.n))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _clip_log(logth: np.ndarray) -> np.ndarray:
        lo = np.log(np.maximum(M.PARAM_BOUNDS[:, 0], 1e-3 * M.PARAM_BOUNDS[:, 1]))
        hi = np.log(M.PARAM_BOUNDS[:, 1])
        return np.clip(logth, lo, hi)

    @property
    def theta(self) -> np.ndarray:
        return np.exp(self.logth)

    @property
    def weights(self) -> np.ndarray:
        w = np.exp(self.logw - self.logw.max())
        return w / w.sum()

    def ess_fraction(self) -> float:
        w = self.weights
        return float(1.0 / np.sum(w * w) / self.n)

    # ------------------------------------------------------------------ dynamics
    def predict(self, u: M.StepInputs, observed_next: bool = False) -> None:
        """Propagate one step.

        When an observation follows, the glucose process noise is not added here:
        ``update`` samples it from the locally optimal proposal instead, which keeps
        the cloud on the data even when the model is far off (avoids degeneracy).
        """
        self.x = M.rk4_step(self.x, self.theta, u)
        self.x[:, 6] += self.rng.normal(0.0, D_NOISE_SD, self.n)
        if not observed_next:
            self.x[:, 0] = np.clip(self.x[:, 0] + self.rng.normal(0.0, G_NOISE_SD, self.n), 30, 600)

    def update(self, y: float, kind: str, hours_since_obs: float | None = None) -> float:
        """Assimilate one observation of glucose; returns ESS fraction before resampling.

        Locally optimal proposal for the linear-Gaussian G noise: weight by the
        predictive density p(y | x_pred) and draw G ~ N(posterior mean, posterior var).

        * CGM: Student-t predictive (robust to compression lows / sensor artefacts).
        * Finger-prick: Gaussian predictive (glucometer error is well characterised), after
          adaptive inflation of the cloud. Between sparse readings the particle cloud is
          over-confident (the conformal layer has to widen it 2-3x), so before a prick the
          spread of G is inflated to the error level actually observed for that gap
          (``prick_inflation_sd``). The same perturbation is mirrored into the drift state
          D (scaled by the particle's clearance rate) so a corrected level persists instead
          of relaxing back to the model's equilibrium within the hour.
        """
        if kind == "prick" and hours_since_obs is not None:
            self._inflate(prick_inflation_sd(hours_since_obs))
        r_var = noise_sd(y, kind) ** 2
        q = G_NOISE_SD**2
        g_pred = self.x[:, 0]
        r = (y - g_pred) / np.sqrt(q + r_var)
        if kind == "cgm":
            self.logw = self.logw + _student_t_logpdf(r)
        else:
            self.logw = self.logw - 0.5 * r * r
        post_var = q * r_var / (q + r_var)
        post_mu = (g_pred * r_var + y * q) / (q + r_var)
        self.x[:, 0] = np.clip(post_mu + self.rng.normal(0, np.sqrt(post_var), self.n), 30, 600)
        self.logw -= self.logw.max()
        ess = self.ess_fraction()
        self.last_ess = ess
        if ess < 0.5:
            self.resample()
        return ess

    def _inflate(self, target_sd: float) -> None:
        w = self.weights
        g = self.x[:, 0]
        mu = float(np.sum(w * g))
        sd = float(np.sqrt(np.sum(w * (g - mu) ** 2)))
        if sd >= target_sd:
            return
        e = self.rng.normal(0.0, np.sqrt(target_sd**2 - sd**2), self.n)
        th = self.theta
        k_clear = th[:, 1] + self.x[:, 1] + self.x[:, 5]  # SG + X + E: glucose clearance rate
        self.x[:, 0] = np.clip(g + e, 30, 600)
        self.x[:, 6] += e * k_clear

    def resample(self) -> None:
        w = self.weights
        idx = _systematic(w, self.n, self.rng)
        # Liu-West kernel shrinkage on parameters
        mean = np.sum(w[:, None] * self.logth, axis=0)
        cov = np.cov(self.logth.T, aweights=w) + 1e-10 * np.eye(M.N_PARAM)
        new = _LW_A * self.logth[idx] + (1 - _LW_A) * mean
        new += self.rng.multivariate_normal(np.zeros(M.N_PARAM), _LW_H2 * cov, self.n)
        self.logth = self._clip_log(new)
        self.x = self.x[idx].copy()
        self.logw = np.full(self.n, -np.log(self.n))

    # ------------------------------------------------------------------ summaries
    def glucose_summary(self) -> tuple[float, float, float, float]:
        """Weighted mean, sd, 5% and 95% quantiles of current glucose."""
        w = self.weights
        g = self.x[:, 0]
        mu = float(np.sum(w * g))
        sd = float(np.sqrt(np.sum(w * (g - mu) ** 2)))
        order = np.argsort(g)
        cw = np.cumsum(w[order])
        q05 = float(g[order][np.searchsorted(cw, 0.05)])
        q95 = float(g[order][min(np.searchsorted(cw, 0.95), self.n - 1)])
        return mu, sd, q05, q95

    def param_posterior(self) -> tuple[np.ndarray, np.ndarray]:
        w = self.weights
        mu = np.sum(w[:, None] * self.logth, axis=0)
        sd = np.sqrt(np.sum(w[:, None] * (self.logth - mu) ** 2, axis=0))
        return mu, sd

    def snapshot(self, m: int) -> Snapshot:
        idx = _systematic(self.weights, m, self.rng)
        return Snapshot(self.x[idx].copy(), self.logth[idx].copy())

    def copy_state(self) -> dict:
        return {"x": self.x.copy(), "logth": self.logth.copy(), "logw": self.logw.copy()}

    def restore(self, st: dict) -> None:
        self.x, self.logth, self.logw = st["x"].copy(), st["logth"].copy(), st["logw"].copy()


def _systematic(w: np.ndarray, m: int, rng: np.random.Generator) -> np.ndarray:
    positions = (rng.random() + np.arange(m)) / m
    cw = np.cumsum(w)
    cw[-1] = 1.0
    return np.searchsorted(cw, positions)


def forecast_batch(
    snaps: list[Snapshot],
    carbs: np.ndarray,
    slow: np.ndarray,
    mets: np.ndarray,
    hour: np.ndarray,
    rng: np.random.Generator,
    process_noise: bool = True,
) -> np.ndarray:
    """Propagate many snapshots at once.

    ``carbs/slow/mets/hour`` have shape ``(H, n_snap)``: per-step inputs for each
    snapshot. Returns glucose trajectories of shape ``(n_snap, m, H)``.
    """
    n_snap = len(snaps)
    m = snaps[0].x.shape[0]
    x = np.concatenate([s.x for s in snaps], axis=0)
    th = np.exp(np.concatenate([s.logth for s in snaps], axis=0))
    h = carbs.shape[0]
    out = np.empty((h, n_snap * m))
    rep = lambda a: np.repeat(a, m)  # noqa: E731
    for k in range(h):
        u = M.StepInputs(carbs=rep(carbs[k]), slow=rep(slow[k]), mets=rep(mets[k]), hour=rep(hour[k]))
        x = M.rk4_step(x, th, u)
        if process_noise:
            x[:, 6] += rng.normal(0.0, D_NOISE_SD, x.shape[0])
            x[:, 0] = np.clip(x[:, 0] + rng.normal(0.0, G_NOISE_SD, x.shape[0]), 30, 600)
        out[k] = x[:, 0]
    return out.T.reshape(n_snap, m, h)
