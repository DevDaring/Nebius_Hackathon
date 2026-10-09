"""Typed tool contracts for the NemoTwins agent (brief section 8).

The language model sees contract tool names (``get_twin_state``, ``get_forecast`` ...). Each name maps
to an internal twin-engine call; every output is wrapped with a schema version, an execution id and
provenance (engine version, subject scope, time origin, unit, source, status). The backend enforces
argument bounds and the allowlist: the model can propose arguments, never patient identity, horizons
beyond the limit, more scenarios than allowed, or a persistent write.

Also here: the deterministic clarification policy (one question with the highest value) and the
evidence receipt built from the generated reports (never hard-coded numbers).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from nemotwins import food
from nemotwins.agent import nemo_text as NT
from nemotwins.config import REPORTS_DIR

SCHEMA_VERSION = "1.0"
MAX_SCENARIOS = 3
MAX_HORIZON_MIN = 240

# contract name -> internal tool name used by the engine wrapper, slots and verifier
CONTRACT_TO_INTERNAL = {
    "get_twin_state": "get_state",
    "get_forecast": "forecast",
    "lookup_food": "lookup_food",
    "preview_meal": "log_meal",
    "simulate_scenarios": "what_if",
    "preview_reading_update": "log_reading",
    "explain_forecast": "explain",
    "next_best_reading": "next_best_prick",
    "outlook_projection": "outlook_90d",
    "get_evidence_receipt": "evidence_receipt",
    "build_visit_summary": "visit_summary",
}
INTERNAL_TO_CONTRACT = {v: k for k, v in CONTRACT_TO_INTERNAL.items()}
SOURCES = {
    "get_state": "twin engine (particle filter + conformal calibration)",
    "forecast": "twin engine (mechanistic model + learned residual + conformal band)",
    "what_if": "twin engine (paired mechanistic counterfactual)",
    "log_reading": "twin engine (proposed reading, not saved)",
    "log_meal": "food table + twin engine (proposed meal, not saved)",
    "lookup_food": "food table (INDB / IFCT / USDA FoodData Central)",
    "explain": "twin engine drivers (physiology) + SHAP (learned residual)",
    "next_best_prick": "twin engine (experimental next-best-reading planner)",
    "outlook_90d": "twin engine projection (GMI formula; not an HbA1c prediction)",
    "evidence_receipt": "generated evaluation reports (reports/*.json)",
    "visit_summary": "authorized structured records + twin engine",
}
STATUS = {
    "get_state": "estimated", "forecast": "forecast", "what_if": "exploratory_simulation",
    "log_reading": "proposed", "log_meal": "proposed", "lookup_food": "reference_data", "explain": "estimated",
    "next_best_prick": "experimental", "outlook_90d": "projection_not_validated",
    "evidence_receipt": "retrospective_evaluation", "visit_summary": "reviewable_summary",
}
# Different names for different interval semantics (never one field name for both).
INTERVAL_SEMANTICS = {
    "get_state": {"band": "present-state 90% band of the current estimate (conformal, 30-minute quantile)"},
    "forecast": {"p_high_2h": "calibrated probability of exceeding 180 mg/dL within 2 hours (held-out reliability)",
                 "peak": "median forecast peak within the forecast window"},
    "what_if": {"delta_peak": "paired change of the median peak; its interval is simulation variability, "
                              "not a clinical confidence interval"},
}

TOOL_SPECS: list[dict] = [
    {"type": "function", "function": {"name": "get_twin_state", "description": "Current twin estimate with its present-state band, data freshness (hours since the last measured reading on the replay clock) and the 2-hour chance of going above 180.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "lookup_food", "description": "Match dish names (any of the six languages) to the food table. Returns food ids, household units and whether the user gave an explicit quantity. Call before get_forecast / simulate_scenarios when food is mentioned.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Dishes with quantities, e.g. '2 roti and dal'"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "get_forecast", "description": "Engine forecast for the next hours if the user eats the given foods now (or nothing). Returns peak, peak time, chance of going above 180 and drivers.", "parameters": {"type": "object", "properties": {"items": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"food_id": {"type": "string"}, "units": {"type": "number", "minimum": 0, "maximum": 20}}, "required": ["food_id", "units"]}}}}}},
    {"type": "function", "function": {"name": "simulate_scenarios", "description": "Exploratory simulation: compare the planned meal against ONE change (carb_scale e.g. 0.5 for half, walk_min after the meal, shift_min to eat later/earlier, or swap_items). Paired on the same particles; reports whether the difference is too small to call.", "parameters": {"type": "object", "properties": {"items": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"food_id": {"type": "string"}, "units": {"type": "number"}}}}, "swap_items": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"food_id": {"type": "string"}, "units": {"type": "number"}}}}, "carb_scale": {"type": "number", "minimum": 0, "maximum": 3}, "walk_min": {"type": "number", "minimum": 0, "maximum": 120}, "shift_min": {"type": "number", "minimum": -240, "maximum": 240}, "label": {"type": "string"}}, "required": ["items"]}}},
    {"type": "function", "function": {"name": "next_best_reading", "description": "Experimental: best time in the next 24 h for a finger-prick reading, with expected uncertainty reduction.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "preview_reading_update", "description": "Propose adding a finger-prick reading the user reports (value in mg/dL). Nothing is saved: the user confirms in the app.", "parameters": {"type": "object", "properties": {"value": {"type": "number", "minimum": 20, "maximum": 600}}, "required": ["value"]}}},
    {"type": "function", "function": {"name": "preview_meal", "description": "Propose logging these foods as eaten now (nutrition from the food table). Nothing is saved: the user confirms in the app.", "parameters": {"type": "object", "properties": {"items": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"food_id": {"type": "string"}, "units": {"type": "number"}}}}}, "required": ["items"]}}},
    {"type": "function", "function": {"name": "explain_forecast", "description": "Ranked drivers of the latest forecast (physiology and learned, reported separately).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "outlook_projection", "description": "90-day projection of time in range and GMI-based estimate (a projection, NOT an HbA1c prediction).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_evidence_receipt", "description": "What the twin's evidence covers: dataset, protocol, participants, evaluated horizon, headline metrics and limitations from the generated reports. Use for questions about accuracy, validation, populations or long-term outcomes.", "parameters": {"type": "object", "properties": {}}}},
]
ALLOWED_CONTRACTS = {s["function"]["name"] for s in TOOL_SPECS}


def execution_id() -> str:
    return uuid.uuid4().hex[:16]


def meta(internal: str, ctx: dict) -> dict:
    """Contract metadata for one tool execution. Kept OUTSIDE the tool output so that ids and
    version strings never count as numbers the reply may quote (numeric grounding)."""
    m = {"schema_version": SCHEMA_VERSION, "execution_id": execution_id(),
         "tool": INTERNAL_TO_CONTRACT.get(internal, internal), "status": STATUS.get(internal, "unknown"),
         "source": SOURCES.get(internal, "twin engine"), "engine_version": engine_version(),
         "subject_scope": "persona authorised by the session (never model-supplied)",
         "time_origin": ctx.get("now") or None, "unit": "mg/dL"}
    if internal in INTERVAL_SEMANTICS:
        m["interval_semantics"] = INTERVAL_SEMANTICS[internal]
    return m


def envelope(internal: str, output: Any, ctx: dict) -> Any:
    """Wrap a tool output with contract metadata (outputs that are errors are wrapped too)."""
    if not isinstance(output, dict):
        return output
    meta = {"schema_version": SCHEMA_VERSION, "execution_id": execution_id(),
            "tool": INTERNAL_TO_CONTRACT.get(internal, internal), "status": STATUS.get(internal, "unknown"),
            "source": SOURCES.get(internal, "twin engine"), "engine_version": engine_version(),
            "subject_scope": "persona authorised by the session (never model-supplied)",
            "time_origin": ctx.get("now") or None, "unit": "mg/dL"}
    if internal in INTERVAL_SEMANTICS:
        meta["interval_semantics"] = INTERVAL_SEMANTICS[internal]
    return {**output, "_contract": meta}


@lru_cache(maxsize=1)
def _summary() -> dict:
    try:
        return json.loads((REPORTS_DIR / "summary.json").read_text())
    except (OSError, ValueError):
        return {}


def engine_version() -> str | None:
    return (_summary().get("manifest") or {}).get("model_version")


def evidence_receipt() -> dict:
    """Facts from the generated reports (current files, not hard-coded values)."""
    s = _summary()
    lad = next((r for r in s.get("ladder") or [] if isinstance(r, dict) and str(r.get("level")) == "2"), {})
    rm = lad.get("rmse") or {}
    headline = {"setting": lad.get("label"), "rmse_mg_dl": {h: round(float(v), 1) for h, v in rm.items()},
                "coverage90": round(float(lad["coverage90"]), 3) if "coverage90" in lad else None,
                "mean_width90_mg_dl": round(float(lad["width90"]), 1) if "width90" in lad else None} if lad else None
    lim = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in (s.get("limitations") or [])][:6]
    return {"report": "reports/summary.json", "report_generated_at": s.get("generated_at"),
            "dataset": s.get("dataset"), "n_patients": s.get("n_patients_eval"),
            "n_forecast_windows": s.get("n_forecast_windows"),
            "evaluated_horizon_min": s.get("validated_horizon_min"),
            "protocol": (s.get("evaluation_protocol") or "")[:300], "engine_version": engine_version(),
            "headline_2_pricks_per_day": headline,
            "status": "retrospective evaluation on a named dataset; not clinical validation",
            "limitations": lim}


# ----------------------------------------------------------------------------- clarification policy
_DECIMAL = re.compile(r"(?<![\d.,])(\d{1,2}[.,]\d)(?![\d])")
_UNIT = re.compile(r"(mg\s*/?\s*dl|mmol)", re.I)
_GLUCOSE_WORDS = re.compile(r"(glucose|sugar|reading|level|meter|glucosa|azúcar|azucar|medición|lectura|nivel|"
                            r"glycémie|glycemie|sucre|mesure|lecture|taux|blutzucker|zucker|messwert|messung|"
                            r"gemessen|wert|glicemia|zucchero|misurazione|lettura|valore|血糖|測定|数値)", re.I)


def unit_clarification(text: str, lang: str, skip: set[str]) -> dict | None:
    """A reading with a decimal value and no unit is ambiguous (6,5 could be mmol/L): ask for the unit."""
    if "unit" in skip or _UNIT.search(text) or not _GLUCOSE_WORDS.search(text):
        return None
    m = _DECIMAL.search(text)
    if not m:
        return None
    raw = m.group(1)
    v = float(raw.replace(",", "."))
    if not 1.0 <= v <= 33.3:
        return None
    return {"slot": "unit", "question": NT.t("clarify_unit", lang, value=raw),
            "options": [{"label": "mg/dL", "text": text.replace(raw, f"{raw} mg/dL", 1)},
                        {"label": "mmol/L", "text": text.replace(raw, f"{raw} mmol/L", 1)}],
            "skip": {"label": NT.t("skip_unit", lang), "text": text, "skip_slots": ["unit"]}}


def _span(text: str, matched: str) -> tuple[int, int] | None:
    """Locate the parser's (token-joined) match in the original text."""
    parts = [re.escape(p) for p in matched.split() if p]
    if not parts:
        return None
    m = re.search(r"[\W_]*".join(parts), text, re.I)
    return (m.start(), m.end()) if m else None


