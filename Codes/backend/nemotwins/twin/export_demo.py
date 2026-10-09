"""Export the minimal runtime data the app needs, so it runs without raw/processed data.

    python -m nemotwins.twin.export_demo

Writes

* ``artifacts/demo_series.parquet``     - only the 3 persona source trajectories
  (open CGMacros participants) from ``data/processed/timeseries.parquet``;
* ``artifacts/demo_covariates.parquet`` - CGMacros covariates only (the population
  prior and persona EHR fields read these).

``TwinEngine`` loads these when ``data/processed`` is missing (e.g. in a Docker image
that ships ``artifacts/`` but not ``data/``).
"""

from __future__ import annotations

import json

import pandas as pd

from nemotwins.config import PROCESSED_DIR
from nemotwins.twin import personas as PS
from nemotwins.twin.engine import DEMO_COVARIATES, DEMO_SERIES


def export() -> dict:
    ts_p, cov_p = PROCESSED_DIR / "timeseries.parquet", PROCESSED_DIR / "covariates.parquet"
    if not (ts_p.exists() and cov_p.exists()):
        raise FileNotFoundError(f"{ts_p} / {cov_p} not found: run the harmonise step first")
    pids = [p["source_pid"] for p in PS.PERSONAS]
    ts = pd.read_parquet(ts_p, filters=[("pid", "in", pids)])
    missing = sorted(set(pids) - set(ts["pid"].unique()))
    if missing:
        raise ValueError(f"persona source trajectories missing from timeseries.parquet: {missing}")
    ts = ts.sort_values(["pid", "t"]).reset_index(drop=True)
    cov = pd.read_parquet(cov_p)
    cov = cov[cov["dataset"] == "cgmacros"].reset_index(drop=True)
    DEMO_SERIES.parent.mkdir(parents=True, exist_ok=True)
    ts.to_parquet(DEMO_SERIES, index=False)
    cov.to_parquet(DEMO_COVARIATES, index=False)
    return {
        "demo_series": str(DEMO_SERIES), "rows": int(len(ts)), "pids": pids,
        "demo_covariates": str(DEMO_COVARIATES), "covariate_rows": int(len(cov)),
        "bytes": DEMO_SERIES.stat().st_size + DEMO_COVARIATES.stat().st_size,
    }


if __name__ == "__main__":
    print(json.dumps(export(), indent=1))
