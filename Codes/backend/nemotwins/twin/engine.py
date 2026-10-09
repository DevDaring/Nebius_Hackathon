"""Twin API (spec section 4.6) - the only way anything else gets glucose numbers.

    get_state(pid, ladder)            current estimate, band, freshness, history, replay clock
    forecast(pid, ladder, meal)       trajectory quantiles, P(high), P(low), drivers, provenance
    what_if(pid, ladder, base, scen)  paired baseline vs scenario on the same particles
    next_best_prick(pid, ladder)      best time, expected gain, reason
    assimilate(pid, ladder, value)    updated state, signed before/after band widths
    outlook_90d(pid, ladder)          projected TIR / eHbA1c (labelled projection)
    explain(forecast_id)              physiology vs learned drivers

Replay clock. Each persona replays a real open CGMacros record. The
replay starts on day 7 at 19:30 (``PS.NOW_DAY`` / ``PS.NOW_HOUR``); a user can advance it
by up to ``MAX_OFFSET_MIN`` minutes. Advancing propagates the twin through the record's
own meals and activity, and assimilates the sensor ladder's scheduled observations at
their own times. User events (readings, meals) carry their replay time ``t_min``
(minutes relative to the replay start) and are applied at that time. The cached base
state sits ``PRE_STEPS`` steps (30 min) before the replay start, so a reading up to
30 minutes old is placed at its own time, never moved forward. Every result is a pure
function of (persona, ladder, covariate revision, timestamped events, clock offset):
the same timestamped input sequence always gives the same state.

Performance: every simulation variant of one request (the forecast itself plus the
counterfactual "driver" runs, or what-if baseline vs scenario) is propagated with common
random numbers, so the variants stay exactly paired. Results are deterministic and kept
in small LRU caches keyed by (call, persona, ladder, revision, events, clock, meal).

Runtime data: the engine needs only the three persona trajectories and CGMacros
covariates. If ``data/processed`` is missing (e.g. in Docker) it falls back to
``artifacts/demo_series.parquet`` and ``artifacts/demo_covariates.parquet`` written by
``python -m nemotwins.twin.export_demo``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pickle
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nemotwins.config import CACHE_DIR, MODELS_DIR, PROCESSED_DIR, REPORTS_DIR
from nemotwins.twin import filter as PF
from nemotwins.twin import hybrid as HY
from nemotwins.twin import model as M
from nemotwins.twin import nbp as NBP
from nemotwins.twin import personas as PS
from nemotwins.twin.calibrate import cem_fit
from nemotwins.twin.prior import PopulationPrior
from nemotwins.twin.runner import (
    HORIZONS,
    Timeline,
    build_timeline,
    habitual_meal_profile,
    observation_schedule,
)

FC_STEPS = 48  # 4 h forecast
EV_STEPS = 24  # 2 h event window
VALIDATED_HORIZON_MIN = 120  # learned correction, conformal bands and event calibration are evaluated to 120 min
M_FC = 400
LADDERS = ("full", "4", "2", "1", "0")
PERSONA_CACHE = MODELS_DIR / "persona_states"
REVISION_CACHE = CACHE_DIR / "persona_states"  # per-lab-revision states (runtime, writable, gitignored)
DEMO_SERIES = MODELS_DIR / "demo_series.parquet"
DEMO_COVARIATES = MODELS_DIR / "demo_covariates.parquet"
CALIBRATION_CURVE = REPORTS_DIR / "calibration_curve.json"
N_GROUPS = 20  # meal-carb uncertainty: one carb draw per group of particles
CACHE_SIZE = 256
PRE_STEPS = 6  # the base state is stored 30 min before the replay start (late readings keep their own time)
MAX_OFFSET_MIN = 720  # the replay clock can run 12 h past its start
STATE_VERSION = 3  # bump when BaseState changes; stale pickles are rebuilt automatically
REVISION_FIELDS = ("hba1c", "bmi")  # covariates of the EHR-conditioned prior a lab revision may change
P_LOW_NOTE = ("Not validated: the training data had too few low-glucose (<70 mg/dL) events to check "
              "this probability. Treat it as indicative only.")


def load_runtime_data(source: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Persona time series + covariates. ``source``: 'processed', 'demo' or None (auto).

    The environment variable ``NEMOTWINS_DATA_SOURCE`` can force one of the two.
    """
    source = source or os.environ.get("NEMOTWINS_DATA_SOURCE") or "auto"
    ts_p, cov_p = PROCESSED_DIR / "timeseries.parquet", PROCESSED_DIR / "covariates.parquet"
    use_processed = source == "processed" or (source == "auto" and ts_p.exists() and cov_p.exists())
    if use_processed:
        pids = [p["source_pid"] for p in PS.PERSONAS]
        ts = pd.read_parquet(ts_p, filters=[("pid", "in", pids)])
        return ts, pd.read_parquet(cov_p), "processed"
    if not (DEMO_SERIES.exists() and DEMO_COVARIATES.exists()):
        raise FileNotFoundError(
            "No runtime data: neither data/processed/*.parquet nor artifacts/demo_*.parquet exist. "
            "Run `python -m nemotwins.twin.export_demo` where the processed data is available.")
    return pd.read_parquet(DEMO_SERIES), pd.read_parquet(DEMO_COVARIATES), "demo"


def _key(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _file_sha(p: Path) -> str:
    try:
        return hashlib.sha1(p.read_bytes()).hexdigest()
    except OSError:
        return "missing"


class _LRU:
    def __init__(self, size: int) -> None:
        self.size = size
        self.d: OrderedDict[str, Any] = OrderedDict()
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get_or(self, key: str, fn: Callable[[], Any]) -> Any:
        with self.lock:
            if key in self.d:
                self.d.move_to_end(key)
                self.hits += 1
                return self.d[key]
        val = fn()
        with self.lock:
            self.misses += 1
            self.d[key] = val
            while len(self.d) > self.size:
                self.d.popitem(last=False)
        return val

    def clear(self) -> None:
        with self.lock:
            self.d.clear()


def freq_text(p: float) -> str:
    n = int(round(p * 10))
    if n <= 0:
        return "less than 1 time in 10"
    if n >= 10:
        return "almost every time"
    return f"about {n} times out of 10"


def wilson(k_over_n: float, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval for an observed proportion (used only if the report has no CI)."""
    if n <= 0 or not math.isfinite(k_over_n):
        return None, None
    p = k_over_n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


_CURVE: dict[str, Any] = {"mtime": None, "data": None}
_CURVE_LOCK = threading.Lock()


def calibration_curve() -> dict | None:
    """``reports/calibration_curve.json`` (re-read when the file changes)."""
    try:
        mt = CALIBRATION_CURVE.stat().st_mtime
    except OSError:
        return None
    with _CURVE_LOCK:
        if _CURVE["mtime"] != mt:
            try:
                _CURVE["data"] = json.loads(CALIBRATION_CURVE.read_text())
                _CURVE["mtime"] = mt
            except (OSError, ValueError):
                return None
        return _CURVE["data"]


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def reliability(p: float, ladder: str, which: str = "high") -> dict:
    """Held-out reliability of the calibration bin that contains ``p``.

    From ``reports/calibration_curve.json`` (patient-grouped out-of-fold predictions):
    the bin's predicted range, the observed event frequency, the number of forecast
    windows, and the 95% CI of that frequency (the report's Wilson CI, or a Wilson CI
    computed here from ``observed`` and ``n`` when the report has none). This is the
    evidence for the probability; it does not shrink when the twin uses more particles."""
    src = "reports/calibration_curve.json"
    empty = {"pred_lo": None, "pred_hi": None, "observed": None, "n": 0, "ci_lo": None, "ci_hi": None,
             "source": src}
    data = calibration_curve()
    try:
        bins = list(data["levels"][ladder][which]) if data else []
    except (KeyError, TypeError):
        bins = []
    if not bins:
        return empty
    nb = int(data.get("n_bins") or 10) if isinstance(data, dict) else 10
    rows = []
    for b in bins:
        lo = _num(b.get("pred_lo", b.get("bin_lo", b.get("p_lo"))))
        hi = _num(b.get("pred_hi", b.get("bin_hi", b.get("p_hi"))))
        if lo is None or hi is None:
            k = int(b.get("bin", 0))
            lo, hi = k / nb, (k + 1) / nb
        rows.append((lo, hi, b))
    inside = [r for r in rows if r[0] <= p <= r[1]]
    nearest = False
    if inside:
        pick = min(inside, key=lambda r: r[1] - r[0])
    else:
        # bins may report the range of predictions actually seen (gaps between bins): take the nearest
        pick = min(rows, key=lambda r: min(abs(p - r[0]), abs(p - r[1])))
        nearest = True
    lo, hi, b = pick
    obs = _num(b.get("observed"))
    n = int(b.get("n", 0) or 0)
    ci = b.get("ci") or b.get("wilson_ci") or b.get("ci95")
    ci_lo = _num(b.get("ci_lo", b.get("wilson_lo", ci[0] if isinstance(ci, list | tuple) and ci else None)))
    ci_hi = _num(b.get("ci_hi", b.get("wilson_hi", ci[1] if isinstance(ci, list | tuple) and len(ci) > 1 else None)))
    if (ci_lo is None or ci_hi is None) and obs is not None:
        ci_lo, ci_hi = wilson(obs, n)
    r3 = lambda v: None if v is None else round(float(v), 3)  # noqa: E731
    out = {"pred_lo": r3(lo), "pred_hi": r3(hi), "observed": r3(obs), "n": n, "ci_lo": r3(ci_lo),
           "ci_hi": r3(ci_hi), "source": src}
    if b.get("n_people") is not None:
        out["n_people"] = int(b["n_people"])
    if nearest:
        out["nearest_bin"] = True
    return out


def p_high_json(p: float, ladder: str) -> dict:
    return {"p": round(float(p), 3), "freq_text": freq_text(p), "validated": True,
            "reliability": reliability(float(p), ladder, "high")}


def p_low_json(p: float) -> dict:
    return {"p": round(float(p), 3), "freq_text": freq_text(p), "validated": False, "note": P_LOW_NOTE}


@dataclass
class BaseState:
    """Twin replayed up to ``b0`` = PRE_STEPS before the persona's replay start (``now_idx``)."""

    persona_id: str
    ladder: str
    tl: Timeline
    now_idx: int  # replay start (day 7, 19:30)
    calib_end: int
    pf_state: dict  # particle filter at b0
    rec: np.ndarray  # (b0+1, 4) mu, sd, q05, q95
    vals: np.ndarray
    kind: np.ndarray
    meal_profile: np.ndarray
    calib_mean: float
    calib_sd: float
    covariates: dict
    pop_median: np.ndarray
    last_obs_idx: int  # as of b0
    last_obs_val: float
    b0: int = 0
    last_obs_kind: int = 0
    version: int = 0
    fingerprint: str = ""
    cov_key: str = ""


@dataclass
class Live:
    """The twin filtered from the base state to the user's replay 'now'."""

    b: BaseState
    i: int  # timeline index of the replay now
    offset: int
    pf_state: dict
    last_obs_idx: int
    last_obs_val: float
    last_obs_kind: str  # "cgm" | "fingerprick"
    last_obs_source: str  # "dataset" | "manual" | "chat" | "replay"
    readings: list[dict] = field(default_factory=list)  # user readings applied: {idx, value, source}
    meals: list[dict] = field(default_factory=list)  # user meals: {idx, carbs, name}
    logged_now: float = 0.0  # carbs of user meals at the replay now (enter the forecast at step 0)
    rec_ext: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))  # steps b0+1..i
    carbs_eff: np.ndarray = field(default_factory=lambda: np.zeros(0))  # dataset + user carbs per step
    n_obs: int = 0

    def rec_at(self, j: int) -> np.ndarray:
        b = self.b
        j = max(0, min(j, self.i))
        return b.rec[j] if j <= b.b0 else self.rec_ext[j - b.b0 - 1]

    def rec_range(self, lo: int, hi: int) -> np.ndarray:
        """Summaries for steps lo..hi (inclusive)."""
        b = self.b
        parts = []
        if lo <= b.b0:
            parts.append(b.rec[lo: min(hi, b.b0) + 1])
        if hi > b.b0:
            parts.append(self.rec_ext[max(lo, b.b0 + 1) - b.b0 - 1: hi - b.b0])
        return np.concatenate(parts) if parts else np.zeros((0, 4))


