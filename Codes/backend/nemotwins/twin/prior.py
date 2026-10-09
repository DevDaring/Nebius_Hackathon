"""EHR-conditioned population prior (spec section 4.2, "Tier 0").

1. For each training patient, approximate the personal posterior over the 7
   log-parameters with CEM on the whole CGM record (``fit_patient_params``).
2. Fit a small ridge regression from EHR covariates (age, sex, BMI, HbA1c) to the
   posterior means; the prior variance per parameter is the residual variance of
   that regression (inflated, floored), so a new patient without any CGM starts
   from a covariate-specific prior rather than a single global one.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import multiprocessing as mp
import os
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from nemotwins.config import MODELS_DIR, PROCESSED_DIR
from nemotwins.twin import model as M
from nemotwins.twin.calibrate import cem_fit
from nemotwins.twin.runner import build_timeline

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
COVS = ("age", "sex_f", "bmi", "hba1c")
PARAM_FITS = MODELS_DIR / "param_fits.parquet"


def _cov_matrix(cov: pd.DataFrame) -> np.ndarray:
    c = cov.copy()
    c["sex_f"] = (c["sex"] == "F").astype(float)
    x = c[list(COVS)].astype(float)
    x = x.fillna(x.median())
    return x.to_numpy()


def stable_seed(pid: str) -> int:
    """Per-patient CEM seed that does not depend on PYTHONHASHSEED (``hash(str)`` is salted
    per process, which made ``param_fits.parquet`` differ between runs)."""
    return zlib.crc32(pid.encode()) % 2**31


def _fit_one(args: tuple[str, pd.DataFrame]) -> tuple[str, np.ndarray, np.ndarray]:
    pid, df = args
    tl = build_timeline(df)
    m, s = cem_fit(
        tl, len(tl.t), np.log(M.GENERIC_PRIOR_MEDIAN), M.GENERIC_PRIOR_LOGSD,
        iters=12, k=192, seed=stable_seed(pid),
    )
    return pid, m, s


def fit_all_patients(ts: pd.DataFrame, workers: int = 30) -> pd.DataFrame:
    jobs = [(str(pid), g) for pid, g in ts.groupby("pid")]
    rows = []
    with cf.ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        for pid, m, s in ex.map(_fit_one, jobs, chunksize=1):
            rows.append({"pid": pid, **{f"mu_{p}": m[i] for i, p in enumerate(M.PARAM_NAMES)},
                         **{f"sd_{p}": s[i] for i, p in enumerate(M.PARAM_NAMES)}})
    return pd.DataFrame(rows).sort_values("pid").reset_index(drop=True)


@dataclass
class PopulationPrior:
    coef: np.ndarray  # (n_cov+1, n_param)
    x_mean: np.ndarray
    x_sd: np.ndarray
    resid_sd: np.ndarray  # (n_param,)

    def predict(self, covariates: dict) -> tuple[np.ndarray, np.ndarray]:
        """Return (median, log-sd) for a patient's covariates."""
        row = np.array(
            [
                float(covariates.get("age", np.nan)),
                1.0 if covariates.get("sex") == "F" else 0.0,
                float(covariates.get("bmi", np.nan)),
                float(covariates.get("hba1c", np.nan)),
            ]
        )
        row = np.where(np.isfinite(row), row, self.x_mean)
        z = np.concatenate([[1.0], (row - self.x_mean) / self.x_sd])
        mu = z @ self.coef
        return np.exp(mu), self.resid_sd.copy()

    def to_json(self) -> dict:
        return {k: getattr(self, k).tolist() for k in ("coef", "x_mean", "x_sd", "resid_sd")}

    @classmethod
    def from_json(cls, d: dict) -> PopulationPrior:
        return cls(**{k: np.array(v) for k, v in d.items()})


def fit_prior(fits: pd.DataFrame, cov: pd.DataFrame, alpha: float = 3.0) -> PopulationPrior:
    d = fits.merge(cov, on="pid")
    x = _cov_matrix(d)
    x_mean, x_sd = x.mean(0), x.std(0) + 1e-9
    z = np.hstack([np.ones((len(x), 1)), (x - x_mean) / x_sd])
    y = d[[f"mu_{p}" for p in M.PARAM_NAMES]].to_numpy()
    reg = alpha * np.eye(z.shape[1])
    reg[0, 0] = 0.0
    coef = np.linalg.solve(z.T @ z + reg, z.T @ y)
    resid = y - z @ coef
    # Inflate by 1.25 (out-of-sample) and floor so the prior never becomes overconfident.
    resid_sd = np.maximum(resid.std(0) * 1.25, 0.15)
    resid_sd = np.minimum(resid_sd, M.GENERIC_PRIOR_LOGSD)
    return PopulationPrior(coef, x_mean, x_sd, resid_sd)


def load_fits() -> pd.DataFrame:
    return pd.read_parquet(PARAM_FITS)


def production_people(cov: pd.DataFrame, dataset: str) -> list[str]:
    """People whose fits train the app's production prior for ``dataset``.

    For CGMacros the three persona source participants are EXCLUDED so the demo personas
    are people the production prior (and hybrid) never saw.
    """
    from nemotwins.twin.personas import PERSONAS

    sub = cov[cov.dataset == dataset]
    person = sub["person"] if "person" in sub else sub["pid"]
    held_out = {p["source_pid"] for p in PERSONAS} if dataset == "cgmacros" else set()
    return sorted(set(person) - held_out)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, path)


def main(refit_params: bool = True) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ts = pd.read_parquet(PROCESSED_DIR / "timeseries.parquet")
    cov = pd.read_parquet(PROCESSED_DIR / "covariates.parquet")
    if refit_params or not PARAM_FITS.exists():
        fits = fit_all_patients(ts)
        tmp = PARAM_FITS.with_name(f".{PARAM_FITS.name}.tmp{os.getpid()}")
        fits.to_parquet(tmp, index=False)
        os.replace(tmp, PARAM_FITS)
    else:
        fits = load_fits()
    person = cov.set_index("pid")["person"] if "person" in cov else cov.set_index("pid")["pid"]
    for ds in ("cgmacros", "shanghai"):
        people = set(production_people(cov, ds))
        pids = [p for p in cov.loc[cov.dataset == ds, "pid"] if person[p] in people]
        pr = fit_prior(fits[fits.pid.isin(pids)], cov)
        _atomic_write_text(MODELS_DIR / f"prior_{ds}.json", json.dumps(pr.to_json(), indent=1))
    print(fits.describe().T[["mean", "std"]])


if __name__ == "__main__":
    main(refit_params="--reuse-fits" not in sys.argv[1:])
