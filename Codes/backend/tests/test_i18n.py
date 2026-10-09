"""Release-language coverage (en-US, es-ES, fr-FR, de-DE, it-IT, ja-JP) of every user-facing
backend string table: templates, slot phrases, safety messages, receipt labels, lexicon."""

from __future__ import annotations

import pytest

from nemotwins.agent import lexicon, safety, slots, templates
from nemotwins.agent.verifier import extract_numbers, sanity, verify
from nemotwins.api import receipt

LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
PEAK_T = "2026-10-05T21:40"

# One tool output per template family, with the fields the orchestrator binds to each slot.
TOOLS = [
    {"estimate": 156.4, "band": {"lo": 131.2, "hi": 181.7}, "p_high_2h": {"p": 0.32}, "p_low_2h": {"p": 0.12}},
    {"meal": {"name": "x", "carbs": 41.4}, "peak": {"t": PEAK_T, "value": 186.4}, "p_high_2h": {"p": 0.32}},
    {"delta_peak": -12.3, "p_high_baseline": 0.62, "p_high_scenario": 0.41, "walk_min": 15},
    {"time": PEAK_T, "expected_gain_pct": 23.4},
    {"value": 150.0, "width_change_h120_pct": -31.6},
    {"physiology": [{"label": "Earlier food still digesting", "effect_on_peak": 18.2}]},
    {"tir_current_pct": 61, "tir_scenario_pct": 70},
    {"stale_after_min": 30},  # action_stale names the 30-minute replay-clock limit
]


def _values(lang: str) -> dict:
    t = templates.clock(PEAK_T, lang)
    return {"est": 156, "lo": 131, "hi": 182, "meal": "dal", "carbs": 41, "peak": 186, "peak_time": t,
            "label": templates.whatif_label("walk", lang, n=15), "dpeak": templates.signed(-12.3), "p0": 62, "p1": 41,
            "time": t, "gain": 23, "value": 150, "pct": 32, "driver": templates.driver_label("earlier_meals", "", lang),
            "contrib": templates.signed(18.2), "tir0": 61, "tir1": 70,
            "phigh_freq": templates.freq(0.32, lang), "plow_freq": templates.freq(0.12, lang)}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", sorted(templates.T))
def test_every_template_renders_and_passes_the_verifier(key: str, lang: str) -> None:
    assert set(templates.T[key]) == set(LANGS), (key, set(templates.T[key]) ^ set(LANGS))
    text = templates.render(key, lang, **_values(lang))
    assert "{" not in text and "}" not in text
    g = verify(text, TOOLS)
    assert g["passed"], (text, g)
    assert sanity(text, lang) == [], (text, sanity(text, lang))
    # same numbers as the English template (the clock hour may be 12- or 24-hour)
    en = templates.render(key, "en-US", **_values("en-US"))
    strip = {9.0, 21.0, 40.0}
    assert sorted(n for n in extract_numbers(text) if n not in strip) == \
           sorted(n for n in extract_numbers(en) if n not in strip), (text, en)


@pytest.mark.parametrize("lang", LANGS)
def test_label_tables_are_complete(lang: str) -> None:
    for table in (templates.WHATIF_LABEL, templates.DRIVER_LABELS, slots.WALK_EFFECT, receipt.LABELS,
                  safety.MESSAGES, safety.READING_TITLES, safety.READING_ACTIONS):
        for key, by_lang in table.items():
            assert by_lang.get(lang), (key, lang)
    for table in (templates.FREQ, slots.RISK_HIGH, slots.RISK_LOW, slots.RANGE, lexicon.AND_WORD, lexicon.LANG_NAME,
                  lexicon.TERMINAL):
        assert table.get(lang), lang
    # driver labels may appear in an LLM draft: they must never trip the medication policy
    for by_lang in templates.DRIVER_LABELS.values():
        assert not safety.output_unsafe(by_lang[lang])


@pytest.mark.parametrize("lang", LANGS)
def test_slot_phrases_pass_the_verifier(lang: str) -> None:
    calls = [{"name": "get_state", "output": TOOLS[0] | {"now": PEAK_T}},
             {"name": "what_if", "output": TOOLS[2] | {"too_small_to_call": False}}]
    s = slots.build(calls, lang)
    assert "emergency_number" not in s  # no country-specific number
    for name in ("band", "risk_high", "risk_low", "walk_effect", "target_range"):
        g = verify(s[name].rendered, [c["output"] for c in calls])
        assert g["passed"], (name, s[name].rendered, g)
    assert any(w in s["risk_low"].rendered for w in ("not validated", "no validada", "non validée",
                                                     "nicht validiert", "non validata", "未検証"))


def test_every_table_has_exactly_the_release_languages() -> None:
    tables = [templates.T, templates.WHATIF_LABEL, templates.DRIVER_LABELS, receipt.LABELS, safety.MESSAGES,
              safety.READING_TITLES, safety.READING_ACTIONS, slots.WALK_EFFECT]
    for table in tables:
        for by_lang in table.values():
            assert set(by_lang) <= set(LANGS)
    for d in (templates.FREQ, slots.RISK_HIGH, slots.RANGE, lexicon.LANG_NAME, lexicon.AND_WORD):
        assert set(d) == set(LANGS)


def test_messages_do_not_hard_code_the_product_name() -> None:
    blobs = [str(t) for t in (templates.T, templates.WHATIF_LABEL, templates.DRIVER_LABELS, receipt.LABELS,
                              safety.MESSAGES, safety.READING_TITLES, safety.READING_ACTIONS, slots.RISK_HIGH,
                              slots.RISK_LOW, slots.WALK_EFFECT)]
    assert not any("nemotwins" in b.lower() for b in blobs)


def test_lexicon_has_every_language_for_the_core_intents() -> None:
    for intent in ("next_prick", "log_reading", "what_if", "explain", "outlook", "education", "forecast", "state"):
        assert set(lexicon.KW_BY_LANG[intent]) == set(LANGS), intent
    for by_lang in (lexicon.OUT_OF_SCOPE_BY_LANG, lexicon.RECIPE_BY_LANG, lexicon.IN_SCOPE_WORDS_BY_LANG,
                    lexicon.HALF_RE_BY_LANG, lexicon.WALK_RE_BY_LANG, lexicon.LATER_RE_BY_LANG,
                    lexicon.EARLIER_RE_BY_LANG, lexicon.LOW_RE_BY_LANG, lexicon.HYPOTHETICAL_BY_LANG):
        assert set(by_lang) == set(LANGS)
    # Japanese has no word boundaries: a \b in a ja pattern would never match between kana/kanji
    for table in [lexicon.KW_BY_LANG[i] for i in lexicon.KW_BY_LANG] + [
            lexicon.OUT_OF_SCOPE_BY_LANG, lexicon.RECIPE_BY_LANG, lexicon.HALF_RE_BY_LANG, lexicon.WALK_RE_BY_LANG,
            lexicon.SWAP_BEFORE_BY_LANG, lexicon.LOW_RE_BY_LANG, lexicon.HYPOTHETICAL_BY_LANG]:
        assert "\\b" not in table.get("ja-JP", ""), table.get("ja-JP")
