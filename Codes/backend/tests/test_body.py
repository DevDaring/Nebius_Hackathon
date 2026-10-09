"""3-D body view: per-organ flows of the physiology model (POST /api/twin/{pid}/body)."""

from __future__ import annotations

import pytest

PID = "biman"
MEAL = {"name": "rice and fish curry", "carbs": 75, "fat": 12, "protein": 20, "fibre": 3}
ORGAN_KEYS = {"stomach", "intestine", "gut_to_blood", "liver", "pancreas", "insulin", "insulin_uptake",
              "exercise_uptake", "unexplained"}


@pytest.fixture(autouse=True)
def _clean(client, auth):
    client.post(f"/api/twin/{PID}/reset", headers=auth)
    yield
    client.post(f"/api/twin/{PID}/reset", headers=auth)


def _body(client, auth, **payload):
    r = client.post(f"/api/twin/{PID}/body", json={"ladder": "2", **payload}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_body_requires_login(client) -> None:
    assert client.post(f"/api/twin/{PID}/body", json={"ladder": "2"}).status_code == 401


def test_body_shapes_labels_and_organs(client, auth) -> None:
    b = _body(client, auth)
    n = len(b["t"])
    assert n == 49  # replay now + 48 five-minute steps (4 h)
    assert b["t"][0] == b["replay_now"]
    assert {o["key"] for o in b["organs"]} == ORGAN_KEYS
    assert all(o["status"] == "simulated" for o in b["organs"])
    assert "not a measurement" in b["label_en"]
    assert b["validated_horizon_min"] == 120
    base = b["baseline"]
    assert set(base["fluxes"]) == ORGAN_KEYS
    for series in base["fluxes"].values():
        assert len(series["q10"]) == len(series["q50"]) == len(series["q90"]) == n
        assert all(lo <= mid <= hi for lo, mid, hi in zip(series["q10"], series["q50"], series["q90"], strict=True))
    for k in ("q05", "q50", "q95"):
        assert len(base["blood"][k]) == n
    assert b["scenario"] is None


def test_body_blood_matches_the_forecast_chart(client, auth) -> None:
    b = _body(client, auth, meal=MEAL)
    fc = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth).json()
    assert b["baseline"]["forecast_id"] == fc["forecast_id"]
    assert b["baseline"]["blood"]["q50"][1:] == fc["traj"]["q50"]


def test_meal_fills_the_stomach_then_it_drains(client, auth) -> None:
    st = _body(client, auth, meal=MEAL)["baseline"]["fluxes"]["stomach"]["q50"]
    peak = max(st)
    assert peak > 40  # most of the 75 g lands in the stomach
    assert st[-1] < peak / 3  # and has mostly moved on after 4 h
    gut = _body(client, auth, meal=MEAL)["baseline"]["fluxes"]["gut_to_blood"]["q50"]
    assert max(gut) > gut[0]


def test_walk_scenario_lights_up_the_muscles_and_lowers_the_peak(client, auth) -> None:
    b = _body(client, auth, meal=MEAL, scenario={"walk_min": 15, "walk_after_min": 15, "label": "15-min walk"})
    assert b["scenario_label"] == "15-min walk"
    base, walk = b["baseline"], b["scenario"]
    assert max(walk["fluxes"]["exercise_uptake"]["q50"]) > 2 * max(base["fluxes"]["exercise_uptake"]["q50"])
    assert max(walk["blood"]["q50"]) < max(base["blood"]["q50"])
    # same past: identical starting point
    assert walk["blood"]["q50"][0] == base["blood"]["q50"][0]
    assert walk["fluxes"]["stomach"]["q50"] == base["fluxes"]["stomach"]["q50"]


def test_scenario_without_meal_is_rejected(client, auth) -> None:
    r = client.post(f"/api/twin/{PID}/body", json={"ladder": "2", "scenario": {"walk_min": 15}}, headers=auth)
    assert r.status_code == 422


def test_body_forecast_is_owned_by_the_caller(client, auth, auth_b) -> None:
    fid = _body(client, auth)["baseline"]["forecast_id"]
    assert client.get(f"/api/twin/{PID}/receipt/{fid}", headers=auth).status_code == 200
    assert client.get(f"/api/twin/{PID}/receipt/{fid}", headers=auth_b).status_code == 404
