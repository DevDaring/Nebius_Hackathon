"""Multilingual dish extraction from chat text (food.find_in_text / orchestrator.parse_foods),
in the six release languages, plus the translated-name provenance rule."""

from __future__ import annotations

import pytest

from nemotwins import food
from nemotwins.agent.orchestrator import parse_foods

RICE, ROTI, DAL = "white_rice_katori", "roti_piece", "dal_toor_katori"

# (text, expected [(food_id, units), ...] in order of mention)
CASES: list[tuple[str, list[tuple[str, float]]]] = [
    # --- English / romanised
    ("if i eat 2 roti and dal now", [(ROTI, 2), (DAL, 1)]),
    ("What happens if I have rice and dal for dinner?", [(RICE, 1), (DAL, 1)]),
    ("3 idlis and sambar", [("idli_piece", 3), ("sambar_katori", 1)]),
    ("chicken biryani and a glass of lassi", [("chicken_biryani_plate", 1), ("lassi_sweet_glass", 1)]),
    ("two chapatis with palak paneer", [(ROTI, 2), ("palak_paneer_katori", 1)]),
    ("ragi mudde with saaru", [("ragi_mudde_piece", 1), ("rasam_katori", 1)]),
    ("half plate rice", [(RICE, 0.5)]),
    ("2 tsp sugar in my chai", [("sugar_tsp", 2), ("masala_chai_sugar_cup", 1)]),
    ("bhat, macher jhol and begun bhaja", [(RICE, 1), ("macher_jhol_katori", 1), ("begun_bhaja_piece", 1)]),
    ("I am eating rice now", [(RICE, 1)]),                       # "am" is not mango
    ("my sugar is 140, can I eat a banana?", [("banana_piece", 1)]),  # blood "sugar" is not table sugar
    ("2 samosas and masala chai", [("samosa_piece", 2), ("masala_chai_sugar_cup", 1)]),
    ("chapatti and aloo sabzi", [(ROTI, 1), ("aloo_sabzi_katori", 1)]),      # spelling variant
    # --- Spanish
    ("arroz con lentejas", [(RICE, 1), (DAL, 1)]),
    ("Si ceno 2 rotis y un cuenco de lentejas", [(ROTI, 2), (DAL, 1)]),
    ("dos platos de arroz", [(RICE, 2)]),
    ("un huevo duro y pan", [("boiled_egg_piece", 1), ("bread_white_slice", 1)]),
    ("2 cucharaditas de azúcar en el té", [("sugar_tsp", 2), ("masala_chai_sugar_cup", 1)]),
    # --- French
    ("du riz et des lentilles", [(RICE, 1), (DAL, 1)]),
    ("du pain et un œuf", [("bread_white_slice", 1), ("boiled_egg_piece", 1)]),
    ("deux idlis et du sambar", [("idli_piece", 2), ("sambar_katori", 1)]),
    # --- German
    ("Reis mit Linsen", [(RICE, 1), (DAL, 1)]),
    ("2 Scheiben Brot und ein Ei", [("bread_white_slice", 2), ("boiled_egg_piece", 1)]),
    # --- Italian
    ("riso e lenticchie", [(RICE, 1), (DAL, 1)]),
    ("un bicchiere di latte e una banana", [("milk_glass", 1), ("banana_piece", 1)]),
    ("pane e un uovo sodo", [("bread_white_slice", 1), ("boiled_egg_piece", 1)]),
    # --- Japanese (no spaces: longest-match segmentation; the amount comes after the dish)
    ("ご飯とダール", [(RICE, 1), (DAL, 1)]),
    ("ご飯を2杯とレンズ豆", [(RICE, 2), (DAL, 1)]),
    ("パン２枚と卵", [("bread_white_slice", 2), ("boiled_egg_piece", 1)]),
    ("晩ご飯にロティ2枚", [(ROTI, 2)]),                  # 晩ご飯 ("dinner") is not rice
]

# No food at all: common words must not match anything.
NO_FOOD = [
    "and now what?",
    "khana kab khaun",
    "what if i walk 15 minutes after dinner",
    "how am i doing right now",
    "my sugar is 210, is that bad?",
    "when should I check next?",
    "I am fine, thank you",
    "I have chest pain",                       # French "pain" (bread) needs an article
    "a latte, please",                         # Italian "latte" (milk) needs an Italian article
    "mi azúcar está alta hoy",                 # blood sugar, not table sugar
    "mein Zucker ist heute hoch",
    "¿cómo estoy ahora?",
    "フライパンで焼いた",                         # frying pan, not bread
    "血糖値はどうですか？",
]


@pytest.mark.parametrize("text,expected", CASES)
def test_dishes_found(text: str, expected: list[tuple[str, float]]) -> None:
    got = [(f["food_id"], f["units"]) for f in parse_foods(text)]
    assert got == [(fid, float(u)) for fid, u in expected], got


@pytest.mark.parametrize("text", NO_FOOD)
def test_no_false_positives(text: str) -> None:
    assert parse_foods(text) == []


def test_table_size() -> None:
    assert len(CASES) >= 30


def test_spanish_rice_with_lentils_finds_rice_and_dal() -> None:
    assert [f["food_id"] for f in parse_foods("arroz con lentejas")] == [RICE, DAL]


def test_every_dish_is_findable_by_its_english_name() -> None:
    misses = []
    for _, r in food.table().iterrows():
        got = [f["food_id"] for f in food.find_in_text(r["name_en"])]
        if r["id"] not in got:
            misses.append((r["id"], r["name_en"], got))
    assert not misses, misses[:10]


