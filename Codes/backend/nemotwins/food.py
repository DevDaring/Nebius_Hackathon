"""Indian food composition table lookups (nutrition never comes from an LLM).

Two kinds of lookup:

* ``match(name)``: fuzzy match of ONE dish name (meal-photo labels, food search box).
* ``find_in_text(text)``: deterministic extraction of every dish named in a chat message, in
  English, Spanish, French, German, Italian or Japanese. It uses exact phrase keys (longest phrase
  first) built from the table's names (name_en, name_es, ...) and aliases (``aliases`` = English /
  romanised Indian names, ``aliases_i18n`` = translated aliases from data/food/names_i18n.csv), a
  simple plural rule and a high-cutoff fuzzy fallback for Latin-script typos only. Japanese has no
  spaces: runs of kana / kanji are segmented by longest match against the known Japanese keys.
  Words that are also common non-food words ("sugar" as in blood sugar, French "pain", ...) only
  count when a quantity (or, for a few words, an article) precedes them.

Provenance rule: a translated name or alias names exactly ONE food id (tests/test_food.py checks
that every alias resolves to the row it was written for).
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from functools import lru_cache

import pandas as pd

from nemotwins.config import FOOD_DIR

LANG_COL = {"en-US": "name_en", "es-ES": "name_es", "fr-FR": "name_fr", "de-DE": "name_de", "it-IT": "name_it",
            "ja-JP": "name_ja"}
NAME_COLS = ("name_en", "name_es", "name_fr", "name_de", "name_it", "name_ja")
ALIAS_COLS = ("aliases", "aliases_i18n")

# Extra everyday words that map to a dish but are not in the table's alias columns (kept empty: the
# translated aliases live in data/food/names_i18n.csv so that regeneration preserves them).
EXTRA_KEYS: dict[str, tuple[str, ...]] = {}

# Keys that are also everyday non-food words (or "sugar" meaning blood sugar): they
# only count as food when a quantity or unit word comes right before them.
NEEDS_QTY = {
    "am", "dose", "dim", "nan", "cha", "mor", "sugar", "anna", "kola", "lau", "pori", "sev", "ata", "aata",
    "sakkare", "chini", "cheeni", "matha", "ghol", "pepe", "chura", "chida",
    "posto",  # Italian "place"; the Bengali dish counts only with a quantity
    "azúcar", "azucar", "sucre", "zucker", "zucchero", "砂糖",
}
# Keys that collide with a common word of ANOTHER release language: they count after a quantity or
# after one of the listed words of their own language (French "du pain" = bread, English "chest pain"
# is not; Italian "un bicchiere di latte" = milk, English "a latte" is a coffee).
NEEDS_DETERMINER: dict[str, set[str]] = {
    "pain": {"du", "le", "un", "une", "deux", "trois", "de", "d", "mon", "ce", "au", "des", "avec", "et", "sans",
             "petit"},
    "latte": {"il", "del", "di", "un", "col", "con", "e", "bicchiere", "tazza", "mio", "senza"},
}
# Never matched on their own (fuzzy or exact), whatever the table says: function words and meal words.
STOP = {
    "and", "now", "khana", "khaana", "khabo", "khele", "tindre", "eat", "ate", "eating", "meal", "food", "dinner",
    "lunch", "breakfast", "snack", "today", "tonight", "with", "without", "then", "what", "will", "happen",
    "after", "before", "plate", "piece", "bowl", "glass", "cup", "katori", "half", "full", "more", "less",
    "range", "ranges",  # fuzzy-matched "orange" ("what is my likely range?")
    "mangi",  # Italian "you eat" (plural of mango is "manghi"); matched mango
    # es
    "y", "con", "sin", "de", "del", "la", "el", "los", "las", "ahora", "si", "qué", "que", "comer", "como", "ceno",
    "cenar", "cena", "almuerzo", "desayuno", "comida", "hoy", "esta", "noche", "después", "antes", "mi",
    # fr
    "et", "avec", "sans", "du", "des", "le", "les", "maintenant", "je", "mange", "manger", "repas", "dîner",
    "déjeuner", "ce", "soir", "mon", "ma",
    # de
    "und", "mit", "ohne", "der", "die", "das", "jetzt", "wenn", "ich", "esse", "essen", "abendessen", "mittagessen",
    "frühstück", "heute", "mein", "meine",
    # it
    "e", "senza", "di", "della", "il", "lo", "ora", "adesso", "se", "mangio", "mangiare", "pranzo", "colazione",
    "pasto", "stasera",
    # "something else" in es / fr / de / it (never a typo of a dish name: "chose" is not "chole")
    "algo", "otra", "otro", "cosa", "chose", "autre", "quelque", "etwas", "anderes", "andere", "qualcosa",
    "qualcos", "altro", "altra",
    # ja (particles and meal words)
    "と", "を", "の", "は", "が", "に", "で", "も", "や", "今", "食事", "夕食", "昼食", "朝食", "晩ご飯", "晩ごはん",
    "朝ご飯", "朝ごはん", "昼ご飯", "昼ごはん", "夕ご飯", "夕ごはん",
}
# Japanese words that CONTAIN a food key but are not that food ("フライパン" is a frying pan,
# "パンダ" a panda). They are segmentation vocabulary only and never match.
JA_NON_FOOD = {"フライパン", "パンダ", "パンツ", "チャイナ", "チャイム", "ナンバー", "ナンセンス", "ライター", "マルチ",
               "ルーチン", "カマンベール"}

QTY_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "half": 0.5, "a": 1, "an": 1, "single": 1,
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "medio": 0.5, "media": 0.5,
    "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "demi": 0.5, "demie": 0.5,
    "ein": 1, "eine": 1, "einen": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "halbe": 0.5,
    "halben": 0.5, "halb": 0.5,
    "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "mezzo": 0.5, "mezza": 0.5,
    "一つ": 1, "ひとつ": 1, "二つ": 2, "ふたつ": 2, "三つ": 3, "みっつ": 3, "半分": 0.5,
}
HALF_WORDS = {"half", "medio", "media", "demi", "demie", "halbe", "halben", "halb", "mezzo", "mezza", "半分"}
UNIT_WORDS = {
    "katori", "katoris", "bowl", "bowls", "plate", "plates", "piece", "pieces", "cup", "cups", "glass", "glasses",
    "tsp", "tbsp", "spoon", "spoons", "serving", "servings", "slice", "slices", "handful",
    "plato", "platos", "taza", "tazas", "vaso", "vasos", "cuenco", "cuencos", "cucharada", "cucharadas",
    "cucharadita", "cucharaditas", "ración", "raciones", "racion", "trozo", "trozos", "rebanada", "rebanadas",
    "pieza", "piezas", "puñado",
    "assiette", "assiettes", "tasse", "tasses", "verre", "verres", "bol", "bols", "cuillère", "cuillères",
    "cuillerée", "cuillerées", "portion", "portions", "tranche", "tranches", "morceau", "morceaux", "poignée",
    "teller", "tassen", "glas", "gläser", "schüssel", "schüsseln", "schale", "löffel", "esslöffel", "teelöffel",
    "portionen", "stück", "scheibe", "scheiben", "handvoll",
    "piatto", "piatti", "tazza", "tazze", "bicchiere", "bicchieri", "ciotola", "ciotole", "cucchiaio", "cucchiai",
    "cucchiaino", "porzione", "porzioni", "fetta", "fette", "pezzo", "pezzi", "manciata",
    "杯", "皿", "枚", "個", "本", "切れ", "膳", "人前", "つ", "碗", "椀", "カップ", "コップ", "カトリ", "小鉢",
}
# A preposition between a unit and the dish: "plato de arroz", "piatto di riso", "2杯のご飯".
UNIT_PREPS = {"of", "de", "d", "di", "del", "della", "du", "des", "von", "の"}
JA_PARTICLES_AFTER = {"を", "は", "が", "も"}

# Inflection rules: (suffix, replacement). Tried on the LAST token of a phrase only when the plain
# phrase is not a key; the result must be an exact key. Plurals in -s / -es (en, es, fr).
_INFLECT = (("es", ""), ("s", ""))

# Kana / kanji (and the iteration mark 々): Japanese text has no spaces between words.
_CJK = "\u3005\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
_CJK_RE = re.compile(f"[{_CJK}]")


@lru_cache
def table() -> pd.DataFrame:
    df = pd.read_csv(FOOD_DIR / "indian_foods.csv")
    for c in ALIAS_COLS:
        df[c] = df[c].fillna("") if c in df.columns else ""
    return df


@lru_cache
def _by_id() -> dict[str, pd.Series]:
    return {r["id"]: r for _, r in table().iterrows()}


@lru_cache
def swaps() -> list[dict]:
    return json.loads((FOOD_DIR / "swaps.json").read_text(encoding="utf-8"))


SWAP_LABEL_COL = {"en-US": "label_en", "es-ES": "label_es", "fr-FR": "label_fr", "de-DE": "label_de",
                  "it-IT": "label_it", "ja-JP": "label_ja"}


def swaps_localised(lang: str = "en-US") -> list[dict]:
    """Contract shape: [{from, to, from_qty, to_qty, label (in ``lang``, English fallback), label_en}]."""
    col = SWAP_LABEL_COL.get(lang, "label_en")
    return [{"from": s["from"], "to": s["to"], "from_qty": s.get("from_qty", 1), "to_qty": s.get("to_qty", 1),
             "label": s.get(col) or s["label_en"], "label_en": s["label_en"]} for s in swaps()]


def _norm(s: str) -> str:
    """NFKC (full-width -> ASCII), lowercase, apostrophes and punctuation -> spaces; keeps Latin letters
    with accents (é, ü, ß, œ), digits, decimal points and kana / kanji."""
    t = unicodedata.normalize("NFKC", str(s)).lower()
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = re.sub(f"[^a-z0-9.\u00c0-\u024f{_CJK} ]+", " ", t)
    # "ご飯2杯" -> "ご飯 2 杯": digits never glue to kana / kanji
    t = re.sub(f"(?<=\\d)(?=[{_CJK}])|(?<=[{_CJK}])(?=\\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _name_variants(name: str) -> tuple[list[str], list[str]]:
    """(full names, reduced names): 'Roti / chapati (no ghee)' -> full [...], reduced ['roti', 'chapati']."""
    if not isinstance(name, str) or not name.strip():
        return [], []
    name = unicodedata.normalize("NFKC", name)  # Japanese full-width brackets -> ( )
    full = [name]
    base = re.sub(r"\([^)]*\)", " ", name)
    parts = [p for p in re.split(r"[/,]", base) if p.strip()]
    reduced = [base, *parts] if base.strip() != name.strip() or len(parts) > 1 else []
    return full, reduced


@lru_cache
def _keys() -> dict[str, str]:
    """Exact phrase key -> food id. Priority: full names > aliases > colloquial > reduced names."""
    ranked: dict[str, tuple[int, int, str]] = {}

    def put(key: str, fid: str, prio: int, order: int) -> None:
        k = _norm(key)
        if not k or k in STOP:
            return
        cur = ranked.get(k)
        if cur is None or (prio, order) < cur[:2]:
            ranked[k] = (prio, order, fid)

    t = table()
    for order, (_, r) in enumerate(t.iterrows()):
        fid = r["id"]
        for col in NAME_COLS:
            full, reduced = _name_variants(r[col])
            for k in full:
                put(k, fid, 0, order)
            for k in reduced:
                put(k, fid, 3, order)
        for col in ALIAS_COLS:
            for a in str(r[col]).split(";"):
                if a.strip():
                    put(a, fid, 1, order)
    ids = set(t["id"])
    for fid, words in EXTRA_KEYS.items():
        if fid in ids:
            for w in words:
                put(w, fid, 2, 0)
    return {k: v[2] for k, v in ranked.items()}


@lru_cache
def _latin_singles() -> list[str]:
    return [k for k in _keys() if " " not in k and re.fullmatch(r"[a-z]{5,}", k) and k not in NEEDS_QTY]


@lru_cache
def _index() -> list[tuple[str, str]]:
    return list(_keys().items())


def food_json(row: pd.Series, lang: str = "en-US") -> dict:
    name = row.get(LANG_COL.get(lang, "name_en"), row["name_en"])
    return {
        "id": row["id"], "name": name if isinstance(name, str) and name else row["name_en"], "name_en": row["name_en"],
        "unit": row["unit"], "unit_label": row["unit_label_en"], "grams_per_unit": float(row["grams_per_unit"]),
        "carbs_g": float(row["carbs_g"]), "fibre_g": float(row["fibre_g"]), "protein_g": float(row["protein_g"]),
        "fat_g": float(row["fat_g"]), "kcal": float(row["kcal"]), "cuisine": row["cuisine"],
        "category": row["category"], "source": row["source"],
    }


def spoken_name(name: str) -> str:
    """Short, TTS-friendly dish name: no brackets, no slashes, no trailing portion note.

    'Roti / chapati (no ghee)' -> 'Roti'; 'Toor / arhar dal (dal tadka)' -> 'Toor dal';
    'Pakora / pakoda (onion), 4 pieces' -> 'Pakora'; 'Dal toor / arhar' -> 'Dal toor'."""
    if not isinstance(name, str):
        return ""
    base = re.sub(r"\s*\([^)]*\)", "", name).split(",")[0].strip()
    parts = [p.strip() for p in base.split("/") if p.strip()]
    if not parts:
        return name.strip()
    first, last = parts[0], parts[-1]
    fw, lw = first.split(), last.split()
    if len(parts) > 1 and len(fw) == 1 and len(lw) > 1:
        return " ".join([fw[0], *lw[1:]])  # shared head noun: "Toor / arhar dal" -> "Toor dal"
    return first


def get(food_id: str) -> pd.Series | None:
    return _by_id().get(food_id)


def match(name: str, n: int = 5, cutoff: float = 0.6) -> list[tuple[str, float]]:
    """Fuzzy match ONE free-text dish name to table ids (best first, with a score)."""
    q = _norm(name)
    if not q:
        return []
    keys = _keys()
    if q in keys:
        exact = keys[q]
        rest = [(f, s) for f, s in _fuzzy(q, n + 1) if f != exact]
        return [(exact, 1.0), *[(f, s) for f, s in rest if s >= cutoff]][:n]
    return [(fid, s) for fid, s in _fuzzy(q, n) if s >= cutoff]


# Words that describe a preparation rather than the dish itself: 'paneer curry' is about paneer.
GENERIC_WORDS = {"curry", "sabzi", "sabji", "subzi", "masala", "gravy", "dish", "fry", "fried", "bhaja", "bhaji",
                 "jhol", "with", "and", "of", "the", "a", "plain", "homemade", "style", "indian", "tarkari",
                 "torkari", "palya", "poriyal", "sukhi", "dry", "item", "side"}


def _fuzzy(q: str, n: int) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    qs = q.split()
    core = [w for w in qs if w not in GENERIC_WORDS and len(w) >= 3]
    for key, fid in _index():
        ks = key.split()
        if q == key:
            s = 1.0
        elif q in ks or key in qs:
            s = 0.85
        elif len(q) > 3 and (q in key or key in q):
            s = 0.8
        else:
            s = difflib.SequenceMatcher(None, q, key).ratio()
        if core and len(qs) > 1 and s < 0.95 and all(w in ks for w in core):
            # every distinctive word of the query is a word of this dish name: 'paneer curry' ->
            # 'matar paneer' ranks above 'chingri malaikari'; a matching preparation word adds a little
            s = max(s, 0.86 + 0.02 * sum(1 for w in qs if w in GENERIC_WORDS and w in ks))
        if s > scores.get(fid, 0):
            scores[fid] = s
    prep = set(qs) & GENERIC_WORDS
    if prep:
        for fid, sc in list(scores.items()):
            if 0.8 <= sc < 1.0:
                scores[fid] = sc + 0.01 * _prep_fit(fid, prep)
    return sorted(scores.items(), key=lambda kv: -kv[1])[:n]


CURRY_WORDS = {"curry", "sabzi", "sabji", "subzi", "masala", "gravy", "jhol", "tarkari", "torkari", "palya", "poriyal"}
FRY_WORDS = {"fry", "fried", "bhaja", "bhaji"}


def _prep_fit(fid: str, prep: set[str]) -> int:
    """Tie-break by preparation: 'paneer curry' prefers curries, 'aloo bhaja' prefers fried sides."""
    r = get(fid)
    if r is None:
        return 0
    text = f"{r['name_en']} {r['aliases']}".lower()
    fit = 0
    if prep & CURRY_WORDS and r["category"] in ("curry", "veg", "dal", "nonveg"):
        fit += 1
    if prep & FRY_WORDS and re.search(r"\b(fry|fried|bhaja|bhaji|fritter)\b", text):
        fit += 2
    return fit


def search(q: str, lang: str = "en-US", n: int = 12) -> list[dict]:
    t = table()
    if not q.strip():
        return [food_json(r, lang) for _, r in t.head(n).iterrows()]
    out: list[dict] = []
    for fid, _ in match(q, n=n, cutoff=0.45):
        r = get(fid)
        if r is not None:
            out.append(food_json(r, lang))
    return out


# ----------------------------------------------------------------------------- free text
@lru_cache
def _ja_vocab() -> tuple[frozenset[str], int]:
    """Japanese segmentation vocabulary: every all-kana/kanji key plus particles, units, quantities,
    stop words and known non-food words that contain a food key."""
    words = {k for k in _keys() if " " not in k and _CJK_RE.search(k)}
    words |= {w for w in (STOP | set(QTY_WORDS) | UNIT_WORDS | JA_NON_FOOD) if _CJK_RE.search(w)}
    return frozenset(words), max(map(len, words), default=1)


def _segment(run: str) -> list[str]:
    """Longest-match segmentation of a kana / kanji run; unknown characters are grouped."""
    vocab, longest = _ja_vocab()
    out: list[str] = []
    junk = ""
    i = 0
    while i < len(run):
        for n in range(min(longest, len(run) - i), 0, -1):
            if run[i:i + n] in vocab:
                if junk:
                    out.append(junk)
                    junk = ""
                out.append(run[i:i + n])
                i += n
                break
        else:
            junk += run[i]
            i += 1
    if junk:
        out.append(junk)
    return out


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for tok in _norm(text.replace("-", " ")).split():
        out.extend(_segment(tok) if _CJK_RE.search(tok) else [tok])
    return out


def _inflected(tok: str) -> list[str]:
    """Candidate base forms (plural -s / -es); the stem must keep >= 3 code points."""
    out: list[str] = []
    if tok in QTY_WORDS or tok in UNIT_WORDS:
        return out
    for suf, rep in _INFLECT:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            out.append(tok[: len(tok) - len(suf)] + rep)
    return out


def _lookup(words: list[str]) -> tuple[str, str] | None:
    """(food id, the key that matched) for an exact phrase, allowing one inflected last word."""
    keys = _keys()
    phrase = " ".join(words)
    if phrase in keys:
        return keys[phrase], phrase
    joined = "".join(words)
    # Japanese phrases come back from the segmenter split: "ご飯" + "大盛り" -> "ご飯大盛り"
    if len(words) > 1 and joined in keys and all(_CJK_RE.search(w) for w in words):
        return keys[joined], joined
    for v in _inflected(words[-1]):
        p = " ".join([*words[:-1], v])
        if p in keys and p not in STOP:
            return keys[p], p
    return None


def _qty_before(toks: list[str], i: int) -> tuple[float, bool, bool]:
    """(quantity, explicit?, from a 'half' word?) for a dish starting at token i
    ("2 roti", "a katori of rice", "dos platos de arroz", "2杯のご飯")."""
    j = i - 1
    unit = False
    if j >= 1 and toks[j] in UNIT_PREPS and toks[j - 1] in UNIT_WORDS:
        j -= 1
    if j >= 0 and toks[j] in UNIT_WORDS:
        j -= 1
        unit = True
    if j >= 0:
        w = toks[j]
        if re.fullmatch(r"\d+(\.\d+)?", w):
            return float(w), True, False
        if w in QTY_WORDS:
            return float(QTY_WORDS[w]), True, w in HALF_WORDS
    return 1.0, unit, False


def _determined(toks: list[str], i: int, words: set[str]) -> bool:
    """A guarded key counts after one of its own language's words, a unit word or a digit."""
    prev = toks[i - 1] if i > 0 else ""
    return prev in words or prev in UNIT_WORDS or prev in UNIT_PREPS or bool(re.fullmatch(r"\d+(\.\d+)?", prev))


