# NemoTwins food table: sources and methods

Access date for all online sources: **2026-10-05**.

Files in this folder:

| File | What it is |
|---|---|
| `indian_foods.csv` | 153 dishes, macros per one household unit |
| `swaps.json` | 44 healthier-swap suggestions (32 Indian, 12 American); every id exists in the CSV. Optional `from_qty`/`to_qty` (default 1) |
| `build_foods.py` | Regenerates `indian_foods.csv` from the raw sources. **Every number comes from this script, not typed by hand** |
| `validate.py` | Checks the CSV and swaps (`python3.12 data/food/validate.py`) |
| `raw/INDB.xlsx`, `raw/recipes.xlsx`, `raw/recipes_servingsize.xlsx`, `raw/recipes_names.xlsx`, `raw/recipe_links.xlsx`, `raw/Units.xlsx`, `raw/README.md` | INDB data files, unmodified, from GitHub |
| `raw/usda_fdc_subset.csv` | The 61 USDA FoodData Central foods used (energy, carbohydrate by difference, fibre, protein, fat per 100 g) |

## 1. Primary source: Indian Nutrient Databank (INDB)

- **Citation:** Vijayakumar A, Dubasi HB, Awasthi A, Jaacks LM. *Development of an Indian Food Composition Database.* Current Developments in Nutrition. 2024;8(7):103790. doi:[10.1016/j.cdnut.2024.103790](https://doi.org/10.1016/j.cdnut.2024.103790) (PMC11277795).
- **Data:** https://github.com/lindsayjaacks/Indian-Nutrient-Databank-INDB- (commit `fbdb62b`, 2025-04-08). Contains 1,014 recipes from *The Art & Science of Cooking* (ASC codes), *Basic Food Preparation* (BFP codes) and open web recipes (OSR codes). Nutrient values are computed from IFCT 2017/2004, UK CoFID and USDA ingredient values.
- **Licence:** the article is "an open access article under the CC BY license (http://creativecommons.org/licenses/by/4.0/)", and the data-availability statement says "All analysis codes and files are publicly and freely available on GitHub". The GitHub repository has no separate LICENSE file. We therefore treat the data as **CC BY 4.0, attribution required**. Required attribution: *"Contains data from the Indian Nutrient Databank (Vijayakumar et al., 2024), CC BY 4.0."*
- **Used for:** 72 of 153 rows (31 `direct`, 41 `per100g_scaled`; source starts with `INDB 2024 recipe <code>`). The rest: 13 USDA-only, 20 IFCT-only, 48 `recipe_derived`.

### Known limitations of INDB and how they are handled
1. **No yield factors.** INDB sums raw-ingredient weights, including any added water, and applies no correction for water lost in cooking (the paper lists this as future work). Per-100 g values are therefore per *raw-ingredient* weight. They are close to as-cooked values for wet dishes such as dal, sambar, curries and upma. They are too low for reduced or dry dishes, and too high when the recipe leaves out cooking water (rajma, chole, curd rice, tamarind rice).
   - For curries, dals and sabzis whose INDB recipe includes its liquid, we use `per100g_scaled` to a 150 g katori. Each row's note says the true value per cooked gram may be somewhat higher.
   - Where the INDB recipe leaves out water or the dish is reduced (rajma, chole, kala chana, curd rice, puliyogare, kheer, halwa, breads, sweets), we use INDB **per-serving** values (`direct`). These are robust because they are the total nutrients of the recipe divided by the number of servings. For these rows `grams_per_unit` is an approximate served weight given for information only, and the macros do not depend on it. The notes say so.
2. **Deep-fried recipes include all of the frying oil.** For example, INDB puri is 738 kcal/100 g with 77.6 g fat, and samosa, kachori, pakora, vada, gulab jamun, kadhi-with-pakodi, boondi raita and kofta have the same problem. Syrup-soaked sweets (rasgulla, gulab jamun) likewise include all of the syrup. **None of these INDB rows are used.** Those dishes come from USDA FNDDS (as-eaten analyses) or from recipes with an explicit oil-uptake assumption (section 5).
3. INDB `carb_g` is available carbohydrate when the ingredient comes from IFCT or UK CoFID. For the few USDA-sourced ingredients inside INDB recipes it is carbohydrate by difference, which is a minor effect.

## 2. USDA FoodData Central (FDC)

- **Citation:** U.S. Department of Agriculture, Agricultural Research Service. *FoodData Central.* https://fdc.nal.usda.gov/
  - SR Legacy (April 2018): `FoodData_Central_sr_legacy_food_csv_2018-04.zip`
  - FNDDS 2021–2023 (Survey Foods, release 2024-10-31): `FoodData_Central_survey_food_csv_2024-10-31.zip`
- **Licence:** public domain / CC0 1.0 (USDA FDC data are published as U.S. Government works; FDC asks for the citation above).
- **Used for:** cooked white and brown rice, puri, naan, samosa, bread, boiled egg, curd, papad, and ingredients (chicken, besan, rice flour, oils, ghee, sugar, lemon juice, coffee, tea). Source strings look like `USDA FDC 2708730 (FNDDS 2021-2023: Samosa)`.
- **Carbohydrate convention:** USDA reports *carbohydrate by difference*, which includes fibre. We convert to available carbohydrate: `carbs_g = carb_by_difference − total dietary fibre`. Energy is USDA's reported kcal.
- FNDDS portion weights used as household measures: 1 idli = 38 g, medium dosa = 80 g, 1 puri = 36 g, samosa (quantity not specified) = 75 g, medium chapati = 40 g.

## 3. Indian Food Composition Tables 2017 (IFCT)

- **Citation:** Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K. *Indian Food Composition Tables 2017.* National Institute of Nutrition, Indian Council of Medical Research, Hyderabad. https://www.nin.res.in/ifct_book.html
- **Licence:** © ICMR-NIN. **Not openly licensed.** The INDB authors also note that IFCT must be obtained from NIN. We reproduce only the 67 ingredient values actually used (in the `IFCT` dict in `build_foods.py`), with attribution, and do not redistribute the table. Values were read from the machine-readable transcription at https://github.com/nodef/ifct2017 (`compositions/index.csv`; the repository's code is AGPL-3.0, and the data remains NIN's). **Before any commercial release, check these 67 values against the printed IFCT 2017 or obtain a licence from NIN.**
- Fields used, per 100 g edible portion: ENERC (kJ, converted at 4.184 kJ/kcal), CHOAVLDF (available carbohydrate), FIBTG (total dietary fibre), PROTCNT (protein), FATCE (total fat).
- **Used for:** Indian ingredients in recipes (atta, maida, raw rice, poha, muri, ragi, jowar, bajra, dals, vegetables, poppy seeds, coconut, jaggery, khoa, milk, goat meat, rohu), and directly for fruits, milk, coconut water, sugarcane juice, omelette, roasted chana and peanuts. The mango row uses the mean of the 7 ripe Indian varieties in IFCT (E036–E042).

## 4. Glycaemic index

- **Citation:** Atkinson FS, Foster-Powell K, Brand-Miller JC. *International tables of glycemic index and glycemic load values: 2008.* Diabetes Care. 2008;31(12):2281–2283. doi:[10.2337/dc08-1239](https://doi.org/10.2337/dc08-1239) (PMC2584181). Article licence: CC BY-NC-ND 3.0. We cite individual GI values only.
- Bands: low ≤ 55, medium 56–69, high ≥ 70 (glucose = 100).
- `gi_band` is set **only** when the CSV row matches a food in Table 1 of that paper:

| Row(s) | Table 1 entry | GI | Band |
|---|---|---|---|
| white_rice_katori, white_rice_plate | White rice, boiled | 73 ± 4 | high |
| brown_rice_katori | Brown rice, boiled | 68 ± 4 | medium |
| roti_piece, roti_ghee_piece | Chapatti 52 ± 4; Wheat roti 62 ± 3 | 52–62 | medium (conservative upper) |
| bread_white_slice | White wheat bread | 75 ± 2 | high |
| bread_brown_slice | Whole wheat/whole meal bread | 74 ± 2 | high |
| milk_glass | Milk, full fat | 39 ± 3 | low |
| banana_piece / mango_katori / apple_piece / orange_piece | Banana 51; Mango 51; Apple 36; Orange 43 | | low |
| pineapple_katori | Pineapple, raw | 59 ± 8 | medium |
| watermelon_katori | Watermelon, raw | 76 ± 4 | high |
| sugar_tsp | Sucrose | 65 ± 4 | medium |

  All other rows are `unknown`. Mixed dishes such as dal, rajma, idli and dosa were not extrapolated from ingredient GIs.

## 5. Methods (`method` column)

| method | meaning |
|---|---|
| `direct` | INDB per-serving values used unchanged (1 unit = 1 INDB serving) |
| `per100g_scaled` | per-100 g values from INDB, USDA or IFCT × `grams_per_unit` |
| `recipe_derived` | sum over a standard recipe: ingredient grams × per-100 g IFCT/USDA values. The full ingredient list with source codes is in the `source` column |

Units: `carbs_g` = available carbohydrate (no fibre); `fibre_g` = total dietary fibre; `kcal` = source-reported energy, or for recipes the sum of the ingredients' reported energies. All macros are per ONE unit.

### Household-measure assumptions
| Measure | Grams | Basis |
|---|---|---|
| katori, cooked rice / dal / sabzi / curry | 150 g | project standard (task spec) |
| plate, plain rice | 250 g | assumption |
| plate, mixed-rice dishes (biryani, lemon rice, etc.) | INDB serving (e.g. 80 g raw rice), ~250–330 g served | INDB serving definition |
| small katori (curd, raita, kesari bath) | 100 g | assumption |
| roti / chapati, medium | 40 g cooked, from 30 g atta | FNDDS "medium chappatti" 40 g; 30 g atta assumed |
| jowar / bajra roti | from 40 g flour (~55 g cooked) | assumption |
| ragi mudde | from 60 g ragi flour (~180 g ball) | assumption; real balls range from 40 to 100 g flour |
| idli | 38 g | FNDDS portion |
| dosa, medium | 80 g | FNDDS portion (nutrients from INDB per dosa) |
| puri | 36 g | FNDDS portion |
| naan | 90 g | assumption (FNDDS full 10-inch naan = 177 g) |
| samosa | 75 g | FNDDS portion |
| glass | 200 ml (milk, coconut water), 250 ml (lassi, chaas, juices) | assumption |
| tea cup | 125 ml (60 ml milk + 2 tsp/8 g sugar) | assumption |
| filter coffee tumbler | 120 ml (90 ml milk + 30 ml decoction + 6 g sugar) | assumption |
| tbsp | 15 g; tsp = 5 g | standard |
| fruit, medium | banana 100 g, apple 150 g, guava 100 g, orange 130 g edible portion; cut fruit 1 katori = 150 g | assumption |

### Recipe assumptions that most affect accuracy
- **Frying-oil uptake** (assumed, typically 12–25 % fat by weight of the fried item): luchi 4.5 g absorbed oil (about 25 % fat, matching FNDDS puri at 24.9 %), kachori 7 g, pakora 9 g per 60 g, medu vada 6 g, masala vada 6 g, bonda 6 g, begun bhaja 5 g, beguni 5 g, fish fry 4 g, fried papad 3 g, gulab jamun 3 g, jalebi 7 g per 50 g.
- **Syrup uptake** (assumed): rasgulla 14 g sugar per 50 g piece, gulab jamun 15 g per piece, jalebi 20 g per 50 g.
- **Chhena** (rasgulla, sandesh): made from IFCT whole cow milk, keeping 80 % of protein, 90 % of fat and 10 % of lactose; the rest is lost in the whey.
- **Cooked weights** for recipe rows (rotis, mudde, curries) are estimates. Per-unit macros depend only on the ingredient amounts.

## American foods (38 rows, cuisine `american`, ids `us_*`)

Added so that visitors from the USA can photograph or enter everyday American meals (burger plates,
pizza, pancake breakfasts, Southern plates, steak dinners, drinks and desserts). Every value comes from
USDA FoodData Central, extracted by script from the FNDDS 2021-2023 survey-food release (2024-10-31) into
`raw/usda_fdc_subset.csv` (one SR Legacy row: cornmeal). Unit weights are FNDDS portion weights (for example
1 cheeseburger with one medium patty = 165 g, 1 medium fast-food order of fries = 145 g, 1 slice of a large
pepperoni pizza = 124 g, 1 can of cola = 372 g). Carbohydrate is available carbohydrate (by difference
minus fibre), as for every USDA row.

Recipes (documented assumptions, no USDA as-eaten entry exists):
- **Fried okra**: 100 g USDA cooked okra + 15 g cornmeal breading + 10 g absorbed frying oil per cup.
- **Sweet tea**: 338 g USDA brewed iced tea + 22 g sugar per 12 fl oz glass ("iced tea" maps here, the
  Southern restaurant default; unsweetened iced tea is a separate row).
- **Mixed berries**: equal parts USDA raw blueberries, raspberries and blackberries.
- **Sauteed vegetables**: USDA cooked bok choy (fat added) + cooked sweet red pepper.

No GI band is assigned to the American rows (`unknown`): they are mostly mixed dishes without a matching
Atkinson 2008 entry. Names in es/fr/de/it/ja are translations only; "pepperoni" is rendered as spicy salami
in Italian and German, where the word means sweet or chili peppers.

## Generic sweets (`mithai_50g`)

"Sweets" without a name maps to 50 g of assorted Indian sweets: the per-gram mean of ten piece sweets in this
table (rasgulla, sandesh, gulab jamun, jalebi, mysore pak, laddoo, burfi, kaju katli, chikki, narkel naru), computed
by `build_foods.py` from those rows. It is an assumption; the specific sweet should be chosen when known.