@pytest.mark.parametrize("col", ["name_es", "name_fr", "name_de", "name_it", "name_ja"])
def test_translated_names_find_their_own_dish(col: str) -> None:
    """Every translated full name resolves to ITS row (never silently to another food)."""
    misses = []
    for _, r in food.table().iterrows():
        assert isinstance(r[col], str) and r[col].strip(), (r["id"], col)
        if food.match(r[col])[0] != (r["id"], 1.0):
            misses.append((r["id"], r[col], food.match(r[col])[:1]))
    assert not misses, misses[:10]


def test_every_translated_alias_resolves_to_exactly_one_food() -> None:
    """Provenance rule: a translated alias names one food id, and that id is the row it was written
    for (no collision with another row's alias or name in any language)."""
    owner: dict[str, set[str]] = {}
    for _, r in food.table().iterrows():
        for a in str(r["aliases_i18n"]).split(";"):
            if a.strip():
                owner.setdefault(food._norm(a), set()).add(r["id"])
    assert owner and not {k: v for k, v in owner.items() if len(v) > 1}
    keys = food._keys()
    wrong = {k: (sorted(v), keys.get(k)) for k, v in owner.items() if keys.get(k) not in v}
    assert not wrong, list(wrong.items())[:10]


@pytest.mark.parametrize("word,fid", [
    ("arroz", RICE), ("riz", RICE), ("Reis", RICE), ("riso", RICE), ("ご飯", RICE),
    ("lentejas", DAL), ("lentilles", DAL), ("Linsen", DAL), ("lenticchie", DAL), ("レンズ豆", DAL),
    ("pan", "bread_white_slice"), ("du pain", "bread_white_slice"), ("Brot", "bread_white_slice"),
    ("pane", "bread_white_slice"), ("パン", "bread_white_slice"),
    ("huevo", "boiled_egg_piece"), ("œuf", "boiled_egg_piece"), ("Ei", "boiled_egg_piece"),
    ("uovo", "boiled_egg_piece"), ("卵", "boiled_egg_piece"),
])
def test_everyday_words_find_the_canonical_food(word: str, fid: str) -> None:
    assert [f["food_id"] for f in food.find_in_text(word)] == [fid]


def test_food_names_by_language() -> None:
    r = food.get(DAL)
    assert food.food_json(r, "es-ES")["name"] == r["name_es"] and food.food_json(r, "ja-JP")["name"] == r["name_ja"]
    assert food.food_json(r, "pt-BR")["name"] == r["name_en"]  # unsupported language -> English
    assert set(food.LANG_COL) == {"en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"}


def test_swap_labels_in_every_language() -> None:
    for lang in food.LANG_COL:
        labels = food.swaps_localised(lang)
        assert labels and all(s["label"] and s["label_en"] for s in labels)
    assert food.swaps_localised("de-DE")[0]["label"] != food.swaps_localised("en-US")[0]["label"]


def test_match_handles_parenthetical_translated_names() -> None:
    assert food.match("arroz")[0] == (RICE, 1.0)
    assert food.match(food.get(RICE)["name_ja"])[0] == (RICE, 1.0)
    assert food.match("ご飯")[0] == (RICE, 1.0)


def test_search_returns_contract_fields() -> None:
    out = food.search("roti", "es-ES")
    assert out and out[0]["id"] == ROTI
    for k in ("id", "name", "name_en", "unit", "unit_label", "grams_per_unit", "carbs_g", "fibre_g", "protein_g",
              "fat_g", "kcal", "cuisine"):
        assert k in out[0]


@pytest.mark.parametrize("text", ["what is my likely range?", "What is time in range and why does it matter?",
                                  "se mangi il riso stasera", "è al mio posto"])
def test_common_words_are_not_foods(text: str) -> None:
    """Found by scanning the UI vocabulary of all locales: 'range' fuzzy-matched orange, Italian 'mangi'
    (you eat) matched mango, 'posto' (place) matched aloo posto."""
    ids = {f["food_id"] for f in food.find_in_text(text)}
    assert not ids & {"orange_piece", "mango_katori", "aloo_posto_katori"}


def test_real_dishes_still_match() -> None:
    assert [f["food_id"] for f in food.find_in_text("2 oranges and 1 aloo posto")] == ["orange_piece", "aloo_posto_katori"]
    assert [f["food_id"] for f in food.find_in_text("un mango")] == ["mango_katori"]


def test_stated_grams_become_table_units_and_count_as_explicit() -> None:
    from nemotwins import food as F

    assert [(f["food_id"], f["units"], f["explicit"]) for f in F.find_in_text("What if I take 100 g sweets tonight?")] == [("mithai_50g", 2.0, True)]
    assert [(f["food_id"], f["units"], f["explicit"]) for f in F.find_in_text("300 grams of rice")] == [("white_rice_katori", 2.0, True)]
    assert F.find_in_text("I will take 50gm sweets at dinner")[0]["units"] == 1.0


def test_singular_sweet_is_an_adjective_unless_an_amount_precedes_it() -> None:
    from nemotwins import food as F

    assert F.find_in_text("a sweet potato") == []
    assert F.find_in_text("my sweet daughter asked about glucose") == []
    assert [f["food_id"] for f in F.find_in_text("what if I take 50gm sweet tonight")] == ["mithai_50g"]
    assert [f["food_id"] for f in F.find_in_text("sweet corn")] == ["us_corn_cob_piece"]
