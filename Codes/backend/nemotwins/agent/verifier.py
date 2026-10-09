"""Numeric grounding verifier (spec section 7.3) - deterministic code, not an LLM.

Every number in a draft reply must match a value produced by a Twin API tool in this
turn (within rounding), or appear in the user's own message, or be one of a tiny set
of fixed reference numbers (target range 70-180, "out of 10"). Full-width (Japanese) digits and
punctuation are normalised first, and a decimal comma (es / fr / de / it: "7,2") reads as a decimal.
No emergency phone number is a fixed number: emergency text is location-neutral.

Semantic binding: a risk percentage in a sentence about low glucose must match a low-risk
field, and one about high glucose a high-risk field (``semantic_errors``). The live
planner writes mostly slots that ``agent/slots.py`` fills deterministically from tool fields; every
digit it writes itself must be grounded here, so this verifier is the authoritative numeric check.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

# Full-width digits and number punctuation (Japanese input methods) -> ASCII.
DIGIT_MAP = str.maketrans("０１２３４５６７８９．，：％＋－", "0123456789.,:%+-")
FIXED = {70.0, 180.0, 10.0, 1.0, 2.0, 4.0, 90.0, 24.0, 12.0}  # 1 and 10: "less than 1 time in 10"
# A number is not part of a Latin word ("HbA1c", "h2o"). CJK characters around a number are fine:
# "65という", "15分後" ("\w" would include kana / kanji and hide every Japanese number).
_LATIN = r"A-Za-z\u00C0-\u024F"
NUM_RE = re.compile(rf"(?<![{_LATIN}\d_.])[-+]?\d+(?:[.,]\d+)?(?![{_LATIN}\d_])")


def normalise_digits(text: str) -> str:
    return text.translate(DIGIT_MAP)


def extract_numbers(text: str) -> list[float]:
    """Numbers in ``text``. "1,200" (comma + exactly 3 digits) is a thousands separator; any other
    comma between digits is a decimal comma ("7,2" -> 7.2)."""
    t = normalise_digits(text)
    t = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", t)  # thousands separators
    out = []
    for m in NUM_RE.finditer(t):
        try:
            out.append(float(m.group(0).replace(",", ".")))
        except ValueError:
            pass
    return out


def _walk(obj: Any, acc: set[float], path: str = "", paths: list[tuple[float, str]] | None = None) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, int | float):
        v = float(obj)
        acc.add(v)
        if paths is not None:
            paths.append((v, path))
        if 0 <= v <= 1:  # probabilities / fractions are spoken as percent or "N in 10"
            acc.add(round(v * 100, 1))
            acc.add(float(round(v * 10)))
        return
    if isinstance(obj, str):
        _times(obj, acc)
        for n in extract_numbers(obj) if len(obj) < 800 else []:
            acc.add(n)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, acc, f"{path}.{k}" if path else str(k), paths)
    elif isinstance(obj, list | tuple):
        # long series (trajectories) are not quotable values except their summary points
        if len(obj) > 60:
            return
        for v in obj:
            _walk(v, acc, path, paths)


def _times(s: str, acc: set[float]) -> None:
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return
    acc.update({float(dt.hour), float(dt.minute), float((dt.hour % 12) or 12)})


# A quantity the user typed with its unit attached ("50gm", "15min") is still the user's own number.
_USER_QTY = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s?(?:g|gm|gms|gram|grams|kg|ml|min|mins|minutes|h|hr|hrs)\b", re.I)


def allowed_values(tool_outputs: list[Any], user_text: str = "") -> set[float]:
    acc: set[float] = set(FIXED)
    for o in tool_outputs:
        _walk(o, acc)
    acc.update(extract_numbers(user_text))
    acc.update(float(m.group(1).replace(",", ".")) for m in _USER_QTY.finditer(normalise_digits(user_text)))
    return acc


def _close(x: float, allowed: set[float]) -> bool:
    for a in allowed:
        tol = max(1.0, abs(a) * 0.02)  # rounding: 156.4 -> "156" or "about 160" is not OK, 156 is
        if abs(x - a) <= tol:
            return True
        if abs(a) >= 20 and abs(x - round(a, -1)) < 1e-9 and abs(x - a) <= 5:  # "about 160" for 157.8
            return True
    return False


# ----------------------------------------------------------------------------- semantic binding
# A risk number must come from a tool field about the SAME event: a percentage (or "N times out of
# 10") in a sentence that names only low glucose must match a low-risk field (p_low...), one in a
# sentence that names only high glucose must match a high-risk field (p_high...). "Your low glucose
# risk is 80%" with p_high = 0.8 and p_low = 0.01 therefore fails.
_LOW_CUE = re.compile(
    r"(\b(?:low|lows|hypo\w*|below 70|under 70|less than 70)\b|"
    r"\b(?:baj\w* de 70|por debajo de 70|menos de 70|glucosa baja|hipoglucemi\w*)|"
    r"\b(?:sous 70|en dessous de 70|moins de 70|glyc[eé]mie basse|hypoglyc[eé]mi\w*)|"
    r"\b(?:unter 70|niedrig\w*|unterzucker\w*|hypoglyk[aä]mi\w*)|"
    r"\b(?:sotto (?:i )?70|meno di 70|glicemia bassa|ipoglicemi\w*)|"
    r"70を下回|70未満|低血糖)", re.I)
_HIGH_CUE = re.compile(
    r"(\b(?:high|highs|hyper\w*|above 180|over 180|more than 180|spike\w*)\b|"
    r"\b(?:super\w* (?:los )?180|por encima de 180|m[aá]s de 180|glucosa alta|hiperglucemi\w*)|"
    r"\b(?:d[eé]pass\w* 180|au-dessus de 180|plus de 180|glyc[eé]mie (?:haute|[eé]lev[eé]e)|hyperglyc[eé]mi\w*)|"
    r"\b(?:[uü]ber 180|hyperglyk[aä]mi\w*)|"
    r"\b(?:super\w* (?:i )?180|sopra (?:i )?180|oltre (?:i )?180|glicemia alta|iperglicemi\w*)|"
    r"180を超え|180超|高血糖)", re.I)
_PCT_AFTER = re.compile(r"^\s*(?:%|percent\b|per cent\b|por ciento\b|pour ?cent\b|prozent\b|per ?cento\b|パーセント)",
                        re.I)
_TEN_AFTER = re.compile(r"^\s*(?:(?:times? )?(?:out of|in) 10\b|ve(?:z|ces) de cada 10\b|(?:fois )?sur 10\b|"
                        r"von 10\b|volt[ae] su 10\b)", re.I)
_TEN_BEFORE = re.compile(r"10\s*回中\s*(?:およそ|約)?\s*$")  # ja: "10回中およそ3回"
_SENT_END = re.compile(r"[!?。！？]|\.(?!\d)")


def _sentence(t: str, start: int, end: int) -> str:
    lo = max((m.end() for m in _SENT_END.finditer(t, 0, start)), default=0)
    m = _SENT_END.search(t, end)
    return t[lo: m.start() if m else len(t)]


def _direction(sentence: str) -> str | None:
    lo, hi = bool(_LOW_CUE.search(sentence)), bool(_HIGH_CUE.search(sentence))
    return "low" if lo and not hi else "high" if hi and not lo else None


def _tokens(path: str) -> set[str]:
    return set(re.split(r"[._]", path.lower()))


def semantic_errors(text: str, tool_outputs: list[Any]) -> list[str]:
    """Risk numbers bound to the wrong event (low vs high). Returns the offending numbers."""
    paths: list[tuple[float, str]] = []
    for o in tool_outputs:
        _walk(o, set(), "", paths)
    t = normalise_digits(text)
    bad = []
    for m in NUM_RE.finditer(t):
        after = t[m.end(): m.end() + 16]
        before = t[max(0, m.start() - 12): m.start()]
        pct = bool(_PCT_AFTER.match(after))
        ten = bool(_TEN_AFTER.match(after)) or bool(_TEN_BEFORE.search(before))
        if not (pct or ten):
            continue
        d = _direction(_sentence(t, m.start(), m.end()))
        if d is None:
            continue
        x = float(m.group(0).replace(",", "."))
        cands = [v for v, p in paths if d in _tokens(p) and 0 <= v <= 1]
        scaled = {round(v * 100, 1) for v in cands} if pct else {float(round(v * 10)) for v in cands}
        if not _close(x, scaled):
            bad.append(_fmt(x))
    return bad


def verify(text: str, tool_outputs: list[Any], user_text: str = "") -> dict:
    nums = extract_numbers(text)
    allowed = allowed_values(tool_outputs, user_text)
    bad = [n for n in nums if not _close(abs(n), allowed | {abs(a) for a in allowed})]
    user_nums = set(extract_numbers(user_text))
    sem = [b for b in semantic_errors(text, tool_outputs) if float(b) not in user_nums]
    return {"passed": not bad and not sem, "numbers": [_fmt(n) for n in nums],
            "ungrounded": [_fmt(n) for n in bad], "misbound": sem}


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


# ----------------------------------------------------------------------------- draft sanity
_LATIN_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))
# Japanese: hiragana, katakana (incl. the long-vowel mark), CJK ideographs, half-width katakana.
_JA_RANGES = ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF66, 0xFF9F))
SCRIPT_RANGES = {"en-US": _LATIN_RANGES, "es-ES": _LATIN_RANGES, "fr-FR": _LATIN_RANGES, "de-DE": _LATIN_RANGES,
                 "it-IT": _LATIN_RANGES, "ja-JP": _JA_RANGES}
MIN_LETTERS = 12
MIN_LETTERS_JA = 6  # one kanji/kana carries more than one Latin letter
MIN_SCRIPT_SHARE = 0.6
_END_OK = re.compile(r"[.!?。！？][\"'”’)\]」』]*\s*$")
_FRAGMENT_LINE = re.compile(r"^[\s\-*•#>]*(?:\S+\s+){0,2}?[-+]?\d[\d.,]*\s*[:：]\s*$|^[\s\-*•]*[-+]?\d[\d.,]*\s*$")


def sanity(text: str, lang: str) -> list[str]:
    """Shape checks on an LLM draft (numbers are checked by ``verify``).

    Problems: ``too_short`` (< 12 letters; < 6 for Japanese), ``wrong_script`` (< 60% of letters
    in the target script: Latin for en/es/fr/de/it, kana/kanji for Japanese), ``fragment_line`` (a
    line that is only "180:" or "Peak 175:"), ``unfinished`` (no terminal . ! ? or 。, i.e. cut off
    mid-sentence)."""
    problems: list[str] = []
    letters = [c for c in text if unicodedata.category(c)[0] in ("L", "M")]
    if len(letters) < (MIN_LETTERS_JA if lang == "ja-JP" else MIN_LETTERS):
        problems.append("too_short")
    rng = SCRIPT_RANGES.get(lang)
    if rng and letters:
        share = sum(1 for c in letters if any(lo <= ord(c) <= hi for lo, hi in rng)) / len(letters)
        if share < MIN_SCRIPT_SHARE:
            problems.append("wrong_script")
    if any(_FRAGMENT_LINE.match(line) for line in text.splitlines() if line.strip()):
        problems.append("fragment_line")
    if text.strip() and not _END_OK.search(text.strip()):
        problems.append("unfinished")
    return problems
