"""Deterministic slot rendering.

The live planner never writes numbers. It writes text with slots such as ``{estimate}`` or
``{risk_high}``; each slot is bound to ONE tool field of this turn and rendered here, in the
user's language, by code. A slot whose tool was not called is rejected, and so is any raw
digit in the draft that the user did not type. Templates use the same ``Slot`` objects, so
every reply carries ``claims``: ``[{slot, field, value, rendered}]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nemotwins.agent import templates as T
from nemotwins.agent.verifier import extract_numbers, normalise_digits

SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
DIGIT_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Slot:
    name: str
    field: str
    value: Any
    rendered: str

    def claim(self) -> dict:
        v = self.value
        if isinstance(v, float):
            v = round(v, 3)
        return {"slot": self.name, "field": self.field, "value": v, "rendered": self.rendered}


RISK_HIGH = {
    "en-US": "chance of going above 180 in the next 2 hours: {freq}",
    "es-ES": "probabilidad de superar 180 en las próximas 2 horas: {freq}",
    "fr-FR": "probabilité de dépasser 180 dans les 2 prochaines heures : {freq}",
    "de-DE": "Wahrscheinlichkeit, in den nächsten 2 Stunden über 180 zu steigen: {freq}",
    "it-IT": "probabilità di superare 180 nelle prossime 2 ore: {freq}",
    "ja-JP": "今後2時間で180を超える確率：{freq}",
}
RISK_LOW = {
    "en-US": "estimated chance of going below 70 in the next 2 hours (not validated): {freq}",
    "es-ES": "probabilidad estimada de bajar de 70 en las próximas 2 horas (no validada): {freq}",
    "fr-FR": "probabilité estimée de descendre sous 70 dans les 2 prochaines heures (non validée) : {freq}",
    "de-DE": "geschätzte Wahrscheinlichkeit, in den nächsten 2 Stunden unter 70 zu fallen (nicht validiert): {freq}",
    "it-IT": "probabilità stimata di scendere sotto 70 nelle prossime 2 ore (non validata): {freq}",
    "ja-JP": "今後2時間で70を下回る推定確率（未検証）：{freq}",
}
RANGE = {"en-US": "{lo} to {hi}", "es-ES": "{lo} a {hi}", "fr-FR": "{lo} à {hi}", "de-DE": "{lo} bis {hi}",
         "it-IT": "da {lo} a {hi}", "ja-JP": "{lo}〜{hi}"}
WALK_EFFECT = {
    "down": {"en-US": "lowers the expected peak by about {n}", "es-ES": "reduce el pico previsto en unos {n}",
             "fr-FR": "abaisse le pic prévu d'environ {n}", "de-DE": "senkt den erwarteten Spitzenwert um etwa {n}",
             "it-IT": "abbassa il picco previsto di circa {n}", "ja-JP": "予測ピークをおよそ{n}下げる"},
    "up": {"en-US": "raises the expected peak by about {n}", "es-ES": "eleva el pico previsto en unos {n}",
           "fr-FR": "augmente le pic prévu d'environ {n}", "de-DE": "erhöht den erwarteten Spitzenwert um etwa {n}",
           "it-IT": "alza il picco previsto di circa {n}", "ja-JP": "予測ピークをおよそ{n}上げる"},
    "small": {"en-US": "changes the expected peak too little to call",
              "es-ES": "cambia el pico previsto demasiado poco para afirmarlo",
              "fr-FR": "modifie trop peu le pic prévu pour conclure",
              "de-DE": "verändert den erwarteten Spitzenwert zu wenig für eine Aussage",
              "it-IT": "cambia il picco previsto troppo poco per affermarlo",
              "ja-JP": "予測ピークへの影響が小さすぎて判断できない"},
}

# Slot catalogue shown to the planner: name -> (tool, field, meaning).
CATALOGUE: dict[str, tuple[str, str, str]] = {
    "estimate": ("get_state", "estimate", "current glucose estimate (mg/dL)"),
    "band": ("get_state", "band", "likely range of current glucose, e.g. '131 to 182'"),
    "band_lo": ("get_state", "band.lo", "lower end of the likely range of current glucose"),
    "band_hi": ("get_state", "band.hi", "upper end of the likely range of current glucose"),
    "chance_high": ("get_state|forecast", "p_high_2h.p", "frequency only, e.g. 'about 7 times out of 10': use in "
                                                         "'the chance of going above 180 in the next 2 hours is {chance_high}'"),
    "risk_high": ("get_state|forecast", "p_high_2h.p", "COMPLETE clause incl. subject and verb; use alone, never after "
                                                       "'is' or 'risk'. Prefer {chance_high}"),
    "risk_low": ("get_state|forecast", "p_low_2h.p", "full phrase incl. 'not validated': chance below 70 (only if asked)"),
    "peak": ("forecast", "peak.value", "expected peak glucose of the forecast"),
    "peak_time": ("forecast", "peak.t", "clock time of that peak"),
    "carbs": ("forecast", "meal.carbs", "grams of carbohydrate in the meal"),
    "meal": ("forecast", "meal.name", "the meal's name"),
    "delta_peak": ("what_if", "delta_peak", "signed change of the peak in the simulated scenario, e.g. '-12'"),
    "peak_before": ("what_if", "baseline_peak", "expected peak without the change"),
    "peak_after": ("what_if", "scenario_peak", "expected peak with the change"),
    "walk_effect": ("what_if", "delta_peak", "phrase: what the simulated walk does to the peak"),
    "risk_high_before": ("what_if", "p_high_baseline", "percent chance above 180 without the change"),
    "risk_high_after": ("what_if", "p_high_scenario", "percent chance above 180 with the change"),
    "next_check": ("next_best_prick", "time", "suggested time for the next finger-prick (experimental)"),
    "nbp_gain": ("next_best_prick", "expected_gain_pct", "percent the twin's uncertainty may shrink"),
    "reading": ("log_reading", "value", "the reading the user reported"),
    "driver": ("explain", "physiology[0].label", "the biggest driver, in words"),
    "driver_effect": ("explain", "physiology[0].effect_on_peak", "signed effect of that driver on the peak"),
    "tir_current": ("outlook_90d", "tir_current_pct", "projected time in range, current habits (percent)"),
    "tir_scenario": ("outlook_90d", "tir_scenario_pct", "projected time in range with the change (percent)"),
    "target_range": ("constant", "target", "the target range '70 to 180'"),
}


def _lang(d: dict[str, str], lang: str) -> str:
    return d.get(lang, d["en-US"])


def risk_phrase(p: float, lang: str, low: bool = False) -> str:
    return _lang(RISK_LOW if low else RISK_HIGH, lang).format(freq=T.freq(p, lang))


def range_phrase(lo: float, hi: float, lang: str) -> str:
    return _lang(RANGE, lang).format(lo=round(lo), hi=round(hi))


def build(calls: list[dict], lang: str) -> dict[str, Slot]:
    """Slots available from this turn's tool calls (the most recent call wins)."""
    s: dict[str, Slot] = {
        "target_range": Slot("target_range", "constant.target", [70, 180], range_phrase(70, 180, lang)),
    }
    for c in calls:
        name, o = c.get("name"), c.get("output") or {}
        if not isinstance(o, dict) or "error" in o:
            continue
        if name == "get_state":
            s["estimate"] = Slot("estimate", "get_state.estimate", o["estimate"], str(round(o["estimate"])))
            b = o["band"]
            s["band"] = Slot("band", "get_state.band", [b["lo"], b["hi"]], range_phrase(b["lo"], b["hi"], lang))
            s["band_lo"] = Slot("band_lo", "get_state.band.lo", b["lo"], str(round(b["lo"])))
            s["band_hi"] = Slot("band_hi", "get_state.band.hi", b["hi"], str(round(b["hi"])))
        if name in ("get_state", "forecast", "log_meal") and isinstance(o.get("p_high_2h"), dict):
            p = float(o["p_high_2h"]["p"])
            s["risk_high"] = Slot("risk_high", f"{name}.p_high_2h.p", p, risk_phrase(p, lang))
            s["chance_high"] = Slot("chance_high", f"{name}.p_high_2h.p", p, T.freq(p, lang))
        if name in ("get_state", "forecast") and isinstance(o.get("p_low_2h"), dict):
            p = float(o["p_low_2h"]["p"])
            s["risk_low"] = Slot("risk_low", f"{name}.p_low_2h.p", p, risk_phrase(p, lang, low=True))
        if name in ("forecast", "log_meal") and isinstance(o.get("peak"), dict):
            s["peak"] = Slot("peak", f"{name}.peak.value", o["peak"]["value"], str(round(o["peak"]["value"])))
            s["peak_time"] = Slot("peak_time", f"{name}.peak.t", o["peak"]["t"], T.clock(o["peak"]["t"], lang))
            meal = o.get("meal") or {}
            if meal:
                s["carbs"] = Slot("carbs", f"{name}.meal.carbs", meal.get("carbs"), str(round(float(meal.get("carbs") or 0))))
                s["meal"] = Slot("meal", f"{name}.meal.name", meal.get("name"), str(meal.get("name") or ""))
        if name == "what_if":
            dp = float(o["delta_peak"])
            s["delta_peak"] = Slot("delta_peak", "what_if.delta_peak", dp, T.signed(dp))
            for k, f in (("peak_before", "baseline_peak"), ("peak_after", "scenario_peak")):
                if o.get(f) is not None:
                    s[k] = Slot(k, f"what_if.{f}", o[f], str(round(float(o[f]))))
            kind = "small" if o.get("too_small_to_call") or abs(round(dp)) < 1 else ("down" if dp < 0 else "up")
            s["walk_effect"] = Slot("walk_effect", "what_if.delta_peak", dp,
                                    WALK_EFFECT[kind].get(lang, WALK_EFFECT[kind]["en-US"]).format(n=abs(round(dp))))
            s["risk_high_before"] = Slot("risk_high_before", "what_if.p_high_baseline", o["p_high_baseline"],
                                         str(round(float(o["p_high_baseline"]) * 100)))
            s["risk_high_after"] = Slot("risk_high_after", "what_if.p_high_scenario", o["p_high_scenario"],
                                        str(round(float(o["p_high_scenario"]) * 100)))
        if name == "next_best_prick" and o.get("time"):
            s["next_check"] = Slot("next_check", "next_best_prick.time", o["time"], T.clock(o["time"], lang))
            s["nbp_gain"] = Slot("nbp_gain", "next_best_prick.expected_gain_pct", o["expected_gain_pct"],
                                 str(round(float(o["expected_gain_pct"]))))
        if name == "log_reading" and o.get("value") is not None:
            s["reading"] = Slot("reading", "log_reading.value", o["value"], str(round(float(o["value"]))))
        if name == "explain" and o.get("physiology"):
            top = o["physiology"][0]
            s["driver"] = Slot("driver", "explain.physiology[0].label", top["label"],
                               T.driver_label(top.get("name"), top["label"], lang))
            s["driver_effect"] = Slot("driver_effect", "explain.physiology[0].effect_on_peak", top["effect_on_peak"],
                                      T.signed(top["effect_on_peak"]))
        if name == "outlook_90d":
            s["tir_current"] = Slot("tir_current", "outlook_90d.tir_current_pct", o["tir_current_pct"],
                                    str(o["tir_current_pct"]))
            s["tir_scenario"] = Slot("tir_scenario", "outlook_90d.tir_scenario_pct", o["tir_scenario_pct"],
                                     str(o["tir_scenario_pct"]))
    return s


def raw_digits(draft: str, user_text: str) -> list[str]:
    """Digits the planner wrote itself (slots removed) that are not the user's own numbers."""
    body = SLOT_RE.sub(" ", normalise_digits(draft))
    mine = set(extract_numbers(user_text))
    out = []
    for m in DIGIT_RE.finditer(body):
        try:
            v = float(m.group(0).replace(",", "."))
        except ValueError:
            continue
        if v not in mine:
            out.append(m.group(0))
    return out


def render(draft: str, slots: dict[str, Slot]) -> tuple[str, list[dict], list[str]]:
    """Fill ``{slot}`` placeholders. Returns (text, claims, unknown slot names)."""
    claims: list[dict] = []
    unknown: list[str] = []

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        sl = slots.get(name)
        if sl is None:
            unknown.append(name)
            return m.group(0)
        claims.append(sl.claim())
        return sl.rendered

    return SLOT_RE.sub(sub, draft), claims, unknown


def catalogue_text(slots: dict[str, Slot] | None = None) -> str:
    names = list(CATALOGUE) if slots is None else [n for n in CATALOGUE if n in slots]
    return "\n".join(f"{{{n}}}: {CATALOGUE[n][2]} (from {CATALOGUE[n][0]})" for n in names)