# Vague amounts right before a dish ("some rice", "un poco de arroz"): replaced by the chosen quantity.
_VAGUE = re.compile(r"(?:\b(?:some|a bit of|a little|a lot of|lots of|un poco de|algo de|mucho|mucha|un peu de|"
                    r"beaucoup de|du|de la|etwas|ein bisschen|viel|un po' di|un po di|del|della|molto)\s+|"
                    r"(?:少し|ちょっと|たくさん)の?)$", re.I)


def _insert_qty(text: str, start: int, q: float) -> str:
    head = text[:start]
    m = _VAGUE.search(head)
    if m:
        head = head[:m.start()]
    return head + f"{q:g} " + text[start:]


def portion_clarification(text: str, found: list[dict], lang: str, skip: set[str]) -> dict | None:
    """At most ONE question: only when no dish in the message has a quantity, and only about the dish
    whose amount matters most (largest carbohydrate per household unit). Once the user names any
    quantity, the other dishes use their usual portion. Option texts are the user's own message with
    the quantity inserted, so they parse in any language."""
    if "portion" in skip or not found or any(f.get("explicit") or f.get("half_word") for f in found):
        return None
    best: tuple[dict, Any, tuple[int, int]] | None = None
    for f in found:
        r = food.get(f["food_id"])
        if r is None:
            continue
        sp = _span(text, str(f.get("matched") or ""))
        if sp is not None and (best is None or float(r["carbs_g"]) > float(best[1]["carbs_g"])):
            best = (f, r, sp)
    if best is None:
        return None
    f, r, sp = best
    fj = food.food_json(r, lang)
    name = food.spoken_name(str(fj["name"])) or str(fj["name"])
    if lang != "ja-JP" and len(name) > 1 and not name[1].isupper():
        name = name[:1].lower() + name[1:]
    unit = NT.unit_name(str(r["unit"]), lang)
    grams = float(r.get("grams_per_unit") or 0)
    opts = []
    for q in (0.5, 1, 2):
        qs = f"{q:g}" if lang in ("en-US", "ja-JP") else f"{q:g}".replace(".", ",")
        opts.append({"label": NT.t("portion_option", lang, qty=qs, unit=unit, grams=round(q * grams)),
                     "text": _insert_qty(text, sp[0], q)})
    return {"slot": "portion", "food_id": f["food_id"], "question": NT.t("clarify_portion", lang, food=name),
            "options": opts, "skip": {"label": NT.t("skip_portion", lang), "text": text, "skip_slots": ["portion"]}}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