def _qty_after_ja(toks: list[str], k: int) -> tuple[float, bool] | None:
    """Japanese puts the amount after the dish: "ご飯を2杯", "パン2枚", "ご飯を半分"."""
    if k < len(toks) and toks[k] in JA_PARTICLES_AFTER:
        k += 1
    if k < len(toks) and re.fullmatch(r"\d+(\.\d+)?", toks[k]) and k + 1 < len(toks) and toks[k + 1] in UNIT_WORDS:
        return float(toks[k]), False
    if k < len(toks) and toks[k] in QTY_WORDS and _CJK_RE.search(toks[k]):
        return float(QTY_WORDS[toks[k]]), toks[k] in HALF_WORDS
    return None


_GRAMS = {"g", "gm", "gms", "gram", "grams"}


def _amount_before(toks: list[str], i: int) -> bool:
    """A weight right before token i: "50gm sweet", "50 g sweet"."""
    prev = toks[i - 1] if i > 0 else ""
    if re.fullmatch(r"\d+(?:[.,]\d+)?(?:g|gm|gms|grams?)?", prev):
        return True
    return prev in _GRAMS and i > 1 and bool(re.fullmatch(r"\d+(?:[.,]\d+)?", toks[i - 2]))


def _grams_before(toks: list[str], i: int) -> float | None:
    """Grams stated right before token i ("150 g rice", "50gm sweets", "100 grams of dal"), else None."""
    j = i - 1
    if j >= 0 and toks[j] in ("of", "de", "di", "von"):
        j -= 1
    if j < 0:
        return None
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(?:g|gm|gms|grams?)", toks[j])
    if m:
        return float(m.group(1).replace(",", "."))
    if toks[j] in _GRAMS and j > 0 and re.fullmatch(r"\d+(?:[.,]\d+)?", toks[j - 1]):
        return float(toks[j - 1].replace(",", "."))
    return None


