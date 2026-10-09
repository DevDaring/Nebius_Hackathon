#!/usr/bin/env python3
"""Build indian_foods.csv for NemoTwins from cited sources.

Every number in the output is computed here from one of:
  * INDB 2024 (raw/INDB.xlsx, CC BY 4.0)            -> "indb100" (per-100 g x grams) or "indbsrv" (INDB per-serving, direct)
  * USDA FoodData Central (raw/usda_fdc_subset.csv)  -> "fdc"  (per-100 g x grams; FNDDS 2021-2023 / SR Legacy)
  * IFCT 2017 ingredient values (IFCT dict below)    -> "ifct" (per-100 g x grams)
  * a standard recipe of IFCT/USDA ingredients       -> "recipe" (sum of ingredient grams x per-100 g values)

Conventions (see SOURCES.md):
  carbs_g  = AVAILABLE carbohydrate (excludes dietary fibre). USDA reports carbohydrate *by difference*
             (includes fibre), so for USDA items carbs_g = carb_by_difference - total_dietary_fibre.
  kcal     = energy as reported by the source (INDB/USDA), or the sum of ingredient energies (recipes).
  All macros are per ONE unit (unit/grams_per_unit columns).

Names / aliases in es, fr, de, it, ja come from names_i18n.csv (merged by id; translations only,
never numbers). name_bn / name_hi / name_kn are provenance columns from the source tables (not shown
in the app).

Run:  python3.12 data/food/build_foods.py
"""
from __future__ import annotations

import csv
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

# ---------------------------------------------------------------------------------------------
# IFCT 2017 (Longvah et al., ICMR-NIN). Only the ingredient rows used below are reproduced, with
# attribution. Columns: name, kcal (ENERC kJ / 4.184), available CHO (CHOAVLDF), total dietary
# fibre (FIBTG), protein (PROTCNT), fat (FATCE); all per 100 g edible portion.
# ---------------------------------------------------------------------------------------------
IFCT = {
    "A003": ("Bajra", 348.0, 61.78, 11.49, 10.96, 5.43),
    "A005": ("Jowar", 334.1, 67.68, 10.22, 9.97, 1.73),
    "A010": ("Ragi", 320.7, 66.82, 11.18, 7.16, 1.92),
    "A011": ("Rice, flakes", 353.7, 76.75, 3.46, 7.44, 1.14),
    "A012": ("Rice, puffed", 361.9, 77.68, 2.56, 7.47, 1.62),
    "A015": ("Rice, raw, milled", 356.4, 78.24, 2.81, 7.94, 0.52),
    "A018": ("Wheat flour, refined (maida)", 351.8, 74.27, 2.76, 10.36, 0.76),
    "A019": ("Wheat flour, atta", 320.3, 64.17, 11.36, 10.57, 1.53),
    "B001": ("Bengal gram, dal", 329.1, 46.72, 15.15, 21.55, 5.31),
    "B002": ("Bengal gram, whole", 287.0, 39.56, 25.22, 18.77, 5.11),
    "B003": ("Black gram, dal", 324.1, 51.0, 11.93, 23.06, 1.69),
    "B010": ("Green gram, dal", 325.8, 52.59, 9.37, 23.88, 1.35),
    "B017": ("Peas, dry", 303.3, 48.93, 17.01, 20.43, 1.89),
    "B021": ("Red gram, dal", 330.8, 55.23, 9.06, 21.7, 1.56),
    "D004": ("Bitter gourd", 20.8, 2.82, 3.78, 1.44, 0.24),
    "D007": ("Bottle gourd", 11.0, 1.68, 2.12, 0.53, 0.13),
    "D031": ("Brinjal - all varieties", 25.3, 3.52, 3.98, 1.48, 0.32),
    "D043": ("Cucumber, green, elongate", 19.6, 3.48, 2.14, 0.71, 0.16),
    "D046": ("Drumstick", 29.4, 3.76, 6.83, 2.62, 0.12),
    "D049": ("French beans, country", 24.4, 2.68, 4.38, 2.49, 0.26),
    "D061": ("Peas, fresh", 81.3, 11.88, 6.32, 7.25, 0.13),
    "D063": ("Plantain, green", 79.8, 17.58, 3.6, 1.18, 0.23),
    "D075": ("Tomato, ripe, hybrid", 18.9, 3.2, 1.58, 0.76, 0.25),
    "E001": ("Apple, big", 62.4, 13.11, 2.59, 0.29, 0.64),
    "E012": ("Banana, ripe, robusta", 105.2, 23.63, 1.94, 1.23, 0.33),
    "E016": ("Custard apple", 98.9, 20.38, 5.1, 1.62, 0.67),
    "E026": ("Grapes, seedless, round, green", 53.5, 11.81, 1.28, 0.62, 0.26),
    "E028": ("Guava, white flesh", 32.3, 5.13, 8.59, 1.44, 0.32),
    "E036": ("Mango, ripe, banganapalli", 41.8, 8.18, 1.88, 0.54, 0.55),
    "E037": ("Mango, ripe, gulabkhas", 50.0, 10.32, 1.67, 0.52, 0.53),
    "E038": ("Mango, ripe, himsagar", 44.7, 9.03, 1.55, 0.46, 0.54),
    "E039": ("Mango, ripe, kesar", 55.2, 11.36, 2.02, 0.54, 0.57),
    "E040": ("Mango, ripe, neelam", 42.5, 8.21, 1.77, 0.68, 0.55),
    "E041": ("Mango, ripe, paheri", 44.9, 8.67, 1.97, 0.68, 0.58),
    "E042": ("Mango, ripe, totapari", 59.3, 12.75, 1.73, 0.41, 0.49),
    "E047": ("Orange, pulp", 37.3, 7.92, 1.29, 0.7, 0.13),
    "E049": ("Papaya, ripe", 23.9, 4.61, 2.83, 0.42, 0.16),
    "E053": ("Pineapple", 43.0, 9.42, 3.46, 0.52, 0.16),
    "E055": ("Pomegranate, maroon seeds", 54.7, 11.58, 2.83, 1.33, 0.15),
    "E057": ("Raisins, dried, black", 305.7, 71.29, 3.92, 2.57, 0.34),
    "E060": ("Sapota", 73.4, 13.9, 9.6, 0.92, 1.26),
    "E064": ("Tamarind, pulp", 288.5, 67.35, 5.31, 2.92, 0.15),
    "E065": ("Water melon, dark green", 20.3, 3.86, 0.7, 0.6, 0.16),
    "F002": ("Carrot, orange", 33.2, 5.55, 4.18, 0.95, 0.47),
    "F006": ("Potato, brown skin, big", 69.8, 14.89, 1.71, 1.54, 0.23),
    "F013": ("Sweet potato, brown skin", 109.0, 24.25, 3.99, 1.33, 0.26),
    "G017": ("Onion, big", 48.0, 9.56, 2.45, 1.5, 0.24),
    "G032": ("Poppy seeds", 422.6, 12.37, 26.68, 20.31, 30.38),
    "H007": ("Coconut, kernel, fresh", 408.9, 6.3, 10.42, 3.84, 41.38),
    "H011": ("Gingelly (sesame) seeds, white", 519.6, 10.83, 16.99, 21.7, 43.05),
    "H012": ("Ground nut", 520.1, 17.27, 10.38, 23.65, 39.63),
    "H013": ("Mustard seeds", 509.6, 16.8, 14.1, 19.51, 40.19),
    "I001": ("Jaggery, cane", 353.7, 84.87, 0.0, 1.85, 0.16),
    "I002": ("Sugarcane, juice", 57.8, 13.11, 0.56, 0.16, 0.4),
    "K002": ("Coconut water", 15.3, 3.16, 0.0, 0.26, 0.16),
    "L002": ("Milk, whole, cow", 72.9, 4.94, 0.0, 3.26, 4.48),
    "L004": ("Khoa", 316.0, 16.53, 0.0, 16.34, 20.62),
    "M007": ("Egg, poultry, omlet", 169.7, 0.0, 0.0, 16.53, 11.6),
    "O001": ("Goat, shoulder, meat", 188.1, 0.0, 0.0, 20.33, 11.94),
    "S006": ("Rohu", 102.3, 0.0, 0.0, 19.71, 2.39),
    "S008": ("Prawns, big", 90.8, 0.0, 0.0, 19.24, 0.52),
}
MANGO_CODES = ["E036", "E037", "E038", "E039", "E040", "E041", "E042"]

# Recipe ingredient keys -> source
ING = {
    # cereals / flours
    "atta": ("ifct", "A019"), "maida": ("ifct", "A018"), "rice_raw": ("ifct", "A015"),
    "rice_flakes": ("ifct", "A011"), "rice_puffed": ("ifct", "A012"), "ragi": ("ifct", "A010"),
    "jowar": ("ifct", "A005"), "bajra": ("ifct", "A003"), "rice_flour": ("fdc", 169714),
    "rice_cooked": ("fdc", 2708408),
    # pulses
    "toor_dal": ("ifct", "B021"), "moong_dal": ("ifct", "B010"), "urad_dal": ("ifct", "B003"),
    "chana_dal": ("ifct", "B001"), "peas_dry": ("ifct", "B017"), "besan": ("fdc", 174288),
    # vegetables
    "onion": ("ifct", "G017"), "tomato": ("ifct", "D075"), "potato": ("ifct", "F006"),
    "brinjal": ("ifct", "D031"), "bottle_gourd": ("ifct", "D007"), "bitter_gourd": ("ifct", "D004"),
    "drumstick": ("ifct", "D046"), "plantain_green": ("ifct", "D063"), "sweet_potato": ("ifct", "F013"),
    "carrot": ("ifct", "F002"), "beans": ("ifct", "D049"), "peas_fresh": ("ifct", "D061"),
    "cucumber": ("ifct", "D043"), "lemon_juice": ("fdc", 167747), "tamarind": ("ifct", "E064"),
    # nuts / seeds / fruit
    "coconut": ("ifct", "H007"), "groundnut": ("ifct", "H012"), "poppy": ("ifct", "G032"),
    "mustard_seed": ("ifct", "H013"), "sesame": ("ifct", "H011"), "raisins": ("ifct", "E057"),
    "banana": ("ifct", "E012"),
    # fats / sugars
    "oil": ("fdc", 171017), "mustard_oil": ("fdc", 172337), "ghee": ("fdc", 2710168),
    "okra_cooked": ("fdc", 2709944), "cornmeal": ("fdc", 168867),
    "blueberries": ("fdc", 2709275), "raspberries": ("fdc", 2709281), "blackberries": ("fdc", 2709273),
    "bok_choy_cooked_fat": ("fdc", 2709888), "red_pepper_cooked": ("fdc", 2709977), "iced_tea": ("fdc", 2710517),
    "sugar": ("fdc", 169655), "jaggery": ("ifct", "I001"),
    # dairy / animal
    "milk": ("ifct", "L002"), "curd": ("fdc", 171284), "khoa": ("ifct", "L004"),
    "egg_boiled": ("fdc", 173424), "chicken": ("fdc", 171052), "goat": ("ifct", "O001"),
    "rohu": ("ifct", "S006"),
    # other
    "papad": ("fdc", 168106), "coffee_brewed": ("fdc", 171890), "tea_brewed": ("fdc", 2710488),
    "water": ("zero", None),
    # chhena (milk curdled with acid, whey drained), expressed per 100 ml milk used. Assumption
    # documented in SOURCES.md: chhena retains 80% of milk protein, 90% of milk fat, 10% of
    # lactose (rest lost in whey). Base = IFCT L002 whole cow milk.
    "chhena_from_milk": ("chhena", "L002"),
}


def load_indb() -> pd.DataFrame:
    d = pd.read_excel(os.path.join(RAW, "INDB.xlsx"))
    return d.set_index("food_code")


def load_fdc() -> pd.DataFrame:
    d = pd.read_csv(os.path.join(RAW, "usda_fdc_subset.csv"))
    return d.set_index("fdc_id")


INDB = load_indb()
FDC = load_fdc()


def per100(kind: str, ref) -> dict:
    """Return per-100 g dict(kcal, carbs (available), fibre, protein, fat) + label."""
    if kind == "ifct":
        if ref == "MANGO_MEAN":
            vals = [IFCT[c] for c in MANGO_CODES]
            m = [sum(v[i] for v in vals) / len(vals) for i in range(1, 6)]
            return dict(kcal=m[0], carbs=m[1], fibre=m[2], protein=m[3], fat=m[4],
                        label="IFCT 2017 E036-E042 (mean of 7 ripe mango varieties)")
        n, k, c, f, p, fa = IFCT[ref]
        return dict(kcal=k, carbs=c, fibre=f, protein=p, fat=fa, label=f"IFCT 2017 {ref} ({n})")
    if kind == "fdc":
        r = FDC.loc[ref]
        fib = 0.0 if pd.isna(r.fibre_total_dietary_g) else float(r.fibre_total_dietary_g)
        return dict(kcal=float(r.energy_kcal), carbs=max(float(r.carb_by_difference_g) - fib, 0.0),
                    fibre=fib, protein=float(r.protein_g), fat=float(r.fat_g),
                    label=f"USDA FDC {ref} ({r.dataset}: {r.description})")
    if kind == "indb":
        r = INDB.loc[ref]
        return dict(kcal=float(r.energy_kcal), carbs=float(r.carb_g), fibre=float(r.fibre_g),
                    protein=float(r.protein_g), fat=float(r.fat_g),
                    label=f"INDB 2024 recipe {ref} ({r.food_name.strip()})")
    if kind == "zero":
        return dict(kcal=0, carbs=0, fibre=0, protein=0, fat=0, label="water")
    if kind == "chhena":
        n, k, c, f, p, fa = IFCT[ref]
        cc, pp, ff = c * 0.10, p * 0.80, fa * 0.90
        return dict(kcal=4 * cc + 4 * pp + 9 * ff, carbs=cc, fibre=0.0, protein=pp, fat=ff,
                    label="chhena from IFCT 2017 L002 cow milk (80% protein/90% fat/10% lactose retained)")
    raise ValueError(kind)


