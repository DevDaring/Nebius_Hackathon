"""Evidence receipt: every important number behind one forecast, with its
status (measured / estimated / simulated / validated / exploratory / not_validated) and its
source (a tool output, an evaluation report, the dataset, or the user)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nemotwins.twin.engine import M_FC, VALIDATED_HORIZON_MIN, TwinEngine

LABELS: dict[str, dict[str, str]] = {
    "last_reading": {
        "en-US": "Last glucose reading",
        "es-ES": "Última medición de glucosa",
        "fr-FR": "Dernière mesure de glycémie",
        "de-DE": "Letzter Blutzucker-Messwert",
        "it-IT": "Ultima misurazione della glicemia",
        "ja-JP": "最新の血糖測定値",
    },
    "estimate_now": {
        "en-US": "Current glucose estimate",
        "es-ES": "Glucosa estimada actual",
        "fr-FR": "Glycémie estimée actuelle",
        "de-DE": "Aktuell geschätzter Blutzucker",
        "it-IT": "Glicemia stimata attuale",
        "ja-JP": "現在の推定血糖値",
    },
    "band_now": {
        "en-US": "Likely range now (90%)",
        "es-ES": "Rango probable ahora (90 %)",
        "fr-FR": "Plage probable actuelle (90 %)",
        "de-DE": "Wahrscheinlicher Bereich jetzt (90 %)",
        "it-IT": "Intervallo probabile ora (90%)",
        "ja-JP": "現在の可能性が高い範囲（90%）",
    },
    "forecast_peak": {
        "en-US": "Expected peak in the next 2 hours",
        "es-ES": "Pico previsto en las próximas 2 horas (pronóstico)",
        "fr-FR": "Pic attendu dans les 2 prochaines heures (prévision)",
        "de-DE": "Erwarteter Spitzenwert in den nächsten 2 Stunden (Prognose)",
        "it-IT": "Picco atteso nelle prossime 2 ore (previsione)",
        "ja-JP": "今後2時間の予測ピーク",
    },
    "p_high": {
        "en-US": "Chance of going above 180 in 2 hours",
        "es-ES": "Probabilidad de superar 180 en 2 horas",
        "fr-FR": "Probabilité de dépasser 180 en 2 heures",
        "de-DE": "Wahrscheinlichkeit, in 2 Stunden über 180 zu steigen",
        "it-IT": "Probabilità di superare 180 in 2 ore",
        "ja-JP": "2時間以内に180を超える確率",
    },
    "p_high_reliability": {
        "en-US": "How often this happened for similar held-out forecasts",
        "es-ES": "Con qué frecuencia ocurrió en pronósticos similares con datos reservados (evaluación retrospectiva)",
        "fr-FR": "Fréquence observée pour des prévisions similaires sur données réservées (évaluation rétrospective)",
        "de-DE": "Wie oft dies bei ähnlichen Prognosen auf zurückgehaltenen Daten eintrat (retrospektive Evaluation)",
        "it-IT": "Quante volte è successo in previsioni simili su dati esclusi (valutazione retrospettiva)",
        "ja-JP": "同様の検証用予測で実際に起きた頻度（後ろ向き評価）",
    },
    "p_low": {
        "en-US": "Chance of going below 70 in 2 hours (not validated)",
        "es-ES": "Probabilidad de bajar de 70 en 2 horas (no validado)",
        "fr-FR": "Probabilité de descendre sous 70 en 2 heures (non validé)",
        "de-DE": "Wahrscheinlichkeit, in 2 Stunden unter 70 zu fallen (nicht validiert)",
        "it-IT": "Probabilità di scendere sotto 70 in 2 ore (non validato)",
        "ja-JP": "2時間以内に70を下回る確率（未検証）",
    },
    "trajectory_240": {
        "en-US": "Median curve at 4 hours (beyond the validated 2 hours)",
        "es-ES": "Curva mediana a las 4 horas (más allá de las 2 horas validadas)",
        "fr-FR": "Courbe médiane à 4 heures (au-delà des 2 heures validées)",
        "de-DE": "Mediankurve nach 4 Stunden (jenseits der validierten 2 Stunden)",
        "it-IT": "Curva mediana a 4 ore (oltre le 2 ore validate)",
        "ja-JP": "4時間後の中央値曲線（検証済みの2時間を超える範囲）",
    },
    "meal_carbs": {
        "en-US": "Meal carbohydrate",
        "es-ES": "Hidratos de carbono de la comida",
        "fr-FR": "Glucides du repas",
        "de-DE": "Kohlenhydrate der Mahlzeit",
        "it-IT": "Carboidrati del pasto",
        "ja-JP": "食事の炭水化物",
    },
    "hba1c": {
        "en-US": "HbA1c used by the twin",
        "es-ES": "HbA1c usada por el gemelo digital",
        "fr-FR": "HbA1c utilisée par le jumeau numérique",
        "de-DE": "Vom digitalen Zwilling verwendeter HbA1c-Wert",
        "it-IT": "HbA1c usata dal gemello digitale",
        "ja-JP": "デジタルツインが使用するHbA1c",
    },
    "bmi": {
        "en-US": "BMI used by the twin",
        "es-ES": "IMC usado por el gemelo digital",
        "fr-FR": "IMC utilisé par le jumeau numérique",
        "de-DE": "Vom digitalen Zwilling verwendeter BMI",
        "it-IT": "IMC usato dal gemello digitale",
        "ja-JP": "デジタルツインが使用するBMI",
    },
    "top_driver": {
        "en-US": "Biggest physiology driver of the peak",
        "es-ES": "Principal factor fisiológico del pico",
        "fr-FR": "Principal facteur physiologique du pic",
        "de-DE": "Wichtigster physiologischer Einflussfaktor auf den Spitzenwert",
        "it-IT": "Principale fattore fisiologico del picco",
        "ja-JP": "ピークの最大の生理的要因",
    },
    "next_check": {
        "en-US": "Suggested next finger-prick (experimental)",
        "es-ES": "Próxima medición capilar sugerida (experimental)",
        "fr-FR": "Prochaine glycémie capillaire suggérée (expérimental)",
        "de-DE": "Vorgeschlagene nächste kapillare Messung (experimentell)",
        "it-IT": "Prossima misurazione capillare suggerita (sperimentale)",
        "ja-JP": "次の指先採血の提案（試験的）",
    },
    "scenario_peak": {
        "en-US": "Simulated peak with the change",
        "es-ES": "Pico con el cambio (simulación exploratoria)",
        "fr-FR": "Pic avec le changement (simulation exploratoire)",
        "de-DE": "Spitzenwert mit der Änderung (explorative Simulation)",
        "it-IT": "Picco con il cambiamento (simulazione esplorativa)",
        "ja-JP": "変更後のピーク（探索的シミュレーション）",
    },
    "scenario_p_high": {
        "en-US": "Simulated chance above 180 with the change",
        "es-ES": "Probabilidad de superar 180 con el cambio (simulación exploratoria)",
        "fr-FR": "Probabilité de dépasser 180 avec le changement (simulation exploratoire)",
        "de-DE": "Wahrscheinlichkeit über 180 mit der Änderung (explorative Simulation)",
        "it-IT": "Probabilità di superare 180 con il cambiamento (simulazione esplorativa)",
        "ja-JP": "変更後に180を超える確率（探索的シミュレーション）",
    },
}

STATUS_EN = {"measured": "measured", "estimated": "estimated by the twin", "simulated": "model simulation",
             "validated": "checked on held-out data", "exploratory": "exploratory", "not_validated": "not validated"}


def _claim(key: str, lang: str, value: Any, unit: str, status: str, kind: str, ref: str, **extra: Any) -> dict:
    lab = LABELS.get(key, {"en-US": key})
    return {"key": key, "label_en": lab["en-US"], "label": lab.get(lang, lab["en-US"]), "value": value, "unit": unit,
            "status": status, "source": {"kind": kind, "ref": ref}, **extra}


def _reading_source(src: str | None) -> tuple[str, str]:
    if src in ("manual", "chat"):
        return "user", f"reading entered by the user ({src})"
    if src == "replay":
        return "dataset", "dataset reference CGM revealed in the replay"
    return "dataset", "sensor-ladder observation from the persona's open CGMacros record"


def build(engine: TwinEngine, ctx: dict, forecast_id: str, persona: dict, lang: str) -> dict:
    pid, ladder = ctx["pid"], ctx["ladder"]
    events, offset, rev = ctx.get("events", []), int(ctx.get("offset", 0)), ctx.get("rev")
    out = ctx["out"]
    st = engine.state(pid, ladder, events, offset=offset, rev=rev)
    prov = out.get("provenance") or {}
    claims: list[dict] = []
    last = st.get("last_observation")
    if last:
        kind, ref = _reading_source(last.get("source"))
        claims.append(_claim("last_reading", lang, last["value"], "mg/dL", "measured", kind, ref, t=last["t"]))
    claims.append(_claim("estimate_now", lang, st["estimate"], "mg/dL", "estimated", "tool", "get_state.estimate",
                         t=st["now"]))
    claims.append(_claim("band_now", lang, [st["band"]["lo"], st["band"]["hi"]], "mg/dL", "estimated", "tool",
                         "get_state.band"))
    if ctx.get("kind") == "scenario":
        claims.append(_claim("scenario_peak", lang, out["peak"]["value"], "mg/dL", "simulated", "tool",
                             "what_if.scenario.peak", t=out["peak"]["t"], baseline_forecast_id=ctx.get("baseline_id")))
        claims.append(_claim("scenario_p_high", lang, out["p_high"]["p"], "probability", "simulated", "tool",
                             "what_if.scenario.p_high.p"))
    else:
        claims.append(_claim("forecast_peak", lang, out["peak"]["value"], "mg/dL", "estimated", "tool",
                             "forecast.peak", t=out["peak"]["t"]))
        rel = out["p_high"].get("reliability") or {}
        claims.append(_claim("p_high", lang, out["p_high"]["p"], "probability", "validated", "tool",
                             "forecast.p_high.p", freq_text=out["p_high"].get("freq_text")))
        claims.append(_claim("p_high_reliability", lang, rel.get("observed"), "proportion", "validated", "report",
                             f"reports/calibration_curve.json#levels.{ladder}.high",
                             n=rel.get("n"), ci=[rel.get("ci_lo"), rel.get("ci_hi")],
                             bin=[rel.get("pred_lo"), rel.get("pred_hi")]))
    claims.append(_claim("p_low", lang, out["p_low"]["p"], "probability", "not_validated", "tool", "forecast.p_low.p"))
    q50 = out["traj"]["q50"]
    if out.get("horizon_min", 0) > VALIDATED_HORIZON_MIN and q50:
        claims.append(_claim("trajectory_240", lang, q50[-1], "mg/dL", "exploratory", "tool", "forecast.traj.q50[-1]",
                             t=out["traj"]["t"][-1]))
    meal = ctx.get("meal")
    if meal and meal.get("carbs") is not None:
        claims.append(_claim("meal_carbs", lang, meal.get("carbs"), "g", "estimated", "user",
                             "meal input; nutrition from the Indian food table", name=meal.get("name")))
    for k, unit in (("hba1c", "%"), ("bmi", "kg/m2")):
        pi = (prov.get("prior_inputs") or {}).get(k) or {}
        if pi.get("source") == "lab upload (confirmed)":
            claims.append(_claim(k, lang, pi.get("value"), unit, "measured", "user",
                                 f"lab upload revision {pi.get('revision')}, collected {pi.get('date') or 'date unknown'}"))
        else:
            claims.append(_claim(k, lang, pi.get("value"), unit, "measured", "dataset",
                                 "persona EHR (open CGMacros source participant)"))
    if ctx.get("kind") == "forecast":
        phys = ctx.get("phys") or []
        if phys:
            top = sorted(phys, key=lambda d: -abs(d["contribution"]))[0]
            claims.append(_claim("top_driver", lang, top["contribution"], "mg/dL on the peak", "simulated", "tool",
                                 f"explain.physiology.{top['name']}", driver=top["label_en"]))
    nbp = st.get("next_best_prick") or {}
    if nbp.get("time"):
        claims.append(_claim("next_check", lang, nbp["time"], "time", "exploratory", "tool", "next_best_prick.time",
                             note="reports/nbp_value.json: no significant accuracy gain shown"))
    ev_out = []
    for e in events:
        t_min = float(e.get("t_min") or 0.0)
        item = {"kind": e.get("kind"), "t": engine.display_time(pid, t_min).isoformat(timespec="minutes"),
                "source": e.get("source", "manual")}
        if e.get("kind") == "reading":
            item["value_mg_dl"] = e.get("value")
        else:
            item.update({"name": e.get("name"), "carbs": e.get("carbs")})
        ev_out.append(item)
    return {
        "forecast_id": forecast_id, "persona_id": pid, "persona_name": persona.get("name"), "synthetic": True,
        "kind": ctx.get("kind", "forecast"), "replay_now": prov.get("replay_now", st["now"]),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "claims": claims,
        "inputs": {"ladder": ladder, "offset_min": offset, "events": ev_out, "meal": meal,
                   "scenario": ctx.get("scenario"), "covariate_revision": prov.get("inputs_revision", 0),
                   "prior_inputs": prov.get("prior_inputs"), "observations_used": prov.get("observations_used")},
        "model": {"model_version": prov.get("model_version", engine.model_version),
                  "hybrid_trained_on": prov.get("hybrid_trained_on", engine.hybrid_trained_on),
                  "conformal_level": out.get("conformal_level", 0.9), "validated_horizon_min": VALIDATED_HORIZON_MIN,
                  "forecast_particles": M_FC,
                  "calibration": "after a 5-day CGM calibration wear (persona replay)",
                  "notes": ["P(>180 in 2 h) reliability comes from patient-grouped held-out forecasts "
                            "(reports/calibration_curve.json).", "P(<70) is not validated.",
                            "Trajectory points beyond 120 minutes are exploratory.",
                            "What-if results are model simulations, not proven effects."]},
        "tool_calls": [
            {"name": "get_state", "args": {"ladder": ladder, "offset_min": offset},
             "output": {"estimate": st["estimate"], "band": st["band"], "now": st["now"],
                        "last_observation": st.get("last_observation")}},
            {"name": "what_if" if ctx.get("kind") == "scenario" else "forecast",
             "args": {"ladder": ladder, "meal": meal, "scenario": ctx.get("scenario"), "offset_min": offset},
             "output": {"forecast_id": forecast_id, "peak": out["peak"], "p_high": out["p_high"]["p"],
                        "p_low": out["p_low"]["p"]}},
        ],
    }


def _fmt(v: Any) -> str:
    if isinstance(v, list):
        return " to ".join(_fmt(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}"
    return "n/a" if v is None else str(v)


def markdown(r: dict) -> str:
    lines = [f"# Evidence receipt: {r.get('persona_name') or r['persona_id']} (synthetic persona)", "",
             f"- Forecast id: `{r['forecast_id']}` ({r.get('kind', 'forecast')})",
             f"- Replay time: {r['replay_now']} (replay clock, not wall-clock time)",
             f"- Generated: {r['generated_at']}", "",
             "Decision support only; not a medical device. No medicine or insulin dose advice.", "",
             "## Claims", "", "| Claim | Value | Unit | Status | Source |", "|---|---|---|---|---|"]
    for c in r["claims"]:
        src = c["source"]
        lines.append(f"| {c['label_en']} | {_fmt(c['value'])} | {c['unit']} | {STATUS_EN.get(c['status'], c['status'])} "
                     f"| {src['kind']}: {src['ref']} |")
    inp = r["inputs"]
    lines += ["", "## Inputs", "", f"- Sensor ladder: {inp['ladder']}; replay offset {inp['offset_min']} min",
              f"- Covariate revision: {inp['covariate_revision']}",
              f"- Observations used: {inp.get('observations_used')}"]
    for k, v in (inp.get("prior_inputs") or {}).items():
        lines.append(f"- Prior input {k}: {_fmt(v.get('value'))} ({v.get('source')}"
                     + (f", {v.get('date')}" if v.get("date") else "") + ")")
    for e in inp.get("events") or []:
        what = f"{e.get('value_mg_dl')} mg/dL reading" if e["kind"] == "reading" else f"meal {e.get('name')} ({e.get('carbs')} g)"
        lines.append(f"- User event at {e['t']}: {what} [{e.get('source')}]")
    m = r["model"]
    lines += ["", "## Model", "", f"- Version: {m['model_version']}", f"- Hybrid trained on: {m['hybrid_trained_on']}",
              f"- Conformal level: {m['conformal_level']}; validated horizon: {m['validated_horizon_min']} min",
              f"- Calibration: {m['calibration']}"]
    lines += [f"- {n}" for n in m.get("notes", [])]
    return "\n".join(lines) + "\n"
