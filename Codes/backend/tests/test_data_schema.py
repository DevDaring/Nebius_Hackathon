"""Harmonised 5-minute schema (data/processed) and the runtime demo extract (artifacts/)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import HAS_PROCESSED

from nemotwins.config import PROCESSED_DIR
from nemotwins.twin import personas as PS
from nemotwins.twin.engine import DEMO_COVARIATES, DEMO_SERIES

TS_COLS = {
    "pid": "string", "dataset": "string", "t": "datetime", "cgm": "float", "cgm_native": "bool", "cbg": "float",
    "carbs": "float", "protein": "float", "fat": "float", "fibre": "float", "kcal": "float", "meal_type": "string",
    "photo": "string", "hr": "float", "mets": "float",
}
COV_COLS = {
    "pid": "string", "dataset": "string", "age": "float", "sex": "string", "bmi": "float", "hba1c": "float",
    "fasting_glucose": "float", "group": "string", "diabetes_years": "float", "insulin_user": "bool",
}

needs_processed = pytest.mark.skipif(not HAS_PROCESSED, reason="data/processed not available")


def _kind(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_float_dtype(s):
        return "float"
    if pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s):
        return "string"
    return str(s.dtype)


@pytest.fixture(scope="module")
def ts() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "timeseries.parquet")


@pytest.fixture(scope="module")
def cov() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "covariates.parquet")


@needs_processed
def test_timeseries_columns_and_dtypes(ts: pd.DataFrame) -> None:
    for col, kind in TS_COLS.items():
        assert col in ts.columns, col
        assert _kind(ts[col]) == kind, (col, ts[col].dtype)


@needs_processed
def test_covariate_columns_and_dtypes(cov: pd.DataFrame) -> None:
    for col, kind in COV_COLS.items():
        assert col in cov.columns, col
        assert _kind(cov[col]) == kind, (col, cov[col].dtype)


@needs_processed
def test_five_minute_grid_unique_and_sorted_per_patient(ts: pd.DataFrame) -> None:
    assert not ts.duplicated(["pid", "t"]).any()
    d = ts.sort_values(["pid", "t"]).groupby("pid")["t"].diff().dropna()
    assert (d == pd.Timedelta(minutes=5)).all()


@needs_processed
def test_value_ranges(ts: pd.DataFrame) -> None:
    cgm = ts["cgm"].dropna()
    assert cgm.between(39, 500).all()  # sensor reporting range
    assert ts["cgm"].isna().mean() < 0.10
    assert not (ts["cgm_native"] & ts["cgm"].isna()).any()  # native samples always have a value
    for c in ("carbs", "protein", "fat", "fibre", "kcal"):
        assert (ts[c].dropna() >= 0).all(), c
    assert ts["mets"].dropna().between(0.5, 20).all()
    assert ts["hr"].dropna().between(25, 230).all()
    assert set(ts["dataset"].unique()) <= {"cgmacros", "shanghai"}


@needs_processed
# Formerly a strict xfail (a 2044.8 mg/dL capillary reading); fixed by the harmonise.py cleaning.
def test_capillary_glucose_plausible(ts: pd.DataFrame) -> None:
    assert ts["cbg"].dropna().between(20, 600).all()


@needs_processed
# Formerly a strict xfail (> 400 g carb meal steps); fixed by the harmonise.py cleaning.
def test_meal_carbs_plausible(ts: pd.DataFrame) -> None:
    assert (ts["carbs"].dropna() <= 400).all()


@needs_processed
def test_covariate_ranges_and_join(ts: pd.DataFrame, cov: pd.DataFrame) -> None:
    assert cov["pid"].is_unique
    assert set(ts["pid"]) == set(cov["pid"])
    assert cov["age"].dropna().between(18, 100).all()
    assert cov["bmi"].dropna().between(12, 70).all()
    assert cov["hba1c"].dropna().between(3.5, 18).all()
    assert cov.loc[cov["dataset"] == "cgmacros", ["age", "bmi", "hba1c"]].notna().all().all()
    assert set(cov["sex"].unique()) <= {"F", "M"}
    assert set(cov["group"].unique()) <= {"T2D", "prediabetes", "healthy"}
    for p in PS.PERSONAS:  # persona source participants are CGMacros T2D
        row = cov.loc[cov["pid"] == p["source_pid"]].iloc[0]
        assert row["dataset"] == "cgmacros" and row["group"] == "T2D"


@pytest.mark.skipif(not DEMO_SERIES.exists(), reason="run python -m nemotwins.twin.export_demo")
def test_demo_extract_matches_processed() -> None:
    demo = pd.read_parquet(DEMO_SERIES)
    demo_cov = pd.read_parquet(DEMO_COVARIATES)
    assert set(demo["pid"]) == {p["source_pid"] for p in PS.PERSONAS}
    assert set(demo_cov["dataset"]) == {"cgmacros"}
    for col in TS_COLS:
        assert col in demo.columns
    if HAS_PROCESSED:
        full = pd.read_parquet(PROCESSED_DIR / "timeseries.parquet", filters=[("pid", "in", sorted(set(demo["pid"])))])
        a = full.sort_values(["pid", "t"]).reset_index(drop=True)
        b = demo.sort_values(["pid", "t"]).reset_index(drop=True)
        assert len(a) == len(b)
        assert np.allclose(a["cgm"].to_numpy(float), b["cgm"].to_numpy(float), equal_nan=True)