def scaled(p: dict, grams: float) -> dict:
    f = grams / 100.0
    return {k: p[k] * f for k in ("kcal", "carbs", "fibre", "protein", "fat")}


def compute(src, grams):
    kind = src[0]
    if kind == "indb100":
        p = per100("indb", src[1])
        return scaled(p, grams), f"{p['label']}; per-100 g x {grams:g} g", "per100g_scaled"
    if kind == "indbsrv":
        r = INDB.loc[src[1]]
        mult = src[2] if len(src) > 2 else 1
        v = dict(kcal=r.unit_serving_energy_kcal, carbs=r.unit_serving_carb_g, fibre=r.unit_serving_fibre_g,
                 protein=r.unit_serving_protein_g, fat=r.unit_serving_fat_g)
        v = {k: float(x) * mult for k, x in v.items()}
        sg = r.unit_serving_energy_kcal / r.energy_kcal * 100
        lab = (f"INDB 2024 recipe {src[1]} ({r.food_name.strip()}); INDB per-serving values"
               f" (1 {r.servings_unit}, INDB serving weight {sg:.0f} g)" + (f" x {mult:g}" if mult != 1 else ""))
        return v, lab, "direct"
    if kind in ("fdc", "ifct"):
        p = per100(kind, src[1])
        return scaled(p, grams), f"{p['label']}; per-100 g x {grams:g} g", "per100g_scaled"
    if kind == "recipe":
        tot = dict(kcal=0.0, carbs=0.0, fibre=0.0, protein=0.0, fat=0.0)
        parts = []
        for key, g in src[1]:
            k2, ref = ING[key]
            p = per100(k2, ref)
            s = scaled(p, g)
            for k in tot:
                tot[k] += s[k]
            if k2 == "zero":
                parts.append(f"{key} {g:g} g")
            elif k2 == "ifct":
                parts.append(f"{key} {g:g} g [IFCT {ref}]")
            elif k2 == "fdc":
                parts.append(f"{key} {g:g} g [FDC {ref}]")
            else:
                parts.append(f"{key} {g:g} ml milk [chhena, IFCT {ref}]")
        return tot, "Recipe-derived: " + " + ".join(parts), "recipe_derived"
    raise ValueError(kind)


# ---------------------------------------------------------------------------------------------
# Row specs
# (id, name_en, name_bn, name_hi, name_kn, aliases, cuisine, category, unit, unit_label_en,
#  grams_per_unit, src, gi_band, notes)
# ---------------------------------------------------------------------------------------------
GI_RICE = "GI: Atkinson 2008 Table 1 white rice, boiled 73+/-4 (high)."
GI_ROTI = ("GI: Atkinson 2008 Table 1 lists Chapatti 52+/-4 and Wheat roti 62+/-3; banded 'medium' "
           "(conservative upper value).")
INDB_W = "INDB serving weight is the sum of raw ingredients (no cooking-loss/yield correction)."
INDB_NOWATER = ("INDB recipe lists no cooking water, so its serving weight understates the served "
                "weight; grams_per_unit is an estimated served weight. Macros are INDB per-serving and do not depend on it.")
NOYIELD = ("INDB per-100 g values are per raw-ingredient weight (no yield factor); if the dish is reduced "
           "more than usual, true values per cooked gram are somewhat higher.")
OIL = "Frying-oil uptake is an assumption (see SOURCES.md); actual values vary with cook and oil temperature."

R = []


def add(*a):
    R.append(a)


# ---------------- STAPLES ----------------
add("white_rice_katori", "Steamed white rice", "ভাত", "चावल (पका हुआ)", "ಅನ್ನ",
    "rice;bhat;bhaat;bhath;chawal;chaawal;chaval;annam;anna;anna saaru;saadam;sadam;plain rice;steamed rice;boiled rice;cooked rice;white rice;sada bhat",
    "pan", "staple", "katori", "1 katori (150 g cooked)", 150, ("fdc", 2708408), "high", GI_RICE)
add("white_rice_plate", "Steamed white rice (full plate)", "ভাত (এক থালা)", "चावल (एक प्लेट)", "ಅನ್ನ (ಒಂದು ತಟ್ಟೆ)",
    "rice plate;plate of rice;full plate rice;bhat thala;thali rice;rice meal",
    "pan", "staple", "plate", "1 plate (250 g cooked)", 250, ("fdc", 2708408), "high", GI_RICE)
add("brown_rice_katori", "Brown rice", "লাল চালের ভাত", "ब्राउन राइस", "ಕಂದು ಅಕ್ಕಿ ಅನ್ನ",
    "brown rice;unpolished rice;hand pounded rice;brown chawal;lal chaler bhat",
    "pan", "staple", "katori", "1 katori (150 g cooked)", 150, ("fdc", 2708414), "medium",
    "GI: Atkinson 2008 Table 1 brown rice, boiled 68+/-4 (medium).")
add("jeera_rice_katori", "Jeera rice", "জিরে ভাত", "जीरा राइस", "ಜೀರಾ ರೈಸ್",
    "jeera rice;jira rice;zeera rice;cumin rice;jeera pulao;jeera chawal",
    "north", "staple", "katori", "1 katori (150 g)", 150, ("indb100", "BFP134"), "unknown", NOYIELD)
add("veg_pulao_katori", "Vegetable pulao", "সবজি পোলাও", "वेज पुलाव", "ವೆಜ್ ಪಲಾವ್",
    "pulao;pulav;pilaf;veg pulao;veg pulav;vegetable pulav;polao;pulaw;tarkari pulao",
    "pan", "staple", "katori", "1 katori (150 g)", 150, ("indb100", "ASC115"), "unknown", NOYIELD)
add("khichdi_plate", "Khichdi (rice + moong dal)", "খিচুড়ি", "खिचड़ी", "ಕಿಚಡಿ",
    "khichdi;khichri;khichuri;khichudi;khichari;kichdi;kitchari;moong dal khichdi;dal khichdi;bhuna khichuri",
    "pan", "staple", "plate", "1 plate (60 g rice + 20 g moong dal + 5 g ghee)", 350, ("indbsrv", "BFP144"), "unknown",
    "INDB serving weight 574 g includes 480 ml water before cooking; served weight ~350 g is an assumption. Bengali khichuri with extra oil/vegetables will be higher in fat.")
add("veg_biryani_plate", "Vegetable biryani", "সবজি বিরিয়ানি", "वेज बिरयानी", "ವೆಜ್ ಬಿರಿಯಾನಿ",
    "veg biryani;vegetable biryani;veg biriyani;vegetable biriyani;tahiri;tehri",
    "north", "staple", "plate", "1 plate (INDB serving)", 302, ("indbsrv", "ASC123"), "unknown", INDB_W)
add("chicken_biryani_plate", "Chicken biryani", "চিকেন বিরিয়ানি", "चिकन बिरयानी", "ಚಿಕನ್ ಬಿರಿಯಾನಿ",
    "chicken biryani;chicken biriyani;murgh biryani;murg biryani;kolkata biryani;hyderabadi biryani;dum biryani;donne biryani;biryani;biriyani",
    "pan", "staple", "plate", "1 plate (~330 g: 75 g raw rice + 100 g chicken)", 330,
    ("recipe", [("rice_raw", 75), ("chicken", 100), ("oil", 6), ("ghee", 6), ("onion", 40), ("curd", 25), ("tomato", 20)]),
    "unknown", "INDB has no chicken biryani; standard restaurant-style recipe. Kolkata biryani usually also contains a potato (+~15 g carbs).")
add("mutton_biryani_plate", "Mutton biryani", "মটন বিরিয়ানি", "मटन बिरयानी", "ಮಟನ್ ಬಿರಿಯಾನಿ",
    "mutton biryani;mutton biriyani;gosht biryani;lamb biryani;goat biryani",
    "pan", "staple", "plate", "1 plate (INDB serving)", 260, ("indbsrv", "ASC122"), "unknown",
    "INDB serving weight 208 g excludes cooking water; ~260 g served is an estimate. " + INDB_W)
add("roti_piece", "Roti / chapati (no ghee)", "রুটি", "रोटी / चपाती", "ಚಪಾತಿ",
    "roti;chapati;chapathi;chappati;chapatti;chappathi;phulka;fulka;rooti;ruti;rutee;chapaati;wheat roti;atta roti;tawa roti;plain roti",
    "pan", "staple", "piece", "1 medium roti (40 g; from 30 g atta)", 40, ("recipe", [("atta", 30)]), "medium",
    GI_ROTI + " Recipe uses IFCT atta (INDB ASC096 is a smaller 36 g-dough chapati with ghee: 73 kcal).")
add("roti_ghee_piece", "Roti with ghee", "ঘি দেওয়া রুটি", "घी वाली रोटी", "ತುಪ್ಪದ ಚಪಾತಿ",
    "ghee roti;roti with ghee;chapati with ghee;chupadi roti;butter roti;ghee chapati",
    "north", "staple", "piece", "1 medium roti + 1/2 tsp ghee (43 g)", 43, ("recipe", [("atta", 30), ("ghee", 3)]), "medium",
    GI_ROTI + " Added fat may lower GI further; band kept conservative.")
add("paratha_piece", "Plain paratha", "পরোটা", "पराठा", "ಪರೋಟ",
    "paratha;parantha;paratha plain;tawa paratha;lachha paratha;tikona paratha;porota;parota",
    "north", "staple", "piece", "1 paratha (INDB serving)", 56, ("indbsrv", "ASC097"), "unknown",
    INDB_W + " Layered maida 'porota/parotta' is a different, richer item.")
add("aloo_paratha_piece", "Aloo paratha", "আলু পরোটা", "आलू पराठा", "ಆಲೂ ಪರೋಟ",
    "aloo paratha;alu paratha;aloo parantha;potato paratha;aloo ka paratha;allu paratha;aaloo paratha",
    "north", "breakfast", "piece", "1 paratha (INDB serving)", 93, ("indbsrv", "ASC098"), "unknown", INDB_W)
add("paneer_paratha_piece", "Paneer paratha", "পনির পরোটা", "पनीर पराठा", "ಪನೀರ್ ಪರೋಟ",
    "paneer paratha;paneer parantha;cottage cheese paratha",
    "north", "breakfast", "piece", "1 paratha (INDB serving)", 85, ("indbsrv", "ASC105"), "unknown", INDB_W)
add("puri_piece", "Puri", "পুরি", "पूरी", "ಪೂರಿ",
    "puri;poori;pooree;puree;wheat puri;atta puri;puri bhaji;poori masala",
    "pan", "staple", "piece", "1 puri (~12 cm, 36 g; FNDDS portion)", 36, ("fdc", 2707714), "unknown",
    "USDA FNDDS 'Bread, puri' (as-eaten, includes absorbed frying oil). INDB puri (ASC107) not used: it counts all frying oil.")
add("luchi_piece", "Luchi (maida puri)", "লুচি", "लूची", "ಲುಚಿ",
    "luchi;loochi;luchie;luchi bengali;maida puri;radhaballavi",
    "bengali", "staple", "piece", "1 luchi (~22 g)", 22, ("recipe", [("maida", 15), ("oil", 5.5)]), "unknown",
    "1 g oil in dough + 4.5 g absorbed oil; gives ~25% fat by weight, matching USDA FNDDS puri (24.9 g fat/100 g). " + OIL)
add("naan_piece", "Naan", "নান", "नान", "ನಾನ್",
    "naan;nan;nann;butter naan;tandoori naan;plain naan;garlic naan",
    "north", "staple", "piece", "1 naan (~90 g)", 90, ("fdc", 2707613), "unknown",
    "90 g assumed for an Indian restaurant naan (FNDDS full 10-inch naan = 177 g). Butter naan adds ~5 g fat.")
add("jowar_roti_piece", "Jowar roti / bhakri", "জোয়ারের রুটি", "ज्वार की रोटी / भाकरी", "ಜೋಳದ ರೊಟ್ಟಿ",
    "jowar roti;jowar bhakri;bhakri;bhakhri;jolada rotti;jolad rotti;jolada roti;jonna rotte;jwari bhakri;sorghum roti;jowar chapati",
    "karnataka", "staple", "piece", "1 roti (~55 g; from 40 g jowar flour)", 55, ("recipe", [("jowar", 40)]), "unknown",
    "Cooked weight ~55 g is an estimate; macros depend only on flour weight.")
add("bajra_roti_piece", "Bajra roti", "বাজরার রুটি", "बाजरे की रोटी", "ಸಜ್ಜೆ ರೊಟ್ಟಿ",
    "bajra roti;bajre ki roti;bajra bhakri;bajri bhakri;sajje rotti;pearl millet roti;kambu roti",
    "north", "staple", "piece", "1 roti (~55 g; from 40 g bajra flour)", 55, ("recipe", [("bajra", 40)]), "unknown",
    "Cooked weight is an estimate; macros depend only on flour weight.")
add("makki_roti_piece", "Makki ki roti", "ভুট্টার রুটি", "मक्की की रोटी", "ಮೆಕ್ಕೆಜೋಳದ ರೊಟ್ಟಿ",
    "makki ki roti;makki di roti;makki roti;makai roti;maize roti;corn roti",
    "north", "staple", "piece", "1 roti with butter (INDB serving)", 85, ("indbsrv", "ASC150"), "unknown", INDB_W)
