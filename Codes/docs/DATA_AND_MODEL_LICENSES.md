# Data, model and asset licences

Checked 2026-10-08. The MIT licence in `LICENSE` covers **source code only**. Datasets, derived
artefacts, models, photographs and fonts keep their own terms, listed below. Attribution alone is
not permission: rows marked ⚠ need a decision by the project owner (and, where noted, the
competition organisers) before public redistribution.

## Datasets and derived artefacts

| Asset | Source / version | Licence | Redistribution in this repository | Where used |
|---|---|---|---|---|
| CGMacros | PhysioNet, v1.0.0, doi:10.13026/3z8q-x658 | CC BY-NC-SA 4.0 | Raw data **not** included (`make data` downloads it). ⚠ Derived artefacts **are** included and inherit NC-SA: `backend/artifacts/demo_series.parquet`, `demo_covariates.parquet`, `param_fits.parquet`, `prior_cgmacros.json`, `hybrid_cgmacros.pkl`, `persona_states/*.pkl`, and the metric reports in `backend/reports/`. They must be shared under CC BY-NC-SA 4.0 and used non-commercially; calling the personas "synthetic" does not remove these conditions. | Twin calibration, population prior, learned residual, all CGMacros experiments, the three demo personas |
| ShanghaiT2DM | figshare 20444397 v3, doi:10.6084/m9.figshare.20444397 | CC BY 4.0 | Raw data not included; `prior_shanghai.json` and transfer reports included with attribution | Cross-population transfer test |
| Indian Nutrient Databank (INDB 2024) | github.com/lindsayjaacks/Indian-Nutrient-Databank-INDB- (commit fbdb62b) | CC BY 4.0 (per the open-access article; the repo has no licence file) | Raw files in `backend/data/food/raw/` with attribution | Food table |
| USDA FoodData Central | SR Legacy 2018-04, FNDDS 2021–2023 | Public domain (CC0) | Subset in `backend/data/food/raw/usda_fdc_subset.csv` | Food table |
| Indian Food Composition Tables 2017 (IFCT) | ICMR-NIN | ⚠ Not openly licensed | Only 67 ingredient values reproduced, with attribution; NIN permission needed for commercial use | Food table (recipe-derived rows) |
| Glycaemic-index bands | Atkinson et al. 2008, Diabetes Care | Citation (facts) | GI band labels only | Food table `gi_band` |
| Food-name translations (es/fr/de/it/ja) | Written for this project, 2026-10-08 | Same as code (MIT) | Included | Food lookup in six languages |

Required attribution lines: "Contains data from CGMacros (Gutierrez-Osuna et al., PhysioNet 2025),
CC BY-NC-SA 4.0." · "Contains data from the Indian Nutrient Databank (Vijayakumar et al., 2024),
CC BY 4.0." · "ShanghaiT2DM: Zhao et al., Scientific Data 2023, CC BY 4.0." · "USDA FoodData Central."

## Models (all called through Nebius Token Factory; no weights are redistributed)

| Model | Role | Terms | Notes |
|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Router, planner, explanation, NeMo Guardrails rails | NVIDIA Nemotron Open Model License | Supported languages per model card: en, es, fr, de, it, ja |
| `nvidia/nemotron-3-super-120b-a12b` | Complex turns (configured; smoke-tested) | NVIDIA Nemotron Open Model License | |
| `google/gemma-3-27b-it` | Meal-photo dish candidates only | Gemma Terms of Use | Non-NVIDIA; used because Token Factory lists no NVIDIA vision model. Never produces nutrient values. |
| Twin engine (particle filter, CEM calibration, LightGBM residual, conformal bands) | Numerical estimates | Code: MIT; fitted artefacts: see CGMacros row | |


## Third-party service: Tavily search

Used only for "further reading": the app sends a fixed topic query (no user text) and shows the title,
link, domain and a short quotation (≤ 280 characters) from allowlisted public-health and diabetes-society
sites, always linking to the source. The content belongs to those sites; no text is stored beyond a 24-hour
in-memory cache. Use is subject to the Tavily terms of service and the source sites' terms.

## Software libraries (runtime)

NeMo Guardrails 0.24.1 (Apache-2.0) · Nebius Python SDK 0.6.20 (MIT) · FastAPI (MIT) · LightGBM
(MIT) · SHAP (MIT) · pandas/NumPy/SciPy/scikit-learn (BSD) · React, i18next, d3, three.js (MIT).
Exact versions: `backend/requirements.lock`, `frontend/package-lock.json`.

## Images, illustrations, fonts

| Asset | Licence | Where |
|---|---|---|
| Sample meal photos (9: 5 American, 4 Indian) | Wikimedia Commons: 4 × CC BY-SA 4.0, 1 × CC BY 3.0, 3 × CC0, 1 × public domain — credits in `backend/fixtures/samples/meals/ATTRIBUTION.md` and shown in the UI | Meal page samples |
| Sign-in statue (3-D human, clothes, shoes, hair, eyes) | MakeHuman base mesh, macro targets, default rig and system assets (male_casualsuit01, shoes01, short02, low-poly eyes), CC0 1.0; posed and fitted by `scripts/landing/build_statue.py` into `frontend/public/models/statue.{json,bin}` | Sign-in page animation |
| Sample lab-report images | Created for the project (synthetic) | Lab upload demo |
| Blue clownfish illustration and favicon | Original SVG drawn for this project (not derived from any film character or third-party artwork); MIT with the code | Decorative background, favicon |
| Plus Jakarta Sans | SIL Open Font License 1.1 (`frontend/public/fonts/`) | UI font |

## Data handling in the deployed demo

Only synthetic personas are served. No real patient records are stored. Raw chat text is **not** stored
by default (the audit log keeps tool calls, checks and a length + hash; `AUDIT_STORE_TEXT=true` changes this);
chat text is sent to Nebius Token Factory for inference. Hosting on Nebius does not by
itself establish clinical compliance, exclusive tenancy or a data-residency guarantee.
