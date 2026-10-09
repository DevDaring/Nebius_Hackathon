"""Numerical regression harness for the twin engine.

Runs the engine on fixed, representative inputs and either records the outputs or compares them with a
recorded snapshot. Changes to the agent, languages or interface must leave the numerical engine's outputs
identical within ``TOL``.

    python -m nemotwins.eval.numerical_regression --record baseline_2026-10-08
    python -m nemotwins.eval.numerical_regression --compare baseline_2026-10-08

Snapshots live in ``reports/regression/`` (new files only; recorded snapshots are never overwritten).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, date, datetime
from typing import Any

from nemotwins.config import REPORTS_DIR

OUT_DIR = REPORTS_DIR / "regression"
TOL = 1e-6  # absolute tolerance; the engine is seeded, so outputs should be bit-for-bit stable
MEAL = {"name": "fixed test meal", "carbs": 60.0, "fibre": 4.0, "protein": 15.0, "fat": 10.0}


def _case_outputs(engine: Any, pid: str) -> dict:
    ladder = "2"
    st = engine.state(pid, ladder, [], offset=0)
    fc = engine.forecast(pid, ladder, [], MEAL, offset=0)
    wi = engine.what_if(pid, ladder, [], MEAL, {"carb_scale": 0.5, "label": "half"}, offset=0)
    walk = engine.what_if(pid, ladder, [], MEAL, {"walk_min": 15.0, "label": "walk"}, offset=0)
    asm = engine.assimilate(pid, ladder, [], 150.0, offset=0)
    return {
        "state": {"now": st["now"], "estimate": st["estimate"], "band": st["band"],
                  "freshness": st["freshness"], "forecast_peak": st["forecast"]["peak"],
                  "p_high": st["forecast"]["p_high"]["p"], "nbp_time": st["next_best_prick"]["time"]},
        "forecast_meal": {"peak": fc["peak"], "p_high": fc["p_high"]["p"], "p_low": fc["p_low"]["p"]},
        "what_if_half": {"delta_peak": wi["delta_peak"], "delta_peak_ci": wi["delta_peak_ci"],
                         "delta_p_high": wi["delta_p_high"], "too_small_to_call": wi["too_small_to_call"]},
        "what_if_walk": {"delta_peak": walk["delta_peak"], "delta_peak_ci": walk["delta_peak_ci"],
                         "too_small_to_call": walk["too_small_to_call"]},
        "assimilate_150": {"estimate_after": asm["state"]["estimate"], "band_after": asm["band_after"],
                           "width_change": asm.get("width_change")},
    }


def run() -> dict:
    from nemotwins.twin import personas as PS
    from nemotwins.twin.engine import get_engine

    e = get_engine()
    return {p["id"]: _case_outputs(e, p["id"]) for p in PS.PERSONAS}


def _flatten(o: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(o, dict):
        out: dict[str, Any] = {}
        for k, v in o.items():
            out |= _flatten(v, f"{prefix}.{k}" if prefix else str(k))
        return out
    if isinstance(o, list):
        out = {}
        for i, v in enumerate(o):
            out |= _flatten(v, f"{prefix}[{i}]")
        return out
    return {prefix: o}


_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}(?::\d{2})?)$")


def _relative_times(outputs: dict) -> dict:
    """The replay clock is anchored to today's calendar date (engine.py), so absolute timestamps move every
    day. Express each timestamp as days + time relative to that persona's replay 'now' before comparing."""
    out = {}
    for pid, rec in outputs.items():
        now = _ISO.match(str(rec.get("state", {}).get("now", "")))
        base = date.fromisoformat(now.group(1)) if now else None

        def conv(o: Any, base: date | None = base) -> Any:
            if isinstance(o, dict):
                return {k: conv(v) for k, v in o.items()}
            if isinstance(o, list):
                return [conv(v) for v in o]
            m = _ISO.match(o) if isinstance(o, str) else None
            if m and base is not None:
                return f"D{(date.fromisoformat(m.group(1)) - base).days:+d}T{m.group(2)}"
            return o
        out[pid] = conv(rec)
    return out


def compare(old: dict, new: dict, tol: float = TOL) -> list[str]:
    a, b = _flatten(_relative_times(old)), _flatten(_relative_times(new))
    diffs = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, int | float) and isinstance(y, int | float) and not isinstance(x, bool):
            if abs(float(x) - float(y)) > tol:
                diffs.append(f"{k}: {x} -> {y}")
        elif x != y:
            diffs.append(f"{k}: {x!r} -> {y!r}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", metavar="LABEL")
    g.add_argument("--compare", metavar="LABEL")
    a = ap.parse_args(argv)
    outputs = run()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if a.record:
        path = OUT_DIR / f"numerical_{a.record}.json"
        if path.exists():
            print(f"{path} exists; refusing to overwrite a recorded snapshot", file=sys.stderr)
            return 2
        body = {"label": a.record, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "inputs": {"ladder": "2", "offset": 0, "meal": MEAL, "readings_assimilated": [150.0]},
                "outputs": outputs}
        text = json.dumps(body, indent=1, sort_keys=True)
        path.write_text(text)
        print(f"recorded {path} sha256={hashlib.sha256(text.encode()).hexdigest()[:16]}")
        return 0
    path = OUT_DIR / f"numerical_{a.compare}.json"
    old = json.loads(path.read_text())["outputs"]
    diffs = compare(old, outputs)
    result = {"compared_to": path.name, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
              "tolerance_abs": TOL, "n_values": len(_flatten(old)), "n_diffs": len(diffs), "diffs": diffs[:200]}
    (OUT_DIR / f"compare_{a.compare}_latest.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "diffs"}))
    for d in diffs[:20]:
        print("  DIFF", d)
    return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
