"""Replay a patient's record through the twin at a given sensor-ladder level.

This is the shared engine behind every experiment and the demo-replay API:

1. Calibration phase: the first ``calib_days`` of CGM are assimilated.
2. Maintenance phase: CGM is hidden; only the ladder's finger-pricks are seen.
3. Forecasts are issued at origins (every 30 min + every meal start) in the
   maintenance phase, batched for speed, and scored against the hidden CGM.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nemotwins.twin import filter as PF
from nemotwins.twin import model as M

HORIZONS = (30, 60, 90, 120)
H_STEPS = 24  # 2 h event window at 5 min
FC_STEPS = 24
LADDER_LEVELS = ("full", "4", "2", "1", "0")
# Realistic self-monitoring times (local clock, hours)
LADDER_TIMES = {
    "4": (7.0, 11.0, 16.0, 22.0),  # fasting, post-breakfast, afternoon, post-dinner
    "2": (7.0, 22.0),  # fasting, post-dinner
    "1": (7.0,),  # fasting
    "0": (),
}
PRICK_REL_SD = 0.05  # simulated glucometer error (ISO-grade meter, MARD ~5%)
REST = M.REST_METS


@dataclass
class Timeline:
    pid: str
    t: np.ndarray  # datetime64[ns]
    hour: np.ndarray
    carbs: np.ndarray
    slow: np.ndarray
    mets: np.ndarray
    cgm: np.ndarray  # reference CGM (NaN where missing)
    cgm_native: np.ndarray
    cbg: np.ndarray  # real finger-pricks (Shanghai)
    meal_start: np.ndarray  # bool


def build_timeline(df: pd.DataFrame) -> Timeline:
    df = df.sort_values("t").reset_index(drop=True)
    t = df["t"].to_numpy("datetime64[ns]")
    ts = pd.to_datetime(df["t"])
    hour = (ts.dt.hour + ts.dt.minute / 60.0).to_numpy(float)
    carbs = df["carbs"].fillna(0).to_numpy(float)
    meal_start = carbs > 0.5
    slow = np.ones(len(df))
    cur = 1.0
    fat, prot, fib = (df[c].fillna(0).to_numpy(float) for c in ("fat", "protein", "fibre"))
    for i in range(len(df)):
        if meal_start[i]:
            cur = M.meal_slow_factor(fat[i], prot[i], fib[i])
        slow[i] = cur
    mets = df["mets"].fillna(REST).clip(lower=1.0).to_numpy(float)
    cgm = df["cgm"].to_numpy(float)
    native = df["cgm_native"].fillna(False).to_numpy(bool)
    cbg = df["cbg"].to_numpy(float) if "cbg" in df else np.full(len(df), np.nan)
    return Timeline(df["pid"].iat[0], t, hour, carbs, slow, mets, cgm, native, cbg, meal_start)


def observation_schedule(
    tl: Timeline, ladder: str, calib_end_idx: int, seed: int = 0,
    prick_times: dict[int, list[float]] | None = None, use_real_cbg: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (values, kind) per step; NaN means no observation.

    ``kind``: 0 none, 1 CGM, 2 finger-prick.
    ``prick_times`` optionally overrides ladder times per day index (Exp. 4).
    ``use_real_cbg`` uses the dataset's real capillary readings in maintenance (Shanghai).
    """
    rng = np.random.default_rng(seed)
    n = len(tl.t)
    vals = np.full(n, np.nan)
    kind = np.zeros(n, dtype=np.int8)
    calib = np.arange(n) < calib_end_idx
    cg_ok = tl.cgm_native & np.isfinite(tl.cgm)
    vals[calib & cg_ok] = tl.cgm[calib & cg_ok]
    kind[calib & cg_ok] = 1
    if ladder == "full":
        m = ~calib & cg_ok
        vals[m] = tl.cgm[m]
        kind[m] = 1
        return vals, kind
    if use_real_cbg:
        m = ~calib & np.isfinite(tl.cbg)
        vals[m] = tl.cbg[m]
        kind[m] = 2
        return vals, kind
    day = ((tl.t - tl.t[0].astype("datetime64[D]")) // np.timedelta64(1, "D")).astype(int)
    for d in np.unique(day[~calib]):
        times = prick_times.get(int(d), []) if prick_times is not None else LADDER_TIMES[ladder]
        idx_day = np.where((day == d) & ~calib)[0]
        for hh in times:
            # nearest step with a real CGM sample (the hidden truth we perturb)
            cand = idx_day[cg_ok[idx_day]]
            if len(cand) == 0:
                continue
            j = cand[np.argmin(np.abs(tl.hour[cand] - hh))]
            if abs(tl.hour[j] - hh) > 0.5:
                continue
            vals[j] = tl.cgm[j] * (1 + rng.normal(0, PRICK_REL_SD))
            kind[j] = 2
    return vals, kind


def habitual_meal_profile(tl: Timeline, end_idx: int) -> np.ndarray:
    """Average carbs eaten per 30-min clock bin over the calibration days."""
    days = max(1.0, (tl.t[end_idx - 1] - tl.t[0]) / np.timedelta64(1, "D")) if end_idx > 0 else 1.0
    bins = (tl.hour[:end_idx] * 2).astype(int) % 48
    prof = np.bincount(bins, weights=tl.carbs[:end_idx], minlength=48) / days
    return prof


def _future_inputs(tl: Timeline, idxs: np.ndarray, steps: int, known_future_meals: bool):
    """Inputs (H, n) for forecasts from origins ``idxs``.

    Meals at the origin step are known (the user just logged/photographed them); later
    meals are unknown unless ``known_future_meals``. Future activity assumed at rest.
    """
    n = len(tl.t)
    k = np.arange(steps)[:, None] + idxs[None, :]
    kc = np.minimum(k, n - 1)
    carbs = np.where(k == idxs[None, :], tl.carbs[kc], tl.carbs[kc] if known_future_meals else 0.0)
    carbs = np.where(k < n, carbs, 0.0)
    slow = tl.slow[kc]
    mets = np.full(k.shape, REST)
    hour = (tl.hour[idxs][None, :] + np.arange(steps)[:, None] * M.DT / 60.0) % 24.0
    return carbs, slow, mets, hour


@dataclass
class RunResult:
    recon: pd.DataFrame  # per-step reconstruction (maintenance + calibration)
    origins: pd.DataFrame  # per-origin features + forecast summaries + truth
    pmax: np.ndarray  # (n_origin, m) particle max over 2 h
    pmin: np.ndarray  # (n_origin, m) particle min over 2 h
    post_mu: np.ndarray
    post_sd: np.ndarray


def run_patient(
    df: pd.DataFrame,
    prior_median: np.ndarray,
    prior_logsd: np.ndarray,
    ladder: str = "2",
    calib_days: float = 5.0,
    n_particles: int = 800,
    m_forecast: int = 150,
    seed: int = 0,
    origin_every_min: int = 30,
    prick_times: dict[int, list[float]] | None = None,
    use_real_cbg: bool = False,
    calib_thin: int = 3,
    use_cem: bool = True,
    covariates: dict | None = None,
    eval_from_days: float | None = None,
    prick_policy: Callable | None = None,
) -> RunResult:
    """Replay one patient. ``prick_policy(pf, ctx, i) -> list[clock hours]`` is called at
    06:00 on each maintenance day to choose that day's finger-prick times (Exp. 4)."""
    tl = build_timeline(df)
    n = len(tl.t)
    t0 = tl.t[0]
    elapsed_days = (tl.t - t0) / np.timedelta64(1, "D")
    calib_end = int(np.searchsorted(elapsed_days, calib_days))
    eval_start = calib_end if eval_from_days is None else int(np.searchsorted(elapsed_days, eval_from_days))
    base_times = {} if prick_policy is not None else prick_times
    vals, kind = observation_schedule(tl, ladder, calib_end, seed, base_times, use_real_cbg)
    if calib_thin > 1:
        # Thin calibration CGM: multi-step prediction error between samples is what
        # identifies the personal parameters (and avoids over-trusting autocorrelated
        # sensor error).
        drop = (np.arange(n) < calib_end) & (np.arange(n) % calib_thin != 0) & (kind == 1)
        vals[drop] = np.nan
        kind[drop] = 0

    cal_true = tl.cgm[:calib_end][tl.cgm_native[:calib_end]]
    calib_mean = float(np.nanmean(cal_true)) if len(cal_true) else np.nan
    calib_sd = float(np.nanstd(cal_true)) if len(cal_true) else np.nan
    meal_profile = habitual_meal_profile(tl, calib_end)
    day_idx = ((tl.t - tl.t[0].astype("datetime64[D]")) // np.timedelta64(1, "D")).astype(int)
    policy_days: set[int] = set()
    cg_ok = tl.cgm_native & np.isfinite(tl.cgm)
    prick_rng = np.random.default_rng(seed + 7)

    first = np.where(np.isfinite(tl.cgm))[0]
    g0 = float(tl.cgm[first[0]]) if len(first) else None
    init_median, init_logsd = prior_median, prior_logsd
    if use_cem and calib_end > 288 // 2:
        from nemotwins.twin.calibrate import cem_fit

        cm, cs = cem_fit(tl, calib_end, np.log(prior_median), prior_logsd, seed=seed)
        init_median, init_logsd = np.exp(cm), cs
    pf = PF.ParticleFilter(n_particles, init_median, init_logsd, seed=seed, g0=g0)
    rng = np.random.default_rng(seed + 1)

    step_min = int(M.DT)
    is_origin = np.zeros(n, bool)
    grid = (np.arange(n) * step_min) % origin_every_min == 0
    is_origin[eval_start:] = grid[eval_start:] | tl.meal_start[eval_start:]
    is_origin[n - FC_STEPS:] = False

    rec = np.zeros((n, 4))
    ess = np.ones(n)
    last_obs_idx = -1
    last_obs_val = np.nan
    hs_since = np.full(n, np.nan)
    last_val_arr = np.full(n, np.nan)
    snaps: list[PF.Snapshot] = []
    o_idx: list[int] = []
    for i in range(n):
        if (
            prick_policy is not None and i >= calib_end and tl.hour[i] >= 6.0
            and day_idx[i] not in policy_days
        ):
            policy_days.add(int(day_idx[i]))
            ctx = {"tl": tl, "meal_profile": meal_profile, "rng": prick_rng}
            # Same reading budget as the fixed 2-a-day schedule on this day (fair comparison)
            n_allowed = sum(hh > tl.hour[i] - 0.5 for hh in LADDER_TIMES["2"])
            for hh in prick_policy(pf, ctx, i)[:n_allowed]:
                cand = np.where((day_idx == day_idx[i]) & cg_ok & (np.arange(n) > i))[0]
                if len(cand) == 0:
                    continue
                j = cand[np.argmin(np.abs(tl.hour[cand] - hh))]
                if abs(tl.hour[j] - hh) <= 0.5:
                    vals[j] = tl.cgm[j] * (1 + prick_rng.normal(0, PRICK_REL_SD))
                    kind[j] = 2
        if i > 0:
            pf.predict(
                M.StepInputs(tl.carbs[i - 1], tl.slow[i - 1], tl.mets[i - 1], tl.hour[i - 1]),
                observed_next=bool(kind[i]),
            )
        if kind[i]:
            hs_prev = (i - last_obs_idx) * step_min / 60.0 if last_obs_idx >= 0 else 24.0
            ess[i] = pf.update(vals[i], "cgm" if kind[i] == 1 else "prick", hours_since_obs=hs_prev)
            last_obs_idx, last_obs_val = i, vals[i]
        else:
            ess[i] = pf.ess_fraction()
        rec[i] = pf.glucose_summary()
        hs_since[i] = (i - last_obs_idx) * step_min / 60.0 if last_obs_idx >= 0 else 99.0
        last_val_arr[i] = last_obs_val
        if is_origin[i]:
            snaps.append(pf.snapshot(m_forecast))
            o_idx.append(i)
    post_mu, post_sd = pf.param_posterior()

    recon = pd.DataFrame(
        {
            "t": tl.t, "mu": rec[:, 0], "sd": rec[:, 1], "q05": rec[:, 2], "q95": rec[:, 3],
            "true": np.where(tl.cgm_native, tl.cgm, np.nan), "obs": vals, "obs_kind": kind,
            "phase": np.where(np.arange(n) < calib_end, "calib", "maint"),
            "hours_since_obs": hs_since, "ess": ess,
        }
    )

    oi = np.array(o_idx, dtype=int)
    rows: dict[str, list | np.ndarray] = {}
    pmax_all, pmin_all = [], []
    if len(oi):
        meds, sds, q05s, q95s, peak = [], [], [], [], []
        for c0 in range(0, len(oi), 120):
            sl = oi[c0:c0 + 120]
            carbs, slow, mets, hour = _future_inputs(tl, sl, FC_STEPS, known_future_meals=False)
            traj = PF.forecast_batch(snaps[c0:c0 + 120], carbs, slow, mets, hour, rng)  # (s, m, H)
            hidx = [h // step_min - 1 for h in HORIZONS]
            meds.append(np.median(traj[:, :, hidx], axis=1))
            sds.append(traj[:, :, hidx].std(axis=1))
            q05s.append(np.quantile(traj[:, :, hidx], 0.05, axis=1))
            q95s.append(np.quantile(traj[:, :, hidx], 0.95, axis=1))
            peak.append(np.median(traj.max(axis=2), axis=1))
            pmax_all.append(traj[:, :, :H_STEPS].max(axis=2).astype(np.float16))
            pmin_all.append(traj[:, :, :H_STEPS].min(axis=2).astype(np.float16))
        med = np.concatenate(meds)
        sd = np.concatenate(sds)
        q05 = np.concatenate(q05s)
        q95 = np.concatenate(q95s)
        # truth
        truths = []
        for h in HORIZONS:
            j = oi + h // step_min
            truths.append(np.where(tl.cgm_native[j], tl.cgm[j], np.nan))
        win = oi[:, None] + np.arange(1, H_STEPS + 1)[None, :]
        # Event windows use the reference CGM incl. short linear gaps (<= 30 min) so
        # 15-min sensors (ShanghaiT2DM) are not rejected by the coverage rule.
        wv = tl.cgm[win]
        cover = np.isfinite(wv).mean(axis=1)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ev_high = np.where(cover >= 0.6, np.nanmax(wv, axis=1) > 180, np.nan)
            ev_low = np.where(cover >= 0.6, np.nanmin(wv, axis=1) < 70, np.nan)

        def back(k: int, arr: np.ndarray) -> np.ndarray:
            return arr[np.maximum(oi - k, 0)]

        carbs_cum = np.cumsum(tl.carbs)
        def carbs_window(steps: int) -> np.ndarray:
            return carbs_cum[oi] - carbs_cum[np.maximum(oi - steps, 0)]

        mets_cum = np.cumsum(tl.mets)
        rows = {
            "pid": tl.pid, "ladder": ladder, "t": tl.t[oi], "idx": oi,
            "hour": tl.hour[oi], "est": rec[oi, 0], "est_sd": rec[oi, 1],
            "slope30": (rec[oi, 0] - back(6, rec[:, 0])) / 30.0,
            "hours_since_obs": hs_since[oi], "last_obs": last_val_arr[oi],
            "carbs_now": tl.carbs[oi], "carbs_2h": carbs_window(24), "carbs_4h": carbs_window(48),
            "slow_now": tl.slow[oi],
            "mets_1h": (mets_cum[oi] - mets_cum[np.maximum(oi - 12, 0)]) / 12.0,
            "meal_origin": tl.meal_start[oi], "ess": ess[oi],
            "calib_mean": calib_mean, "calib_sd": calib_sd,
            "peak_med": np.concatenate(peak), "ev_high": ev_high, "ev_low": ev_low,
            "p_high_raw": (np.concatenate(pmax_all).astype(float) > 180).mean(axis=1),
            "p_low_raw": (np.concatenate(pmin_all).astype(float) < 70).mean(axis=1),
        }
        for k, h in enumerate(HORIZONS):
            rows[f"med_{h}"] = med[:, k]
            rows[f"sd_{h}"] = sd[:, k]
            rows[f"q05_{h}"] = q05[:, k]
            rows[f"q95_{h}"] = q95[:, k]
            rows[f"true_{h}"] = truths[k]
        if covariates:
            for key in ("age", "bmi", "hba1c"):
                rows[key] = covariates.get(key, np.nan)
    origins = pd.DataFrame(rows)
    pmax = np.concatenate(pmax_all) if pmax_all else np.zeros((0, m_forecast), np.float16)
    pmin = np.concatenate(pmin_all) if pmin_all else np.zeros((0, m_forecast), np.float16)
    return RunResult(recon, origins, pmax, pmin, post_mu, post_sd)