add("ragi_mudde_piece", "Ragi mudde (finger millet ball)", "রাগি মুদ্দে", "रागी मुद्दे", "ರಾಗಿ ಮುದ್ದೆ",
    "ragi mudde;ragi muddhe;ragi ball;mudde;ragi kali;ragi sangati;ragi kazhi;finger millet ball;nachni ball",
    "karnataka", "staple", "piece", "1 ball (~180 g; from 60 g ragi flour)", 180, ("recipe", [("ragi", 60), ("water", 120)]), "unknown",
    "Ball size varies widely (40-100 g flour); 60 g flour assumed. Macros scale with flour.")
add("ragi_roti_piece", "Ragi roti", "রাগি রুটি", "रागी रोटी", "ರಾಗಿ ರೊಟ್ಟಿ",
    "ragi rotti;ragi roti;nachni roti;finger millet roti;ragi akki rotti",
    "karnataka", "staple", "piece", "1 roti (~65 g; from 40 g ragi flour)", 65,
    ("recipe", [("ragi", 40), ("onion", 15), ("oil", 3)]), "unknown", "Cooked weight is an estimate.")
add("akki_roti_piece", "Akki roti (rice-flour roti)", "চালের আটার রুটি", "चावल के आटे की रोटी", "ಅಕ್ಕಿ ರೊಟ್ಟಿ",
    "akki rotti;akki roti;rice rotti;rice roti;rice flour roti;chawal ki roti",
    "karnataka", "breakfast", "piece", "1 roti (~75 g; from 40 g rice flour)", 75,
    ("recipe", [("rice_flour", 40), ("onion", 15), ("coconut", 5), ("oil", 4)]), "unknown", "Cooked weight is an estimate.")
add("idli_piece", "Idli", "ইডলি", "इडली", "ಇಡ್ಲಿ",
    "idli;idly;iddli;idlee;itli;rice idli;plain idli;thatte idli",
    "south", "breakfast", "piece", "1 idli (38 g; FNDDS portion)", 38, ("indb100", "ASC144"), "unknown",
    "INDB batter includes its water, and steaming changes weight little. Thatte idli is ~2.5x larger.")
add("dosa_piece", "Plain dosa", "দোসা", "डोसा", "ದೋಸೆ",
    "dosa;dosai;dose;dhosa;thosai;plain dosa;sada dosa;benne dose;butter dosa",
    "south", "breakfast", "piece", "1 medium dosa (INDB serving; ~80 g cooked)", 80, ("indbsrv", "BFP148"), "unknown",
    "INDB recipe = 32.5 g rice + 7.5 g urad dal + ~3.75 g butter per dosa. Cooked weight from FNDDS 'medium dosa' (80 g).")
add("masala_dosa_piece", "Masala dosa", "মসলা দোসা", "मसाला डोसा", "ಮಸಾಲೆ ದೋಸೆ",
    "masala dosa;masala dose;masale dose;mysore masala dosa;masal dosa;masala dosai",
    "south", "breakfast", "piece", "1 masala dosa (INDB serving)", 210, ("indbsrv", "ASC146"), "unknown", INDB_W)
add("set_dosa_piece", "Set dosa (1 piece)", "সেট দোসা", "सेट डोसा", "ಸೆಟ್ ದೋಸೆ",
    "set dosa;set dose;sponge dosa;spongy dosa;set dosai",
    "karnataka", "breakfast", "piece", "1 piece (~70 g; usually served as 3)", 70,
    ("recipe", [("rice_raw", 25), ("urad_dal", 5), ("rice_flakes", 7), ("oil", 2)]), "unknown", "Cooked weight is an estimate.")
add("rava_dosa_piece", "Rava dosa", "রাভা দোসা", "रवा डोसा", "ರವೆ ದೋಸೆ",
    "rava dosa;rawa dosa;rava dose;suji dosa;semolina dosa;onion rava dosa",
    "south", "breakfast", "piece", "1 dosa (INDB serving)", 73, ("indbsrv", "ASC147"), "unknown", INDB_W)
add("neer_dosa_piece", "Neer dosa", "নীর দোসা", "नीर डोसा", "ನೀರ್ ದೋಸೆ",
    "neer dosa;neer dose;neeru dose;water dosa",
    "karnataka", "breakfast", "piece", "1 piece (~45 g; from 20 g rice)", 45,
    ("recipe", [("rice_raw", 20), ("coconut", 3), ("oil", 1)]), "unknown", "Cooked weight is an estimate.")
add("uttapam_piece", "Uttapam", "উত্তাপম", "उत्तपम", "ಉತ್ತಪ್ಪ",
    "uttapam;uthappam;uttappa;oothappam;onion uttapam;uthapam",
    "south", "breakfast", "piece", "1 uttapam (INDB serving)", 68, ("indbsrv", "BFP152"), "unknown", INDB_W)
add("upma_katori", "Upma (rava)", "উপমা", "उपमा", "ಉಪ್ಪಿಟ್ಟು",
    "upma;uppittu;uppit;khara bath;khara bhath;rava upma;suji upma;upuma;uppuma",
    "south", "breakfast", "katori", "1 katori (150 g)", 150, ("indb100", "BFP039"), "unknown", NOYIELD)
add("poha_plate", "Poha (vegetable poha)", "চিঁড়ের পোলাও", "पोहा", "ಅವಲಕ್ಕಿ ಒಗ್ಗರಣೆ",
    "poha;pohe;kanda poha;batata poha;aval upma;avalakki;avalakki oggarane;chire pulao;chirer polao;beaten rice upma",
    "pan", "breakfast", "plate", "1 plate (150 g)", 150, ("indb100", "BFP045"), "unknown", NOYIELD)
add("rava_idli_piece", "Rava idli", "রাভা ইডলি", "रवा इडली", "ರವೆ ಇಡ್ಲಿ",
    "rava idli;rava idly;suji idli;semolina idli;rawa idli",
    "karnataka", "breakfast", "piece", "1 rava idli (INDB serving)", 45, ("indbsrv", "BFP579"), "unknown",
    "INDB serving weight 30 g excludes water; ~45 g served is an estimate. " + INDB_W)
add("bisi_bele_bath_plate", "Bisi bele bath", "বিসি বেলে বাথ", "बिसी बेले भात", "ಬಿಸಿ ಬೇಳೆ ಬಾತ್",
    "bisi bele bath;bisibelebath;bisi bele baath;bisibele bhath;bisi bele bhaat;sambar rice;sambar sadam;sambar bath",
    "karnataka", "staple", "plate", "1 plate (~300 g)", 300,
    ("recipe", [("rice_raw", 50), ("toor_dal", 25), ("carrot", 20), ("beans", 20), ("peas_fresh", 15), ("potato", 15),
                ("onion", 15), ("tamarind", 5), ("oil", 5), ("ghee", 5), ("groundnut", 5)]), "unknown",
    "INDB has no bisi bele bath. Spice powder (~5 g) omitted. Served weight is an estimate.")
add("puliyogare_plate", "Puliyogare (tamarind rice)", "তেঁতুল ভাত", "इमली चावल", "ಪುಳಿಯೋಗರೆ",
    "puliyogare;puliogare;puliyodharai;pulihora;tamarind rice;huli anna;imli chawal;puli sadam",
    "karnataka", "staple", "plate", "1 plate (INDB serving: from 80 g raw rice)", 250, ("indbsrv", "ASC127"), "unknown", INDB_NOWATER)
add("lemon_rice_plate", "Lemon rice (chitranna)", "লেবু ভাত", "नींबू चावल", "ಚಿತ್ರಾನ್ನ",
    "lemon rice;chitranna;chitrannam;elumichai sadam;nimbu chawal;nimbe chitranna",
    "karnataka", "staple", "plate", "1 plate (INDB serving: from 80 g raw rice + 25 g peanuts)", 300, ("indbsrv", "ASC124"), "unknown",
    "INDB weight 319 g incl. 160 g cooking water; ~300 g served assumed. Macros are INDB per-serving.")
add("vangi_bath_plate", "Vangi bath (brinjal rice)", "বেগুন ভাত", "वांगी भात", "ವಾಂಗಿ ಬಾತ್",
    "vangi bath;vangibath;vangi bhath;vaangi bath;brinjal rice;eggplant rice;baingan rice",
    "karnataka", "staple", "plate", "1 plate (INDB serving: from 80 g raw rice)", 291, ("indbsrv", "BFP132"), "unknown", INDB_W)
add("curd_rice_plate", "Curd rice", "দই ভাত", "दही चावल", "ಮೊಸರನ್ನ",
    "curd rice;mosaranna;mosaru anna;thayir sadam;thair sadam;dahi chawal;dahi bhaat;doi bhat;daddojanam",
    "south", "staple", "plate", "1 plate (INDB serving: from 80 g raw rice)", 300, ("indbsrv", "ASC126"), "unknown", INDB_NOWATER)
add("bread_white_slice", "White bread (1 slice)", "পাউরুটি", "ब्रेड (सफ़ेद)", "ಬ್ರೆಡ್",
    "bread;white bread;pauruti;pau ruti;double roti;sandwich bread;bread slice;toast;bread toast",
    "pan", "staple", "piece", "1 slice (25 g)", 25, ("fdc", 174924), "high",
    "GI: Atkinson 2008 Table 1 white wheat bread 75+/-2 (high).")
add("bread_brown_slice", "Whole-wheat (brown) bread (1 slice)", "ব্রাউন ব্রেড", "ब्राउन ब्रेड", "ಬ್ರೌನ್ ಬ್ರೆಡ್",
    "brown bread;whole wheat bread;wholemeal bread;atta bread;wheat bread",
    "pan", "staple", "piece", "1 slice (28 g)", 28, ("fdc", 172688), "high",
    "GI: Atkinson 2008 Table 1 whole wheat/whole meal bread 74+/-2 (high).")
add("chira_dry_katori", "Flattened rice (chira / poha), dry", "চিঁড়ে", "चिवड़ा / पोहा (सूखा)", "ಅವಲಕ್ಕಿ",
    "chira;chire;chida;chura;chiwda;chivda raw;poha raw;aval;avalakki;beaten rice;flattened rice;rice flakes",
    "pan", "staple", "katori", "1 katori dry (40 g)", 40, ("ifct", "A011"), "unknown",
    "Dry weight; when soaked it roughly doubles in weight with no added nutrients.")
add("muri_cup", "Puffed rice (muri)", "মুড়ি", "मुरमुरे", "ಮಂಡಕ್ಕಿ",
    "muri;moori;murmura;murmure;mamra;kurmura;puffed rice;mandakki;kadlepuri;pori;borugulu;laiya",
    "pan", "snack", "cup", "1 cup (20 g)", 20, ("ifct", "A012"), "unknown", "Very light; 1 cup ~ 20 g.")
add("jhal_muri_bowl", "Jhal muri", "ঝালমুড়ি", "झालमुड़ी", "ಚುರುಮುರಿ",
    "jhal muri;jhalmuri;jhaal muri;masala muri;muri makha;churmuri;churumuri;bhel;dry bhel",
    "bengali", "snack", "bowl", "1 bowl (~90 g)", 90,
    ("recipe", [("rice_puffed", 30), ("onion", 15), ("cucumber", 15), ("tomato", 10), ("groundnut", 8),
                ("chana_dal", 5), ("mustard_oil", 4)]), "unknown",
    "Roasted chana approximated by raw chana dal. Chanachur/sev toppings (if added) increase fat and kcal.")
add("chire_doi_bowl", "Chire doi (flattened rice with curd, banana, jaggery)", "চিঁড়ে দই", "दही चूड़ा", "ಮೊಸರು ಅವಲಕ್ಕಿ",
    "chire doi;doi chire;chira doi;dahi chura;dahi chiwda;mosaru avalakki;curd poha;phalahar",
    "bengali", "breakfast", "bowl", "1 bowl (~200 g)", 200,
    ("recipe", [("rice_flakes", 40), ("curd", 100), ("banana", 50), ("jaggery", 10)]), "unknown", "")

# ---------------- DALS / LEGUMES ----------------
add("dal_moong_katori", "Moong dal", "মুগ ডাল", "मूंग दाल", "ಹೆಸರು ಬೇಳೆ ತೊವ್ವೆ",
    "moong dal;mung dal;moong ki dal;muger dal;mug dal;moog dal;hesaru bele;hesarubele togge;pesara pappu;yellow moong dal;dhuli moong dal",
    "pan", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "ASC151"), "unknown",
    "INDB recipe: 30 g moong dal + 1 tsp oil + 1 cup water per bowl (thin home-style dal). " + NOYIELD)
add("dal_masoor_katori", "Masoor dal", "মুসুর ডাল", "मसूर दाल", "ಮಸೂರ್ ಬೇಳೆ ಸಾರು",
    "masoor dal;masur dal;musur dal;mosur dal;mushur dal;red lentil dal;lentil dal;lal dal;dal bengali",
    "pan", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "ASC157"), "unknown",
    "INDB recipe uses whole masoor (30 g) with tomato/onion and 2 tsp oil; split masoor dal has similar macros. " + NOYIELD)
add("dal_toor_katori", "Toor / arhar dal (dal tadka)", "অড়হর ডাল", "अरहर / तूर दाल", "ತೊಗರಿ ಬೇಳೆ ಸಾರು",
    "toor dal;tur dal;tuvar dal;toovar dal;arhar dal;arahar dal;orhor dal;dal tadka;dal fry;yellow dal;tadka dal;togari bele;togari bele saaru;paruppu;pappu;dal;lentils;lentil;cooked lentils;lentil curry",
    "pan", "dal", "katori", "1 katori (150 g; from 25 g dry dal)", 150,
    ("recipe", [("toor_dal", 25), ("tomato", 20), ("onion", 10), ("ghee", 2), ("oil", 2), ("water", 91)]), "unknown",
    "INDB has no plain toor dal; standard recipe. Restaurant dal fry/tadka often has 2-3x the fat.")
