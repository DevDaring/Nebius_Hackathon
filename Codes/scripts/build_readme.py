#!/usr/bin/env python3
"""Inject results tables from backend/reports/*.json into README.md.

Every number in the tables is read from a report written by the experiment scripts
(``make experiments``); nothing is typed by hand. The tables replace whatever sits
between the markers::

    <!-- RESULTS:START -->
    ...
    <!-- RESULTS:END -->

If README.md is missing or has no markers, the tables are printed to stdout.

Usage::

    python scripts/build_readme.py            # update README.md (or print)
    python scripts/build_readme.py --stdout   # print only
    python scripts/build_readme.py --check    # exit 1 if README.md is out of date (CI)

Standard library only, so it runs without the backend venv.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "backend" / "reports"
README = ROOT.parent / "README.md"  # repository root, outside Codes/
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
HORIZONS = ("30", "60", "90", "120")


# ----------------------------------------------------------------------------- formatting
def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def f1(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{v:.1f}"


def f2(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{v:.2f}"


def pct(x: Any) -> str:
    """Fraction (0-1) -> percent."""
    v = _num(x)
    return "n/a" if v is None else f"{100 * v:.1f}%"


def pct_already(x: Any) -> str:
    """Value already in percent."""
    v = _num(x)
    return "n/a" if v is None else f"{v:.1f}%"


def ci(triple: Any, fmt=f1) -> str:
    """[point, lo, hi] -> 'point (lo-hi)'."""
    if not isinstance(triple, (list, tuple)) or len(triple) != 3 or _num(triple[0]) is None:
        return "n/a"
    return f"{fmt(triple[0])} ({fmt(triple[1])}–{fmt(triple[2])})"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def load(name: str) -> dict | None:
    p = REPORTS / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def source(rep: dict, name: str) -> str:
    when = rep.get("generated_at", "unknown time")
    by = rep.get("generated_by", "unknown script")
    return f"<sub>Source: `backend/reports/{name}.json`, generated {when} by `{by}`.</sub>"


def rmse_cells(m: dict) -> list[str]:
    r = m.get("rmse") or {}
    return [f1(r.get(h)) for h in HORIZONS]


def clarke_ab(clarke: dict | None) -> str:
    if not clarke:
        return "n/a"
    a, b = _num(clarke.get("A")), _num(clarke.get("B"))
    return "n/a" if a is None or b is None else f"{a + b:.1f}%"


# ----------------------------------------------------------------------------- sections
def sensor_ladder() -> str | None:
    rep = load("sensor_ladder")
    if not rep:
        return None
    rows = []
    for lv in rep.get("levels", []):
        cov = lv.get("coverage90") or {}
        rows.append([
            lv.get("label", lv.get("level", "?")),
            *rmse_cells(lv),
            ci(lv.get("rmse60_ci")),
            pct(cov.get("60")),
            f1((lv.get("width90") or {}).get("60")),
            ci(lv.get("auroc_high_ci"), f2) if lv.get("auroc_high_ci") else f2(lv.get("auroc_high")),
            clarke_ab((lv.get("reconstruction") or {}).get("clarke")),
        ])
    parts = [
        "### Sensor ladder (Experiment 1, headline)",
        rep.get("dataset", ""),
        "",
        f"_Protocol:_ {rep.get('protocol', '')}",
        "",
        table(["Glucose data after calibration", "RMSE 30 min", "RMSE 60 min", "RMSE 90 min", "RMSE 120 min",
               "RMSE 60 min (95% CI)", "90% band coverage (60 min)", "90% band width (60 min, mg/dL)",
               "AUROC P(>180 in 2 h) (95% CI)", "Clarke A+B, virtual CGM"], rows),
        "",
        "RMSE in mg/dL against the hidden CGM. Clarke A+B = share of the twin's reconstructed glucose trace "
        "in clinically acceptable zones.",
    ]
    lows = [lv.get("low_events") for lv in rep.get("levels", []) if lv.get("low_events")]
    if lows:
        le = lows[0]
        parts += ["", f"P(<70 in 2 h) is **not validated**: {le.get('note', '')} "
                      f"(scored windows with a low: {le.get('positive_windows')}, "
                      f"patients with a low: {le.get('patients_with_lows')})."]
    parts += ["", source(rep, "sensor_ladder")]
    return "\n".join(parts)


BASELINE_LABEL = {
    "persistence": "Persistence (last value)",
    "population_time_of_day": "Population time-of-day curve",
    "personal_average": "Personal average",
    "lightgbm_sparse_only": "LightGBM on sparse features (no twin)",
    "mechanistic_only": "Mechanistic twin only",
    "full_hybrid": "Full hybrid twin",
}


def baselines() -> str | None:
    rep = load("baselines")
    if not rep:
        return None
    row = next((r for r in rep.get("rows", []) if str(r.get("level")) == "2"), None)
    if row is None:
        return None
    rows = []
    for key, m in row.get("methods", {}).items():
        rows.append([BASELINE_LABEL.get(key, key), *rmse_cells(m), f1(m.get("mard_60")), f2(m.get("auroc_high"))])
    return "\n".join([
        "### Baselines at 2 finger-pricks per day (Experiment 3)",
        "",
        table(["Method", "RMSE 30", "RMSE 60", "RMSE 90", "RMSE 120", "MARD 60 (%)", "AUROC P(>180)"], rows),
        "",
        f"{rep.get('notes', '')} n/a = the method does not produce event probabilities.",
        "",
        source(rep, "baselines"),
    ])


def transfer() -> str | None:
    rep = load("transfer")
    if not rep:
        return None
    rows = []
    for r in rep.get("rows", []):
        rows.append([
            r.get("test", "?"), r.get("train", "?"), r.get("setting", "?"), str(r.get("n_patients", "n/a")),
            ci(r.get("rmse60_ci")), pct((r.get("coverage90") or {}).get("60")), f2(r.get("auroc_high")),
        ])
    parts = [
        "### Cross-population transfer (Experiment 5)",
        "",
        f"_Protocol:_ {rep.get('protocol', '')}",
        "",
        table(["Test on", "Fitted on", "Maintenance data", "Patients", "RMSE 60 min (95% CI)",
               "90% coverage (60 min)", "AUROC P(>180)"], rows),
    ]
    gap = rep.get("gap_rmse60") or {}
    if gap:
        parts += ["", "Transfer gap in RMSE at 60 min (transfer minus in-domain, mg/dL): "
                  + "; ".join(f"{k.replace('_', ' ')}: {f1(v)}" for k, v in gap.items()) + "."]
    ins = rep.get("shanghai_by_insulin") or {}
    if ins:
        parts += ["", "ShanghaiT2DM by insulin use (insulin is not represented in the model): "
                  + "; ".join(f"{k.replace('_', ' ')} (n={v.get('n_patients')}): RMSE 60 min "
                              f"{f1((v.get('rmse') or {}).get('60'))}" for k, v in ins.items()) + "."]
    if any(r.get("auroc_high") is None for r in rep.get("rows", [])):
        parts += ["", "n/a AUROC: no event probabilities were reported for that arm."]
    parts += ["", source(rep, "transfer")]
    return "\n".join(parts)


def nbp() -> str | None:
    rep = load("nbp_value")
    if not rep:
        return None
    rows = []
    for arm, m in rep.get("arms", {}).items():
        rec = m.get("reconstruction") or {}
        rows.append([arm, f1(rec.get("rmse")), ci(m.get("rmse60_ci")),
                     pct((m.get("coverage90") or {}).get("60")), f2(m.get("auroc_high"))])
    parts = [
        "### Next-best-prick placement (Experiment 4)",
        "",
        f"_Protocol:_ {rep.get('protocol', '')}",
        "",
        table(["Prick timing", "Reconstruction RMSE (mg/dL)", "Forecast RMSE 60 min (95% CI)",
               "90% coverage (60 min)", "AUROC P(>180)"], rows),
    ]
    diffs = rep.get("paired_differences") or {}
    if diffs:
        drows = []
        for k, d in diffs.items():
            c = d.get("ci95") or [None, None]
            lo, hi = _num(c[0]), _num(c[1])
            sig = "n/a" if lo is None or hi is None else ("no (CI includes 0)" if lo <= 0 <= hi else "yes")
            drows.append([k.replace("_", " "), f2(d.get("mean_recon_rmse_change")),
                          f"{f2(c[0])} to {f2(c[1])}", f"{d.get('patients_improved')}/{d.get('n_patients')}", sig])
        parts += ["", table(["Paired comparison", "Mean change in reconstruction RMSE (mg/dL)", "95% CI",
                             "Patients improved", "Significant"], drows)]
    parts += ["", source(rep, "nbp_value")]
    return "\n".join(parts)


def subgroups() -> str | None:
    rep = load("subgroups")
    if not rep:
        return None
    rows = []
    for r in rep.get("rows", []):
        rows.append([r.get("dimension", "?"), r.get("group", "?"), str(r.get("n_patients", "n/a")),
                     f1(r.get("rmse60")), pct(r.get("coverage90_60")), f2(r.get("auroc_high")),
                     f2(r.get("ece_high")), "**FLAG**" if r.get("flagged") else "ok"])
    ov = rep.get("overall") or {}
    flagged = [f"{r.get('dimension')} {r.get('group')}" for r in rep.get("rows", []) if r.get("flagged")]
    return "\n".join([
        f"### {rep.get('title', 'Subgroup audit')}",
        "",
        f"Overall: RMSE 60 min {f1(ov.get('rmse60'))} mg/dL, 90% coverage {pct(ov.get('coverage90_60'))}, "
        f"ECE P(>180) {f2(ov.get('ece_high'))}. Flag rule: {rep.get('flag_rule', '')}.",
        "",
        table(["Dimension", "Group", "Patients", "RMSE 60", "90% coverage (60)", "AUROC P(>180)", "ECE P(>180)",
               "Flag"], rows),
        "",
        ("Flagged subgroups: " + ", ".join(flagged) + ".") if flagged else "No subgroup met the flag rule. "
        "Several groups are small (see the Patients column), so this is weak evidence of fairness.",
        "",
        source(rep, "subgroups"),
    ])


def calibration_length() -> str | None:
    rep = load("calibration_length")
    if not rep:
        return None
    rows = [[str(r.get("cgm_days")), str(r.get("n_patients")), *rmse_cells(r), ci(r.get("rmse60_ci")),
             pct((r.get("coverage90") or {}).get("60")), f2(r.get("auroc_high"))] for r in rep.get("rows", [])]
    return "\n".join([
        "### Calibration length (Experiment 2)",
        "",
        f"_Protocol:_ {rep.get('protocol', '')}",
        "",
        table(["CGM days", "Patients", "RMSE 30", "RMSE 60", "RMSE 90", "RMSE 120", "RMSE 60 (95% CI)",
               "90% coverage (60)", "AUROC P(>180)"], rows),
        "",
        source(rep, "calibration_length"),
    ])


def build() -> str:
    sections = [s() for s in (sensor_ladder, baselines, calibration_length, nbp, transfer, subgroups)]
    present = [s for s in sections if s]
    if not present:
        return "_No reports found in backend/reports/. Run `make reproduce`._"
    head = ("_Tables generated by `scripts/build_readme.py` from `backend/reports/*.json`. "
            "Do not edit by hand; run `make readme`._")
    return "\n\n".join([head, *present])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stdout", action="store_true", help="print the tables instead of editing README.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if README.md tables are out of date")
    args = ap.parse_args()

    body = build()
    block = f"{START}\n{body}\n{END}"
    text = README.read_text(encoding="utf-8") if README.exists() else None
    has_markers = text is not None and START in text and END in text

    if args.stdout or not has_markers:
        if not args.stdout:
            why = "README.md not found" if text is None else "README.md has no RESULTS markers"
            print(f"[build_readme] {why}; printing tables to stdout.", file=sys.stderr)
        print(body)
        return 1 if args.check else 0

    assert text is not None
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    new = pattern.sub(lambda _m: block, text, count=1)
    if args.check:
        if new != text:
            print("[build_readme] README.md results tables are out of date; run `make readme`.", file=sys.stderr)
            return 1
        return 0
    if new != text:
        README.write_text(new, encoding="utf-8")
        print("[build_readme] README.md results tables updated.", file=sys.stderr)
    else:
        print("[build_readme] README.md already up to date.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