class TwinEngine:
    def __init__(self, data_source: str | None = None, persona_cache: Path | None = None) -> None:
        self.ts, self.cov, self.data_source = load_runtime_data(data_source)
        self.persona_cache = persona_cache or PERSONA_CACHE
        prior_path, hybrid_path = MODELS_DIR / "prior_cgmacros.json", MODELS_DIR / "hybrid_cgmacros.pkl"
        self.prior = PopulationPrior.from_json(json.loads(prior_path.read_text()))
        with open(hybrid_path, "rb") as f:
            self.hybrid: HY.HybridBundle = pickle.load(f)
        _single_thread(self.hybrid)
        prior_sha, hybrid_sha = _file_sha(prior_path), _file_sha(hybrid_path)
        self.fingerprint = _key(STATE_VERSION, prior_sha, self.data_source)
        self.model_version = f"nemotwins engine v{STATE_VERSION} (prior {prior_sha[:8]}, hybrid {hybrid_sha[:8]})"
        self.hybrid_trained_on = _hybrid_meta(self.hybrid)
        self._base: dict[tuple[str, str, str], BaseState] = {}
        self._cem_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        self._lock = threading.Lock()
        self._forecasts: OrderedDict[str, dict] = OrderedDict()
        self._fc_lock = threading.Lock()
        self._explainers: dict = {}
        self._cache = _LRU(CACHE_SIZE)
        self._live_cache = _LRU(CACHE_SIZE)
        self.time_shift = self._compute_shift()
        self.warm_done = False

    # ------------------------------------------------------------------ clock
    def _compute_shift(self) -> dict[str, timedelta]:
        """Display shift so each persona's replay start shows as today 19:30 (local time)."""
        today = datetime.now().date()
        out = {}
        for p in PS.PERSONAS:
            df = self.ts[self.ts.pid == p["source_pid"]]
            t0 = pd.Timestamp(df.t.min()).normalize()
            now = t0 + pd.Timedelta(days=PS.NOW_DAY, hours=PS.NOW_HOUR)
            target = pd.Timestamp(datetime.combine(today, datetime.min.time())) + pd.Timedelta(hours=PS.NOW_HOUR)
            out[p["id"]] = (target - now).to_pytimedelta()
        return out

    def _fmt(self, pid: str, t: Any) -> str:
        return (pd.Timestamp(t) + self.time_shift[pid]).isoformat(timespec="minutes")

    def display_time(self, pid: str, offset_min: float) -> datetime:
        """Displayed (shifted) local time of replay offset ``offset_min``."""
        b = self.base(pid, "2")
        return (pd.Timestamp(b.tl.t[b.now_idx]) + self.time_shift[pid]
                + pd.Timedelta(minutes=float(offset_min))).to_pydatetime()

    def offset_of(self, pid: str, display: datetime) -> float:
        """Inverse of ``display_time``: minutes relative to the replay start (may be negative)."""
        start = self.display_time(pid, 0)
        return (display.replace(tzinfo=None) - start).total_seconds() / 60.0

    def replay_info(self, pid: str, offset: int = 0) -> dict:
        b = self.base(pid, "2")
        i = self._now_index(b, offset)
        t = pd.Timestamp(b.tl.t[i])
        day = int((t.normalize() - pd.Timestamp(b.tl.t[0]).normalize()).days)
        return {"now": self._fmt(pid, t), "day": day, "offset_min": int(offset), "max_offset_min": MAX_OFFSET_MIN,
                "label_en": f"Replay · day {day} · {t.strftime('%H:%M')}", "mode": "replay"}

    @staticmethod
    def _now_index(b: BaseState, offset: int) -> int:
        off = int(min(max(int(offset), 0), MAX_OFFSET_MIN))
        return int(min(b.now_idx + off // int(M.DT), len(b.tl.t) - 1))

    # ------------------------------------------------------------------ base replay
    @staticmethod
    def cov_key(rev: dict | None) -> str:
        if not rev:
            return ""
        fields = rev.get("fields") or {}
        vals = {k: round(float(fields[k]["value"]), 3) for k in REVISION_FIELDS
                if k in fields and _num(fields[k].get("value")) is not None}
        return _key(vals)[:12] if vals else ""

    def base(self, pid: str, ladder: str, rev: dict | None = None) -> BaseState:
        ck = self.cov_key(rev)
        key = (pid, ladder, ck)
        st = self._base.get(key)
        if st is not None:
            return st
        with self._lock:
            if key not in self._base:
                path = (self.persona_cache / f"{pid}_{ladder}.pkl" if not ck
                        else REVISION_CACHE / f"{pid}_{ladder}_rev{ck}.pkl")
                loaded = None
                if path.exists():
                    try:
                        with open(path, "rb") as f:
                            loaded = pickle.load(f)
                    except Exception:  # noqa: BLE001 - a corrupt or incompatible pickle is rebuilt
                        loaded = None
                if (loaded is None or getattr(loaded, "version", 0) != STATE_VERSION
                        or getattr(loaded, "fingerprint", "") != self.fingerprint):
                    loaded = self._replay(pid, ladder, cov_override=_overrides(rev))
                    loaded.cov_key = ck
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = path.with_suffix(f".tmp{os.getpid()}")
                        with open(tmp, "wb") as f:
                            pickle.dump(loaded, f)
                        os.replace(tmp, path)
                    except OSError:  # read-only image: keep it in memory only
                        pass
                self._base[key] = loaded
        return self._base[key]

    def warm(self, default_states: bool = True) -> None:
        """Load every persona base state; build the SHAP explainer and the default (no user
        events, ladder 2, replay start) state per persona so the first real request is fast."""
        for p in PS.PERSONAS:
            for lad in LADDERS:
                self.base(p["id"], lad)
        self._explainer()
        if default_states:
            for p in PS.PERSONAS:
                self.state(p["id"], "2", [])
        self.warm_done = True

    def warm_revision(self, pid: str, rev: dict, ladders: tuple[str, ...] = LADDERS) -> None:
        for lad in ladders:
            self.base(pid, lad, rev)

    def _cem(self, pid: str, tl: Timeline, calib_end: int, med: np.ndarray, sd: np.ndarray, seed: int,
             ck: str) -> tuple[np.ndarray, np.ndarray]:
        key = (pid, ck)
        if key not in self._cem_cache:
            self._cem_cache[key] = cem_fit(tl, calib_end, np.log(med), sd, seed=seed)
        return self._cem_cache[key]

    def _replay(self, pid: str, ladder: str, seed: int = 2026, cov_override: dict | None = None) -> BaseState:
        persona = PS.BY_ID[pid]
        df = self.ts[self.ts.pid == persona["source_pid"]]
        tl = build_timeline(df)
        n = len(tl.t)
        elapsed = (tl.t - tl.t[0]) / np.timedelta64(1, "D")
        calib_end = int(np.searchsorted(elapsed, PS.CALIB_DAYS))
        t_now = tl.t[0].astype("datetime64[D]") + np.timedelta64(int((PS.NOW_DAY + PS.NOW_HOUR / 24) * 1440), "m")
        now_idx = min(int(np.searchsorted(tl.t, t_now)), n - 1)
        b0 = max(calib_end, now_idx - PRE_STEPS)
        vals, kind = observation_schedule(tl, ladder, calib_end, seed)
        drop = (np.arange(n) < calib_end) & (np.arange(n) % 3 != 0) & (kind == 1)
        vals[drop], kind[drop] = np.nan, 0
        covd = self.cov.loc[self.cov.pid == persona["source_pid"]].iloc[0].to_dict()
        if cov_override:
            covd.update(cov_override)
        med, sd = self.prior.predict(covd)
        cm, cs = self._cem(pid, tl, calib_end, med, sd, seed, _key(cov_override or {})[:12])
        pf = PF.ParticleFilter(1000, np.exp(cm), cs, seed=seed, g0=float(tl.cgm[np.isfinite(tl.cgm)][0]))
        rec = np.zeros((b0 + 1, 4))
        last_i, last_v, last_k = -1, np.nan, 0
        for i in range(b0 + 1):
            if i > 0:
                pf.predict(M.StepInputs(tl.carbs[i - 1], tl.slow[i - 1], tl.mets[i - 1], tl.hour[i - 1]),
                           observed_next=bool(kind[i]))
            if kind[i]:
                hs_prev = (i - last_i) * M.DT / 60.0 if last_i >= 0 else 24.0
                pf.update(vals[i], "cgm" if kind[i] == 1 else "prick", hours_since_obs=hs_prev)
                last_i, last_v, last_k = i, vals[i], int(kind[i])
            rec[i] = pf.glucose_summary()
        cal = tl.cgm[:calib_end][tl.cgm_native[:calib_end]]
        return BaseState(
            pid, ladder, tl, now_idx, calib_end, pf.copy_state(), rec, vals, kind,
            habitual_meal_profile(tl, calib_end), float(np.nanmean(cal)), float(np.nanstd(cal)), covd, med,
            last_i, float(last_v), b0=b0, last_obs_kind=last_k, version=STATE_VERSION, fingerprint=self.fingerprint,
        )

    # ------------------------------------------------------------------ live filter
    def _event_idx(self, b: BaseState, t_min: Any, i_now: int) -> int:
        t = _num(t_min)
        j = b.now_idx + int(round((t if t is not None else 0.0) / M.DT))
        return int(min(max(j, b.b0), i_now))

    def _live(self, pid: str, ladder: str, events: list[dict], offset: int = 0,
              rev: dict | None = None) -> tuple[Live, PF.ParticleFilter]:
        b = self.base(pid, ladder, rev)
        key = _key("live", pid, ladder, self.cov_key(rev), _ev_key(events), int(offset))
        lv: Live = self._live_cache.get_or(key, lambda: self._run_live(b, events, int(offset)))
        pf = PF.ParticleFilter(1000, b.pop_median, M.GENERIC_PRIOR_LOGSD, seed=7)
        pf.restore(lv.pf_state)
        return lv, pf

    def _run_live(self, b: BaseState, events: list[dict], offset: int) -> Live:
        tl = b.tl
        i_now = self._now_index(b, offset)
        pf = PF.ParticleFilter(1000, b.pop_median, M.GENERIC_PRIOR_LOGSD, seed=7)
        pf.restore(b.pf_state)
        pf.rng = np.random.default_rng(11)
        carbs_eff = tl.carbs[: i_now + 1].astype(float).copy()
        readings: dict[int, list[tuple[float, str]]] = {}
        user_readings, user_meals = [], []
        logged_now = 0.0
        for ev in events:
            j = self._event_idx(b, ev.get("t_min"), i_now)
            if ev["kind"] == "reading":
                readings.setdefault(j, []).append((float(ev["value"]), str(ev.get("source", "manual"))))
                user_readings.append({"idx": j, "value": float(ev["value"]), "source": str(ev.get("source", "manual"))})
            elif ev["kind"] == "meal":
                c = float(ev.get("carbs", 0) or 0)
                user_meals.append({"idx": j, "carbs": c, "name": ev.get("name", "Meal")})
                if j >= i_now:
                    logged_now += c
                else:
                    carbs_eff[j] += c
        last_i, last_v = b.last_obs_idx, b.last_obs_val
        last_kind = "cgm" if b.last_obs_kind == 1 else "fingerprick"
        last_src = "dataset"

        def apply_user(j: int) -> None:
            nonlocal last_i, last_v, last_kind, last_src
            for v, src in readings.get(j, []):
                hs_prev = (j - last_i) * M.DT / 60.0 if last_i >= 0 else 24.0
                pf.update(v, "prick", hours_since_obs=hs_prev)
                last_i, last_v, last_kind, last_src = j, v, "fingerprick", src

        apply_user(b.b0)
        rec_ext = np.zeros((max(0, i_now - b.b0), 4))
        for j in range(b.b0 + 1, i_now + 1):
            observed = bool(b.kind[j]) or j in readings
            pf.predict(M.StepInputs(carbs_eff[j - 1], tl.slow[j - 1], tl.mets[j - 1], tl.hour[j - 1]),
                       observed_next=observed)
            if b.kind[j]:
                hs_prev = (j - last_i) * M.DT / 60.0 if last_i >= 0 else 24.0
                pf.update(float(b.vals[j]), "cgm" if b.kind[j] == 1 else "prick", hours_since_obs=hs_prev)
                last_i, last_v = j, float(b.vals[j])
                last_kind, last_src = ("cgm" if b.kind[j] == 1 else "fingerprick"), "dataset"
            apply_user(j)
            rec_ext[j - b.b0 - 1] = pf.glucose_summary()
        n_obs = int((b.kind[: i_now + 1] > 0).sum()) + len(user_readings)
        return Live(b, i_now, offset, pf.copy_state(), last_i, float(last_v), last_kind, last_src,
                    user_readings, user_meals, logged_now, rec_ext, carbs_eff, n_obs)

    # ------------------------------------------------------------------ forecasting core
    def _features(self, lv: Live, pf: PF.ParticleFilter, carbs_now: float,
                  med: dict, sd: dict, peak_med: float, p_hi_raw: float, p_lo_raw: float) -> pd.DataFrame:
        b, i = lv.b, lv.i
        mu, s, _, _ = pf.glucose_summary()
        hs = (i - lv.last_obs_idx) * M.DT / 60.0 if lv.last_obs_idx >= 0 else 99.0
        carbs = lv.carbs_eff[: i + 1]
        row = {
            "pid": b.persona_id, "ladder": b.ladder, "hour": b.tl.hour[i], "est": mu, "est_sd": s,
            "slope30": (mu - float(lv.rec_at(i - 6)[0])) / 30.0, "hours_since_obs": hs,
            "last_obs": lv.last_obs_val, "carbs_now": carbs_now,
            "carbs_2h": carbs[-24:].sum() + carbs_now, "carbs_4h": carbs[-48:].sum() + carbs_now,
            "slow_now": b.tl.slow[i], "mets_1h": float(np.mean(b.tl.mets[max(i - 12, 0): i + 1])),
            "ess": pf.ess_fraction(), "peak_med": peak_med, "p_high_raw": p_hi_raw, "p_low_raw": p_lo_raw,
            "calib_mean": b.calib_mean, "calib_sd": b.calib_sd,
            "age": b.covariates.get("age"), "bmi": b.covariates.get("bmi"), "hba1c": b.covariates.get("hba1c"),
        }
        for h in HORIZONS:
            row[f"med_{h}"], row[f"sd_{h}"] = med[h], sd[h]
        return HY.add_features(pd.DataFrame([row]))

    def _variant_inputs(self, lv: Live, meal: dict | None, scen: dict | None, logged_carbs: float,
                        seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Per-group inputs (FC_STEPS, N_GROUPS) for one simulation variant."""
        i = lv.i
        carbs = np.zeros((FC_STEPS, N_GROUPS))
        slow = np.full((FC_STEPS, N_GROUPS), lv.b.tl.slow[i])
        mets = np.full((FC_STEPS, N_GROUPS), M.REST_METS)
        carbs[0] += logged_carbs
        draw_rng = np.random.default_rng(seed + 99)
        if meal:
            scen = scen or {}
            c = _effective_carbs(meal, scen)
            c_sd = float(meal.get("carbs_sd", 0.15 * c))
            c_draw = np.clip(c + draw_rng.normal(0, 1, N_GROUPS) * c_sd, 0, None)
            start = int(max(0, float(meal.get("minutes_from_now", 0)) + float(scen.get("shift_min", 0))) // M.DT)
            if start < FC_STEPS:
                carbs[start] += c_draw
                sf = M.meal_slow_factor(float(meal.get("fat", 10) + scen.get("fat_delta", 0)),
                                        float(meal.get("protein", 10) + scen.get("protein_delta", 0)),
                                        float(meal.get("fibre", 3) + scen.get("fibre_delta", 0)))
                slow[start:] = sf
            walk = float(scen.get("walk_min", 0))
            if walk > 0:
                w0 = start + int(float(scen.get("walk_after_min", 15)) // M.DT)
                mets[w0: w0 + int(walk // M.DT)] = 3.5
        return carbs, slow, mets

    def _simulate_many(self, lv: Live, snap: PF.Snapshot, variants: list[dict], seed: int,
                       states_out: list[dict] | None = None) -> list[np.ndarray]:
        """Simulate several input/parameter variants of the same particles in ONE batched loop.

        Each variant: {"meal", "scen", "logged", "overrides"}. All variants share the same
        process-noise draws (common random numbers), so each returned (m, FC_STEPS) array is
        identical to simulating that variant alone with ``seed``.
        """
        per = snap.x.shape[0] // N_GROUPS
        mm = per * N_GROUPS
        nv = len(variants)
        i = lv.i
        hours = (lv.b.tl.hour[i] + np.arange(FC_STEPS) * M.DT / 60.0) % 24
        xs, lts, cs, ss, ms = [], [], [], [], []
        for v in variants:
            c, sl, me = self._variant_inputs(lv, v.get("meal"), v.get("scen"), float(v.get("logged", 0.0)), seed)
            x, lt = snap.x[:mm].copy(), snap.logth[:mm].copy()
            for k, val in (v.get("overrides") or {}).items():
                if k in M.STATE_NAMES:
                    x[:, M.STATE_NAMES.index(k)] = val
                elif k in M.PARAM_NAMES:
                    lt[:, M.PARAM_NAMES.index(k)] = np.log(max(val, 1e-9))
            xs.append(x)
            lts.append(lt)
            cs.append(np.repeat(c, per, axis=1))
            ss.append(np.repeat(sl, per, axis=1))
            ms.append(np.repeat(me, per, axis=1))
        rec: list[np.ndarray] | None = [] if states_out is not None else None
        th_all = np.exp(np.concatenate(lts))
        slow_all = np.concatenate(ss, axis=1)
        mets_all = np.concatenate(ms, axis=1)
        x0_all = np.concatenate(xs)
        out = _propagate_crn(x0_all, th_all, np.concatenate(cs, axis=1), slow_all, mets_all,
                             np.repeat(hours[:, None], nv * mm, axis=1), np.random.default_rng(seed), nv, rec)
        if states_out is not None and rec is not None:
            st = np.stack(rec)  # (H, nv*mm, N_STATE)
            for k in range(nv):
                seg = slice(k * mm, (k + 1) * mm)
                states_out.append({"x0": x0_all[seg], "states": st[:, seg, :], "theta": th_all[seg],
                                   "slow": slow_all[:, seg], "slow0": float(lv.b.tl.slow[i])})
        return [out[:, k * mm:(k + 1) * mm].T.copy() for k in range(nv)]

    def _simulate(self, lv: Live, snap: PF.Snapshot, meal: dict | None, scen: dict | None,
                  logged_carbs: float, seed: int, overrides: dict | None = None) -> np.ndarray:
        """Return (m, FC_STEPS) trajectories. Common random numbers via ``seed``."""
        return self._simulate_many(lv, snap, [{"meal": meal, "scen": scen, "logged": logged_carbs,
                                               "overrides": overrides}], seed)[0]

    def _hybridise_many(self, lv: Live, pf: PF.ParticleFilter, trajs: list[np.ndarray],
                        carbs_now: list[float]) -> list[dict]:
        """Learned residual + conformal widening + calibrated events for several variants (one model call)."""
        hidx = {h: h // 5 - 1 for h in HORIZONS}
        rows, pmaxs, pmins = [], [], []
        for traj, cn in zip(trajs, carbs_now, strict=True):
            med = {h: float(np.median(traj[:, k])) for h, k in hidx.items()}
            sd = {h: float(traj[:, k].std()) for h, k in hidx.items()}
            pmax, pmin = traj[:, :EV_STEPS].max(axis=1), traj[:, :EV_STEPS].min(axis=1)
            rows.append(self._features(lv, pf, cn, med, sd, float(np.median(pmax)),
                                       float((pmax > 180).mean()), float((pmin < 70).mean())))
            pmaxs.append(pmax)
            pmins.append(pmin)
        feats_all = pd.concat(rows, ignore_index=True)
        applied_all = self.hybrid.apply(feats_all, np.stack(pmaxs), np.stack(pmins))
        steps = np.arange(1, FC_STEPS + 1) * M.DT
        out = []
        for r, traj in enumerate(trajs):
            applied = applied_all.iloc[[r]].reset_index(drop=True)
            res = {h: float(applied[f"res_{h}"].iat[0]) for h in HORIZONS}
            # residual correction curve: 0 at origin, interpolated over horizons, held after 120 min
            # (beyond VALIDATED_HORIZON_MIN the trajectory is exploratory)
            r_curve = np.interp(steps, [0, *HORIZONS], [0.0, *[res[h] for h in HORIZONS]])
            shifted = traj + r_curve[None, :]
            q = {k: np.quantile(shifted, v, axis=0) for k, v in
                 (("q05", 0.05), ("q25", 0.25), ("q50", 0.5), ("q75", 0.75), ("q95", 0.95))}
            # widen the particle band so it matches the conformal 90% band at each horizon
            half_conf = np.array([(applied[f"hi_{h}"].iat[0] - applied[f"lo_{h}"].iat[0]) / 2 for h in HORIZONS])
            half_part = np.array([(q["q95"][hidx[h]] - q["q05"][hidx[h]]) / 2 for h in HORIZONS])
            ratio = np.maximum(1.0, half_conf / np.maximum(half_part, 1.0))
            scale = np.interp(steps, [0, *HORIZONS], [ratio[0], *ratio])
            q = _widen(q, scale)
            out.append({
                "q": q, "applied": applied, "res": res, "p_high": float(applied["p_high"].iat[0]),
                "p_low": float(applied["p_low"].iat[0]),
                "abstain": bool(applied["abstain"].iat[0]), "feats": feats_all.iloc[[r]].reset_index(drop=True),
                "shifted": shifted, "r_curve": r_curve, "scale": scale,
            })
        return out

    def _hybridise(self, lv: Live, pf: PF.ParticleFilter, traj: np.ndarray, carbs_now: float) -> dict:
        return self._hybridise_many(lv, pf, [traj], [carbs_now])[0]

    def _snapshot(self, pf: PF.ParticleFilter) -> PF.Snapshot:
        pf.rng = np.random.default_rng(5)
        return pf.snapshot(M_FC)

    def _remember(self, fid: str, ctx: dict) -> None:
        with self._fc_lock:
            self._forecasts[fid] = ctx
            self._forecasts.move_to_end(fid)
            while len(self._forecasts) > 500:
                self._forecasts.popitem(last=False)

    def forecast_context(self, forecast_id: str) -> dict | None:
        with self._fc_lock:
            return self._forecasts.get(forecast_id)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._live_cache.clear()

    # ------------------------------------------------------------------ provenance
    def _provenance(self, pid: str, lv: Live, rev: dict | None) -> dict:
        cov = lv.b.covariates
        fields = (rev or {}).get("fields") or {}
        prior_inputs: dict[str, dict] = {}
        for k in ("hba1c", "bmi", "age", "sex"):
            if k in fields and k in REVISION_FIELDS:
                f = fields[k]
                prior_inputs[k] = {"value": _num(f.get("value")), "source": "lab upload (confirmed)",
                                   "date": f.get("collection_date"), "revision": f.get("revision")}
            else:
                v = cov.get(k)
                val: Any = v if isinstance(v, str) else _num(v)
                if isinstance(val, float):
                    val = round(val, 2)
                prior_inputs[k] = {"value": val, "source": "persona EHR", "date": None}
        return {"model_version": self.model_version, "hybrid_trained_on": self.hybrid_trained_on,
                "inputs_revision": int((rev or {}).get("revision") or 0), "prior_inputs": prior_inputs,
                "observations_used": int(lv.n_obs), "replay_now": self._fmt(pid, lv.b.tl.t[lv.i])}

    # ------------------------------------------------------------------ public API
    def forecast(self, pid: str, ladder: str, events: list[dict], meal: dict | None = None,
                 horizon_min: int = 240, with_drivers: bool = True, *, offset: int = 0,
                 rev: dict | None = None) -> dict:
        out, ctx = self._forecast_cached(pid, ladder, events, meal, horizon_min, with_drivers, offset, rev)
        self._remember(out["forecast_id"], ctx)
        return copy.deepcopy(out)

    def _forecast_cached(self, pid: str, ladder: str, events: list[dict], meal: dict | None, horizon_min: int,
                         with_drivers: bool, offset: int, rev: dict | None) -> tuple[dict, dict]:
        key = _key("forecast", pid, ladder, _ev_key(events), meal, horizon_min, with_drivers, int(offset), rev)
        return self._cache.get_or(key, lambda: self._forecast(pid, ladder, events, meal, horizon_min,
                                                               with_drivers, offset, rev))

    def _forecast(self, pid: str, ladder: str, events: list[dict], meal: dict | None, horizon_min: int,
                  with_drivers: bool, offset: int, rev: dict | None) -> tuple[dict, dict]:
        lv, pf = self._live(pid, ladder, events, offset, rev)
        snap = self._snapshot(pf)
        logged = lv.logged_now
        variants = [{"meal": meal, "logged": logged}]
        if with_drivers:
            variants += self._driver_variants(lv, meal, logged)
        trajs = self._simulate_many(lv, snap, variants, seed=21)
        traj = trajs[0]
        hy = self._hybridise(lv, pf, traj, _effective_carbs(meal, {}) + logged)
        fid = uuid.uuid4().hex[:12]
        origin = lv.b.tl.t[lv.i]
        steps = int(max(1, min(FC_STEPS, horizon_min // 5)))
        times = [self._fmt(pid, origin + np.timedelta64(5 * (k + 1), "m")) for k in range(steps)]
        q = hy["q"]
        peak_k = int(np.argmax(q["q50"][:min(EV_STEPS, steps)]))
        abstain_reason = None
        if hy["abstain"]:
            abstain_reason = "This situation is unlike what I learned from. A finger-prick now would help me."
        out = {
            "forecast_id": fid, "origin": self._fmt(pid, origin), "horizon_min": steps * 5,
            "traj": {"t": times, **{k: _r(q[k][:steps]) for k in q}, "validated_horizon_min": VALIDATED_HORIZON_MIN},
            "p_high": p_high_json(hy["p_high"], ladder), "p_low": p_low_json(hy["p_low"]),
            "p_low_validated": False,
            "peak": {"t": times[peak_k], "value": round(float(q["q50"][peak_k]), 1)},
            "conformal_level": 0.9,
            "abstain": {"flag": hy["abstain"], "reason": abstain_reason},
            "drivers": [],
            "provenance": self._provenance(pid, lv, rev),
        }
        ctx = {"kind": "forecast", "pid": pid, "ladder": ladder, "events": events, "meal": meal, "hy": hy,
               "snap": snap, "logged": logged, "lv": lv, "out": out, "offset": int(offset), "rev": rev}
        if with_drivers:
            phys = self._driver_contribs(variants, trajs)
            learned = self._shap(hy["feats"])
            out["drivers"] = sorted(phys + learned, key=lambda d: -abs(d["contribution"]))[:5]
            ctx["phys"], ctx["learned"] = phys, learned
        return out, ctx

    def _driver_variants(self, lv: Live, meal: dict | None, logged: float) -> list[dict]:
        """Counterfactual runs: switch one physiological factor off (or to typical) at a time."""
        pop_si = float(lv.b.pop_median[0])
        v: list[dict] = []
        if meal and meal.get("carbs", 0) > 0:
            v.append({"meal": None, "logged": logged, "name": "meal_carbs",
                      "label": f"This meal's carbs ({float(meal.get('carbs', 0)):.0f} g)"})
        v += [
            {"meal": meal, "logged": 0.0, "overrides": {"Q1": 0.0, "Q2": 0.0}, "name": "earlier_meals",
             "label": "Earlier food still digesting"},
            {"meal": meal, "logged": logged, "overrides": {"SI": pop_si}, "name": "insulin_sensitivity",
             "label": "Your insulin sensitivity vs typical"},
            {"meal": meal, "logged": logged, "overrides": {"CAMP": 1e-3}, "name": "dawn_effect",
             "label": "Time of day (body clock)"},
            {"meal": meal, "logged": logged, "overrides": {"E": 0.0}, "name": "recent_activity",
             "label": "Recent activity"},
            {"meal": meal, "logged": logged, "overrides": {"D": 0.0}, "name": "unexplained",
             "label": "Recent unexplained trend"},
        ]
        return v

    @staticmethod
    def _driver_contribs(variants: list[dict], trajs: list[np.ndarray]) -> list[dict]:
        def peak(traj: np.ndarray) -> float:
            return float(np.median(traj[:, :EV_STEPS].max(axis=1)))

        p0 = peak(trajs[0])
        return [{"name": v["name"], "label_en": v["label"], "contribution": round(p0 - peak(t), 1),
                 "source": "physiology"} for v, t in zip(variants[1:], trajs[1:], strict=True)]

    def _drivers(self, ctx: dict) -> tuple[list[dict], list[dict]]:
        lv, snap, meal, logged = ctx["lv"], ctx["snap"], ctx["meal"], ctx["logged"]
        variants = [{"meal": meal, "logged": logged}, *self._driver_variants(lv, meal, logged)]
        trajs = self._simulate_many(lv, snap, variants, seed=21)
        return self._driver_contribs(variants, trajs), self._shap(ctx["hy"]["feats"])

    LEARNED_LABELS = {
        "est": "Current glucose level", "est_sd": "How unsure the twin is", "slope30": "Direction of the last 30 min",
        "hs_cap": "Hours since your last reading", "last_minus_est": "Last reading vs twin estimate",
        "carbs_now": "Carbs in this meal", "carbs_2h": "Carbs in the last 2 h", "carbs_4h": "Carbs in the last 4 h",
        "slow_now": "Meal fat/protein/fibre", "mets_1h": "Activity in the last hour", "hour_sin": "Time of day",
        "hour_cos": "Time of day", "ladder_num": "How many readings you take", "peak_med": "Physiology model's peak",
        "p_high_raw": "Physiology model's high-risk estimate", "p_low_raw": "Physiology model's low-risk estimate",
        "ess": "Twin confidence", "calib_mean": "Your usual glucose level", "calib_sd": "Your usual swings",
        "est_minus_calib": "Today vs your usual level", "age": "Age", "bmi": "BMI", "hba1c": "HbA1c",
        "last_or_mean": "Last reading (or your usual level)",
    }

    def _explainer(self, h: int = 60) -> Any:
        with self._lock:
            if h not in self._explainers:
                import shap

                self._explainers[h] = shap.TreeExplainer(self.hybrid.models[h])
            return self._explainers[h]

    def _shap(self, feats: pd.DataFrame) -> list[dict]:
        cols = HY.feats(self.hybrid.with_cov)
        sv = self._explainer().shap_values(feats[cols].to_numpy(float))[0]
        merged: dict[str, float] = {}
        for c, v in zip(cols, sv, strict=True):
            lab = self.LEARNED_LABELS.get(c, c)
            merged[lab] = merged.get(lab, 0.0) + float(v)
        top = sorted(merged.items(), key=lambda kv: -abs(kv[1]))[:5]
        return [{"name": k.lower().replace(" ", "_"), "label_en": k, "contribution": round(v, 1), "source": "learned"}
                for k, v in top]

    def explain(self, forecast_id: str) -> dict | None:
        ctx = self.forecast_context(forecast_id)
        if not ctx or ctx.get("kind") != "forecast":
            return None
        if "phys" not in ctx:
            ctx["phys"], ctx["learned"] = self._drivers(ctx)
        phys = sorted(ctx["phys"], key=lambda d: -abs(d["contribution"]))
        top = phys[0] if phys else None
        text = (f"The biggest driver of the next 2 hours is '{top['label_en']}' "
                f"({top['contribution']:+.0f} mg/dL on the peak)." if top else "")
        return {"physiology": copy.deepcopy(phys), "learned": copy.deepcopy(ctx["learned"]), "tool_calls": [],
                "text_en": text}

    def state(self, pid: str, ladder: str, events: list[dict], reveal: bool = False, *, offset: int = 0,
              rev: dict | None = None) -> dict:
        key = _key("state", pid, ladder, _ev_key(events), bool(reveal), int(offset), rev)
        out = self._cache.get_or(key, lambda: self._state(pid, ladder, events, reveal, offset, rev))
        # the nested forecast stays explainable / receipt-able even after a long cache hit
        _o, ctx = self._forecast_cached(pid, ladder, events, None, 240, True, offset, rev)
        self._remember(out["forecast"]["forecast_id"], ctx)
        return copy.deepcopy(out)

    def _state(self, pid: str, ladder: str, events: list[dict], reveal: bool, offset: int,
               rev: dict | None) -> dict:
        lv, pf = self._live(pid, ladder, events, offset, rev)
        b, i = lv.b, lv.i
        mu, sd, q05, q95 = pf.glucose_summary()
        hs = (i - lv.last_obs_idx) * M.DT / 60.0 if lv.last_obs_idx >= 0 else 99.0
        fresh = 1.0 if ladder == "full" else float(np.exp(-hs / 8.0))
        label = "fresh" if fresh > 0.6 else ("ageing" if fresh > 0.25 else "stale")
        lo = max(0, i - 36 * 12)
        rec = lv.rec_range(lo, i).copy()
        rec[-1] = [mu, sd, q05, q95]
        tt = b.tl.t[lo: i + 1]
        hist_t = [self._fmt(pid, t) for t in tt]
        readings: list[dict[str, Any]] = []
        for j in range(lo, i + 1):
            if b.kind[j] == 2 or (b.kind[j] == 1 and (j % 3 == 0)):
                readings.append({"t": self._fmt(pid, b.tl.t[j]), "value": round(float(b.vals[j]), 1),
                                 "kind": "cgm" if b.kind[j] == 1 else "fingerprick", "source": "dataset"})
        for r in lv.readings:
            if r["idx"] >= lo:
                readings.append({"t": self._fmt(pid, b.tl.t[r["idx"]]), "value": round(float(r["value"]), 1),
                                 "kind": "fingerprick", "source": r["source"]})
        readings.sort(key=lambda x: str(x["t"]))
        meals: list[dict[str, Any]] = []
        for j in np.where(b.tl.carbs[lo: i + 1] > 0.5)[0] + lo:
            hr = b.tl.hour[j]
            name = "Breakfast" if hr < 11 else ("Lunch" if hr < 16 else ("Snack" if hr < 18 else "Dinner"))
            meals.append({"t": self._fmt(pid, b.tl.t[j]), "name": name, "carbs": round(float(b.tl.carbs[j]), 0),
                          "source": "dataset"})
        for m in lv.meals:
            meals.append({"t": self._fmt(pid, b.tl.t[m["idx"]]), "name": m.get("name") or "Meal",
                          "carbs": float(m["carbs"]), "source": "user"})
        meals.sort(key=lambda x: str(x["t"]))
        hourly = pd.Series(b.tl.mets[lo: i + 1], index=pd.to_datetime(tt)).resample("1h").mean()
        steps = np.nan_to_num(np.maximum(hourly.to_numpy() - 1.3, 0) * 1800).round()  # approx steps/hour from METs
        z = 0.674
        hist: dict[str, Any] = {
            "virtual_cgm": {"t": hist_t, "q05": _r(rec[:, 2]), "q25": _r(rec[:, 0] - z * rec[:, 1]),
                            "q50": _r(rec[:, 0]), "q75": _r(rec[:, 0] + z * rec[:, 1]), "q95": _r(rec[:, 3])},
            "readings": readings, "meals": meals,
            "steps": {"t": [self._fmt(pid, t) for t in hourly.index], "v": steps.tolist(),
                      "note": "estimated from wearable METs"},
        }
        if reveal:
            tv = b.tl.cgm[lo: i + 1]
            ok = np.isfinite(tv)
            hist["true_cgm"] = {"t": [h for h, k in zip(hist_t, ok, strict=True) if k], "v": _r(tv[ok]),
                                "note": "Dataset reference CGM - hidden from the twin"}
        # forecast and next-best-prick come from the same cache the dedicated endpoints use
        fc = self.forecast(pid, ladder, events, None, offset=offset, rev=rev)
        nbp = self.next_best_prick(pid, ladder, events, offset=offset, rev=rev)
        # Conformal now-band: same calibrated quantile as the 30-min forecast for this
        # ladder level and time since the last reading (raw particle spread under-covers).
        hb = int(HY.hs_bin(np.array([hs]), pd.Series([ladder]))[0])
        qn = self.hybrid.q.get((ladder, hb, 30), self.hybrid.q_fallback[30])
        half = max((q95 - q05) / 2, qn * (sd + HY.SD_FLOOR))  # conservative: 30-min quantile
        band = {"lo": round(max(mu - half, 40.0), 1), "hi": round(mu + half, 1)}
        abstain = fc["abstain"]
        if pf.ess_fraction() < 0.02:
            abstain = {"flag": True, "reason": "My particles disagree too much. Please take a finger-prick."}
        last = None
        if lv.last_obs_idx >= 0:
            last = {"t": self._fmt(pid, b.tl.t[lv.last_obs_idx]), "value": round(lv.last_obs_val, 1),
                    "kind": lv.last_obs_kind, "source": lv.last_obs_source}
        return {
            "now": self._fmt(pid, b.tl.t[i]), "ladder": ladder, "estimate": round(mu, 1), "band": band,
            "freshness": {"score": round(fresh, 3), "hours_since_reading": round(hs, 2), "label": label},
            "last_observation": last, "abstain": abstain, "ess": round(pf.ess_fraction(), 3),
            "history": hist, "forecast": fc, "next_best_prick": nbp, "target": {"lo": 70, "hi": 180},
            "p_low_validated": False, "replay": self.replay_info(pid, offset),
        }

    def next_best_prick(self, pid: str, ladder: str, events: list[dict], *, offset: int = 0,
                        rev: dict | None = None) -> dict:
        key = _key("nbp", pid, ladder, _ev_key(events), int(offset), rev)
        return copy.deepcopy(self._cache.get_or(key, lambda: self._next_best_prick(pid, ladder, events, offset,
                                                                                   rev)))

    def _next_best_prick(self, pid: str, ladder: str, events: list[dict], offset: int, rev: dict | None) -> dict:
        lv, pf = self._live(pid, ladder, events, offset, rev)
        b = lv.b
        pf.rng = np.random.default_rng(3)
        snap = pf.snapshot(200)
        i = lv.i
        hour0 = float(b.tl.hour[i])
        res = NBP.recommend(snap, hour0, b.meal_profile, horizon_h=24.0, rng=np.random.default_rng(4))
        note = "Experimental: the next-best-prick schedule has not been shown to improve accuracy (reports/nbp_value.json)."
        if res["best_step"] is None:
            return {"time": None, "expected_gain_pct": 0.0, "reason": "No waking time left to check.", "candidates": [],
                    "experimental": True, "note": note}
        best_t = b.tl.t[i] + np.timedelta64(int(res["best_step"] * 5), "m")
        best_hour = (hour0 + res["best_step"] * 5 / 60) % 24
        cands = [{"t": self._fmt(pid, b.tl.t[i] + np.timedelta64(int(s * 5), "m")), "gain_pct": round(float(g) * 100, 1)}
                 for s, g in zip(res["cand_steps"], res["gains"], strict=True)]
        return {"time": self._fmt(pid, best_t), "expected_gain_pct": round(res["best_gain"] * 100, 1),
                "reason": _nbp_reason(best_hour, b.meal_profile), "candidates": cands, "experimental": True,
                "note": note}

    def assimilate(self, pid: str, ladder: str, events: list[dict], value: float, *, offset: int = 0,
                   rev: dict | None = None, t_min: float | None = None, source: str = "manual") -> dict:
        """Add a reading at replay time ``t_min`` (default: the replay now).

        ``width_change``: signed % change of the 90% band (negative = narrower), for the current
        band and for the forecast band at 120 min; a band may honestly widen after a surprising
        reading. ``narrowed_pct`` = -h120.signed_pct (may be negative)."""
        before = self.state(pid, ladder, events, offset=offset, rev=rev)
        tm = float(offset if t_min is None else t_min)
        ev = {"kind": "reading", "value": float(value), "t_min": tm, "source": source}
        after = self.state(pid, ladder, [*events, ev], offset=offset, rev=rev)
        return _assimilation(before, after, value, self._estimate_at(pid, ladder, events, offset, rev, tm))

    def _estimate_at(self, pid: str, ladder: str, events: list[dict], offset: int, rev: dict | None,
                     t_min: float) -> float:
        lv, _pf = self._live(pid, ladder, events, offset, rev)
        j = self._event_idx(lv.b, t_min, lv.i)
        return float(lv.rec_at(j)[0])

    def what_if(self, pid: str, ladder: str, events: list[dict], base_meal: dict, scenario: dict, *,
                offset: int = 0, rev: dict | None = None) -> dict:
        key = _key("what_if", pid, ladder, _ev_key(events), base_meal, scenario, int(offset), rev)
        out, ctxs = self._cache.get_or(key, lambda: self._what_if(pid, ladder, events, base_meal, scenario,
                                                                  offset, rev))
        for fid, ctx in ctxs:
            self._remember(fid, ctx)
        return copy.deepcopy(out)

    def _what_if(self, pid: str, ladder: str, events: list[dict], base_meal: dict, scenario: dict,
                 offset: int, rev: dict | None) -> tuple[dict, list[tuple[str, dict]]]:
        """Paired counterfactual on the same particles and noise.

        The baseline IS the forecast of the base meal (same object, same ``forecast_id`` as
        ``/forecast`` with that meal): it stays pinned while scenarios change. The scenario is
        simulated on the same particle snapshot with the same random numbers. The learned
        residual and conformal widening are fitted on observational data, so they are applied
        to the baseline only and carried over unchanged (as a shared offset) to the scenario;
        the difference therefore comes from the mechanistic layer. The scenario's P(>180) is
        the calibrated baseline probability plus the paired particle change.
        """
        fb, ctx_b = self._forecast_cached(pid, ladder, events, base_meal, 240, True, offset, rev)
        lv, snap, hyb, logged = ctx_b["lv"], ctx_b["snap"], ctx_b["hy"], ctx_b["logged"]
        ts = self._simulate(lv, snap, base_meal, scenario, logged, seed=21)
        sb = hyb["shifted"]
        ss = ts + hyb["r_curve"][None, :]
        qs = _widen({k: np.quantile(ss, v, axis=0) for k, v in
                     (("q05", 0.05), ("q25", 0.25), ("q50", 0.5), ("q75", 0.75), ("q95", 0.95))}, hyb["scale"])
        # Particle peaks / troughs widened like the conformal band (the raw cloud is too narrow,
        # which would make exceedance fractions jump); each scenario particle keeps its own
        # paired change relative to its baseline twin.
        sc = float(np.mean(hyb["scale"][:EV_STEPS]))
        pmax_b, pmax_s = sb[:, :EV_STEPS].max(axis=1), ss[:, :EV_STEPS].max(axis=1)
        pmin_b, pmin_s = sb[:, :EV_STEPS].min(axis=1), ss[:, :EV_STEPS].min(axis=1)
        wmax_b = np.median(pmax_b) + (pmax_b - np.median(pmax_b)) * sc
        wmin_b = np.median(pmin_b) + (pmin_b - np.median(pmin_b)) * sc
        hb = (wmax_b > 180).astype(float)
        hs_ = (wmax_b + (pmax_s - pmax_b) > 180).astype(float)
        lb = (wmin_b < 70).astype(float)
        ls = (wmin_b + (pmin_s - pmin_b) < 70).astype(float)
        p_hi_s = _shift_prob(hyb["p_high"], hb.mean(), hs_.mean())
        p_lo_s = _shift_prob(hyb["p_low"], lb.mean(), ls.mean())
        n = len(hb)
        hys = {**hyb, "q": qs, "shifted": ss, "p_high": p_hi_s, "p_low": p_lo_s}
        # paired bootstrap over particles: SIMULATION variability of the change (not clinical uncertainty)
        rng = np.random.default_rng(0)
        idx = rng.integers(0, n, (1000, n))
        boots = _shift_prob(hyb["p_high"], hb[idx].mean(axis=1), hs_[idx].mean(axis=1)) - hyb["p_high"]
        cal_delta = p_hi_s - hyb["p_high"]
        lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        pk_b, pk_s = sb[:, :EV_STEPS].max(axis=1), ss[:, :EV_STEPS].max(axis=1)
        peak_b, peak_s = float(np.median(pk_b)), float(np.median(pk_s))
        pk_boot = np.median(pk_s[idx[:300]], axis=1) - np.median(pk_b[idx[:300]], axis=1)
        pk_lo, pk_hi = float(np.percentile(pk_boot, 2.5)), float(np.percentile(pk_boot, 97.5))
        prob_small = bool((lo <= 0 <= hi) or abs(cal_delta) < 0.03)
        peak_small = bool((pk_lo <= 0 <= pk_hi) or abs(peak_s - peak_b) < 5.0)
        too_small = prob_small and peak_small
        fs = self._package(pid, lv, hys, ladder, rev)
        if too_small:
            note = "The difference is within the twin's uncertainty - too small to call."
        elif prob_small:
            note = (f"Your peak changes by {peak_s - peak_b:+.0f} mg/dL, but the chance of going above 180 "
                    "barely changes.")
        else:
            note = f"This change moves your chance of going above 180 by {cal_delta * 100:+.0f} points."
        interval_note = ("Interval = simulation variability (paired bootstrap over the twin's particles), "
                         "not a clinical confidence interval.")
        out = {"baseline": copy.deepcopy(fb), "scenario": fs,
               "delta_p_high": {"mean": round(cal_delta, 3) + 0.0, "lo": round(lo, 3) + 0.0, "hi": round(hi, 3) + 0.0,
                                "interval_kind": "simulation_variability", "note": interval_note},
               "delta_peak": round(peak_s - peak_b, 1),
               "delta_peak_ci": {"lo": round(pk_lo, 1), "hi": round(pk_hi, 1), "interval_kind": "simulation_variability"},
               "too_small_to_call": too_small, "p_high_change_small": prob_small, "note": note,
               "method": "paired mechanistic counterfactual; learned residual shared with the baseline",
               "label_en": "Model simulation — not a proven effect",
               "assumptions_en": _assumptions(base_meal, scenario),
               "baseline_pinned": True}
        sctx = {"kind": "scenario", "pid": pid, "ladder": ladder, "events": events, "meal": base_meal,
                "scenario": scenario, "lv": lv, "out": fs, "offset": int(offset), "rev": rev,
                "baseline_id": fb["forecast_id"]}
        return out, [(fb["forecast_id"], ctx_b), (fs["forecast_id"], sctx)]

    # ------------------------------------------------------------------ body view
    def body(self, pid: str, ladder: str, events: list[dict], meal: dict | None = None,
             scenario: dict | None = None, *, offset: int = 0, rev: dict | None = None) -> dict:
        """Per-organ glucose flows of the mechanistic layer for the 3-D body view.

        The same particles, inputs and random numbers as ``forecast`` (seed 21), so the blood
        values match the chart. Organ flows are SIMULATED by the simplified physiology model;
        only blood glucose is validated (see reports/).
        """
        key = _key("body", pid, ladder, _ev_key(events), meal, scenario, int(offset), rev)
        out = copy.deepcopy(self._cache.get_or(key, lambda: self._body(pid, ladder, events, meal, scenario,
                                                                       offset, rev)))
        # make the baseline forecast addressable by explain / receipt, like forecast() does
        _, ctx = self._forecast_cached(pid, ladder, events, meal, 240, True, offset, rev)
        self._remember(out["baseline"]["forecast_id"], ctx)
        return out

    def _body(self, pid: str, ladder: str, events: list[dict], meal: dict | None, scenario: dict | None,
              offset: int, rev: dict | None) -> dict:
        fb, ctx = self._forecast_cached(pid, ladder, events, meal, 240, True, offset, rev)
        lv, snap, hyb, logged = ctx["lv"], ctx["snap"], ctx["hy"], ctx["logged"]
        variants = [{"meal": meal, "scen": None, "logged": logged}]
        if scenario and meal:
            variants.append({"meal": meal, "scen": scenario, "logged": logged})
        states: list[dict] = []
        self._simulate_many(lv, snap, variants, seed=21, states_out=states)
        origin = lv.b.tl.t[lv.i]
        times = [self._fmt(pid, origin + np.timedelta64(5 * k, "m")) for k in range(FC_STEPS + 1)]
        g0 = snap.x[:, 0]
        now_blood = [float(np.quantile(g0, 0.05)), float(np.median(g0)), float(np.quantile(g0, 0.95))]

        def blood_of(traj: dict) -> dict:
            return {k: _r([now_blood[i], *traj[k]]) for i, k in ((0, "q05"), (1, "q50"), (2, "q95"))}

        base = {"forecast_id": fb["forecast_id"], "blood": blood_of(fb["traj"]),
                "fluxes": _organ_fluxes(states[0]), "learned_correction": _r([0.0, *hyb["r_curve"]])}
        scen_out = None
        scen_label = None
        if len(states) > 1 and meal and scenario:
            w = self.what_if(pid, ladder, events, meal, scenario, offset=offset, rev=rev)
            scen_out = {"forecast_id": w["scenario"]["forecast_id"], "blood": blood_of(w["scenario"]["traj"]),
                        "fluxes": _organ_fluxes(states[1]), "learned_correction": base["learned_correction"]}
            scen_label = scenario.get("label") or "Scenario"
        return {
            "persona_id": pid, "replay_now": self._fmt(pid, origin), "t": times,
            "validated_horizon_min": VALIDATED_HORIZON_MIN,
            "label_en": "Simplified physiology model — not a measurement of your organs",
            "validated_en": "Only blood glucose (the forecast) is validated; organ flows are simulated by the model.",
            "organs": ORGANS, "baseline": base, "scenario": scen_out, "scenario_label": scen_label,
        }

    def _package(self, pid: str, lv: Live, hy: dict, ladder: str, rev: dict | None) -> dict:
        origin = lv.b.tl.t[lv.i]
        times = [self._fmt(pid, origin + np.timedelta64(5 * (k + 1), "m")) for k in range(FC_STEPS)]
        q = hy["q"]
        pk = int(np.argmax(q["q50"][:EV_STEPS]))
        return {"forecast_id": uuid.uuid4().hex[:12], "origin": self._fmt(pid, origin), "horizon_min": FC_STEPS * 5,
                "traj": {"t": times, **{k: _r(q[k]) for k in q}, "validated_horizon_min": VALIDATED_HORIZON_MIN},
                "p_high": p_high_json(hy["p_high"], ladder), "p_low": p_low_json(hy["p_low"]),
                "p_low_validated": False,
                "peak": {"t": times[pk], "value": round(float(q["q50"][pk]), 1)}, "conformal_level": 0.9,
                "abstain": {"flag": hy["abstain"], "reason": None}, "drivers": [],
                "provenance": self._provenance(pid, lv, rev)}

    def outlook_90d(self, pid: str, ladder: str, events: list[dict], *, offset: int = 0,
                    rev: dict | None = None) -> dict:
        key = _key("outlook", pid, ladder, _ev_key(events), int(offset), rev)
        return copy.deepcopy(self._cache.get_or(key, lambda: self._outlook_90d(pid, ladder, events, offset, rev)))

    def _outlook_90d(self, pid: str, ladder: str, events: list[dict], offset: int, rev: dict | None) -> dict:
        """Projection: simulate typical days under current habits vs the top what-if change."""
        lv, pf = self._live(pid, ladder, events, offset, rev)
        b = lv.b
        pf.rng = np.random.default_rng(8)
        snap = pf.snapshot(200)
        steps = 288 * 2
        m = snap.x.shape[0]
        ins = []
        for factor, walk in ((1.0, False), (0.75, True)):
            carbs, slow, mets, hours = NBP.expected_inputs(float(b.tl.hour[lv.i]), steps, b.meal_profile * factor)
            if walk:
                for s_ in np.where(carbs > 15)[0]:
                    mets[s_ + 3: s_ + 6] = 3.5
            ins.append((carbs, slow, mets, hours))
        # both habits on the same particles and noise (paired), one batched run
        rep = lambda k: np.concatenate([np.repeat(a[k][:, None], m, axis=1) for a in ins], axis=1)  # noqa: E731
        out = _propagate_crn(np.concatenate([snap.x, snap.x]), np.exp(np.concatenate([snap.logth, snap.logth])),
                             rep(0), rep(1), rep(2), rep(3), np.random.default_rng(9), 2)
        res = {}
        for k, name in enumerate(("current", "scenario")):
            day2 = out[288:, k * m:(k + 1) * m]
            res[name] = {"tir": float(((day2 >= 70) & (day2 <= 180)).mean()), "mean": float(day2.mean())}
        days = list(range(0, 91, 5))
        hba1c0 = float(b.covariates.get("hba1c", 7.0))

        def gmi(mean_g: float) -> float:
            return 3.31 + 0.02392 * mean_g

        def traj_hba1c(target: float) -> list[float]:
            return [round(float(target + (hba1c0 - target) * np.exp(-d / 40.0)), 2) for d in days]

        ramp = [min(1.0, d / 14.0) for d in days]
        # Anchor "current habits" to what was actually observed over the last 7 days (the same TIR and
        # mean the doctor brief shows); the simulation supplies only the change the scenario makes.
        s7 = self.summary_7d(pid, offset=offset)
        anchored = s7["mean"] is not None
        tir0 = float(s7["tir_7d"]) if anchored else res["current"]["tir"]
        mean0 = float(s7["mean"]) if anchored else res["current"]["mean"]
        d_tir = res["scenario"]["tir"] - res["current"]["tir"]
        d_mean = res["scenario"]["mean"] - res["current"]["mean"]
        tir_c = [round(tir0, 3)] * len(days)
        tir_s = [round(float(np.clip(tir0 + r * d_tir, 0.0, 1.0)), 3) for r in ramp]
        return {"label": "projection", "days": days, "tir_current": tir_c, "tir_scenario": tir_s,
                "ehba1c_current": traj_hba1c(gmi(mean0)),
                "ehba1c_scenario": traj_hba1c(gmi(mean0 + d_mean)),
                "scenario_label": "Smaller rice portions (-25% carbs) and a 15-minute walk after meals",
                "anchor": {"tir_7d": round(tir0, 3), "mean_7d": round(mean0, 1),
                           "source": "observed last 7 days" if anchored else "simulated typical day"},
                "note": ("Projection. 'Current habits' starts from the observed last-7-day time in range and mean "
                         "glucose; the scenario adds the change the twin simulates for a typical day. eHbA1c uses "
                         "the GMI formula (3.31 + 0.02392 x mean glucose), drifting towards it over ~40 days. "
                         "Not a validated HbA1c prediction.")}

    # ------------------------------------------------------------------ dataset reference (historical / evaluation)
    def summary_7d(self, pid: str, offset: int = 0) -> dict:
        """HISTORICAL statistics from the dataset's reference CGM (hidden from the sparse twin) over
        the 7 days before the replay now, plus a 48 h sparkline of the twin's own reconstruction.
        Values are None when no reference CGM is available."""
        b = self.base(pid, "2")
        i = self._now_index(b, offset)
        tv = b.tl.cgm[max(0, i - 7 * 288): i + 1]
        tv = tv[np.isfinite(tv)]
        rec = b.rec[max(0, min(i, b.b0) - 48 * 12): min(i, b.b0) + 1, 0]
        spark = [round(float(v), 0) for v in rec[::12]]
        if len(tv) == 0:
            return {"tir_7d": None, "tar_7d": None, "tbr_7d": None, "mean": None, "gmi": None, "sparkline": spark,
                    "values": tv}
        return {"tir_7d": float(((tv >= 70) & (tv <= 180)).mean()), "tar_7d": float((tv > 180).mean()),
                "tbr_7d": float((tv < 70).mean()), "mean": float(tv.mean()), "gmi": float(3.31 + 0.02392 * tv.mean()),
                "sparkline": spark, "values": tv}

    def daily_profile(self, pid: str, offset: int = 0) -> dict:
        """AGP-style 24 h profile of the dataset reference CGM up to the replay now (historical)."""
        b = self.base(pid, "2")
        i = self._now_index(b, offset)
        df = pd.DataFrame({"t": pd.to_datetime(b.tl.t[: i + 1]), "g": b.tl.cgm[: i + 1]}).dropna()
        labels = [f"{h // 2:02d}:{(h % 2) * 30:02d}" for h in range(48)]
        if df.empty:
            return {"t": labels, **{k: [None] * 48 for k in ("q05", "q25", "q50", "q75", "q95")},
                    "source": "dataset reference CGM (unavailable)"}
        df["bin"] = df.t.dt.hour * 2 + df.t.dt.minute // 30
        g = df.groupby("bin").g
        prof: dict[str, Any] = {k: g.quantile(v).reindex(range(48)).interpolate().bfill().ffill().round(1).tolist()
                                for k, v in (("q05", 0.05), ("q25", 0.25), ("q50", 0.5), ("q75", 0.75), ("q95", 0.95))}
        prof["t"] = labels
        prof["source"] = "dataset reference CGM (historical)"
        return prof

    def reference_at(self, pid: str, offset: int = 0) -> dict | None:
        """The dataset's reference CGM at the replay now (nearest sample within 10 min), hidden
        from the twin until revealed. None if the record has no CGM there."""
        b = self.base(pid, "2")
        i = self._now_index(b, offset)
        best = None
        for d in (0, -1, 1, -2, 2):
            j = i + d
            if 0 <= j < len(b.tl.t) and j <= i + 2 and np.isfinite(b.tl.cgm[j]):
                best = j
                break
        if best is None:
            return None
        return {"t": self._fmt(pid, b.tl.t[best]), "value": round(float(b.tl.cgm[best]), 1),
                "t_min": float(offset) + (best - i) * M.DT}

    def usual_meal_carbs(self, pid: str, start_h: float = 18.0, end_h: float = 23.5) -> float:
        """Average daily carbohydrate eaten between ``start_h`` and ``end_h`` over the calibration days."""
        b = self.base(pid, "2")
        bins = np.arange(48) / 2.0
        sel = (bins >= start_h) & (bins < end_h)
        return round(float(b.meal_profile[sel].sum()), 1)


def _overrides(rev: dict | None) -> dict | None:
    if not rev:
        return None
    fields = rev.get("fields") or {}
    out = {k: float(fields[k]["value"]) for k in REVISION_FIELDS if k in fields and _num(fields[k].get("value")) is not None}
    return out or None


def _ev_key(events: list[dict]) -> list[dict]:
    """Only what the twin uses (times, values, carbs, source) - receipt metadata such as
    received_at or idempotency keys never changes the state or the cache key."""
    keep = ("kind", "value", "t_min", "carbs", "name", "source")
    return [{k: e.get(k) for k in keep if k in e} for e in events]


def _assimilation(before: dict, after: dict, value: float, est_at: float) -> dict:
    wb = before["band"]["hi"] - before["band"]["lo"]
    wa = after["band"]["hi"] - after["band"]["lo"]
    fb, fa = before["forecast"]["traj"], after["forecast"]["traj"]
    k = min(VALIDATED_HORIZON_MIN // 5 - 1, len(fb["q05"]) - 1)
    wfb, wfa = fb["q95"][k] - fb["q05"][k], fa["q95"][k] - fa["q05"][k]

    def sp(b: float, a: float) -> float:
        return round((a - b) / max(b, 1e-6) * 100, 1) + 0.0

    h120 = {"before": round(wfb, 1), "after": round(wfa, 1), "signed_pct": sp(wfb, wfa),
            "horizon_min": VALIDATED_HORIZON_MIN}
    now = {"before": round(wb, 1), "after": round(wa, 1), "signed_pct": sp(wb, wa)}
    return {"state": after, "band_before": before["band"], "band_after": after["band"],
            "width_change": {"now": now, "h120": h120},
            "narrowed_pct": round(-h120["signed_pct"], 1) + 0.0,
            "now_band_narrowed_pct": round(-now["signed_pct"], 1) + 0.0,
            "innovation": round(float(value) - est_at, 1)}


def _assumptions(base_meal: dict, scen: dict) -> list[str]:
    a = ["Same particles and the same random numbers as the baseline (paired simulation); the baseline is the "
         "plain forecast of this meal and does not change between scenarios.",
         f"The meal ({float(base_meal.get('carbs', 0)):.0f} g carbohydrate) is eaten "
         f"{float(base_meal.get('minutes_from_now', 0) or 0):.0f} min after the replay now; no other new meals "
         "in the next 4 hours; activity at rest unless a walk is set.",
         "The learned correction and the uncertainty widening are copied from the baseline: the difference comes "
         "from the physiology model only."]
    if scen.get("carb_scale") not in (None, 1, 1.0):
        a.append(f"Portion: carbohydrate x{float(scen['carb_scale']):g}.")
    if scen.get("carb_delta"):
        a.append(f"Swap: carbohydrate {float(scen['carb_delta']):+.0f} g, with the replacement food's fibre, "
                 "fat and protein from the Indian food table.")
    if scen.get("walk_min"):
        a.append(f"Walk: {float(scen['walk_min']):.0f} min at about 3.5 METs (brisk), starting "
                 f"{float(scen.get('walk_after_min', 15)):.0f} min after the meal.")
    if scen.get("shift_min"):
        a.append(f"Meal time shifted by {float(scen['shift_min']):+.0f} min.")
    a.append("Learned from observational data: the simulated difference is not a proven causal effect.")
    return a


def _people_text(node: dict) -> str | None:
    people = node.get("people") or node.get("train_people") or node.get("participants") or node.get("train_pids")
    n = node.get("n_people") or (len(people) if isinstance(people, list | tuple) else None)
    excl = node.get("excluded_people") or node.get("excluded")
    ds = node.get("dataset") or "CGMacros"
    if n is None and not excl:
        return None
    txt = f"{ds}, {n} people" if n is not None else str(ds)
    if excl:
        txt += f"; excludes the demo-persona source participants ({', '.join(sorted(map(str, excl)))})"
    return txt


def _hybrid_meta(bundle: Any) -> str:
    """What the production hybrid was trained on, as recorded with the artifact (manifest first)."""
    p = MODELS_DIR / "manifest.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            d = {}
        node = d.get("hybrid_trained_on") if isinstance(d, dict) else None
        if isinstance(node, str) and node.strip():
            return node.strip()
        if isinstance(node, dict):
            for k in ("description", "note"):
                if isinstance(node.get(k), str) and node[k].strip():
                    return str(node[k]).strip()
            txt = _people_text(node)
            if txt:
                return txt
    for attr in ("trained_on", "train_note", "training_note"):
        v = getattr(bundle, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    mem = getattr(bundle, "membership", None)
    if isinstance(mem, dict) and mem:
        rows = mem.get("hybrid_training_rows") or mem.get("residual_models") or mem.get("trained_on")
        if isinstance(rows, list | tuple):
            return f"CGMacros, {len(set(rows))} people (membership recorded in the artifact)"
    return "CGMacros production fit (training membership not recorded in the artifact)"


def _logit(p: Any) -> Any:
    p = np.clip(p, 0.01, 0.99)
    return np.log(p / (1 - p))


def _shift_prob(p_cal: float, raw_base: Any, raw_scen: Any) -> Any:
    """Move a calibrated probability by the paired particle change, on the logit scale.

    Keeps the result inside (0, 1) and in the direction the physiology says.
    """
    z = _logit(p_cal) + _logit(raw_scen) - _logit(raw_base)
    out = 1.0 / (1.0 + np.exp(-z))
    same = np.isclose(raw_scen, raw_base)
    out = np.where(same, p_cal, out)
    return float(out) if np.ndim(out) == 0 else out


def _widen(q: dict, scale: np.ndarray) -> dict:
    """Scale the particle quantile band around the median (conformal widening)."""
    q = dict(q)
    for k in ("q05", "q25", "q75", "q95"):
        q[k] = np.clip(q["q50"] + (q[k] - q["q50"]) * scale, 30, 500)
    return q


def _effective_carbs(meal: dict | None, scen: dict | None) -> float:
    """Carbs actually eaten in a (possibly modified) meal."""
    if not meal:
        return 0.0
    scen = scen or {}
    return max(0.0, float(meal.get("carbs", 0.0)) * float(scen.get("carb_scale", 1.0))
               + float(scen.get("carb_delta", 0.0)))


def _single_thread(bundle: HY.HybridBundle) -> None:
    """One-row predictions are dominated by thread start-up; single-threaded is ~10x faster."""
    for mdl in [*bundle.models.values(), bundle.clf_high, bundle.clf_low]:
        if mdl is not None and hasattr(mdl, "set_params"):
            try:
                mdl.set_params(n_jobs=1)
            except (TypeError, ValueError):
                pass


ORGANS: list[dict] = [
    {"key": "stomach", "label_en": "Stomach", "unit": "g carbs",
     "description_en": "Carbohydrate from the meal still waiting in the stomach (first gut compartment).",
     "status": "simulated"},
    {"key": "intestine", "label_en": "Intestine", "unit": "g carbs",
     "description_en": "Carbohydrate being absorbed in the intestine (second gut compartment).", "status": "simulated"},
    {"key": "gut_to_blood", "label_en": "From gut into blood", "unit": "mg/dL per min",
     "description_en": "How fast glucose from food is entering the blood.", "status": "simulated"},
    {"key": "liver", "label_en": "Liver and baseline balance", "unit": "mg/dL per min",
     "description_en": "Pulls glucose back toward your usual level: positive = releasing glucose, "
                       "negative = taking it up.", "status": "simulated"},
    {"key": "pancreas", "label_en": "Pancreas (insulin release)", "unit": "µU/mL per min",
     "description_en": "Insulin released in response to glucose above your usual level.", "status": "simulated"},
    {"key": "insulin", "label_en": "Insulin in blood", "unit": "µU/mL above usual",
     "description_en": "Insulin above your usual level, which helps muscles and fat take up glucose.",
     "status": "simulated"},
    {"key": "insulin_uptake", "label_en": "Muscle and fat uptake (insulin)", "unit": "mg/dL per min",
     "description_en": "Glucose moved out of the blood with the help of insulin.", "status": "simulated"},
    {"key": "exercise_uptake", "label_en": "Muscles working", "unit": "mg/dL per min",
     "description_en": "Extra glucose used by muscles during and after activity such as a walk.",
     "status": "simulated"},
    {"key": "unexplained", "label_en": "Unexplained trend", "unit": "mg/dL per min",
     "description_en": "Recent drift the physiology model cannot explain (stress, illness, unlogged food...).",
     "status": "simulated"},
]


def _organ_fluxes(sv: dict) -> dict:
    """Median and 10-90% range across particles of each organ flow, at 'now' and every 5 min.

    Uses the mechanistic model's own terms (twin/model.py ``_deriv``):
    gut -> blood = F_BIO*1000*(KABS/slow)*Q2/VG; liver/baseline = SG*(GB - G);
    pancreas = GAM*max(G - GB, 0); insulin uptake = X*G; exercise uptake = E*G; drift = D.
    """
    th = sv["theta"]
    SG, GAM, KABS, GB = th[:, 1], th[:, 2], th[:, 3], th[:, 4]

    def terms(x: np.ndarray, slow: np.ndarray | float) -> dict[str, np.ndarray]:
        G, X, Ins, Q1, Q2, E, D = (x[..., k] for k in range(M.N_STATE))
        return {"stomach": Q1, "intestine": Q2,
                "gut_to_blood": M.F_BIO * 1000.0 * (KABS / slow) * Q2 / M.VG_DL,
                "liver": SG * (GB - G), "pancreas": GAM * np.maximum(G - GB, 0.0), "insulin": Ins,
                "insulin_uptake": X * G, "exercise_uptake": E * G, "unexplained": D}

    now = terms(sv["x0"], sv["slow0"])
    later = terms(sv["states"], sv["slow"])
    out = {}
    for k in now:
        series = np.vstack([now[k][None, :], later[k]])  # (H+1, m)
        nd = 2 if k in ("gut_to_blood", "liver", "insulin_uptake", "exercise_uptake", "unexplained") else 1
        out[k] = {q: [round(float(v), nd + 1) for v in np.quantile(series, qq, axis=1)]
                  for q, qq in (("q10", 0.1), ("q50", 0.5), ("q90", 0.9))}
    return out


def _propagate_crn(x: np.ndarray, th: np.ndarray, carbs: np.ndarray, slow: np.ndarray, mets: np.ndarray,
                   hour: np.ndarray, rng: np.random.Generator, n_var: int,
                   record: list[np.ndarray] | None = None) -> np.ndarray:
    """RK4-propagate ``n_var`` stacked copies of the same particle set with shared noise.

    Inputs are per particle, shape (H, n_var * m). Noise is drawn exactly like
    ``filter.forecast_batch`` does for ONE copy (drift noise, then glucose noise, each of
    size m per step) and reused for every copy, so copy k equals a separate
    ``forecast_batch`` run of that variant with the same seed. Returns (H, n_var * m).
    """
    m = x.shape[0] // n_var
    h = carbs.shape[0]
    out = np.empty((h, x.shape[0]))
    for k in range(h):
        u = M.StepInputs(carbs=carbs[k], slow=slow[k], mets=mets[k], hour=hour[k])
        x = M.rk4_step(x, th, u)
        dn = rng.normal(0.0, PF.D_NOISE_SD, m)
        gn = rng.normal(0.0, PF.G_NOISE_SD, m)
        x[:, 6] += np.tile(dn, n_var)
        x[:, 0] = np.clip(x[:, 0] + np.tile(gn, n_var), 30, 600)
        out[k] = x[:, 0]
        if record is not None:
            record.append(x.copy())
    return out


def _r(a: Any) -> list[float]:
    return [round(float(v), 1) for v in np.asarray(a)]


def _nbp_reason(hour: float, meal_profile: np.ndarray) -> str:
    hh = int(hour) % 24
    mm = int(round((hour - int(hour)) * 60)) % 60
    clock = f"{(hh % 12) or 12}:{mm:02d} {'am' if hh < 12 else 'pm'}"
    bins = np.arange(48) / 2.0
    before = [(b, c) for b, c in zip(bins, meal_profile, strict=True) if c > 10 and 0 < (hour - b) % 24 <= 3]
    if before:
        mh = before[-1][0]
        meal = "breakfast" if mh < 11 else ("lunch" if mh < 16 else "dinner")
        return (f"Check at {clock}. About {int(((hour - mh) % 24) * 60)} minutes after your usual {meal}, "
                "a reading tells me most about how strongly you respond to food.")
    if hour < 9:
        return f"Check at {clock}. A fasting reading anchors my estimate of your overnight level."
    return f"Check at {clock}. That is when my picture of your glucose is blurriest, so it will teach me the most."


_ENGINE: TwinEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> TwinEngine:
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = TwinEngine()
    return _ENGINE


def clone_events(events: list[dict]) -> list[dict]:
    return copy.deepcopy(events)