add("dal_chana_katori", "Chana dal", "ছোলার ডাল (উত্তর ভারতীয়)", "चना दाल", "ಕಡಲೆ ಬೇಳೆ ಸಾರು",
    "chana dal;channa dal;chane ki dal;chana dal tadka;kadale bele;senaga pappu;bengal gram dal",
    "north", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "OSR142"), "unknown", NOYIELD)
add("cholar_dal_katori", "Cholar dal (Bengali chana dal with coconut)", "ছোলার ডাল", "छोलार दाल", "ಛೋಲಾರ್ ದಾಲ್",
    "cholar dal;cholar daal;chholar dal;narkel diye cholar dal;bengali chana dal",
    "bengali", "dal", "katori", "1 katori (150 g; from 30 g dry dal)", 150,
    ("recipe", [("chana_dal", 30), ("coconut", 8), ("sugar", 3), ("ghee", 3), ("oil", 2), ("raisins", 2), ("water", 102)]),
    "unknown", "Standard Bengali recipe (sweetish, with coconut and raisins).")
add("dal_makhani_katori", "Dal makhani", "ডাল মাখানি", "दाल मखनी", "ದಾಲ್ ಮಖನಿ",
    "dal makhani;dal makhni;daal makhani;maa ki dal;kali dal;black dal;dal bukhara",
    "north", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "OSR139"), "unknown",
    "INDB recipe includes 4 cups water before simmering; restaurant dal makhani is more reduced and richer (likely 1.5-2x). " + NOYIELD)
add("sambar_katori", "Sambar", "সাম্বার", "सांभर", "ಸಾಂಬಾರ್",
    "sambar;sambhar;saambar;saambaar;huli;tiffin sambar;sambar dal;kuzhambu;mixed veg sambar",
    "south", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "ASC167"), "unknown", NOYIELD)
add("rasam_katori", "Rasam / saaru", "রসম", "रसम", "ಸಾರು",
    "rasam;saaru;saru;charu;chaaru;tomato rasam;pepper rasam;tili saaru;puli rasam;rasam saaru",
    "south", "dal", "katori", "1 katori (150 g)", 150, ("indb100", "BFP176"), "unknown", "")
add("rajma_katori", "Rajma (kidney bean curry)", "রাজমা", "राजमा", "ರಾಜ್ಮಾ",
    "rajma;rajmah;rajma masala;rajma curry;kidney beans curry;red beans curry;rajma chawal",
    "north", "dal", "katori", "1 katori (INDB serving: from 30 g dry rajma)", 150, ("indbsrv", "ASC165"), "unknown", INDB_NOWATER)
add("chole_katori", "Chole (chickpea curry)", "ছোলে / কাবুলি ছোলার তরকারি", "छोले", "ಚೋಲೆ",
    "chole;chhole;cholle;chana masala;channa masala;kabuli chana;chickpea curry;pindi chole;safed chana;chole masala;kadale curry",
    "north", "dal", "katori", "1 katori (INDB serving: from 30 g dry chickpeas)", 150, ("indbsrv", "ASC162"), "unknown", INDB_NOWATER)
add("kala_chana_katori", "Kala chana curry (black chickpea)", "কালো ছোলার তরকারি", "काले चने", "ಕರಿ ಕಡಲೆ ಸಾರು",
    "kala chana;kale chane;black chana;black chickpea curry;kadala curry;kala chana masala;bengal gram curry",
    "north", "dal", "katori", "1 katori (INDB serving: from ~30 g dry chana)", 150, ("indbsrv", "ASC161"), "unknown", INDB_NOWATER)
add("ghugni_katori", "Ghugni (dried yellow pea curry)", "ঘুগনি", "घुगनी", "ಘುಗ್ನಿ",
    "ghugni;ghoogni;ghugni chaat;matar ghugni;yellow peas curry;dried peas curry;ragda",
    "bengali", "dal", "katori", "1 katori (150 g; from 30 g dry peas)", 150,
    ("recipe", [("peas_dry", 30), ("potato", 15), ("onion", 15), ("tomato", 10), ("mustard_oil", 5), ("water", 75)]),
    "unknown", "Standard home recipe.")
add("kadhi_katori", "Kadhi (without pakodi)", "কড়ি", "कढ़ी", "ಮಜ್ಜಿಗೆ ಹುಳಿ",
    "kadhi;kadi;karhi;punjabi kadhi;gujarati kadhi;kadhi chawal;majjige huli;mor kuzhambu;more kuzhambu",
    "north", "curry", "katori", "1 katori (150 g)", 150,
    ("recipe", [("curd", 60), ("besan", 8), ("oil", 2), ("ghee", 2), ("water", 78)]), "unknown",
    "INDB kadhi (ASC168) not used: it counts all pakodi frying oil. Add a pakora row for kadhi-pakora.")

# ---------------- VEG CURRIES / SABZI ----------------
add("palak_paneer_katori", "Palak paneer", "পালং পনির", "पालक पनीर", "ಪಾಲಕ್ ಪನೀರ್",
    "palak paneer;saag paneer;spinach paneer;palak panir;palong paneer",
    "north", "curry", "katori", "1 katori (150 g)", 150, ("indb100", "ASC215"), "unknown",
    "Home-style INDB recipe; restaurant versions with cream/butter are richer. " + NOYIELD)
add("paneer_butter_masala_katori", "Paneer butter masala", "পনির বাটার মসলা", "पनीर बटर मसाला", "ಪನೀರ್ ಬಟರ್ ಮಸಾಲ",
    "paneer butter masala;paneer makhani;paneer makhanwala;butter paneer;paneer in butter sauce;shahi paneer",
    "north", "curry", "katori", "1 katori (150 g)", 150, ("indb100", "ASC222"), "unknown",
    "INDB 'Paneer in butter sauce'; restaurant versions often contain more cream/butter. " + NOYIELD)
add("matar_paneer_katori", "Matar paneer", "মটর পনির", "मटर पनीर", "ಮಟರ್ ಪನೀರ್",
    "matar paneer;mutter paneer;peas paneer;paneer matar;motor paneer",
    "north", "curry", "katori", "1 katori (150 g)", 150, ("indb100", "ASC191"), "unknown", NOYIELD)
add("kadai_paneer_katori", "Kadai paneer", "কড়াই পনির", "कड़ाही पनीर", "ಕಡಾಯಿ ಪನೀರ್",
    "kadai paneer;kadhai paneer;karahi paneer;paneer kadai",
    "north", "curry", "katori", "1 katori (150 g)", 150, ("indb100", "ASC226"), "unknown", NOYIELD)
add("aloo_sabzi_katori", "Aloo sabzi (potato curry)", "আলুর তরকারি", "आलू की सब्ज़ी", "ಆಲೂಗಡ್ಡೆ ಪಲ್ಯ",
    "aloo sabzi;aloo ki sabji;alu sabji;aloo bhaji;potato curry;potato sabzi;aloo tarkari;alur torkari;alur dom;batata bhaji;poori bhaji;aloo palya",
    "pan", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "BFP239"), "unknown", NOYIELD)
add("aloo_gobi_katori", "Aloo gobi", "আলু ফুলকপির তরকারি", "आलू गोभी", "ಆಲೂ ಗೋಬಿ",
    "aloo gobi;aloo gobhi;alu gobi;potato cauliflower;phulkopir torkari;gobi aloo;cauliflower curry",
    "north", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC171"), "unknown", NOYIELD)
add("aloo_matar_katori", "Aloo matar", "আলু মটর", "आलू मटर", "ಆಲೂ ಮಟರ್",
    "aloo matar;aloo mutter;alu matar;potato peas curry;matar aloo",
    "north", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC190"), "unknown", NOYIELD)
add("bhindi_katori", "Bhindi (okra) sabzi", "ঢ্যাঁড়স ভাজা", "भिंडी की सब्ज़ी", "ಬೆಂಡೆಕಾಯಿ ಪಲ್ಯ",
    "bhindi;bhindi fry;bhindi masala;bhindi sabzi;okra;okra fry;ladies finger;ladyfinger;bhendi;bende kayi palya;dherosh bhaja;dherosh;vendakkai poriyal",
    "pan", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "BFP269"), "unknown", NOYIELD)
add("baingan_bharta_katori", "Baingan bharta (begun pora)", "বেগুন পোড়া", "बैंगन का भर्ता", "ಬದನೆಕಾಯಿ ಭರ್ತ",
    "baingan bharta;baingan ka bharta;bharta;begun pora;begun bharta;brinjal bharta;eggplant mash;vangyache bharit;badanekayi gojju",
    "pan", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC177"), "unknown", NOYIELD)
add("mixed_veg_katori", "Mixed vegetable sabzi", "পাঁচমিশালি তরকারি", "मिक्स वेज", "ಮಿಕ್ಸ್ ವೆಜ್ ಪಲ್ಯ",
    "mixed veg;mix veg;mixed vegetable;mixed vegetable curry;sabzi;subzi;sabji;tarkari;torkari;panchmishali torkari;gobi matar aloo;mixed vegetable sabzi",
    "pan", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "BFP276"), "unknown",
    "INDB 'Cauliflower, pea and potato bhujia' used as the representative mixed-vegetable sabzi. " + NOYIELD)
add("cabbage_poriyal_katori", "Cabbage poriyal / palya", "বাঁধাকপির তরকারি", "पत्तागोभी की सब्ज़ी", "ಎಲೆಕೋಸು ಪಲ್ಯ",
    "cabbage poriyal;cabbage palya;cabbage thoran;kosu palya;ele kosu palya;bandhakopi;badhakopir torkari;patta gobhi sabzi;cabbage sabzi;cabbage stir fry",
    "karnataka", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC181"), "unknown",
    "INDB 'Carrot and cabbage with coconut' (thoran-style) used. " + NOYIELD)
add("beans_poriyal_katori", "Beans palya / poriyal", "বিনস ভাজা", "बीन्स की सब्ज़ी", "ಹುರುಳಿಕಾಯಿ ಪಲ್ಯ",
    "beans palya;beans poriyal;beans thoran;hurali kayi palya;french beans sabzi;beans sabzi;green beans stir fry",
    "karnataka", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC179"), "unknown", NOYIELD)
add("avial_katori", "Avial", "আভিয়াল", "अवियल", "ಅವಿಯಲ್",
    "avial;aviyal;avail;mixed vegetables in coconut",
    "south", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC219"), "unknown", NOYIELD)
add("sarson_saag_katori", "Sarson ka saag", "সর্ষে শাক", "सरसों का साग", "ಸಾಸಿವೆ ಸೊಪ್ಪಿನ ಪಲ್ಯ",
    "sarson ka saag;sarson saag;saag;mustard greens curry;sarso da saag",
    "north", "veg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC217"), "unknown", NOYIELD)
add("lauki_sabzi_katori", "Lauki / lau (bottle gourd) sabzi", "লাউয়ের তরকারি", "लौकी की सब्ज़ी", "ಸೋರೆಕಾಯಿ ಪಲ್ಯ",
    "lauki;lauki sabzi;lauki ki sabji;ghiya;dudhi;doodhi;lau;lau ghonto;lau torkari;bottle gourd curry;sorekai palya;sorakaya",
    "pan", "veg", "katori", "1 katori (150 g cooked)", 150,
    ("recipe", [("bottle_gourd", 160), ("tomato", 15), ("oil", 5)]), "unknown", "Standard recipe; cooked weight assumes ~10% water loss.")
add("shukto_katori", "Shukto (Bengali mixed bitter vegetable)", "শুক্তো", "शुक्तो", "ಶುಕ್ತೋ",
    "shukto;sukto;shuktoni;shukto bengali;bitter gourd mixed veg",
    "bengali", "veg", "katori", "1 katori (150 g)", 150,
    ("recipe", [("bitter_gourd", 20), ("plantain_green", 20), ("potato", 20), ("sweet_potato", 15), ("brinjal", 20),
                ("drumstick", 15), ("milk", 20), ("ghee", 3), ("mustard_oil", 5), ("poppy", 2), ("mustard_seed", 2), ("sugar", 2)]),
    "unknown", "Standard Bengali recipe; vegetable mix varies by household.")
add("aloo_posto_katori", "Aloo posto (potato in poppy-seed paste)", "আলু পোস্ত", "आलू पोस्तो", "ಆಲೂ ಪೋಸ್ತೋ",
    "aloo posto;alu posto;aloo posta;alur posto;posto;potato poppy seed",
    "bengali", "veg", "katori", "1 katori (150 g)", 150,
    ("recipe", [("potato", 125), ("poppy", 12), ("mustard_oil", 8)]), "unknown", "Standard Bengali recipe.")
add("begun_bhaja_piece", "Begun bhaja (fried brinjal slice)", "বেগুন ভাজা", "बैंगन भाजा", "ಬದನೆಕಾಯಿ ಫ್ರೈ",
    "begun bhaja;baigun bhaja;begun vaja;fried brinjal;brinjal fry;baingan fry;eggplant fry",
    "bengali", "veg", "piece", "1 slice (~35 g fried, from 45 g brinjal)", 35,
    ("recipe", [("brinjal", 45), ("mustard_oil", 5)]), "unknown", "Brinjal absorbs a lot of oil; 5 g absorbed oil per slice assumed. " + OIL)
add("beguni_piece", "Beguni (batter-fried brinjal)", "বেগুনি", "बेगुनी", "ಬದನೆಕಾಯಿ ಬಜ್ಜಿ",
    "beguni;begooni;brinjal fritter;baingan pakora;badanekayi bajji;telebhaja",
    "bengali", "snack", "piece", "1 piece (~35 g)", 35,
    ("recipe", [("brinjal", 25), ("besan", 8), ("rice_flour", 2), ("oil", 5)]), "unknown", OIL)

# ---------------- NON-VEG ----------------
add("chicken_curry_katori", "Chicken curry", "মুরগির ঝোল", "चिकन करी", "ಕೋಳಿ ಸಾರು",
    "chicken curry;murgir jhol;murgir mangsho;chicken jhol;chicken masala;chicken gravy;murgh curry;kozhi curry;koli saaru;chicken saaru",
    "pan", "nonveg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC240"), "unknown",
    "INDB recipe with boneless chicken; values per raw-ingredient weight, so per cooked gram may be ~10-20% higher. " + NOYIELD)
add("butter_chicken_katori", "Butter chicken", "বাটার চিকেন", "बटर चिकन", "ಬಟರ್ ಚಿಕನ್",
    "butter chicken;murgh makhani;chicken makhani;chicken makhanwala",
    "north", "nonveg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC242"), "unknown", NOYIELD)
