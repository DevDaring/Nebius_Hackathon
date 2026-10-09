# Data: sources, licences and harmonised schema

Access date for every source below: **2026-10-05**.

> **No open Indian CGM dataset is known.** The twin was trained and evaluated on US adults
> (CGMacros) and Chinese adults (ShanghaiT2DM). Indian meals are handled through an Indian
> food composition table (`data/food/`), not by pretending the training data is Indian.

Raw and processed research data are **never committed**. Recreate them with:

```bash
make data          # = python -m nemotwins.data.download && python -m nemotwins.data.harmonise
```

| Folder | Content | In git? |
|---|---|---|
| `data/raw/` | Downloaded archives, extracted as published | No |
| `data/processed/` | Harmonised Parquet (`timeseries.parquet`, `covariates.parquet`) | No |
| `data/cache/` | Stage-1 replay cache of the experiments (`nemotwins.eval.stage1`) | No |
| `data/food/` | Indian food table, swaps, build scripts and INDB source files | Yes |

The Docker image does not contain `raw/` or `processed/`; the demo replays the small
persona extracts in `artifacts/` (see `make personas`).

---

## 1. CGMacros v1.0.0 (primary dataset)

- **What:** 45 adults (15 healthy, 16 prediabetes, 14 T2D by lab HbA1c) wearing a Dexcom G6
  and a FreeStyle Libre Pro CGM, with logged meals and macronutrients, meal photographs, an
  activity tracker (heart rate, METs / activity calories) and baseline labs. Records span about
  7 to 19 days per participant (median about 10.6 days).
- **Source:** PhysioNet, https://physionet.org/content/cgmacros/1.0.0/
  (downloaded from the PhysioNet open-data S3 mirror,
  `physionet-open.s3.amazonaws.com/cgmacros/1.0.0/CGMacros_dateshifted365.zip`).
- **DOI:** [10.13026/3z8q-x658](https://doi.org/10.13026/3z8q-x658)
- **Licence:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
  (CC BY-NC-SA 4.0). Non-commercial use only; derived data must be shared under the same licence.
- **Cite:**
  - Gutierrez-Osuna R, Kerr D, Mortazavi B, Das A. *CGMacros: a scientific dataset for
    personalized nutrition and diet monitoring* (version 1.0.0). PhysioNet. 2025.
    https://doi.org/10.13026/3z8q-x658
  - Das A, Kerr D, Glanz N, Bevier W, Santiago R, Gutierrez-Osuna R, Mortazavi B. *CGMacros: a
    scientific dataset for personalized nutrition and diet monitoring.* Scientific Data (under
    review at the time of access, per the PhysioNet page).
  - The PhysioNet platform citation listed on the project page.
- **Used for:** calibration, the sensor-ladder, baseline, calibration-length, next-best-prick,
  subgroup and error-grid experiments, the population prior and the hybrid residual model, and
  the trajectories behind the three synthetic composite demo personas. The Dexcom G6 column
  (`Dexcom GL`) is the reference CGM (see `docs/DESIGN_DECISIONS.md`).

## 2. ShanghaiT2DM (transfer test)

- **What:** CGM recordings (15-minute sampling), capillary blood glucose (finger-prick)
  readings, free-text diet notes and clinical summaries for adults with T2D in Shanghai.
  The archive contains 109 T2DM recordings from 100 patients (some patients have more than one
  recording period) and a separate ShanghaiT1DM set, which is not used.
- **Source:** figshare article 20444397, *Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM*,
  https://doi.org/10.6084/m9.figshare.20444397 (file `data.zip`, version 3).
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Cite:** Zhao Q, Zhu J, Shen X, Lin C, Zhang Y, Liang Y, Cao B, Li J, Liu X, Rao W, Wang C.
  *Chinese diabetes datasets for data-driven machine learning.* Scientific Data. 2023;10:35.
  https://doi.org/10.1038/s41597-023-01940-7
- **Used for:** cross-population transfer (Experiment 5), including the only arm with **real**
  finger-prick readings. Meal carbohydrates are approximated from the English diet notes by
  keyword matching (`SH_CARBS_PER_100G` in `nemotwins/data/harmonise.py`), and insulin use is
  derived from the "Hypoglycemic Agents" column; see `docs/DESIGN_DECISIONS.md`.

## 3. Indian Nutrient Databank (INDB 2024)

- **Source:** https://github.com/lindsayjaacks/Indian-Nutrient-Databank-INDB- (files kept
  unmodified in `data/food/raw/`).
