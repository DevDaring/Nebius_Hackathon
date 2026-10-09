"""Metrics: accuracy, event discrimination, calibration, coverage, Clarke error grid.

Confidence intervals resample PEOPLE (``person`` column; falls back to ``pid``), so repeat
recordings of one person and the many overlapping forecast windows of one recording are
never treated as independent.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(p)
    return float(np.sqrt(np.mean((y[m] - p[m]) ** 2))) if m.any() else float("nan")


def mard(y: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(p) & (y > 0)
    return float(np.mean(np.abs(p[m] - y[m]) / y[m]) * 100) if m.any() else float("nan")


def auroc(y: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def auprc(y: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, p))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(p)
    return float(np.mean((p[m] - y[m]) ** 2)) if m.any() else float("nan")


def wilson_ci(k: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``k / n``."""
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def reliability(
    y: np.ndarray, p: np.ndarray, bins: int = 10, groups: np.ndarray | None = None,
) -> tuple[list[dict], float]:
    """Reliability-diagram bins and expected calibration error.

    Each bin: edges ``pred_lo``/``pred_hi``, ``mean_pred``, ``observed`` frequency, ``n``
    forecast windows, Wilson 95% interval (``ci_lo``/``ci_hi``) of the observed frequency and,
    when ``groups`` (person ids) is given, ``n_people``.
    """
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    g = np.asarray(groups)[m] if groups is not None else None
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    out: list[dict] = []
    ece = 0.0
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        conf, freq = float(p[sel].mean()), float(y[sel].mean())
        ece += sel.mean() * abs(conf - freq)
        lo, hi = wilson_ci(float(y[sel].sum()), n)
        row = {"bin": b, "pred_lo": float(edges[b]), "pred_hi": float(edges[b + 1]), "mean_pred": conf,
               "observed": freq, "n": n, "ci_lo": lo, "ci_hi": hi}
        if g is not None:
            row["n_people"] = int(len(set(g[sel])))
        out.append(row)
    return out, float(ece)


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> tuple[float, float]:
    m = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    if not m.any():
        return float("nan"), float("nan")
    cov = float(np.mean((y[m] >= lo[m]) & (y[m] <= hi[m])))
    return cov, float(np.mean(hi[m] - lo[m]))


def clarke_zone(ref: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """Clarke error grid zones (Clarke et al., Diabetes Care 1987), vectorised."""
    r, p = np.asarray(ref, float), np.asarray(pred, float)
    zone = np.full(len(r), "B", dtype=object)
    a = (np.abs(p - r) <= 0.2 * r) | ((r < 70) & (p < 70))
    e = ((r <= 70) & (p >= 180)) | ((r >= 180) & (p <= 70))
    c = ((r >= 70) & (r <= 290) & (p >= r + 110)) | ((r >= 130) & (r <= 180) & (p <= (7 / 5) * r - 182))
    d = ((r >= 240) & (p >= 70) & (p <= 180)) | ((r <= 175 / 3) & (p >= 70) & (p <= 180)) | (
        (r >= 175 / 3) & (r <= 70) & (p >= (6 / 5) * r)
    )
    zone[d] = "D"
    zone[c] = "C"
    zone[e] = "E"
    zone[a] = "A"
    return zone


def clarke_summary(ref: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    m = np.isfinite(ref) & np.isfinite(pred)
    z = clarke_zone(ref[m], pred[m])
    return {k: float(np.mean(z == k) * 100) for k in "ABCDE"}


def group_col(df: pd.DataFrame) -> str:
    return "person" if "person" in df else "pid"


def bootstrap_by_person(
    df: pd.DataFrame, fn: Callable[[pd.DataFrame], float], n_boot: int = 500, seed: int = 2026,
) -> tuple[float, float, float]:
    """Point estimate and 95% percentile CI of ``fn(df)``, resampling PEOPLE with replacement
    (all of a resampled person's recordings and forecast windows come along)."""
    rng = np.random.default_rng(seed)
    df = df.reset_index(drop=True)
    groups = {k: idx.to_numpy() for k, idx in df.groupby(group_col(df)).groups.items()}
    keys = np.array(list(groups), dtype=object)
    point = fn(df)
    vals: list[float] = []
    for _ in range(n_boot):
        pick = rng.choice(len(keys), len(keys), replace=True)
        vals.append(fn(df.iloc[np.concatenate([groups[keys[k]] for k in pick])]))
    arr = np.array([v for v in vals if np.isfinite(v)])
    if len(arr) == 0:
        return float(point), float("nan"), float("nan")
    return float(point), float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


# Backwards-compatible name (it always resampled the grouping unit; that unit is now the person).
bootstrap_by_patient = bootstrap_by_person