add("tandoori_chicken_serving", "Tandoori chicken", "তন্দুরি চিকেন", "तंदूरी चिकन", "ತಂದೂರಿ ಚಿಕನ್",
    "tandoori chicken;tandoori murgh;chicken tandoori;tangdi kabab;chicken tikka",
    "north", "nonveg", "serving", "1 serving (150 g edible, ~2 pieces)", 150, ("indb100", "ASC241"), "unknown", NOYIELD)
add("egg_curry_serving", "Egg curry (1 egg with gravy)", "ডিমের ঝোল", "अंडा करी", "ಮೊಟ್ಟೆ ಸಾರು",
    "egg curry;anda curry;dimer jhol;dim er jhol;egg masala;motte saaru;motte curry;muttai kulambu",
    "pan", "nonveg", "serving", "1 egg with gravy (INDB serving)", 152, ("indbsrv", "BFP240"), "unknown", INDB_W)
add("dimer_dalna_serving", "Dimer dalna (egg and potato curry)", "ডিমের ডালনা", "अंडा आलू करी", "ಮೊಟ್ಟೆ ಆಲೂ ಸಾರು",
    "dimer dalna;dim er dalna;dimer dalna with potato;egg potato curry;dim aloo;egg aloo curry",
    "bengali", "nonveg", "serving", "1 egg + potato with gravy (~170 g)", 170,
    ("recipe", [("egg_boiled", 50), ("potato", 50), ("onion", 20), ("tomato", 20), ("mustard_oil", 8), ("sugar", 1), ("water", 25)]),
    "unknown", "Standard Bengali recipe.")
add("boiled_egg_piece", "Boiled egg", "সেদ্ধ ডিম", "उबला अंडा", "ಬೇಯಿಸಿದ ಮೊಟ್ಟೆ",
    "boiled egg;egg;anda;dim;dim sedho;hard boiled egg;ubla anda;motte",
    "pan", "nonveg", "piece", "1 large egg (50 g edible)", 50, ("fdc", 173424), "unknown", "")
add("omelette_piece", "Omelette (1 egg)", "ওমলেট", "ऑमलेट", "ಆಮ್ಲೆಟ್",
    "omelette;omelet;omlet;amlet;mamlet;egg omelette;masala omelette;anda omelette;dimer omelette",
    "pan", "nonveg", "piece", "1-egg omelette (~55 g)", 55, ("ifct", "M007"), "unknown",
    "IFCT 2017 analysed omelette; a masala omelette with onion/extra oil is slightly higher.")
add("mutton_curry_katori", "Mutton curry", "পাঁঠার মাংসের ঝোল", "मटन करी", "ಮಟನ್ ಸಾರು",
    "mutton curry;mutton;mutton masala;mutton gravy;gosht;rogan josh;roghan josh;mangsher jhol;mangsho;goat curry;lamb curry;kuri saaru;mutton saaru",
    "pan", "nonveg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC227"), "unknown",
    "INDB 'Roghan josh' used as representative mutton curry. " + NOYIELD)
add("kosha_mangsho_katori", "Kosha mangsho (Bengali dry mutton curry)", "কষা মাংস", "कोषा मांगशो", "ಕೋಷಾ ಮಾಂಸ",
    "kosha mangsho;kosha mangso;kosha mutton;kasha mangsho;bengali mutton kosha;golbari kosha",
    "bengali", "nonveg", "katori", "1 katori (~150 g; from 100 g raw mutton)", 150,
    ("recipe", [("goat", 100), ("onion", 40), ("curd", 15), ("mustard_oil", 12)]), "unknown",
    "Rich, oil-heavy dish; 12 g mustard oil per serving assumed. Often served with potato (+~15 g carbs).")
add("macher_jhol_katori", "Macher jhol (Bengali fish curry)", "মাছের ঝোল", "माछेर झोल (बंगाली मछली करी)", "ಮೀನಿನ ಸಾರು (ಬಂಗಾಳಿ)",
    "macher jhol;maacher jhol;machher jhol;mach er jhol;fish jhol;bengali fish curry;rui macher jhol;katla jhol;fish curry bengali",
    "bengali", "nonveg", "katori", "1 katori (150 g; ~1 piece fish)", 150, ("indb100", "BFP223"), "unknown",
    "INDB 'Bengal fish curry' (mustard oil). " + NOYIELD)
add("fish_curry_katori", "Fish curry", "মাছের কারি", "मछली करी", "ಮೀನು ಸಾರು",
    "fish curry;machli curry;machhi curry;meen curry;meen kuzhambu;meenu saaru;meen gassi;fish masala;fish gravy",
    "pan", "nonveg", "katori", "1 katori (150 g)", 150, ("indb100", "ASC246"), "unknown", "INDB recipe with rohu. " + NOYIELD)
add("chingri_malaikari_katori", "Chingri malaikari (prawn coconut curry)", "চিংড়ি মালাইকারি", "झींगा मलाई करी", "ಸಿಗಡಿ ಮಲೈಕರಿ",
    "chingri malaikari;chingri malai curry;prawn malai curry;prawn malaikari;prawn curry;jhinga curry;chingri;shrimp curry;sigadi curry",
    "bengali", "nonveg", "katori", "1 katori (150 g)", 150, ("indb100", "BFP230"), "unknown",
    "Closest INDB match is 'Prawn curry (with coconut)'; true malaikari uses coconut milk and ghee and is likely richer in fat.")
add("fish_fry_piece", "Fish fry (mach bhaja)", "মাছ ভাজা", "मछली फ्राई", "ಮೀನು ಫ್ರೈ",
    "fish fry;mach bhaja;maach bhaja;macher bhaja;rui mach bhaja;fried fish;tawa fish;fish tawa fry;meen fry;meenu fry",
    "bengali", "nonveg", "piece", "1 piece (~50 g fried, from 60 g raw rohu/katla)", 50,
    ("recipe", [("rohu", 60), ("mustard_oil", 4)]), "unknown",
    "Turmeric-salt pan-fried fish. Breaded Kolkata 'fish fry' cutlet is different (~2x kcal, ~15 g carbs). " + OIL)

# ---------------- SNACKS ----------------
add("samosa_piece", "Samosa", "শিঙাড়া", "समोसा", "ಸಮೋಸ",
    "samosa;samosha;shingara;singara;singhara;aloo samosa;samsa;samose",
    "pan", "snack", "piece", "1 samosa (75 g; FNDDS portion)", 75, ("fdc", 2708730), "unknown",
    "USDA FNDDS 'Samosa' (as eaten). INDB samosa not used: it counts all frying oil.")
add("kachori_piece", "Kachori (moong dal)", "কচুরি", "कचौड़ी", "ಕಚೋರಿ",
    "kachori;kachauri;kachuri;khasta kachori;dal kachori;moong dal kachori;koraishutir kochuri",
    "pan", "snack", "piece", "1 kachori (~45 g)", 45,
    ("recipe", [("maida", 25), ("moong_dal", 8), ("oil", 10)]), "unknown",
    "3 g oil in dough + 7 g absorbed; INDB kachori not used (counts all frying oil). " + OIL)
add("pakora_plate", "Pakora / pakoda (onion), 4 pieces", "পেঁয়াজি", "पकौड़ा", "ಈರುಳ್ಳಿ ಬಜ್ಜಿ",
    "pakora;pakoda;pakodi;pakore;bhajji;bhaji;bajji;onion pakoda;pyaaz pakora;kanda bhaji;piyaji;peyaji;telebhaja;fritters;bhajia",
    "pan", "snack", "serving", "4 pieces (~60 g)", 60,
    ("recipe", [("besan", 20), ("onion", 30), ("rice_flour", 3), ("oil", 9)]), "unknown",
    "9 g absorbed oil per 60 g (15% fat by weight) assumed. " + OIL)
add("medu_vada_piece", "Medu vada", "মেদু বড়া", "मेदु वड़ा", "ಉದ್ದಿನ ವಡೆ",
    "medu vada;medu wada;vada;vadai;wada;vade;uddina vade;ulundu vadai;minapa garelu;urad dal vada;sambar vada",
    "south", "snack", "piece", "1 vada (~50 g)", 50,
    ("recipe", [("urad_dal", 25), ("onion", 3), ("oil", 6)]), "unknown",
    "6 g absorbed oil (~12% fat by weight) assumed; INDB medu vada not used (counts all frying oil). " + OIL)
add("masala_vada_piece", "Masala vada (chana dal vada)", "ডালের বড়া", "मसाला वड़ा", "ಮಸಾಲೆ ವಡೆ",
    "masala vada;masala vade;paruppu vadai;chattambade;ambode;dal vada;chana dal vada;dal bora",
    "south", "snack", "piece", "1 vada (~45 g)", 45,
    ("recipe", [("chana_dal", 25), ("onion", 10), ("oil", 6)]), "unknown", OIL)
add("bonda_piece", "Aloo bonda / batata vada", "আলুর চপ", "आलू बोंडा / बटाटा वड़ा", "ಆಲೂ ಬೋಂಡಾ",
    "bonda;aloo bonda;potato bonda;batata vada;alur chop;aloo chop;alu chop;mysore bonda",
    "pan", "snack", "piece", "1 piece (~60 g)", 60,
    ("recipe", [("potato", 40), ("onion", 5), ("besan", 12), ("oil", 6)]), "unknown",
    "Mysore bonda (maida-curd batter, no potato) differs. " + OIL)
add("dhokla_piece", "Dhokla", "ধোকলা", "ढोकला", "ಢೋಕ್ಲಾ",
    "dhokla;khaman;khaman dhokla;besan dhokla;dokla",
    "pan", "snack", "piece", "1 piece (INDB serving)", 40, ("indbsrv", "ASC474"), "unknown", INDB_W)
add("pav_bhaji_plate", "Pav bhaji (bhaji + 2 pav)", "পাও ভাজি", "पाव भाजी", "ಪಾವ್ ಭಾಜಿ",
    "pav bhaji;pao bhaji;paav bhaji;bhaji pav",
    "pan", "snack", "plate", "1 plate (bhaji + ~2 pav; INDB serving)", 580, ("indbsrv", "OSR112"), "unknown",
    "INDB recipe includes buttered buns (~103 g bun per serving). " + INDB_W)
add("sprouts_salad_katori", "Sprouted moong salad", "অঙ্কুরিত মুগের স্যালাড", "अंकुरित मूंग सलाद", "ಮೊಳಕೆ ಹೆಸರುಕಾಳು ಸಲಾಡ್",
    "sprouts;sprouts salad;sprouted moong;moong sprouts;sprouts chaat;ankurit moong;molake kaalu",
    "pan", "snack", "katori", "1 katori (150 g)", 150, ("indb100", "ASC259"), "unknown", "")
add("roasted_chana_katori", "Roasted chana", "ছোলা ভাজা", "भुने चने", "ಹುರಿಗಡಲೆ",
    "roasted chana;bhuna chana;chana;chola bhaja;phutana;hurigadale;putani;roasted gram;chana snack",
    "pan", "snack", "katori", "1 small katori (30 g)", 30, ("ifct", "B002"), "unknown",
    "IFCT whole Bengal gram (raw) used as proxy; roasting removes a little water, so true values are slightly higher.")
add("peanuts_handful", "Peanuts (handful)", "চিনাবাদাম", "मूंगफली", "ಕಡಲೆಕಾಯಿ",
    "peanuts;peanut;groundnut;moongphali;mungfali;china badam;badam bhaja;kadlekai;shenga",
    "pan", "snack", "serving", "1 handful (30 g)", 30, ("ifct", "H012"), "unknown", "IFCT raw groundnut values.")
add("chikki_piece", "Peanut chikki", "বাদাম চাক্তি", "मूंगफली चिक्की", "ಕಡಲೆಕಾಯಿ ಚಿಕ್ಕಿ",
    "chikki;peanut chikki;groundnut chikki;badam chakti;gajak;peanut brittle;kadalekai chikki",
    "pan", "sweet", "piece", "1 piece (INDB serving)", 25, ("indbsrv", "ASC382"), "unknown", INDB_W)
add("papad_roasted_piece", "Papad (roasted)", "পাঁপড় (সেঁকা)", "पापड़ (भुना)", "ಹಪ್ಪಳ (ಸುಟ್ಟ)",
    "papad;papadum;pappadam;poppadom;papar;papor;pampad;happala;roasted papad",
    "pan", "accompaniment", "piece", "1 medium papad (12 g)", 12, ("fdc", 168106), "unknown", "")
