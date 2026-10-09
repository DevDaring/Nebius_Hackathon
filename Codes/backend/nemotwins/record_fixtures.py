"""Re-record the offline-demo vision fixtures with the Nebius Token Factory vision model (APP_MODE=live).

Live vision parse of every sample meal photo and lab report through ``perception.meal.parse`` /
``perception.lab.parse`` (with ``sample_id``), which writes ``fixtures/meal_parse/<id>.json`` and
``fixtures/lab_parse/<id>.json``. Lab values are scored against the synthetic reports' ground truth.

    APP_MODE=live python -m nemotwins.record_fixtures

Secrets are never logged.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from nemotwins.config import get_settings


# ----------------------------------------------------------------------------- helpers
def set_mode(mode: str) -> None:
    os.environ["APP_MODE"] = "live" if mode == "live" else "demo"
    get_settings.cache_clear()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _log(msg: str) -> None:
    print(msg, flush=True)



def step_vision() -> dict:
    from nemotwins.perception import lab, meal
    from nemotwins.providers.llm import LLMUnavailable, available

    set_mode("live")
    if not available("vision"):
        raise SystemExit("vision step needs APP_MODE=live, TOKENFACTORY_2009_API_KEY and NEMOTRON_VISION_MODEL")
    out: dict[str, Any] = {"meals": [], "labs": []}
    for s in meal.samples():
        t0 = time.perf_counter()
        try:
            r = meal.record_fixture(s["id"])  # the only writer of packaged meal fixtures
            ok = r.get("source") == "live"
            rec = {"id": s["id"], "ok": ok, "source": r.get("source"), "model": r.get("model"),
                   "dishes": [{"detected": d["detected"], "food_id": d["food_id"], "units": d["units"],
                               "needs_pick": d["needs_pick"]} for d in r["dishes"]],
                   "total_carbs": r["total"]["carbs"], "carbs_sd": r["carbs_sd"]}
        except (LLMUnavailable, ValueError) as exc:
            rec = {"id": s["id"], "ok": False, "error": str(exc)[:200]}
        rec["ms"] = round((time.perf_counter() - t0) * 1000)
        out["meals"].append(rec)
        _log(f"meal {s['id']}: {'live' if rec['ok'] else 'FAILED'} "
             f"{len(rec.get('dishes', []))} dishes, {rec.get('total_carbs')} g carbs, {rec['ms']} ms")
    truth = {t["id"]: t.get("ground_truth", {}) for t in json.loads((lab.SAMPLES_DIR / "samples.json").read_text())}
    key_map = {"fasting_glucose": "fpg"}
    for s in lab.samples():
        t0 = time.perf_counter()
        try:
            r = lab.record_fixture(s["id"])  # the only writer of packaged lab fixtures
            gt = truth.get(s["id"], {})
            fields = {f["code"]: f["value"] for f in r["fields"] if f["code"] != "medication"}
            meds = [f["value"] for f in r["fields"] if f["code"] == "medication"]
            scored = {}
            for code in lab.FIELDS:
                want = gt.get(key_map.get(code, code))
                if want is None:
                    continue
                got = fields.get(code)
                scored[code] = {"truth": want, "parsed": got,
                                "match": got is not None and abs(float(got) - float(want)) <= 1e-6}
            n_ok = sum(v["match"] for v in scored.values())
            rec = {"id": s["id"], "ok": r.get("source") == "live", "source": r.get("source"), "model": r.get("model"),
                   "fields_correct": n_ok, "fields_total": len(scored), "fields": scored, "medications": meds,
                   "medications_truth": gt.get("medications", [])}
        except (LLMUnavailable, ValueError) as exc:
            rec = {"id": s["id"], "ok": False, "error": str(exc)[:200]}
        rec["ms"] = round((time.perf_counter() - t0) * 1000)
        out["labs"].append(rec)
        _log(f"lab {s['id']}: {'live' if rec['ok'] else 'FAILED'} "
             f"{rec.get('fields_correct')}/{rec.get('fields_total')} fields exact, {rec['ms']} ms")
    return out



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    if not get_settings().live:
        _log("APP_MODE is not 'live'; the vision step switches it on for its calls.")
    v = step_vision()
    summary = {"meals_live": sum(m["ok"] for m in v["meals"]), "meals": len(v["meals"]),
               "labs_live": sum(m["ok"] for m in v["labs"]), "labs": len(v["labs"]),
               "lab_fields_correct": sum(m.get("fields_correct", 0) for m in v["labs"]),
               "lab_fields_total": sum(m.get("fields_total", 0) for m in v["labs"]), "detail": v}
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