- **Licence:** CC BY 4.0 (the accompanying open-access article is CC BY 4.0 and the data are
  declared freely available; the repository has no separate licence file).
- **Cite:** Vijayakumar A, Dubasi HB, Awasthi A, Jaacks LM. *Development of an Indian Food
  Composition Database.* Current Developments in Nutrition. 2024;8(7):103790.
  https://doi.org/10.1016/j.cdnut.2024.103790
- **Attribution line:** "Contains data from the Indian Nutrient Databank (Vijayakumar et al.,
  2024), CC BY 4.0."

## 4. USDA FoodData Central

- **Source:** https://fdc.nal.usda.gov/ (SR Legacy 2018-04 and FNDDS 2021-2023 survey foods).
- **Licence:** public domain (CC0 1.0); FDC asks for a citation.
- **Cite:** U.S. Department of Agriculture, Agricultural Research Service. *FoodData Central.*

## 5. Indian Food Composition Tables 2017 (IFCT)

- **Source:** Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K. *Indian Food Composition
  Tables 2017.* National Institute of Nutrition (ICMR), Hyderabad.
  https://www.nin.res.in/ifct_book.html
- **Licence:** © ICMR-NIN, **not openly licensed**. We reproduce only the individual
  ingredient values actually used, with attribution, and do not redistribute the table.
  **Permission from NIN is needed before any commercial use.**

Full per-row provenance, unit conversions and the glycaemic-index sources are in
[`data/food/SOURCES.md`](food/SOURCES.md).

---

## Harmonised schema (`data/processed/`)

Written by `python -m nemotwins.data.harmonise`.

### `timeseries.parquet`: one row per patient per 5 minutes

| Column | Type | Meaning |
|---|---|---|
| `pid` | str | Patient/recording id: `cgm001`... (CGMacros), `sh<file stem>` (ShanghaiT2DM, one id per recording) |
| `dataset` | str | `cgmacros` or `shanghai` |
| `t` | datetime | Start of the 5-minute bin (dataset's own, date-shifted clock) |
| `cgm` | float32, mg/dL | Reference CGM: Dexcom G6 (CGMacros) or the study CGM (Shanghai; linearly interpolated inside gaps of at most 30 min) |
| `cgm_native` | bool | True where `cgm` is an actual sensor sample, not interpolation |
| `cbg` | float, mg/dL | Real capillary finger-prick (Shanghai only; NaN for CGMacros) |
| `carbs`, `protein`, `fat`, `fibre` | float, g | Meal macros in the bin where the meal started (CGMacros scaled by "Amount Consumed"; Shanghai carbs approximated, other macros 0) |
| `kcal` | float | Meal energy (CGMacros only) |
| `meal_type` | str | As logged in CGMacros, lower-cased (breakfast, lunch, dinner, snack variants); `meal` for Shanghai |
| `photo` | str | Relative path of the CGMacros meal photo, if any |
| `hr` | float, bpm | Heart rate (CGMacros) |
| `mets` | float | Activity intensity in METs (CGMacros; from METs or activity kcal and body weight) |

### `covariates.parquet`: one row per patient/recording

| Column | Meaning |
|---|---|
| `pid`, `dataset` | As above |
| `age`, `sex` (`F`/`M`), `bmi` | Baseline characteristics |
| `hba1c` | HbA1c in % (Shanghai converted from mmol/mol: % = mmol/mol / 10.929 + 2.15) |
| `fasting_glucose` | mg/dL |
| `group` | `healthy` (<5.7%), `prediabetes` (5.7-6.4%), `T2D` (>=6.5%) for CGMacros; all `T2D` for Shanghai |
| `diabetes_years` | Shanghai only |
| `insulin_user`, `medications` | Shanghai only (CGMacros: `False`, empty) |
| `ethnicity` | Self-identified (CGMacros) or "Chinese (Han, Shanghai)" |