add("papad_fried_piece", "Papad (fried)", "পাঁপড় ভাজা", "पापड़ (तला)", "ಹಪ್ಪಳ (ಕರಿದ)",
    "fried papad;papad fry;papor bhaja;fried pappadam;fried happala",
    "pan", "accompaniment", "piece", "1 medium papad, fried (~15 g)", 15,
    ("recipe", [("papad", 12), ("oil", 3)]), "unknown", OIL)

# ---------------- SWEETS ----------------
add("mishti_doi_cup", "Mishti doi (sweet curd)", "মিষ্টি দই", "मिष्टी दोई", "ಮಿಷ್ಟಿ ದೋಯಿ",
    "mishti doi;misti doi;mishti dahi;sweet curd;sweet dahi;sweet yogurt;lal doi",
    "bengali", "sweet", "cup", "1 small clay cup (100 g)", 100,
    ("recipe", [("milk", 150), ("sugar", 12)]), "unknown",
    "150 ml whole milk reduced to ~100 g and set with 12 g sugar/caramel (standard recipe).")
add("rasgulla_piece", "Rasgulla (rosogolla)", "রসগোল্লা", "रसगुल्ला", "ರಸಗುಲ್ಲ",
    "rasgulla;rasagola;rosogolla;roshogolla;rossogolla;rasagulla;rasgolla;sponge rasgulla",
    "bengali", "sweet", "piece", "1 piece with some syrup (~50 g)", 50,
    ("recipe", [("chhena_from_milk", 75), ("maida", 1), ("sugar", 14)]), "unknown",
    "Chhena from 75 ml milk + ~14 g sugar absorbed from syrup (assumption). INDB rasgulla (BFP392) not used: its per-serving value includes the whole syrup.")
add("sandesh_piece", "Sandesh", "সন্দেশ", "संदेश", "ಸಂದೇಶ್",
    "sandesh;sondesh;shondesh;sandesh sweet;nolen gurer sandesh;kanchagolla",
    "bengali", "sweet", "piece", "1 piece (~30 g)", 30,
    ("recipe", [("chhena_from_milk", 100), ("sugar", 8)]), "unknown", "Chhena from 100 ml milk + 8 g sugar (standard recipe).")
add("gulab_jamun_piece", "Gulab jamun", "গোলাপ জাম / পান্তুয়া", "गुलाब जामुन", "ಗುಲಾಬ್ ಜಾಮೂನ್",
    "gulab jamun;gulabjamun;gulab jamoon;jamun sweet;pantua;kalo jaam;kala jamun;lal mohan",
    "pan", "sweet", "piece", "1 piece with syrup (~45 g)", 45,
    ("recipe", [("khoa", 15), ("maida", 3), ("oil", 3), ("sugar", 15)]), "unknown",
    "3 g absorbed frying fat and ~15 g sugar absorbed from syrup (assumptions). INDB gulab jamun not used (counts all oil and syrup).")
add("jalebi_serving", "Jalebi (2 pieces)", "জিলিপি", "जलेबी", "ಜಿಲೇಬಿ",
    "jalebi;jilebi;jilipi;jilapi;jalabi;zulbia;imarti",
    "pan", "sweet", "serving", "2 medium pieces (~50 g)", 50,
    ("recipe", [("maida", 15), ("curd", 3), ("oil", 7), ("sugar", 20)]), "unknown",
    "7 g absorbed oil and 20 g sugar from syrup per 50 g are assumptions; jalebi composition varies a lot.")
add("kheer_bowl", "Kheer / payesh (rice pudding)", "পায়েস", "खीर", "ಪಾಯಸ",
    "kheer;khir;payesh;payesam;payasam;chawal ki kheer;rice kheer;rice payasam;paramannam;doodh pak",
    "pan", "sweet", "bowl", "1 bowl (from 250 ml milk + 10 g rice + 1.5 tbsp sugar)", 200, ("indbsrv", "ASC282"), "unknown",
    "INDB weight 401 g includes 120 ml water that evaporates; ~200 g served is an estimate. Macros are INDB per-serving.")
add("semiya_payasam_bowl", "Semiya payasam (vermicelli kheer)", "সেমাইয়ের পায়েস", "सेवइयां खीर", "ಶ್ಯಾವಿಗೆ ಪಾಯಸ",
    "semiya payasam;semiya kheer;seviyan;sevaiyan kheer;vermicelli kheer;shavige payasa;semai payesh",
    "south", "sweet", "bowl", "1 bowl (from 200 ml milk + 10 g vermicelli)", 180, ("indbsrv", "ASC285"), "unknown",
    "Served weight after reduction is an estimate. Macros are INDB per-serving.")
add("mysore_pak_piece", "Mysore pak", "মাইসোর পাক", "मैसूर पाक", "ಮೈಸೂರು ಪಾಕ್",
    "mysore pak;mysorepak;mysore paak;mysuru pak;ghee mysore pak",
    "karnataka", "sweet", "piece", "1 piece (~30 g)", 30,
    ("recipe", [("besan", 7), ("ghee", 10), ("sugar", 15)]), "unknown",
    "Proportions besan:ghee:sugar ~ 1:1.4:2 assumed (traditional recipes vary).")
add("besan_laddoo_piece", "Laddoo (besan)", "লাড্ডু", "बेसन लड्डू", "ಉಂಡೆ (ಕಡಲೆಹಿಟ್ಟು)",
    "laddoo;ladoo;laddu;ladu;besan ladoo;besan laddu;besan ke laddu;unde;boondi laddoo;motichoor laddoo",
    "pan", "sweet", "piece", "1 laddoo (INDB serving)", 35, ("indbsrv", "ASC343"), "unknown",
    "Boondi/motichoor laddoo has similar energy but more sugar and less protein. " + INDB_W)
add("narkel_naru_piece", "Narkel naru (coconut laddoo)", "নারকেল নাড়ু", "नारियल लड्डू", "ಕೊಬ್ಬರಿ ಉಂಡೆ",
    "narkel naru;narikel naru;narkol naru;coconut ladoo;nariyal laddoo;kobbari unde;thengai laddu",
    "bengali", "sweet", "piece", "1 piece (~25 g)", 25,
    ("recipe", [("coconut", 20), ("jaggery", 12)]), "unknown", "Fresh coconut + jaggery; cooked weight after moisture loss is an estimate.")
add("burfi_piece", "Burfi (khoa)", "বরফি", "बर्फी", "ಬರ್ಫಿ",
    "burfi;barfi;khoa burfi;milk burfi;mawa barfi;plain barfi",
    "pan", "sweet", "piece", "1 piece (INDB serving)", 44, ("indbsrv", "ASC335"), "unknown", INDB_W)
add("kaju_katli_piece", "Kaju katli", "কাজু বরফি", "काजू कतली", "ಕಾಜು ಕಟ್ಲಿ",
    "kaju katli;kaju barfi;kaju burfi;cashew burfi;kaju katri",
    "north", "sweet", "piece", "1 large piece (INDB serving, ~29 g)", 29, ("indbsrv", "ASC339"), "unknown",
    "INDB piece is large; a typical shop diamond (~13 g) is about half. " + INDB_W)
add("gajar_halwa_bowl", "Gajar halwa", "গাজরের হালুয়া", "गाजर का हलवा", "ಕ್ಯಾರೆಟ್ ಹಲ್ವ",
    "gajar halwa;gajar ka halwa;carrot halwa;gajrela;gajorer halua",
    "north", "sweet", "bowl", "1 bowl (INDB serving)", 168, ("indbsrv", "ASC295"), "unknown", INDB_W)
add("suji_halwa_bowl", "Suji halwa (sheera)", "সুজির হালুয়া", "सूजी का हलवा", "ಸಜ್ಜಿಗೆ",
    "suji halwa;sooji halwa;rava halwa;sheera;sooji ka halwa;sujir halua;mohan bhog;sajjige",
    "north", "sweet", "bowl", "1 bowl (from 25 g suji + 20 g ghee + 20 g sugar)", 130, ("indbsrv", "ASC293"), "unknown",
    "INDB weight 160 g includes 90 ml water; served weight is an estimate. Macros are INDB per-serving.")
add("kesari_bath_katori", "Kesari bath", "কেশরী বাথ", "केसरी भात / सूजी हलवा", "ಕೇಸರಿ ಬಾತ್",
    "kesari bath;kesari bhath;kesari;rava kesari;kesaribath;sooji kesari",
    "karnataka", "sweet", "katori", "1 small katori (100 g)", 100, ("indb100", "OSR014"), "unknown", NOYIELD)
add("holige_piece", "Holige / obbattu (puran poli)", "পুরণ পোলি", "पूरन पोली", "ಹೋಳಿಗೆ / ಒಬ್ಬಟ್ಟು",
    "holige;obbattu;puran poli;puranpoli;bobbatlu;sweet roti;chana dal holige",
    "karnataka", "sweet", "piece", "1 piece (INDB serving)", 53, ("indbsrv", "ASC467"), "unknown", INDB_W)

# ---------------- BEVERAGES ----------------
add("masala_chai_sugar_cup", "Masala chai with sugar", "চা (দুধ-চিনি)", "मसाला चाय (चीनी वाली)", "ಮಸಾಲ ಟೀ (ಸಕ್ಕರೆ ಸಹಿತ)",
    "chai;masala chai;tea;milk tea;cha;dudh cha;chaha;doodh wali chai;tea with sugar;cutting chai;adrak chai",
    "pan", "beverage", "cup", "1 cup (125 ml: 60 ml milk + 2 tsp sugar)", 125,
    ("recipe", [("milk", 60), ("sugar", 8), ("tea_brewed", 57)]), "unknown",
    "Standard recipe (INDB ASC001 'Hot tea' is lighter: 34 kcal, 5.4 g carbs per cup).")
add("chai_nosugar_cup", "Chai without sugar", "চিনি ছাড়া চা", "बिना चीनी की चाय", "ಸಕ್ಕರೆ ಇಲ್ಲದ ಟೀ",
    "chai without sugar;sugar free chai;tea without sugar;no sugar tea;fika cha;milk tea no sugar",
    "pan", "beverage", "cup", "1 cup (125 ml: 60 ml milk, no sugar)", 125,
    ("recipe", [("milk", 60), ("tea_brewed", 65)]), "unknown", "")
add("lal_cha_cup", "Lal cha (black tea with 1 tsp sugar)", "লাল চা", "काली चाय (चीनी वाली)", "ಕಪ್ಪು ಟೀ",
    "lal cha;liquor cha;black tea;kali chai;lemon tea;red tea",
    "bengali", "beverage", "cup", "1 cup (125 ml + 1 tsp sugar)", 125,
    ("recipe", [("tea_brewed", 120), ("sugar", 5)]), "unknown", "")
add("filter_coffee_cup", "Filter coffee with sugar", "ফিল্টার কফি", "फ़िल्टर कॉफ़ी", "ಫಿಲ್ಟರ್ ಕಾಫಿ",
    "filter coffee;filter kaapi;kaapi;madras coffee;south indian coffee;degree coffee;coffee;milk coffee",
    "south", "beverage", "cup", "1 tumbler (120 ml: 90 ml milk + 30 ml decoction + 1.5 tsp sugar)", 126,
    ("recipe", [("milk", 90), ("coffee_brewed", 30), ("sugar", 6)]), "unknown", "")
add("filter_coffee_nosugar_cup", "Filter coffee without sugar", "চিনি ছাড়া কফি", "बिना चीनी की कॉफ़ी", "ಸಕ್ಕರೆ ಇಲ್ಲದ ಕಾಫಿ",
    "coffee without sugar;sugar free coffee;filter coffee no sugar;kaapi without sugar",
    "south", "beverage", "cup", "1 tumbler (120 ml: 90 ml milk + 30 ml decoction)", 120,
    ("recipe", [("milk", 90), ("coffee_brewed", 30)]), "unknown", "")
add("lassi_sweet_glass", "Sweet lassi", "মিষ্টি লস্যি", "मीठी लस्सी", "ಸಿಹಿ ಲಸ್ಸಿ",
    "lassi;sweet lassi;meethi lassi;lassi sweet;punjabi lassi",
    "north", "beverage", "glass", "1 glass (250 ml)", 250, ("indb100", "ASC021"), "unknown",
    "INDB recipe: 100 g curd + 20 g sugar diluted to ~440 ml; thick Punjabi lassi is ~2x richer.")
add("chaas_glass", "Buttermilk / chaas (salted)", "ঘোল", "छाछ", "ಮಜ್ಜಿಗೆ",
    "chaas;chhaas;chhach;buttermilk;majjige;mor;neer mor;ghol;matha;salted lassi;namkeen lassi;masala chaas",
    "pan", "beverage", "glass", "1 glass (250 ml)", 250, ("indb100", "ASC022"), "unknown", "")
add("nimbu_pani_sugar_glass", "Nimbu pani / lemonade with sugar", "লেবুর শরবত", "नींबू पानी (चीनी वाला)", "ನಿಂಬೆ ಪಾನಕ",
    "nimbu pani;nimbu paani;lemonade;lemon water;shikanji;shikanjvi;lebur sharbat;lemon juice;nimbe panaka",
    "pan", "beverage", "glass", "1 glass (250 ml)", 250, ("indb100", "ASC008"), "unknown", "")