def find_in_text(text: str, max_n: int = 6, dish_names: bool = False) -> list[dict]:
    """Every dish named in ``text`` -> [{food_id, units, matched, half_word, explicit}] in order of mention.

    ``dish_names``: the text is a list of dishes (the lookup tool), so a lone "sweet" is a food, not an adjective."""
    toks = tokens(text)
    found: list[dict] = []
    seen: set[str] = set()
    i = 0
    while i < len(toks):
        hit = None
        for n in range(min(max_n, len(toks) - i), 0, -1):
            words = toks[i:i + n]
            if n == 1 and (words[0] in STOP or words[0] in QTY_WORDS or words[0] in UNIT_WORDS
                           or re.fullmatch(r"[\d.]+", words[0])):
                continue
            res = _lookup(words)
            if res is None and n == 1:
                res = _fuzzy_token(words[0])
            if res is not None:
                hit = (res[0], res[1], n)
                break
        if hit is None:
            i += 1
            continue
        fid, key, n = hit
        if key == "sweets" and toks[i] != "sweets" and not dish_names and not _amount_before(toks, i):
            # singular "sweet" is an adjective ("sweet potato", "my sweet daughter") unless an amount precedes it
            i += 1
            continue
        qty, explicit, half = _qty_before(toks, i)
        grams = _grams_before(toks, i)
        row = get(fid)
        if grams and row is not None and float(row["grams_per_unit"]) > 0:
            # a stated weight becomes table units ("150 g rice" = 1 katori of 150 g); it is an explicit amount
            qty, explicit, half = round(min(8.0, max(0.25, grams / float(row["grams_per_unit"]))), 2), True, False
        if not explicit and _CJK_RE.search(key):
            after = _qty_after_ja(toks, i + n)
            if after is not None:
                qty, half = after
                explicit = True
        phrase = " ".join(toks[i:i + n])
        if key in JA_NON_FOOD or (key in NEEDS_QTY and not explicit) or (
                key in NEEDS_DETERMINER and not _determined(toks, i, NEEDS_DETERMINER[key])):
            i += 1
            continue
        if fid not in seen:
            seen.add(fid)
            found.append({"food_id": fid, "units": qty, "matched": phrase, "half_word": half, "explicit": explicit})
        i += n
    return found


def _fuzzy_token(tok: str) -> tuple[str, str] | None:
    if not re.fullmatch(r"[a-z]{5,}", tok) or tok in STOP:
        return None
    m = difflib.get_close_matches(tok, _latin_singles(), n=1, cutoff=0.88)
    return (_keys()[m[0]], m[0]) if m else None


def macros(items: list[dict]) -> dict:
    """Sum macros for [{food_id, units}]."""
    tot = {"carbs": 0.0, "fibre": 0.0, "protein": 0.0, "fat": 0.0, "kcal": 0.0}
    for it in items:
        r = get(it["food_id"])
        if r is None:
            continue
        u = float(it.get("units", 1))
        tot["carbs"] += u * r["carbs_g"]
        tot["fibre"] += u * r["fibre_g"]
        tot["protein"] += u * r["protein_g"]
        tot["fat"] += u * r["fat_g"]
        tot["kcal"] += u * r["kcal"]
    return {k: round(v, 1) for k, v in tot.items()}
