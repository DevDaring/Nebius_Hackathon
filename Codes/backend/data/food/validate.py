#!/usr/bin/env python3
"""Validate indian_foods.csv and swaps.json.

Checks
  * required columns present, ids unique and snake_case
  * no missing macros; macros and grams non-negative
  * enum columns (cuisine, category, unit, gi_band, method) use allowed values
  * source/method present on every row
  * energy check: 4*carbs + 4*protein + 9*fat within +/-25% of kcal (warning only; ignored when the
    absolute difference is <= 10 kcal, e.g. near-zero-calorie drinks)
  * every swap id exists in the CSV
Exit code 1 on errors (warnings do not fail).

Run:  python3.12 data/food/validate.py
"""
from __future__ import annotations

import json
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "indian_foods.csv")
SWAPS = os.path.join(HERE, "swaps.json")

I18N_NAMES = ["name_es", "name_fr", "name_de", "name_it", "name_ja"]
COLUMNS = ["id", "name_en", "name_bn", "name_hi", "name_kn", *I18N_NAMES, "aliases", "aliases_i18n", "cuisine",
           "category", "unit", "unit_label_en", "grams_per_unit", "carbs_g", "fibre_g", "protein_g", "fat_g", "kcal", "gi_band",
           "source", "method", "notes"]
MACROS = ["carbs_g", "fibre_g", "protein_g", "fat_g", "kcal"]
ENUMS = {
    "cuisine": {"bengali", "north", "karnataka", "south", "pan", "american"},
    "category": {"staple", "dal", "curry", "veg", "nonveg", "snack", "sweet", "beverage", "fruit",
                 "breakfast", "accompaniment"},
    "unit": {"katori", "piece", "plate", "glass", "cup", "bowl", "tbsp", "serving"},
    "gi_band": {"low", "medium", "high", "unknown"},
    "method": {"direct", "per100g_scaled", "recipe_derived"},
}
# Japanese names must contain kana or kanji. (name_bn / name_hi / name_kn are source provenance columns.)
SCRIPT_RANGES = {"name_ja": (0x3040, 0x9FFF)}


def main() -> int:
    errors, warnings = [], []
    df = pd.read_csv(CSV, dtype={"id": str}, keep_default_na=False, na_values=[""])

    missing_cols = [c for c in COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"missing columns: {missing_cols}")
    if list(df.columns) != COLUMNS:
        warnings.append(f"column order differs from spec: {list(df.columns)}")

    dup = df[df["id"].duplicated(keep=False)]["id"].unique().tolist()
    if dup:
        errors.append(f"duplicate ids: {dup}")
    bad_ids = [i for i in df["id"] if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", str(i))]
    if bad_ids:
        errors.append(f"non-snake_case ids: {bad_ids}")

    for c in MACROS + ["grams_per_unit"]:
        na = df[df[c].isna()]["id"].tolist()
        if na:
            errors.append(f"missing {c}: {na}")
        num = pd.to_numeric(df[c], errors="coerce")
        neg = df[num < 0]["id"].tolist()
        if neg:
            errors.append(f"negative {c}: {neg}")

    for c in ("name_en", *I18N_NAMES, "aliases", "aliases_i18n", "unit_label_en", "source", "method"):
        empty = df[df[c].isna() | (df[c].astype(str).str.strip() == "")]["id"].tolist()
        if empty:
            errors.append(f"empty {c}: {empty}")

    for c, allowed in ENUMS.items():
        bad = df[~df[c].isin(allowed)][["id", c]].values.tolist()
        if bad:
            errors.append(f"invalid {c} values: {bad}")

    for c, (lo, hi) in SCRIPT_RANGES.items():
        for i, s in zip(df["id"], df[c].astype(str), strict=True):
            if not any(lo <= ord(ch) <= hi for ch in s):
                warnings.append(f"{i}: {c} '{s}' contains no characters of the expected script")

    # energy consistency
    calc = 4 * df["carbs_g"] + 4 * df["protein_g"] + 9 * df["fat_g"]
    for i, k, cval in zip(df["id"], df["kcal"], calc, strict=True):
        diff = cval - k
        if abs(diff) <= 10:
            continue
        rel = diff / k if k else float("inf")
        if abs(rel) > 0.25:
            warnings.append(f"{i}: 4C+4P+9F = {cval:.0f} vs kcal {k} ({rel:+.0%})")

    # alias sanity: lower-case, no empty tokens
    for col in ("aliases", "aliases_i18n"):
        for i, a in zip(df["id"], df[col].astype(str), strict=True):
            toks = a.split(";")
            if any(t.strip() == "" for t in toks):
                warnings.append(f"{i}: empty {col} token")

    # translated names must be unique within each language (two rows must never share a name)
    for c in I18N_NAMES:
        dup = df[df[c].duplicated(keep=False)][["id", c]].values.tolist()
        if dup:
            errors.append(f"duplicate {c}: {dup}")
    # a translated alias must name ONE food: never on two rows
    owner: dict[str, set] = {}
    for i, a in zip(df["id"], df["aliases_i18n"].astype(str), strict=True):
        for t in a.split(";"):
            if t.strip():
                owner.setdefault(t.strip().lower(), set()).add(i)
    clash = {k: sorted(v) for k, v in owner.items() if len(v) > 1}
    if clash:
        errors.append(f"translated aliases on more than one food: {clash}")

    # swaps
    ids = set(df["id"])
    with open(SWAPS, encoding="utf-8") as f:
        swaps = json.load(f)
    for n, s in enumerate(swaps):
        for k in ("from", "to", "label_en"):
            if k not in s:
                errors.append(f"swap #{n} missing key {k}")
        for k in ("from", "to"):
            if s.get(k) not in ids:
                errors.append(f"swap #{n} {k}='{s.get(k)}' not in CSV")
        for k in ("from_qty", "to_qty"):
            if k in s and not (isinstance(s[k], (int, float)) and s[k] > 0):
                errors.append(f"swap #{n} {k} must be a positive number")

    print(f"rows: {len(df)}  swaps: {len(swaps)}")
    print("by method:", df["method"].value_counts().to_dict())
    print("by cuisine:", df["cuisine"].value_counts().to_dict())
    print("gi_band:", df["gi_band"].value_counts().to_dict())
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print("OK" if not errors else f"FAILED ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