add("nimbu_pani_nosugar_glass", "Nimbu pani without sugar", "চিনি ছাড়া লেবু জল", "बिना चीनी नींबू पानी", "ಸಕ್ಕರೆ ಇಲ್ಲದ ನಿಂಬೆ ನೀರು",
    "lemon water no sugar;nimbu pani without sugar;sugar free lemonade;salted lemon water;lebu jol",
    "pan", "beverage", "glass", "1 glass (250 ml; juice of 1/2 lemon)", 250,
    ("recipe", [("lemon_juice", 15), ("water", 235)]), "unknown", "")
add("milk_glass", "Milk (whole, 1 glass)", "দুধ", "दूध", "ಹಾಲು",
    "milk;doodh;dudh;haalu;paal;glass of milk;full cream milk;cow milk",
    "pan", "beverage", "glass", "1 glass (200 ml)", 200, ("ifct", "L002"), "low",
    "GI: Atkinson 2008 Table 1 milk, full fat 39+/-3 (low).")
add("coconut_water_glass", "Tender coconut water", "ডাবের জল", "नारियल पानी", "ಎಳನೀರು",
    "coconut water;daab;daber jol;nariyal pani;elaneer;tender coconut;ilaneer",
    "pan", "beverage", "glass", "1 glass (200 ml)", 200, ("ifct", "K002"), "unknown", "")
add("sugarcane_juice_glass", "Sugarcane juice", "আখের রস", "गन्ने का रस", "ಕಬ್ಬಿನ ಹಾಲು",
    "sugarcane juice;ganne ka ras;ganna juice;akher rosh;kabbina haalu;sugar cane juice",
    "pan", "beverage", "glass", "1 glass (250 ml)", 250, ("ifct", "I002"), "unknown", "")
add("ragi_malt_glass", "Ragi malt (with milk and jaggery)", "রাগি মল্ট", "रागी माल्ट", "ರಾಗಿ ಮಾಲ್ಟ್",
    "ragi malt;ragi ambli;ragi java;ragi kanji;ragi porridge;nachni satva;ragi drink",
    "karnataka", "beverage", "glass", "1 glass (~200 ml: 15 g ragi + 150 ml milk + 8 g jaggery)", 200,
    ("recipe", [("ragi", 15), ("milk", 150), ("jaggery", 8), ("water", 27)]), "unknown", "Standard recipe.")

# ---------------- FRUITS ----------------
add("banana_piece", "Banana", "কলা", "केला", "ಬಾಳೆಹಣ್ಣು",
    "banana;kela;kola;bale hannu;balehannu;pazham;robusta banana;yelakki banana",
    "pan", "fruit", "piece", "1 medium banana (100 g edible)", 100, ("ifct", "E012"), "low",
    "GI: Atkinson 2008 Table 1 banana, raw 51+/-3 (low).")
add("mango_katori", "Mango (ripe)", "আম", "आम", "ಮಾವಿನ ಹಣ್ಣು",
    "mango;aam;am;amba;mavina hannu;alphonso;himsagar;langra;banganapalli;mango slices",
    "pan", "fruit", "katori", "1 katori slices (150 g)", 150, ("ifct", "MANGO_MEAN"), "low",
    "GI: Atkinson 2008 Table 1 mango, raw 51+/-5 (low). IFCT mean of 7 Indian varieties (carbs 8.2-12.8 g/100 g).")
add("apple_piece", "Apple", "আপেল", "सेब", "ಸೇಬು",
    "apple;seb;sev;apel;sebu",
    "pan", "fruit", "piece", "1 medium apple (150 g edible)", 150, ("ifct", "E001"), "low",
    "GI: Atkinson 2008 Table 1 apple, raw 36+/-2 (low).")
add("guava_piece", "Guava", "পেয়ারা", "अमरूद", "ಸೀಬೆಹಣ್ಣು",
    "guava;amrood;amrud;peyara;seebe hannu;perakka;jam fruit",
    "pan", "fruit", "piece", "1 medium guava (100 g edible)", 100, ("ifct", "E028"), "unknown", "IFCT white-flesh guava.")
add("papaya_katori", "Papaya (ripe)", "পেঁপে", "पपीता", "ಪರಂಗಿ ಹಣ್ಣು",
    "papaya;papita;pepe;parangi hannu;ripe papaya",
    "pan", "fruit", "katori", "1 katori cubes (150 g)", 150, ("ifct", "E049"), "unknown", "")
add("orange_piece", "Orange", "কমলালেবু", "संतरा", "ಕಿತ್ತಳೆ",
    "orange;santra;santara;komla;komlalebu;kittale;narangi;mosambi",
    "pan", "fruit", "piece", "1 medium orange (130 g edible)", 130, ("ifct", "E047"), "low",
    "GI: Atkinson 2008 Table 1 orange, raw 43+/-3 (low). Mosambi (sweet lime) is a different fruit.")
add("pineapple_katori", "Pineapple", "আনারস", "अनानास", "ಅನಾನಸ್",
    "pineapple;ananas;anaras;ananas hannu",
    "pan", "fruit", "katori", "1 katori cubes (150 g)", 150, ("ifct", "E053"), "medium",
    "GI: Atkinson 2008 Table 1 pineapple, raw 59+/-8 (medium).")
add("watermelon_katori", "Watermelon", "তরমুজ", "तरबूज", "ಕಲ್ಲಂಗಡಿ",
    "watermelon;tarbooj;tarbuj;tormuj;kallangadi;water melon",
    "pan", "fruit", "katori", "1 katori cubes (150 g)", 150, ("ifct", "E065"), "high",
    "GI: Atkinson 2008 Table 1 watermelon, raw 76+/-4 (high); glycaemic load per serving is small.")
add("grapes_katori", "Grapes", "আঙুর", "अंगूर", "ದ್ರಾಕ್ಷಿ",
    "grapes;angoor;angur;draksha;drakshi;green grapes",
    "pan", "fruit", "katori", "1 katori (100 g)", 100, ("ifct", "E026"), "unknown", "IFCT seedless green grapes.")
add("pomegranate_katori", "Pomegranate (arils)", "বেদানা", "अनार", "ದಾಳಿಂಬೆ",
    "pomegranate;anar;anaar;bedana;dalimbe;dalimb",
    "pan", "fruit", "katori", "1 katori arils (100 g)", 100, ("ifct", "E055"), "unknown", "")
add("sapota_piece", "Sapota (chikoo)", "সফেদা", "चीकू", "ಸಪೋಟ",
    "sapota;chikoo;chiku;sapodilla;sofeda;sapota hannu",
    "pan", "fruit", "piece", "1 fruit (100 g edible)", 100, ("ifct", "E060"), "unknown", "")
add("custard_apple_piece", "Custard apple (sitaphal)", "আতা", "सीताफल", "ಸೀತಾಫಲ",
    "custard apple;sitaphal;sharifa;ata;aata;seetha phala",
    "pan", "fruit", "piece", "1 fruit (100 g edible pulp)", 100, ("ifct", "E016"), "unknown", "")

# ---------------- ACCOMPANIMENTS ----------------
add("curd_katori", "Curd / dahi (plain)", "টক দই", "दही", "ಮೊಸರು",
    "curd;dahi;doi;tok doi;mosaru;thayir;yogurt;yoghurt;plain curd;plain yogurt",
    "pan", "accompaniment", "katori", "1 katori (100 g)", 100, ("fdc", 171284), "unknown",
    "USDA whole-milk plain yogurt; curd from toned milk has ~1/2 the fat.")
add("raita_katori", "Raita (cucumber)", "রায়তা", "रायता", "ರಾಯಿತ",
    "raita;raitha;kheera raita;cucumber raita;boondi raita;onion raita;mosaru bajji;pachadi",
    "pan", "accompaniment", "katori", "1 katori (100 g)", 100, ("indb100", "ASC273"), "unknown",
    "Boondi raita has extra fried boondi (more fat/carbs).")
add("pickle_tbsp", "Pickle (mango, oil-based)", "আচার", "अचार", "ಉಪ್ಪಿನಕಾಯಿ",
    "pickle;achar;achaar;aachar;aam ka achar;mango pickle;uppinakayi;avakaya;oorugai",
    "pan", "accompaniment", "tbsp", "1 tbsp (15 g)", 15, ("indb100", "ASC507"), "unknown", "High in sodium.")
add("salad_plate", "Green salad (kachumber)", "স্যালাড", "सलाद", "ಸಲಾಡ್",
    "salad;green salad;kachumber;kachumbar;cucumber salad;onion tomato cucumber;sliced salad",
    "pan", "accompaniment", "plate", "1 small plate (~115 g)", 115,
    ("recipe", [("cucumber", 50), ("tomato", 40), ("onion", 20), ("lemon_juice", 5)]), "unknown", "")
add("kosambari_katori", "Kosambari (moong dal salad)", "কোসাম্বারি", "कोसंबरी", "ಕೋಸಂಬರಿ",
    "kosambari;kosumbari;hesaru bele kosambari;moong dal salad;cucumber kosambari",
    "karnataka", "accompaniment", "katori", "1 katori (~100 g)", 100,
    ("recipe", [("moong_dal", 20), ("cucumber", 50), ("carrot", 20), ("coconut", 5), ("lemon_juice", 5), ("oil", 1)]),
    "unknown", "Soaked (uncooked) moong dal; weight given dry.")
add("coconut_chutney_tbsp", "Coconut chutney", "নারকেলের চাটনি", "नारियल चटनी", "ಕಾಯಿ ಚಟ್ನಿ",
    "coconut chutney;kayi chutney;thengai chutney;nariyal chutney;white chutney;chutney",
    "south", "accompaniment", "tbsp", "1 tbsp (15 g)", 15, ("indb100", "ASC386"), "unknown",
    "Usually served as 2-3 tbsp with idli/dosa.")
add("green_chutney_tbsp", "Green chutney (mint-coriander)", "ধনেপাতার চাটনি", "हरी चटनी", "ಹಸಿರು ಚಟ್ನಿ",
    "green chutney;hari chutney;pudina chutney;mint chutney;coriander chutney;dhania chutney",
    "pan", "accompaniment", "tbsp", "1 tbsp (15 g)", 15, ("indb100", "ASC387"), "unknown", "")
add("ghee_tsp", "Ghee (1 tsp)", "ঘি", "घी", "ತುಪ್ಪ",
    "ghee;ghi;clarified butter;tuppa;neyyi;desi ghee",
    "pan", "accompaniment", "serving", "1 tsp (5 g)", 5, ("fdc", 2710168), "unknown", "")
add("sugar_tsp", "Sugar (1 tsp)", "চিনি", "चीनी", "ಸಕ್ಕರೆ",
    "sugar;chini;cheeni;sakkare;white sugar;table sugar",
    "pan", "accompaniment", "serving", "1 tsp (5 g)", 5, ("fdc", 169655), "medium",
    "GI: Atkinson 2008 Table 1 sucrose 65+/-4 (medium). Quantity is 1 teaspoon (5 g).")


# ---------------- GENERIC SWEETS ----------------
# "Sweets" without a name: the per-gram mean of the table's piece sweets (computed after them, see main()).
MITHAI_IDS = ['rasgulla_piece', 'sandesh_piece', 'gulab_jamun_piece', 'jalebi_serving', 'mysore_pak_piece', 'besan_laddoo_piece', 'burfi_piece', 'kaju_katli_piece', 'chikki_piece', 'narkel_naru_piece']
add("mithai_50g", "Indian sweets, assorted (mithai, 50 g)", "মিষ্টি", "मिठाई", "ಸಿಹಿ",
    "sweets;mithai;mithaai;indian sweets;assorted sweets;mixed sweets;desserts",
    "pan", "sweet", "serving", "50 g (about 1-2 pieces)", 50, ("mean_of", MITHAI_IDS), "unknown",
    "Assumption: per-gram mean of 10 piece sweets in this table (rasgulla, sandesh, gulab jamun, jalebi, mysore pak, "
    "laddoo, burfi, kaju katli, chikki, narkel naru). Pick the specific sweet when known: carbs per gram range ~28-63 g/100 g.")

