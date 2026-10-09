"""Learned residual, conformal bands, calibrated event probabilities, abstain
(spec section 4.3).

* Residual model: LightGBM per horizon predicts (true - mechanistic median) from the
  twin's state summary, time since last observation, meals, activity, time of day.
* Conformal: normalised split conformal. Score = |y - yhat| / (particle sd + 5),
  quantiles stratified by sensor-ladder level x hours-since-last-reading bin x horizon,
  computed on out-of-fold predictions of training patients only.
* Events: the particle ensemble's 2-h max/min is shifted by the predicted residual,
  giving raw P(>180) / P(<70), then isotonic-calibrated (out-of-fold).
* Abstain: Mahalanobis distance of the feature vector beyond the training 99th
  percentile, or effective particle fraction below 2%.

Inner folds (out-of-fold predictions for conformal, isotonic and the stacked classifier)
are grouped by PERSON (``o["person"]`` when present, else ``pid``), so repeat recordings
of one person never straddle an inner train/test split. ``HybridBundle.membership``
records which people every fitted component was trained on (audited in
``artifacts/manifest.json``).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from nemotwins.twin.runner import HORIZONS

warnings.filterwarnings("ignore", message="X does not have valid feature names")

LADDER_NUM = {"full": 288.0, "4": 4.0, "2": 2.0, "1": 1.0, "0": 0.0}
HS_BINS = (0.0, 1.0, 4.0, 8.0, 1e9)
ALPHA = 0.10
SD_FLOOR = 5.0

BASE_FEATS = [
    "est", "est_sd", "slope30", "hs_cap", "last_minus_est", "carbs_now", "carbs_2h", "carbs_4h",
    "slow_now", "mets_1h", "hour_sin", "hour_cos", "ladder_num", "peak_med", "p_high_raw",
    "p_low_raw", "ess", "calib_mean", "calib_sd", "est_minus_calib", "last_or_mean",
]
CLF_EXTRA = ["p_adj"]
COV_FEATS = ["age", "bmi", "hba1c"]
ABSTAIN_FEATS = ["est", "est_sd", "hs_cap", "carbs_2h", "ladder_num", "calib_mean"]

# ``deterministic`` + ``force_row_wise`` make repeated fits bit-identical (same model maths).
LGB_PARAMS: dict[str, Any] = dict(
    n_estimators=250, learning_rate=0.04, num_leaves=15, min_child_samples=60,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1,
    deterministic=True, force_row_wise=True,
)


def add_features(o: pd.DataFrame) -> pd.DataFrame:
    o = o.copy()
    o["hs_cap"] = o["hours_since_obs"].clip(upper=48.0)
    last = o["last_obs"].where(np.isfinite(o["last_obs"]), o["est"])
    o["last_minus_est"] = last - o["est"]
    o["hour_sin"] = np.sin(2 * np.pi * o["hour"] / 24)
    o["hour_cos"] = np.cos(2 * np.pi * o["hour"] / 24)
    o["ladder_num"] = o["ladder"].map(LADDER_NUM).astype(float)
    o["est_minus_calib"] = o["est"] - o["calib_mean"]
    o["last_or_mean"] = o["last_obs"].where(np.isfinite(o["last_obs"]), o["calib_mean"])
    for c in COV_FEATS:
        if c not in o:
            o[c] = np.nan
    return o


def feats(with_cov: bool = True) -> list[str]:
    return BASE_FEATS + (COV_FEATS if with_cov else [])


def hs_bin(hs: np.ndarray, ladder: pd.Series) -> np.ndarray:
    b = np.digitize(np.asarray(hs, float), HS_BINS[1:-1])
    return np.where(ladder.to_numpy() == "full", -1, b)


@dataclass
class HybridBundle:
    models: dict[int, lgb.LGBMRegressor] = field(default_factory=dict)
    q: dict[tuple[str, int, int], float] = field(default_factory=dict)
    q_fallback: dict[int, float] = field(default_factory=dict)
    iso_high: IsotonicRegression | None = None
    iso_low: IsotonicRegression | None = None
    clf_high: lgb.LGBMClassifier | None = None
    clf_low: lgb.LGBMClassifier | None = None
    ab_mean: np.ndarray | None = None
    ab_icov: np.ndarray | None = None
    ab_thresh: float = np.inf
    with_cov: bool = True
    # people (``person`` ids) each fitted component was trained on; see ``fit_hybrid``
    membership: dict[str, Any] = field(default_factory=dict)

    # -------------------------------------------------------------- prediction
    def residuals(self, o: pd.DataFrame) -> dict[int, np.ndarray]:
        x = o[feats(self.with_cov)].to_numpy(float)
        return {h: np.asarray(self.models[h].predict(x)) for h in HORIZONS}

    def apply(self, o: pd.DataFrame, pmax: np.ndarray, pmin: np.ndarray) -> pd.DataFrame:
        o = add_features(o)
        res = self.residuals(o)
        bins = hs_bin(o["hours_since_obs"], o["ladder"])
        for h in HORIZONS:
            pred = o[f"med_{h}"].to_numpy() + res[h]
            scale = o[f"sd_{h}"].to_numpy() + SD_FLOOR
            qs = np.array([
                self.q.get((lad, int(b), h), self.q_fallback[h]) for lad, b in zip(o["ladder"], bins, strict=True)
            ])
            o[f"pred_{h}"] = pred
            o[f"res_{h}"] = res[h]
            o[f"lo_{h}"] = np.maximum(pred - qs * scale, 30)
            o[f"hi_{h}"] = pred + qs * scale
        shift = np.mean([res[h] for h in HORIZONS], axis=0)
        o["p_high_adj"] = (pmax.astype(float) + shift[:, None] > 180).mean(axis=1)
        o["p_low_adj"] = (pmin.astype(float) + shift[:, None] < 70).mean(axis=1)
        o["p_high"] = self._event_prob(o, "high")
        o["p_low"] = self._event_prob(o, "low")
        o["abstain"] = self.abstain_flags(o)
        return o

    def _event_prob(self, o: pd.DataFrame, which: str) -> np.ndarray:
        """Stacked classifier on twin features + particle probability, then isotonic."""
        clf = getattr(self, f"clf_{which}")
        iso = getattr(self, f"iso_{which}")
        raw = o[f"p_{which}_adj"].to_numpy(float)
        if clf is not None:
            raw = clf.predict_proba(_clf_x(o, which, self.with_cov))[:, 1]
        return iso.predict(raw) if iso is not None else raw

    def abstain_flags(self, o: pd.DataFrame) -> np.ndarray:
        if self.ab_mean is None or self.ab_icov is None:
            return np.zeros(len(o), bool)
        z = o[ABSTAIN_FEATS].to_numpy(float) - self.ab_mean
        z = np.nan_to_num(z)
        d2 = np.einsum("ij,jk,ik->i", z, self.ab_icov, z)
        return (d2 > self.ab_thresh) | (o["ess"].to_numpy() < 0.02)


MIN_EVENT_PATIENTS = 15
CLF_PARAMS: dict[str, Any] = dict(LGB_PARAMS, min_child_samples=120, n_estimators=200)


def person_ids(o: pd.DataFrame) -> pd.Series:
    """Person id per row (repeat recordings of one person share it); falls back to ``pid``."""
    return (o["person"] if "person" in o else o["pid"]).astype(str)


def inner_fold_of(o: pd.DataFrame, inner_folds: int, seed: int) -> np.ndarray:
    """Inner fold per row, assigned per PERSON (shuffled with ``seed``)."""
    people = np.array(sorted(person_ids(o).unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(people)
    fold_of = {p: k % inner_folds for k, p in enumerate(people)}
    return person_ids(o).map(fold_of).to_numpy()


def _people(o: pd.DataFrame, mask: np.ndarray | None = None) -> list[str]:
    s = person_ids(o)
    return sorted(set(s[mask] if mask is not None else s))


def _clf_x(o: pd.DataFrame, which: str, with_cov: bool) -> np.ndarray:
    x = o[feats(with_cov)].to_numpy(float)
    return np.hstack([x, o[[f"p_{which}_adj"]].to_numpy(float)])


def _fit_clf(o: pd.DataFrame, which: str, with_cov: bool, seed: int) -> lgb.LGBMClassifier | None:
    y = o[f"ev_{which}"].to_numpy(float)
    m = np.isfinite(y)
    if m.sum() < 100 or y[m].sum() < 20 or y[m].sum() > m.sum() - 20:
        return None
    # Events must come from enough different patients, otherwise the classifier learns
    # individual quirks (CGMacros has lows in only 9 of 45 participants).
    if person_ids(o)[m & (y == 1)].nunique() < MIN_EVENT_PATIENTS:
        return None
    cols = [*feats(with_cov), f"p_{which}_adj"]
    mono = _mono(cols, 1 if which == "high" else -1)
    mono[-1] = 1  # the particle probability is monotone in its own event
    clf = lgb.LGBMClassifier(random_state=seed, monotone_constraints=mono, **CLF_PARAMS)
    clf.fit(_clf_x(o, which, with_cov)[m], y[m].astype(int))
    return clf


MONO_UP = ("carbs_now", "carbs_2h", "carbs_4h")  # more carbohydrate never lowers glucose


def _mono(cols: list[str], sign: int = 1) -> list[int]:
    return [sign if c in MONO_UP else 0 for c in cols]


def _fit_models(o: pd.DataFrame, with_cov: bool, seed: int = 0) -> dict[int, lgb.LGBMRegressor]:
    x = o[feats(with_cov)].to_numpy(float)
    models: dict[int, lgb.LGBMRegressor] = {}
    for h in HORIZONS:
        y = (o[f"true_{h}"] - o[f"med_{h}"]).to_numpy(float)
        m = np.isfinite(y)
        mdl = lgb.LGBMRegressor(random_state=seed, monotone_constraints=_mono(feats(with_cov)), **LGB_PARAMS)
        mdl.fit(x[m], y[m])
        models[h] = mdl
    return models


def fit_hybrid(
    o: pd.DataFrame, pmax: np.ndarray, pmin: np.ndarray, with_cov: bool = True, inner_folds: int = 3,
    seed: int = 0,
) -> HybridBundle:
    """Fit on training patients only. Conformal + isotonic use inner out-of-fold preds
    (inner folds grouped by person)."""
    o = add_features(o).reset_index(drop=True)
    inner = inner_fold_of(o, inner_folds, seed)
    everyone = _people(o)
    membership: dict[str, Any] = {
        "residual_models": everyone, "conformal": everyone, "abstain": everyone,
        "inner_folds": [{"k": k, "trained_on": _people(o, inner != k), "predicted": _people(o, inner == k)}
                        for k in range(inner_folds)],
    }
    oof = {h: np.full(len(o), np.nan) for h in HORIZONS}
    for k in range(inner_folds):
        tr, te = inner != k, inner == k
        models = _fit_models(o[tr], with_cov, seed)
        x = o.loc[te, feats(with_cov)].to_numpy(float)
        for h in HORIZONS:
            oof[h][te] = models[h].predict(x)
    shift_oof = np.mean([oof[h] for h in HORIZONS], axis=0)
    o["p_high_adj"] = (pmax.astype(float) + shift_oof[:, None] > 180).mean(axis=1)
    o["p_low_adj"] = (pmin.astype(float) + shift_oof[:, None] < 70).mean(axis=1)
    clf_oof = {w: o[f"p_{w}_adj"].to_numpy(float).copy() for w in ("high", "low")}
    for k in range(inner_folds):
        tr, te = inner != k, inner == k
        for w in ("high", "low"):
            c = _fit_clf(o[tr], w, with_cov, seed)
            if c is not None:
                clf_oof[w][te] = np.asarray(c.predict_proba(_clf_x(o[te], w, with_cov)))[:, 1]

    b = HybridBundle(models=_fit_models(o, with_cov, seed), with_cov=with_cov, membership=membership)
    bins = hs_bin(o["hours_since_obs"], o["ladder"])
    for h in HORIZONS:
        pred = o[f"med_{h}"].to_numpy() + oof[h]
        score = np.abs(o[f"true_{h}"].to_numpy() - pred) / (o[f"sd_{h}"].to_numpy() + SD_FLOOR)
        ok = np.isfinite(score)
        b.q_fallback[h] = _conformal_q(score[ok])
        frame = pd.DataFrame({"lad": o["ladder"], "bin": bins, "s": score})[ok]
        for (lad, bn), g in frame.groupby(["lad", "bin"]):
            if len(g) >= 50:
                b.q[(lad, int(bn), h)] = _conformal_q(g["s"].to_numpy())
    b.clf_high = _fit_clf(o, "high", with_cov, seed)
    b.clf_low = _fit_clf(o, "low", with_cov, seed)
    for w in ("high", "low"):
        membership[f"classifier_{w}"] = everyone if getattr(b, f"clf_{w}") is not None else None
    p_hi = clf_oof["high"] if b.clf_high is not None else o["p_high_adj"].to_numpy(float)
    p_lo = clf_oof["low"] if b.clf_low is not None else o["p_low_adj"].to_numpy(float)
    for attr, p, ycol in (("iso_high", p_hi, "ev_high"), ("iso_low", p_lo, "ev_low")):
        y = o[ycol].to_numpy(float)
        m = np.isfinite(y)
        if m.sum() > 50 and len(np.unique(y[m])) == 2:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(p[m], y[m])
            setattr(b, attr, iso)
            membership[attr] = _people(o, m)
    xa = np.nan_to_num(o[ABSTAIN_FEATS].to_numpy(float))
    b.ab_mean = xa.mean(axis=0)
    cov = np.cov(xa.T) + 1e-6 * np.eye(xa.shape[1])
    b.ab_icov = np.linalg.inv(cov)
    z = xa - b.ab_mean
    d2 = np.einsum("ij,jk,ik->i", z, b.ab_icov, z)
    b.ab_thresh = float(np.quantile(d2, 0.99))
    return b


def _conformal_q(scores: np.ndarray, alpha: float = ALPHA) -> float:
    n = len(scores)
    if n == 0:
        return 1.645
    k = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, k))
