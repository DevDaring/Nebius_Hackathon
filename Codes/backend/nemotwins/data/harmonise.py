"""Harmonise CGMacros and ShanghaiT2DM into one 5-minute schema.

Output (``data/processed``):

* ``timeseries.parquet`` - one row per patient per 5 minutes::

    pid, dataset, t, cgm, cgm_native, cbg, carbs, protein, fat, fibre, kcal,
    meal_type, photo, hr, mets

  ``cgm`` is the reference sensor (Dexcom G6 for CGMacros, the study CGM for
  Shanghai). ``cgm_native`` is True where the value is an actual sensor sample
  rather than linear interpolation (Shanghai samples every 15 min). ``cbg`` is a
  real capillary finger-prick (Shanghai only). Meal macros sit on the 5-min bin in
  which the meal started.

* ``covariates.parquet`` - one row per patient (age, sex, BMI, HbA1c %, group...).

Run ``python -m nemotwins.data.harmonise``.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from nemotwins.config import PROCESSED_DIR, RAW_DIR

STEP = "5min"


# ----------------------------------------------------------------------------- CGMacros
def _cgmacros_root() -> Path:
    hits = list((RAW_DIR / "cgmacros").glob("**/bio.csv"))
    if not hits:
        raise FileNotFoundError("CGMacros not found; run `make data` (nemotwins.data.download)")
    return hits[0].parent


def _mets(x: pd.DataFrame, weight_kg: float | None) -> pd.Series:
    """Activity intensity in METs.

    CGMacros stores METs x10 (10 == 1.0 MET); some participants have no METs column,
    for them METs ~ activity kcal/min * 60 / body-weight-kg.
    """
    if "METs" in x:
        return x["METs"] / 10.0
    if "Calories (Activity)" in x and weight_kg:
        return (x["Calories (Activity)"] * 60.0 / weight_kg).clip(0.8, 15)
    return pd.Series(np.nan, index=x.index)


def load_cgmacros() -> tuple[pd.DataFrame, pd.DataFrame]:
    root = _cgmacros_root()
    bio = pd.read_csv(root / "bio.csv")
    bio.columns = [c.strip() for c in bio.columns]
    # bio.csv body weight is in lb
    weights = dict(zip(bio["subject"].astype(int), bio["Body weight"].astype(float) * 0.4536, strict=True))
    frames = []
    for f in sorted(root.glob("CGMacros-*/CGMacros-*.csv")):
        sid = int(f.stem.split("-")[1])
        x = pd.read_csv(f, parse_dates=["Timestamp"]).sort_values("Timestamp")
        x = x.set_index("Timestamp")
        amount = x.get("Amount Consumed", pd.Series(100.0, index=x.index)).fillna(100.0).clip(0, 100) / 100.0
        meals = x.loc[x["Meal Type"].notna() | x["Carbs"].notna()]
        g = pd.DataFrame(
            {
                "cgm": x["Dexcom GL"].resample(STEP).mean(),
                "hr": x["HR"].resample(STEP).mean(),
                "mets": _mets(x, weights.get(sid)).resample(STEP).mean(),
            }
        )
        g["cgm_native"] = g["cgm"].notna()
        g["cbg"] = np.nan
        for col, src in [
            ("carbs", "Carbs"),
            ("protein", "Protein"),
            ("fat", "Fat"),
            ("fibre", "Fiber"),
            ("kcal", "Calories"),
        ]:
            vals = (meals[src].fillna(0) * amount.loc[meals.index]).resample(STEP).sum()
            g[col] = vals.reindex(g.index).fillna(0.0)
        mt = meals["Meal Type"].dropna().astype(str).str.strip().str.lower()
        g["meal_type"] = mt.resample(STEP).first().reindex(g.index)
        ph = meals["Image path"].dropna().astype(str)
        g["photo"] = ph.resample(STEP).first().reindex(g.index).map(
            lambda p, s=sid: f"CGMacros-{s:03d}/{p}" if isinstance(p, str) else None
        )
        g["pid"] = f"cgm{sid:03d}"
        g["dataset"] = "cgmacros"
        frames.append(g.reset_index().rename(columns={"Timestamp": "t"}))
    ts = pd.concat(frames, ignore_index=True)

    a1c = bio["A1c PDL (Lab)"].astype(float)
    cov = pd.DataFrame(
        {
            "pid": bio["subject"].map(lambda s: f"cgm{int(s):03d}"),
            "dataset": "cgmacros",
            "age": bio["Age"].astype(float),
            "sex": bio["Gender"].str.strip().str.upper().str[0],
            "bmi": bio["BMI"].astype(float),
            "hba1c": a1c,
            "fasting_glucose": pd.to_numeric(bio["Fasting GLU - PDL (Lab)"], errors="coerce"),
            "group": np.where(a1c >= 6.5, "T2D", np.where(a1c >= 5.7, "prediabetes", "healthy")),
            "diabetes_years": np.nan,
            "insulin_user": False,
            "medications": "",
            "ethnicity": bio["Self-identify"].astype(str).str.strip(),
            "person": bio["subject"].map(lambda s: f"cgm{int(s):03d}"),
        }
    )
    return ts, cov


# ----------------------------------------------------------------------------- Shanghai
# Approximate carbohydrate grams per 100 g as eaten, for keyword matching of the
# English diet notes in ShanghaiT2DM. Values are rounded from USDA FoodData Central
# generic entries (e.g. cooked white rice 28 g, steamed bun ~47 g, boiled noodles 25 g,
# whole milk 5 g). This is an approximation; see docs/DESIGN_DECISIONS.md.
SH_CARBS_PER_100G: list[tuple[str, float]] = [
    ("rice in soup", 12), ("porridge", 10), ("congee", 10), ("millet porridge", 10),
    ("fried rice", 30), ("rice", 28), ("coarse grain steamed bread", 45),
    ("steamed bread", 47), ("steamed bun", 47), ("pork bun", 40), ("vegetable bun", 40),
    ("bun", 45), ("buckwheat bread", 45), ("bread", 49), ("buckwheat noodles", 24),
    ("noodles", 25), ("noodle", 25), ("wonton", 25), ("dumpling", 25), ("cake", 50),
    ("biscuit", 70), ("cracker", 70), ("cereal", 70), ("oat", 60), ("coarse grain", 30),
    ("corn", 19), ("sweet potato", 20), ("potato", 17), ("taro", 26), ("yam", 27),
    ("pumpkin", 7), ("bean curd roll", 6), ("tofu", 3), ("soybean milk", 3), ("soy milk", 3),
    ("yogurt", 12), ("milk", 5), ("beer", 4), ("juice", 11), ("banana", 23),
    ("apple", 14), ("orange", 12), ("peach", 10), ("pear", 15), ("grape", 18),
    ("watermelon", 8), ("kiwi", 15), ("fruit", 13), ("tomato", 4), ("cucumber", 4),
    ("vegetable", 5), ("cabbage", 5), ("lettuce", 3), ("spinach", 4), ("gourd", 4),
    ("radish", 4), ("eggplant", 6), ("cauliflower", 5), ("celery", 3), ("mushroom", 3),
    ("egg", 1), ("fish", 0), ("shrimp", 0), ("beef", 0), ("pork", 1), ("chicken", 0),
    ("duck", 0), ("meat", 1), ("hairtail", 0), ("sea cucumber", 1), ("soup", 3),
    ("coffee", 0), ("tea", 0),
]
DEFAULT_UNKNOWN_MEAL_CARBS = 50.0


def _parse_meal_carbs(text: str) -> float:
    total = 0.0
    any_known = False
    for raw in str(text).split("\n"):
        item = raw.strip().lower()
        if not item:
            continue
        if "not available" in item:
            return DEFAULT_UNKNOWN_MEAL_CARBS
        m = re.search(r"(\d+(?:\.\d+)?)\s*(g|ml)\b", item)
        grams = float(m.group(1)) if m else 100.0
        for key, per100 in SH_CARBS_PER_100G:
            if key in item:
                total += grams * per100 / 100.0
                any_known = True
                break
    return total if any_known else DEFAULT_UNKNOWN_MEAL_CARBS


def _shanghai_root() -> Path:
    hits = list((RAW_DIR / "shanghai").glob("**/Shanghai_T2DM_Summary.xlsx"))
    if not hits:
        raise FileNotFoundError("ShanghaiT2DM not found; run `make data`")
    return hits[0].parent


def load_shanghai() -> tuple[pd.DataFrame, pd.DataFrame]:
    root = _shanghai_root()
    summ = pd.read_excel(root / "Shanghai_T2DM_Summary.xlsx")
    summ.columns = [str(c).strip() for c in summ.columns]
    frames = []
    for f in sorted((root / "Shanghai_T2DM").glob("*.xls*")):
        if f.name.startswith("~$"):
            continue
        x = pd.read_excel(f)
        x.columns = [str(c).strip() for c in x.columns]
        x = x.rename(columns={"CGM": "CGM (mg / dl)", "CBG": "CBG (mg / dl)"})
        x["Date"] = pd.to_datetime(x["Date"])
        x = x.sort_values("Date").drop_duplicates("Date").set_index("Date")
        cgm = pd.to_numeric(x["CGM (mg / dl)"], errors="coerce")
        native = cgm.resample(STEP).mean()
        g = pd.DataFrame({"cgm_raw": native})
        g["cgm_native"] = g["cgm_raw"].notna()
        # Linear interpolation strictly between native samples, at most 30 min gaps.
        g["cgm"] = g["cgm_raw"].interpolate(limit=6, limit_area="inside")
        g = g.drop(columns="cgm_raw")
        cbg = pd.to_numeric(x.get("CBG (mg / dl)"), errors="coerce")
        g["cbg"] = cbg.dropna().resample(STEP).mean().reindex(g.index)
        diet_col = "Dietary intake"
        meals = x[diet_col].dropna() if diet_col in x else pd.Series(dtype=object)
        carbs = meals.map(_parse_meal_carbs)
        g["carbs"] = carbs.resample(STEP).sum().reindex(g.index).fillna(0.0)
        for col in ["protein", "fat", "fibre", "kcal"]:
            g[col] = 0.0
        g["meal_type"] = None
        g.loc[g["carbs"] > 0, "meal_type"] = "meal"
        g["photo"] = None
        g["hr"] = np.nan
        g["mets"] = np.nan
        g["pid"] = "sh" + f.stem.replace("_", "-")
        g["dataset"] = "shanghai"
        frames.append(g.reset_index().rename(columns={"Date": "t"}))
    ts = pd.concat(frames, ignore_index=True)

    agents = summ["Hypoglycemic Agents"].astype(str).str.lower()
    insulin_words = "insulin|humulin|novolin|gansulin|lantus|glargine|aspart|lispro|degludec|detemir|novorapid|levemir|toujeo|tresiba|humalog|30r|50r|70/30|40r"
    a1c_mmol = pd.to_numeric(summ["HbA1c (mmol/mol)"], errors="coerce")
    cov = pd.DataFrame(
        {
            "pid": "sh" + summ["Patient Number"].astype(str).str.replace("_", "-"),
            "dataset": "shanghai",
            "age": pd.to_numeric(summ["Age (years)"], errors="coerce"),
            "sex": summ["Gender (Female=1, Male=2)"].map({1: "F", 2: "M"}),
            "bmi": pd.to_numeric(summ["BMI (kg/m2)"], errors="coerce"),
            "hba1c": (a1c_mmol / 10.929 + 2.15).round(2),
            "fasting_glucose": pd.to_numeric(summ["Fasting Plasma Glucose (mg/dl)"], errors="coerce"),
            "group": "T2D",
            "diabetes_years": pd.to_numeric(summ["Duration of diabetes (years)"], errors="coerce"),
            "insulin_user": agents.str.contains(insulin_words, regex=True),
            # several recordings can belong to one person: 2044_0_..., 2044_1_...
            "person": "sh" + summ["Patient Number"].astype(str).str.split("_").str[0],
            "medications": summ["Hypoglycemic Agents"].astype(str).str.strip(),
            "ethnicity": "Chinese (Han, Shanghai)",
        }
    )
    return ts, cov


CBG_RANGE = (20.0, 600.0)  # glucometer measuring range; outside = transcription error
MAX_MEAL_CARBS = 300.0  # g per 5-min step; larger values are logging errors


def clean(ts: pd.DataFrame) -> pd.DataFrame:
    """Remove physiologically impossible values (documented in docs/DESIGN_DECISIONS.md).

    * capillary readings outside the glucometer range (e.g. one 2044.8 mg/dL entry);
    * meal carbs above MAX_MEAL_CARBS g per step. When kcal is recorded, carbs are
      re-derived as 50% of energy (4 kcal/g); otherwise capped.
    """
    ts = ts.copy()
    bad = ~ts["cbg"].between(*CBG_RANGE) & ts["cbg"].notna()
    ts.loc[bad, "cbg"] = np.nan
    big = ts["carbs"] > MAX_MEAL_CARBS
    est = (ts["kcal"] * 0.5 / 4.0).where(ts["kcal"] > 0)
    ts.loc[big, "carbs"] = np.minimum(est[big].fillna(MAX_MEAL_CARBS), MAX_MEAL_CARBS)
    if bad.any() or big.any():
        print(f"clean: dropped {int(bad.sum())} out-of-range finger-pricks, fixed {int(big.sum())} meal carb values")
    return ts


def harmonise() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    parts_ts, parts_cov = [], []
    for loader in (load_cgmacros, load_shanghai):
        ts, cov = loader()
        parts_ts.append(ts)
        parts_cov.append(cov)
        print(f"{loader.__name__}: {ts.pid.nunique()} patients, {len(ts)} rows")
    ts = pd.concat(parts_ts, ignore_index=True)
    cov = pd.concat(parts_cov, ignore_index=True)
    cov = cov[cov.pid.isin(ts.pid.unique())].reset_index(drop=True)
    cols = ["pid", "dataset", "t", "cgm", "cgm_native", "cbg", "carbs", "protein", "fat",
            "fibre", "kcal", "meal_type", "photo", "hr", "mets"]
    ts = clean(ts[cols]).sort_values(["pid", "t"]).reset_index(drop=True)
    ts["cgm"] = ts["cgm"].astype("float32")
    ts.to_parquet(PROCESSED_DIR / "timeseries.parquet", index=False)
    cov.to_parquet(PROCESSED_DIR / "covariates.parquet", index=False)
    print(f"wrote {PROCESSED_DIR}/timeseries.parquet ({len(ts)} rows) and covariates.parquet")


if __name__ == "__main__":
    harmonise()