# ---------------- AMERICAN (USDA FNDDS 2021-2023 portions and per-100 g values) ----------------
# For visitors from the USA: common restaurant and home dishes, so a photo of a burger plate or a
# pancake breakfast maps to cited nutrition. Unit weights are USDA FNDDS portion weights.
FNDDS_W = "Unit weight is the USDA FNDDS portion weight for this food."
GI_UNKNOWN_US = "No GI value assigned (mixed dish or no matching Atkinson 2008 entry)."
for _a in [
    ("us_cheeseburger_piece", "Cheeseburger", "cheeseburger;cheese burger;burger with cheese;bacon cheeseburger;double cheeseburger;cheeseburger sandwich",
     "nonveg", "piece", "1 cheeseburger, 1 medium patty (165 g)", 165, ("fdc", 2706897),
     "Fast-food cheeseburger, one medium patty. Bacon adds ~2 slices (about +90 kcal, no carbohydrate); a second patty adds protein and fat, not carbohydrate."),
    ("us_hamburger_piece", "Hamburger", "hamburger;burger;beef burger;plain burger;hamburger sandwich",
     "nonveg", "piece", "1 hamburger (145 g)", 145, ("fdc", 2706920), ""),
    ("us_french_fries_serving", "French fries", "french fries;fries;fast food fries;potato fries;crinkle fries;steak fries;shoestring fries;crinkle cut fries",
     "snack", "serving", "1 medium fast-food order (145 g)", 145, ("fdc", 2709461), "Small order 110 g, large order 180 g (USDA FNDDS)."),
    ("us_pizza_pepperoni_slice", "Pepperoni pizza (slice)", "pepperoni pizza;pepperoni pizza slice;slice of pepperoni pizza;pepperoni slice;pepperoni",
     "nonveg", "piece", "1 slice (124 g, medium crust)", 124, ("fdc", 2708640), "Thin crust slices are lighter (~91 g); thick crust heavier."),
    ("us_pizza_cheese_slice", "Cheese pizza (slice)", "cheese pizza;cheese pizza slice;pizza;pizza slice;plain pizza;slice of pizza",
     "veg", "piece", "1 slice of a large pizza (119 g, medium crust)", 119, ("fdc", 2708616), ""),
    ("us_pancake_piece", "Pancake", "pancake;pancakes;hotcake;hotcakes;flapjack;flapjacks;buttermilk pancake;stack of pancakes;pancake stack",
     "breakfast", "piece", "1 medium restaurant pancake (50 g)", 50, ("fdc", 2708299), "Syrup and butter are separate items."),
    ("us_syrup_tbsp", "Pancake syrup", "syrup;pancake syrup;maple syrup;table syrup;waffle syrup",
     "accompaniment", "tbsp", "1 tbsp (20 g)", 20, ("fdc", 2710272), "USDA 'Syrup, NFS'; pure maple syrup is similar in carbohydrate per tablespoon."),
    ("us_scrambled_eggs_serving", "Scrambled eggs", "scrambled eggs;scrambled egg;eggs;fried eggs;sunny side up eggs;over easy eggs;eggs any style",
     "breakfast", "serving", "2 eggs scrambled with butter (110 g)", 110, ("fdc", 2707201), "Fried eggs are similar; almost no carbohydrate."),
    ("us_bacon_slice", "Bacon (slice)", "bacon;bacon strip;bacon strips;crispy bacon;bacon slice;bacon slices;rasher",
     "nonveg", "piece", "1 medium slice, cooked (8 g)", 8, ("fdc", 2705889), ""),
    ("us_mac_cheese_cup", "Macaroni and cheese", "mac and cheese;macaroni and cheese;mac n cheese;mac & cheese;macaroni cheese;baked mac and cheese",
     "staple", "cup", "1 cup (230 g)", 230, ("fdc", 2708812), "Restaurant style. A side serving is often 1/2 cup."),
    ("us_fried_chicken_piece", "Fried chicken (piece)", "fried chicken;southern fried chicken;crispy fried chicken;fried chicken drumstick;fried chicken thigh;fried chicken wing;fried chicken breast;breaded chicken",
     "nonveg", "piece", "1 piece, coating eaten (85 g edible)", 85, ("fdc", 2705949), ""),
    ("us_fried_okra_cup", "Fried okra", "fried okra;breaded okra;southern fried okra;okra fried",
     "veg", "cup", "1 cup (~125 g: okra + cornmeal breading + oil)", 125,
     ("recipe", [("okra_cooked", 100), ("cornmeal", 15), ("oil", 10)]),
     "USDA has no breaded fried okra; recipe of USDA cooked okra, cornmeal breading and absorbed frying oil (oil uptake is an assumption)."),
    ("us_steak_serving", "Steak", "steak;beef steak;grilled steak;sirloin steak;ribeye steak;rib eye steak;new york strip;t-bone steak;filet mignon",
     "nonveg", "serving", "1 regular steak, cooked (160 g)", 160, ("fdc", 2705823), "No carbohydrate."),
    ("us_mashed_potatoes_serving", "Mashed potatoes", "mashed potatoes;mashed potato;potato mash;whipped potatoes",
     "veg", "serving", "1/2 cup (125 g)", 125, ("fdc", 2709496), "Made with milk. Gravy adds roughly 3 g carbohydrate per 1/4 cup."),
    ("us_corn_cob_piece", "Corn on the cob", "corn on the cob;corn cob;sweet corn;buttered corn;ear of corn",
     "veg", "piece", "1 regular ear (108 g edible)", 108, ("fdc", 2709909), "Restaurant style (fat added)."),
    ("us_coleslaw_serving", "Coleslaw", "coleslaw;cole slaw;slaw;cabbage slaw",
     "veg", "serving", "1/2 cup (110 g)", 110, ("fdc", 2709815), ""),
    ("us_caesar_salad_serving", "Caesar salad (no dressing)", "caesar salad;chicken caesar salad;romaine salad",
     "veg", "serving", "1 side salad without dressing (113 g)", 113, ("fdc", 2709591), "Dressing not included: creamy dressing adds fat and about 1 g carbohydrate per tablespoon."),
    ("us_grilled_chicken_piece", "Grilled chicken breast", "grilled chicken;grilled chicken breast;chicken breast;baked chicken breast;roast chicken breast",
     "nonveg", "piece", "1 medium breast, skin not eaten (120 g)", 120, ("fdc", 2705968), "No carbohydrate."),
    ("us_hot_dog_piece", "Hot dog (in a bun)", "hot dog;hotdog;frankfurter;hot dog sandwich;wiener;frank in a bun",
     "nonveg", "piece", "1 hot dog in a white bun (102 g)", 102, ("fdc", 2707056), ""),
    ("us_cola_can", "Cola (regular)", "cola;coke;coca cola;pepsi;soda;soft drink;regular soda",
     "beverage", "serving", "1 can, 12 fl oz (372 g)", 372, ("fdc", 2710541), "Sugar-sweetened. A medium fountain drink is 512 g (USDA)."),
    ("us_diet_cola_can", "Diet cola", "diet coke;diet cola;coke zero;pepsi zero;diet soda;zero sugar soda;diet pepsi",
     "beverage", "serving", "1 can, 12 fl oz (360 g)", 360, ("fdc", 2710542), ""),
    ("us_orange_juice_glass", "Orange juice", "orange juice;fresh orange juice;glass of orange juice",
     "beverage", "glass", "1 cup, 8 fl oz (248 g)", 248, ("fdc", 2709186), "100% juice."),
    ("us_apple_pie_slice", "Apple pie (slice)", "apple pie;apple pie slice;slice of apple pie",
     "sweet", "piece", "1 regular slice (150 g)", 150, ("fdc", 2707995), ""),
    ("us_ice_cream_serving", "Ice cream", "ice cream;vanilla ice cream;scoop of ice cream;chocolate ice cream;ice cream scoop",
     "sweet", "serving", "1/2 cup (68 g)", 67.5, ("fdc", 2705629), "USDA 1 cup = 135 g; a scoop in USDA is 120 g."),
    ("us_cookie_piece", "Chocolate chip cookie", "chocolate chip cookie;cookie;cookies;choc chip cookie",
     "sweet", "piece", "1 medium cookie (30 g)", 30, ("fdc", 2707909), ""),
    ("us_doughnut_piece", "Doughnut", "doughnut;donut;glazed donut;glazed doughnut;ring donut",
     "sweet", "piece", "1 doughnut (75 g)", 75, ("fdc", 2708062), ""),
    ("us_waffle_piece", "Waffle", "waffle;waffles;belgian waffle;buttermilk waffle",
     "breakfast", "piece", "1 medium waffle (75 g)", 75, ("fdc", 2708325), "Syrup and butter are separate items."),
    ("us_dill_pickle_piece", "Dill pickle (spear)", "dill pickle;pickle spear;dill pickle spear;gherkin;kosher dill",
     "accompaniment", "piece", "1 spear (40 g)", 40, ("fdc", 2710078), ""),
    ("us_tomato_slices_serving", "Sliced tomato", "tomato slices;sliced tomato;tomato slice;sliced tomatoes;tomatoes",
     "veg", "serving", "3 slices (60 g)", 60, ("fdc", 2709719), ""),
    ("us_carrots_raw_serving", "Raw carrots", "raw carrots;carrot sticks;shredded carrots;baby carrots;carrots",
     "veg", "serving", "1/2 cup (60 g)", 60, ("fdc", 2709660), ""),
    ("us_butter_pat", "Butter (pat)", "butter;butter pat;pat of butter;whipped butter;butter balls;salted butter",
     "accompaniment", "serving", "1 pat (7 g)", 7, ("fdc", 2710155), "Almost pure fat; no carbohydrate."),
    ("us_lettuce_serving", "Lettuce", "lettuce;lettuce leaf;lettuce leaves;iceberg lettuce;romaine lettuce;shredded lettuce",
     "veg", "serving", "1 cup shredded (35 g)", 35, ("fdc", 2709789), ""),
    ("us_mixed_berries_serving", "Mixed berries", "mixed berries;berries;blueberries;raspberries;blackberries;berry bowl",
     "fruit", "serving", "1/2 cup (75 g: blueberries, raspberries, blackberries)", 75,
     ("recipe", [("blueberries", 25), ("raspberries", 25), ("blackberries", 25)]), "Equal parts of three USDA raw berries."),
    ("us_sauteed_vegetables_serving", "Sauteed vegetables (bok choy, sweet peppers)", "sauteed vegetables;sautéed vegetables;stir-fried vegetables;stir fried vegetables;stir fry vegetables;vegetable stir fry;stir-fried greens;sauteed greens;sautéed greens;bok choy;sweet peppers",
     "veg", "serving", "1/2 cup (~85 g, cooked with fat)", 85,
     ("recipe", [("bok_choy_cooked_fat", 55), ("red_pepper_cooked", 30)]), "USDA cooked bok choy and sweet red pepper, fat added."),
    ("us_mixed_vegetables_serving", "Mixed vegetables (corn, peas, carrots, beans)", "mixed vegetables;classic mixed vegetables;peas and carrots;vegetable medley",
     "veg", "serving", "1/2 cup (93 g)", 93, ("fdc", 2710012), "Restaurant style (fat added)."),
    ("us_sweet_tea_glass", "Sweet tea (iced)", "sweet tea;iced tea;sweetened iced tea;southern sweet tea",
     "beverage", "glass", "1 glass, 12 fl oz (~360 g) with ~22 g sugar", 360,
     ("recipe", [("iced_tea", 338), ("sugar", 22)]),
     "USDA has no brewed sweet tea; USDA brewed iced tea plus ~22 g sugar per 12 fl oz (an assumption; restaurant sweet tea varies). Choose unsweetened iced tea if no sugar was added."),
    ("us_unsweet_tea_glass", "Iced tea (unsweetened)", "unsweetened iced tea;unsweet tea;unsweet iced tea;iced tea no sugar",
     "beverage", "glass", "1 glass, 12 fl oz (360 g)", 360, ("fdc", 2710517), ""),
    ("us_bagel_piece", "Bagel", "bagel;plain bagel;wheat bagel;bagel with cream cheese",
     "staple", "piece", "1 regular bagel (105 g)", 105, ("fdc", 2707732), "Cream cheese adds fat (about 1 g carbohydrate per tablespoon)."),
]:
    _id, _en, _al, _cat, _unit, _lab, _g, _src, _notes = _a
    add(_id, _en, "", "", "", _al, "american", _cat, _unit, _lab, _g, _src, "unknown",
        " ".join(x for x in (_notes, FNDDS_W if _src[0] == "fdc" else "", GI_UNKNOWN_US) if x))


def r1(x):
    return round(float(x) + 1e-9, 1)


I18N = os.path.join(HERE, "names_i18n.csv")
I18N_LANGS = ("es", "fr", "de", "it", "ja")


def load_i18n() -> dict[str, dict[str, str]]:
    """Translated names and per-language aliases (es/fr/de/it/ja), keyed by food id.

    Kept in a separate source file so regenerating the table never loses them. Every id in the
    table must have a row and vice versa (no silent gaps)."""
    with open(I18N, encoding="utf-8", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    ids = [a[0] for a in R]
    missing, extra = set(ids) - set(rows), set(rows) - set(ids)
    if missing or extra:
        raise SystemExit(f"names_i18n.csv out of sync: missing {sorted(missing)}, unknown {sorted(extra)}")
    return rows


def main():
    i18n = load_i18n()
    rows = []
    computed: dict[str, tuple[dict, float]] = {}
    for (id_, en, bn, hi, kn, aliases, cuisine, cat, unit, label, grams, src, gi, notes) in R:
        if src[0] == "mean_of":  # per-gram mean of rows computed above
            per_g = [{k: computed[i][0][k] / computed[i][1] for k in ("kcal", "carbs", "fibre", "protein", "fat")} for i in src[1]]
            v = {k: sum(x[k] for x in per_g) / len(per_g) * grams for k in ("kcal", "carbs", "fibre", "protein", "fat")}
            source, method = "Derived: per-gram mean of " + ", ".join(src[1]) + f"; x {grams:g} g", "recipe_derived"
        else:
            v, source, method = compute(src, grams)
        computed[id_] = (v, float(grams))
        tr = i18n[id_]
        rows.append(dict(
            id=id_, name_en=en, name_bn=bn, name_hi=hi, name_kn=kn,
            **{f"name_{lg}": tr[f"name_{lg}"].strip() for lg in I18N_LANGS},
            aliases=aliases,
            aliases_i18n=";".join(a.strip() for lg in I18N_LANGS for a in tr[f"aliases_{lg}"].split(";") if a.strip()),
            cuisine=cuisine, category=cat, unit=unit, unit_label_en=label, grams_per_unit=grams,
            carbs_g=r1(v["carbs"]), fibre_g=r1(v["fibre"]), protein_g=r1(v["protein"]), fat_g=r1(v["fat"]),
            kcal=int(round(v["kcal"])), gi_band=gi, source=source, method=method, notes=notes.strip(),
        ))
    cols = ["id", "name_en", "name_bn", "name_hi", "name_kn", *[f"name_{lg}" for lg in I18N_LANGS], "aliases",
            "aliases_i18n", "cuisine", "category", "unit", "unit_label_en", "grams_per_unit", "carbs_g", "fibre_g",
            "protein_g", "fat_g", "kcal", "gi_band", "source", "method", "notes"]
    out = os.path.join(HERE, "indian_foods.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
