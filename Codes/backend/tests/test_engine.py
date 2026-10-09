"""Twin API service (twin/engine.py): batching equivalence, determinism, contract flags."""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import HAS_PROCESSED

from nemotwins.twin import personas as PS

MEAL = {"name": "rice and dal", "carbs": 70.0, "fibre": 4.0, "protein": 12.0, "fat": 6.0}
PIDS = [p["id"] for p in PS.PERSONAS]


def _finite(o) -> bool:
    if isinstance(o, float):
        return math.isfinite(o)
    if isinstance(o, dict):
        return all(_finite(v) for v in o.values())
    if isinstance(o, list):
        return all(_finite(v) for v in o)
    return True


def test_batched_simulation_equals_separate_runs(engine) -> None:
    b, pf = engine._live("biman", "2", [])
    snap = engine._snapshot(pf)
    variants = [{"meal": MEAL, "logged": 0.0}, {"meal": None, "logged": 0.0},
                {"meal": MEAL, "logged": 0.0, "overrides": {"SI": 1e-4}},
                {"meal": MEAL, "scen": {"walk_min": 20, "carb_scale": 0.5}, "logged": 10.0}]
    batched = engine._simulate_many(b, snap, variants, seed=21)
    for v, tr in zip(variants, batched, strict=True):
        alone = engine._simulate(b, snap, v.get("meal"), v.get("scen"), v.get("logged", 0.0), 21, v.get("overrides"))
        np.testing.assert_array_equal(tr, alone)


def test_forecast_is_deterministic_and_cached(engine) -> None:
    engine.clear_cache()
    a = engine.forecast("lakshmi", "2", [], MEAL)
    engine.clear_cache()
    b = engine.forecast("lakshmi", "2", [], MEAL)
    assert a["traj"] == b["traj"] and a["p_high"] == b["p_high"] and a["drivers"] == b["drivers"]
    c = engine.forecast("lakshmi", "2", [], MEAL)  # cache hit: same id, still explainable
    assert c["forecast_id"] == b["forecast_id"]
    assert engine.explain(c["forecast_id"])["physiology"]
    c["traj"]["q50"][0] = -1.0  # callers get copies; the cache is not mutated
    assert engine.forecast("lakshmi", "2", [], MEAL)["traj"]["q50"][0] != -1.0


@pytest.mark.parametrize("pid", PIDS)
def test_forecast_contract_flags(engine, pid: str) -> None:
    fc = engine.forecast(pid, "2", [], MEAL)
    assert fc["p_low_validated"] is False and fc["p_low"]["validated"] is False
    assert len(fc["traj"]["t"]) == 48 and fc["horizon_min"] == 240
    q = fc["traj"]
    assert all(a <= b <= c <= d <= e for a, b, c, d, e in zip(q["q05"], q["q25"], q["q50"], q["q75"], q["q95"],
                                                                 strict=True))
    assert 1 <= len(fc["drivers"]) <= 5
    assert _finite(fc)


@pytest.mark.parametrize("ladder", ["full", "4", "2", "1", "0"])
def test_state_every_ladder(engine, ladder: str) -> None:
    st = engine.state("ramesh", ladder, [])
    assert st["p_low_validated"] is False
    assert st["band"]["lo"] <= st["estimate"] <= st["band"]["hi"]
    assert st["forecast"]["p_low_validated"] is False
    assert st["next_best_prick"]["time"]
    assert _finite(st)


@pytest.mark.parametrize("pid", PIDS)
def test_now_band_narrowest_with_full_cgm(engine, pid: str) -> None:
    """With a CGM the current band is tighter than with any finger-prick ladder level.
    (Across the sparse levels the width is not monotone; see the sensor-ladder report.)"""
    width = {lad: engine.state(pid, lad, [])["band"] for lad in ("full", "4", "2", "1", "0")}
    width = {k: v["hi"] - v["lo"] for k, v in width.items()}
    assert width["full"] < min(width[k] for k in ("4", "2", "1", "0")), width


def test_assimilate_reports_signed_width_changes(engine) -> None:
    """The current band narrows after a reading at the estimate; the 2-hour band change is reported
    SIGNED (it may widen) and narrowed_pct is its negation (no clipping)."""
    st = engine.state("lakshmi", "1", [])
    a = engine.assimilate("lakshmi", "1", [], st["estimate"])
    before = a["band_before"]["hi"] - a["band_before"]["lo"]
    after = a["band_after"]["hi"] - a["band_after"]["lo"]
    assert after < before
    wc = a["width_change"]
    assert wc["now"]["before"] == pytest.approx(before, abs=0.11) and wc["now"]["after"] == pytest.approx(after, abs=0.11)
    assert wc["now"]["signed_pct"] < 0
    assert wc["h120"]["horizon_min"] == 120
    assert a["narrowed_pct"] == pytest.approx(-wc["h120"]["signed_pct"], abs=0.051)
    fb, fa = st["forecast"]["traj"], a["state"]["forecast"]["traj"]
    assert wc["h120"]["before"] == pytest.approx(fb["q95"][23] - fb["q05"][23], abs=0.11)
    assert wc["h120"]["after"] == pytest.approx(fa["q95"][23] - fa["q05"][23], abs=0.11)
    assert a["state"]["freshness"]["label"] == "fresh"


@pytest.mark.parametrize("pid", PIDS)
def test_what_if_directions(engine, pid: str) -> None:
    """Less carbohydrate or a walk never raises the paired peak or P(>180)."""
    half = engine.what_if(pid, "2", [], MEAL, {"carb_scale": 0.5})
    assert half["delta_peak"] < 0
    assert half["delta_p_high"]["mean"] <= 0
    walk = engine.what_if(pid, "2", [], MEAL, {"walk_min": 20})
    assert walk["delta_peak"] <= 0
    assert walk["delta_p_high"]["mean"] <= 0
    assert half["delta_p_high"]["lo"] <= half["delta_p_high"]["mean"] <= half["delta_p_high"]["hi"]
    assert _finite(half)


def test_next_best_prick_contract(engine) -> None:
    nb = engine.next_best_prick("biman", "2", [])
    assert nb["time"] and nb["candidates"]
    assert nb["expected_gain_pct"] == max(c["gain_pct"] for c in nb["candidates"])
    assert 0 <= nb["expected_gain_pct"] <= 100


def test_outlook_is_labelled_projection(engine) -> None:
    o = engine.outlook_90d("ramesh", "2", [])
    assert o["label"] == "projection" and "Not a validated" in o["note"]
    assert len(o["days"]) == len(o["tir_current"]) == len(o["ehba1c_scenario"])


@pytest.mark.skipif(not HAS_PROCESSED, reason="needs data/processed to compare against")
def test_demo_data_fallback_matches_processed(engine) -> None:
    from nemotwins.twin.engine import DEMO_SERIES, TwinEngine

    if not DEMO_SERIES.exists():
        pytest.skip("run python -m nemotwins.twin.export_demo")
    demo = TwinEngine(data_source="demo")
    assert demo.data_source == "demo" and len(demo.cov) == 45
    a = demo.forecast("biman", "2", [], MEAL)
    b = engine.forecast("biman", "2", [], MEAL)
    assert a["traj"] == b["traj"] and a["p_high"] == b["p_high"]
