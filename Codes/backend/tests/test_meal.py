"""perception/meal.py: unit conversion via grams, plausible clamps, dish ranking (no network)."""

from __future__ import annotations

import json

import pytest

from nemotwins import food
from nemotwins.config import FIXTURES_DIR
from nemotwins.perception import meal as M


def test_different_unit_converts_through_model_grams() -> None:
    r = food.get("aloo_sabzi_katori")  # table unit: 1 katori (150 g)
    units, note = M.table_units(r, 5, "piece", 75)
    assert units == 0.5 and "converted" in note


def test_different_unit_without_grams_uses_typical_unit_weight() -> None:
    r = food.get("veg_biryani_plate")
    units, _ = M.table_units(r, 1, "katori", None)
    assert 0.25 <= units < 1


def test_same_unit_keeps_portion_and_clamps_absurd_values() -> None:
    r = food.get("roti_piece")
    assert M.table_units(r, 3, "pieces", 999)[0] == 3
    units, note = M.table_units(r, 40, "piece", None)
    assert units == 8 and "clamped" in note
    assert M.table_units(food.get("white_rice_katori"), 0.01, "katori", None)[0] == 0.25


def test_map_to_table_uses_grams_for_aloo_bhaja_pieces() -> None:
    out = M.map_to_table([{"name": "aloo bhaja", "portion": 5, "unit": "piece", "grams": 60, "confidence": 0.9}])
    d = out["dishes"][0]
    assert d["food_id"] == "aloo_sabzi_katori" and d["units"] == 0.4 and d["portion_note"]
    assert out["total"]["carbs"] == round(0.4 * float(food.get("aloo_sabzi_katori")["carbs_g"]), 1)


def test_map_to_table_tolerates_junk_fields() -> None:
    out = M.map_to_table([{"name": "roti", "portion": "two", "unit": None}, "not a dish"])  # type: ignore[list-item]
    assert out["dishes"][0]["food_id"] == "roti_piece" and out["dishes"][0]["units"] == 1


@pytest.mark.parametrize("q,prefix", [("paneer curry", "paneer"), ("aloo bhaja", "aloo"), ("begun bhaja", "begun")])
def test_search_ranks_the_named_ingredient_first(q: str, prefix: str) -> None:
    out = food.search(q)
    assert prefix in out[0]["id"]
    if q == "paneer curry":
        assert out[0]["category"] == "curry"
        assert all("paneer" in f["id"] for f in out[:4])


@pytest.mark.parametrize("sample", ["bengali_fish_thali", "karnataka_oota", "north_indian_thali", "south_breakfast",
                                    "us_burger_plate", "us_pepperoni_pizza", "us_pancake_breakfast", "us_southern_plate",
                                    "us_steak_dinner"])
def test_recorded_samples_map_to_plausible_meals(sample: str) -> None:
    rec = json.loads((FIXTURES_DIR / "meal_parse" / f"{sample}.json").read_text())
    out = M.map_to_table(rec["dishes"])
    assert 10 < out["total"]["carbs"] < 250
    for d in out["dishes"]:
        if d["food_id"]:
            assert 0.25 <= d["units"] <= 8


def test_vision_prompt_asks_for_grams() -> None:
    assert '"grams"' in M.VISION_PROMPT


def test_vision_prompt_is_not_limited_to_indian_dishes() -> None:
    assert "any cuisine" in M.VISION_PROMPT and "Indian dish name" not in M.VISION_PROMPT


EXPECTED_US = {
    "us_burger_plate": {"us_cheeseburger_piece", "us_french_fries_serving", "us_dill_pickle_piece"},
    "us_pepperoni_pizza": {"us_pizza_pepperoni_slice"},
    "us_pancake_breakfast": {"us_pancake_piece", "us_scrambled_eggs_serving", "us_bacon_slice", "us_butter_pat"},
    "us_southern_plate": {"us_fried_chicken_piece", "us_fried_okra_cup", "us_mac_cheese_cup"},
    "us_steak_dinner": {"us_steak_serving", "us_mashed_potatoes_serving"},
}


@pytest.mark.parametrize("sample", sorted(EXPECTED_US))
def test_american_samples_map_to_usda_foods_without_manual_picks(sample: str) -> None:
    rec = json.loads((FIXTURES_DIR / "meal_parse" / f"{sample}.json").read_text())
    out = M.map_to_table(rec["dishes"])
    ids = {d["food_id"] for d in out["dishes"]}
    assert EXPECTED_US[sample] <= ids and not any(d["needs_pick"] for d in out["dishes"])
    for fid in EXPECTED_US[sample]:
        assert "FDC" in str(food.get(fid)["source"])  # USDA FoodData Central row or a recipe of FDC rows


def _plate(*names: str) -> list[dict]:
    return [{"name": n, "portion": 1, "unit": "piece", "confidence": 0.9} for n in names]


def test_ambiguous_names_follow_the_rest_of_the_plate() -> None:
    us = M.map_to_table(_plate("cheeseburger", "french fries", "pickle"))
    assert [d["food_id"] for d in us["dishes"]][-1] == "us_dill_pickle_piece"
    india = M.map_to_table(_plate("steamed rice", "sambar", "pickle"))
    assert [d["food_id"] for d in india["dishes"]][-1] == "pickle_tbsp"
    alone = M.map_to_table(_plate("pickle"))  # no plate context: the best name match stays
    assert alone["dishes"][0]["food_id"] == "pickle_tbsp"


def test_butter_is_butter_not_a_ghee_roti() -> None:
    out = M.map_to_table(_plate("pancakes", "butter"))
    assert out["dishes"][1]["food_id"] == "us_butter_pat" and out["dishes"][1]["carbs"] == 0
