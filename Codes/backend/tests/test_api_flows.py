"""API contract end to end: replay clock, timestamped readings, the shared safety policy, ownership,
lab revisions, evidence receipts, clinician queue, ops (readiness, rate limits, upload bounds,
manifest-only samples). Runs against the nemotwins_test database in demo mode."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
import pytest

from nemotwins.agent import safety

PID = "ramesh"
LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
MEAL = {"name": "rice and dal", "carbs": 55.5, "fibre": 3.0, "protein": 12.0, "fat": 6.0}
STATUSES = {"measured", "estimated", "simulated", "validated", "exploratory", "not_validated"}


def _reset(client, headers, pid: str = PID) -> None:
    assert client.post(f"/api/twin/{pid}/reset", params={"labs": 1}, headers=headers).json() == {"ok": True}


@pytest.fixture(autouse=True)
def _clean(client, auth, auth_b):
    from nemotwins.api.main import RATE

    RATE.reset()
    for h in (auth, auth_b):
        for pid in (PID, "lakshmi"):
            _reset(client, h, pid)
    yield
    for h in (auth, auth_b):
        for pid in (PID, "lakshmi"):
            _reset(client, h, pid)


def _state(client, auth, pid: str = PID, ladder: str = "2") -> dict:
    r = client.get(f"/api/twin/{pid}/state", params={"ladder": ladder}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _assim(client, auth, value: float, unit: str = "mg/dL", pid: str = PID, lang: str = "en-US", **extra):
    return client.post(f"/api/twin/{pid}/assimilate", params={"lang": lang},
                       json={"ladder": "2", "value": value, "unit": unit, **extra}, headers=auth)


def _shift(iso: str, minutes: float) -> str:
    return (datetime.fromisoformat(iso) + timedelta(minutes=minutes)).isoformat(timespec="minutes")


# ----------------------------------------------------------------------------- ops
def test_ready_reports_db_and_model(client, engine) -> None:
    engine.warm()
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json() == {"ready": True, "db": True, "model": True}


def test_rate_limit_returns_429_with_retry_after(client, auth, monkeypatch) -> None:
    from nemotwins.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_chat_per_min", 2)
    body = {"patient_id": PID, "text": "what is time in range", "lang": "en-US", "ladder": "2"}
    assert client.post("/api/agent/chat", json=body, headers=auth).status_code == 200
    assert client.post("/api/agent/chat", json=body, headers=auth).status_code == 200
    r = client.post("/api/agent/chat", json=body, headers=auth)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


@pytest.mark.parametrize("path,field,setting", [("/api/meal/photo", "image", "max_image_bytes"),
                                                ("/api/lab/parse", "file", "max_image_bytes"),
                                                ("/api/speech/stt", "audio", "max_audio_bytes")])
def test_uploads_have_a_hard_byte_bound(client, auth, monkeypatch, path, field, setting) -> None:
    from nemotwins.api.main import BodyLimitMiddleware
    from nemotwins.config import get_settings

    monkeypatch.setattr(get_settings(), setting, 1000)
    monkeypatch.setattr(BodyLimitMiddleware, "SLACK", 512)
    big = b"\xff\xd8" + b"0" * 5000
    r = client.post(path, files={field: ("x.jpg", big, "image/jpeg")}, headers=auth)
    assert r.status_code == 413, r.text


BAD_IDS = ["../lab_parse/lab_biman", "/etc/passwd", "../../nemotwins/api/main", "lab_biman.json",
           "LAB_BIMAN", "lab_biman/../lab_ramesh", "%2e%2e%2fsecret", "bengali_fish_thali/../../x", ""]


@pytest.mark.parametrize("sid", BAD_IDS)
def test_sample_ids_are_manifest_only(client, auth, sid: str) -> None:
    if not sid:
        return
    assert client.post("/api/lab/parse", data={"sample_id": sid}, headers=auth).status_code == 404
    assert client.post("/api/meal/photo", data={"sample_id": sid}, headers=auth).status_code == 404


def test_sample_file_route_serves_manifest_files_only(client) -> None:
    assert client.get("/api/samples/labs/samples.json").status_code == 404
    assert client.get("/api/samples/meals/ATTRIBUTION.md").status_code == 404
    assert client.get("/api/samples/labs/lab_biman.png").status_code == 200


def _sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_live_sample_parse_never_alters_packaged_fixtures(client, auth, monkeypatch, tmp_path) -> None:
    from nemotwins.perception import lab as LAB
    from nemotwins.perception import meal as MEAL
    from nemotwins.providers.llm import LLMResult

    class FakeLLM:
        def json(self, role, messages, **kw):
            return ({"values": {"hba1c": 9.9}, "units": {"hba1c": "%"}, "collection_date": "2026-10-01"},
                    LLMResult("", [], "fake", "vision", 1, {}))

    lab_fx = LAB.PARSE_FIXTURES / "lab_biman.json"
    meal_fx = MEAL.PARSE_FIXTURES / "bengali_fish_thali.json"
    before = (_sha(lab_fx), _sha(meal_fx))
    monkeypatch.setattr(LAB, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(LAB, "available", lambda role: True)
    monkeypatch.setattr(LAB, "LLMClient", FakeLLM)
    monkeypatch.setattr(MEAL, "available", lambda role: True)
    from nemotwins.api import main as M

    monkeypatch.setattr(M, "_vision_status", lambda: {"enabled": True, "model": "fake/vision", "nvidia": False,
                                                       "provider": "nebius_tokenfactory", "reason": None})
    monkeypatch.setattr(MEAL, "detect", lambda image, mime: ([{"name": "roti", "portion": 2, "unit": "piece"}],
                                                             "fake:vision"))
    r = client.post("/api/lab/parse", data={"sample_id": "lab_biman"}, headers=auth)
    assert r.status_code == 200 and r.json()["source"] == "live" and r.json()["parse_id"]
    m = client.post("/api/meal/photo", data={"sample_id": "bengali_fish_thali"}, headers=auth)
    assert m.status_code == 200 and m.json()["source"] == "live"
    up = client.post("/api/meal/photo", files={"image": ("x.jpg", b"\xff\xd8 not really", "image/jpeg")}, headers=auth)
    assert up.status_code == 200
    assert (_sha(lab_fx), _sha(meal_fx)) == before  # packaged fixtures untouched
    saved = sorted(p.relative_to(tmp_path).parts[1] for p in tmp_path.rglob("*.json"))
    assert saved == ["lab", "meal", "meal"]  # runtime results, per user, server-generated ids


# ----------------------------------------------------------------------------- replay clock
def test_replay_clock_advance_persist_cap_and_reset(client, auth) -> None:
    s0 = _state(client, auth)
    assert s0["replay"] == {"now": s0["now"], "day": 7, "offset_min": 0, "max_offset_min": 720,
                            "label_en": "Replay · day 7 · 19:30", "mode": "replay"}
    r = client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 150}, headers=auth)
    assert r.status_code == 200
    a = r.json()
    assert a["replay"]["offset_min"] == 150 and a["replay"]["label_en"] == "Replay · day 7 · 22:00"
    assert a["now"] == _shift(s0["now"], 150)
    # the ladder's scheduled 22:00 finger-prick inside the window was assimilated at its own time
    assert a["last_observation"]["t"] == a["now"] and a["last_observation"]["source"] == "dataset"
    assert _state(client, auth)["replay"]["offset_min"] == 150  # persisted per user + persona
    assert _state(client, auth, "lakshmi")["replay"]["offset_min"] == 0
    for _ in range(3):
        last = client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 240}, headers=auth).json()
    assert last["replay"]["offset_min"] == 720 and last["replay"]["label_en"] == "Replay · day 8 · 07:30"
    _reset(client, auth)
    assert _state(client, auth)["replay"]["offset_min"] == 0


def test_advancing_is_path_independent(client, auth) -> None:
    for _ in range(2):
        client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 60}, headers=auth)
    two_steps = _state(client, auth)
    _reset(client, auth)
    one_step = client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 120}, headers=auth).json()
    for k in ("now", "estimate", "band", "freshness", "last_observation"):
        assert two_steps[k] == one_step[k], k
    assert two_steps["forecast"]["traj"] == one_step["forecast"]["traj"]


def test_same_timestamped_sequence_gives_the_same_state(engine) -> None:
    """Determinism: the state depends only on the timestamped inputs, not on the order they arrived."""
    r1 = {"kind": "reading", "value": 160.0, "t_min": 40.0, "source": "manual"}
    r2 = {"kind": "reading", "value": 120.0, "t_min": 75.0, "source": "manual"}
    m1 = {"kind": "meal", "name": "dal rice", "carbs": 60.0, "t_min": 50.0, "source": "chat"}
    engine.clear_cache()
    a = engine.state(PID, "2", [r1, m1, r2], offset=90)
    engine.clear_cache()
    b = engine.state(PID, "2", [r2, r1, m1], offset=90)  # late / out-of-order arrival
    for x in (a, b):
        x["forecast"].pop("forecast_id")  # a fresh id per computation; every number is identical
    assert a == b
    c = engine.state(PID, "2", [r1, m1], offset=90)
    assert c["estimate"] != a["estimate"]


def test_an_old_observation_cannot_become_a_fresh_reading(client, auth) -> None:
    now = _state(client, auth)["now"]
    r = _assim(client, auth, 150, observed_at=_shift(now, -45))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "stale_observation"
    r = _assim(client, auth, 150, observed_at=_shift(now, -20))
    assert r.status_code == 200, r.text
    st = r.json()["state"]
    assert st["last_observation"]["t"] == _shift(now, -20)  # kept at its own time
    assert st["freshness"]["hours_since_reading"] == pytest.approx(20 / 60, abs=0.01)
    obs = r.json()["observation"]
    assert obs["t_min"] == -20.0 and obs["source"] == "manual" and obs["received_at"]
    # a timezone-aware time is converted (19:10 IST == 13:40 UTC)
    aware = (datetime.fromisoformat(_shift(now, -5)) - timedelta(hours=5, minutes=30)).isoformat() + "+00:00"
    assert _assim(client, auth, 151, observed_at=aware).json()["observation"]["t_min"] == -5.0


def test_mmol_conversion_and_idempotency(client, auth) -> None:
    r1 = _assim(client, auth, 7.0, "mmol/L", idempotency_key="k-123").json()
    assert r1["observation"]["value_mg_dl"] == 126.1 and r1["observation"]["original_value"] == 7.0
    assert r1["duplicate"] is False
    n = len([x for x in r1["state"]["history"]["readings"] if x.get("source") == "manual"])
    r2 = _assim(client, auth, 7.0, "mmol/L", idempotency_key="k-123").json()
    assert r2["duplicate"] is True
    assert r2["band_after"] == r1["band_after"] and r2["width_change"] == r1["width_change"]
    st = _state(client, auth)
    assert len([x for x in st["history"]["readings"] if x.get("source") == "manual"]) == n == 1


# ----------------------------------------------------------------------------- shared safety (P0)
CHAT = {"en-US": "my sugar is {v}", "es-ES": "mi glucosa es {v}", "fr-FR": "ma glycémie est de {v}",
        "de-DE": "mein Blutzucker ist {v}", "it-IT": "la mia glicemia è {v}", "ja-JP": "血糖値は{v}でした"}


@pytest.mark.parametrize("value,level,emergency", [(45, "very_low", True), (62, "low", False), (150, "ok", False),
                                                   (270, "high", False), (350, "very_high", False)])
def test_identical_readings_get_identical_safety_on_every_entry_path(client, auth, value, level, emergency) -> None:
    for lang in LANGS:
        _reset(client, auth)
        expected = safety.assess_reading(value, None, lang)
        assert expected["level"] == level and expected["emergency"] is emergency
        m = _assim(client, auth, value, lang=lang)
        assert m.status_code == 200, m.text  # extreme values are stored ...
        ms = m.json()["safety"]  # ... but the safety result comes first
        assert {k: ms[k] for k in ("level", "emergency", "title", "message", "actions")} == \
               {k: expected[k] for k in ("level", "emergency", "title", "message", "actions")}
        assert m.json()["state"]["last_observation"]["value"] == float(value)
        c = client.post("/api/agent/chat", json={"patient_id": PID, "text": CHAT[lang].format(v=value), "lang": lang,
                                                 "ladder": "2"}, headers=auth).json()
        if level != "ok":
            assert c["reply"].startswith(expected["message"]), (lang, c["reply"])
            assert c["safety"]["emergency"] is emergency
            if not emergency:
                assert c["safety"]["level"] == level
        assert c["pending_action"]["kind"] == "log_reading" and c["pending_action"]["payload"]["value"] == float(value)
        conf = client.post("/api/agent/confirm", json={"action_id": c["pending_action"]["id"], "confirm": True,
                                                       "lang": lang}, headers=auth).json()
        assert conf["safety"]["level"] == level and conf["safety"]["emergency"] is emergency
        if level != "ok":
            assert conf["reply"].startswith(expected["message"])


def test_mmol_entry_gets_the_same_safety_as_mg_dl(client, auth) -> None:
    a = _assim(client, auth, 3.0, "mmol/L").json()["safety"]
    b = safety.assess_reading(54.0, None, "en-US")
    assert a["level"] == b["level"] == "low" and a["message"] == safety.assess_reading(54.048, None, "en-US")["message"]


# ----------------------------------------------------------------------------- reveal
def test_reveal_watch_the_twin_learn(client, auth) -> None:
    client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 30}, headers=auth)
    st = _state(client, auth)
    r = client.post(f"/api/twin/{PID}/reveal", json={"ladder": "2", "assimilate": False}, headers=auth).json()
    assert r["reference"]["source_en"] == "Dataset reference CGM — hidden from the twin until revealed"
    assert r["reference"]["t"] <= st["now"] and r["after"] is None
    assert r["before"]["estimate"] == st["estimate"] and r["before"]["band"] == st["band"]
    assert r["before"]["forecast_peak"] == st["forecast"]["peak"] and r["before"]["p_high"]["validated"] is True
    assert _state(client, auth)["estimate"] == st["estimate"]  # revealing alone changes nothing
    a = client.post(f"/api/twin/{PID}/reveal", json={"ladder": "2", "assimilate": True}, headers=auth).json()
    after = a["after"]
    assert after["state"]["last_observation"]["source"] == "replay"
    assert after["state"]["last_observation"]["value"] == a["reference"]["value"]
    assert after["safety"]["level"] == safety.reading_level(a["reference"]["value"])
    assert after["width_change"]["h120"]["horizon_min"] == 120
    again = client.post(f"/api/twin/{PID}/reveal", json={"ladder": "2", "assimilate": True}, headers=auth).json()
    assert again["after"]["duplicate"] is True


# ----------------------------------------------------------------------------- forecast, receipt, ownership
def test_forecast_reliability_comes_from_the_report(client, auth) -> None:
    from nemotwins.twin.engine import reliability

    fc = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth).json()
    ph = fc["p_high"]
    assert ph["validated"] is True and "lo" not in ph and "hi" not in ph
    assert ph["reliability"] == reliability(ph["p"], "2", "high")
    rel = ph["reliability"]
    assert rel["source"] == "reports/calibration_curve.json" and rel["n"] > 0
    assert rel["ci_lo"] <= rel["observed"] <= rel["ci_hi"]
    if not rel.get("nearest_bin"):
        assert rel["pred_lo"] <= ph["p"] <= rel["pred_hi"]
    assert fc["p_low"]["validated"] is False and "lo" not in fc["p_low"]
    prov = fc["provenance"]
    assert prov["inputs_revision"] == 0 and prov["prior_inputs"]["hba1c"]["source"] == "persona EHR"
    assert prov["replay_now"] == fc["origin"] and prov["model_version"] and prov["hybrid_trained_on"]


def test_particle_count_does_not_change_the_reliability_evidence(engine, monkeypatch) -> None:
    from nemotwins.twin import engine as ENG

    a = engine.forecast(PID, "2", [], MEAL)
    monkeypatch.setattr(ENG, "M_FC", 800)
    engine.clear_cache()
    b = engine.forecast(PID, "2", [], MEAL)
    engine.clear_cache()
    for fc in (a, b):
        assert set(fc["p_high"]) == {"p", "freq_text", "validated", "reliability"}
        assert fc["p_high"]["reliability"] == ENG.reliability(fc["p_high"]["p"], "2", "high")
    if ENG.reliability(a["p_high"]["p"], "2")["pred_lo"] == ENG.reliability(b["p_high"]["p"], "2")["pred_lo"]:
        assert a["p_high"]["reliability"] == b["p_high"]["reliability"]  # same bin -> identical interval


def test_receipt_json_markdown_and_localisation(client, auth) -> None:
    fc = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth).json()
    r = client.get(f"/api/twin/{PID}/receipt/{fc['forecast_id']}", params={"lang": "fr-FR"}, headers=auth)
    assert r.status_code == 200
    rc = r.json()
    assert rc["forecast_id"] == fc["forecast_id"] and rc["persona_id"] == PID and rc["replay_now"] == fc["origin"]
    by = {c["key"]: c for c in rc["claims"]}
    assert by["p_high"]["status"] == "validated" and by["p_high"]["value"] == fc["p_high"]["p"]
    assert by["p_high_reliability"]["source"] == {"kind": "report",
                                                  "ref": "reports/calibration_curve.json#levels.2.high"}
    assert by["p_low"]["status"] == "not_validated" and by["trajectory_240"]["status"] == "exploratory"
    assert by["meal_carbs"]["value"] == 55.5 and by["last_reading"]["status"] == "measured"
    assert by["forecast_peak"]["value"] == fc["peak"]["value"] and by["next_check"]["status"] == "exploratory"
    assert all(c["status"] in STATUSES and c["source"]["kind"] in {"tool", "report", "dataset", "user"}
               for c in rc["claims"])
    assert by["p_high"]["label"] != by["p_high"]["label_en"]  # localised label, English kept
    assert {"inputs", "model", "tool_calls", "generated_at"} <= set(rc)
    md = client.get(f"/api/twin/{PID}/receipt/{fc['forecast_id']}", params={"format": "md"}, headers=auth)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"] and md.text.startswith("# Evidence receipt")
    assert "not validated" in md.text and "exploratory" in md.text


def test_forecasts_are_owned_by_user_and_persona(client, auth, auth_b) -> None:
    fc = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth).json()
    fid = fc["forecast_id"]
    assert client.get(f"/api/twin/{PID}/explain/{fid}", headers=auth).status_code == 200
    assert client.get(f"/api/twin/{PID}/receipt/{fid}", headers=auth).status_code == 200
    # another user, even for the same persona and identical inputs
    assert client.get(f"/api/twin/{PID}/explain/{fid}", headers=auth_b).status_code == 404
    assert client.get(f"/api/twin/{PID}/receipt/{fid}", headers=auth_b).status_code == 404
    # the same user through a mismatched persona
    assert client.get(f"/api/twin/lakshmi/explain/{fid}", headers=auth).status_code == 404
    assert client.get(f"/api/twin/lakshmi/receipt/{fid}", headers=auth).status_code == 404
    # B legitimately creates the same forecast: B may now read it too (authorised access works)
    fb = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth_b).json()
    assert client.get(f"/api/twin/{PID}/receipt/{fb['forecast_id']}", headers=auth_b).status_code == 200


def test_labs_and_fhir_are_per_user(client, auth, auth_b) -> None:
    fields = [{"code": "hba1c", "name": "HbA1c", "value": 63, "unit": "mmol/mol", "ref_range": "",
               "implausible": False, "loinc": "4548-4", "collection_date": "2026-09-28"},
              {"code": "ldl", "name": "LDL", "value": 3.2, "unit": "mmol/L", "ref_range": "", "implausible": False,
               "collection_date": "2026-09-28"}]
    r = client.post("/api/lab/confirm", json={"patient_id": PID, "fields": fields}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resource_count"] == 2 and body["revision"]["revision"] == 1
    assert body["revision"]["fields"]["hba1c"]["value"] == 7.9 and set(body["revision"]["fields"]) == {"hba1c"}
    a_bundle = client.get(f"/api/fhir/{PID}/bundle", headers=auth).json()
    b_bundle = client.get(f"/api/fhir/{PID}/bundle", headers=auth_b).json()
    a_obs = [e["resource"] for e in a_bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    assert len(a_obs) == 2 and all(o["effectiveDateTime"] == "2026-09-28" for o in a_obs)
    ldl = next(o for o in a_obs if o["code"]["coding"][0]["code"] == "13457-7")
    assert ldl["valueQuantity"] == {"value": 123.7, "unit": "mg/dL", "system": "http://unitsofmeasure.org",
                                    "code": "mg/dL"}
    assert [e["resource"]["resourceType"] for e in b_bundle["entry"]] == ["Patient"]  # B sees nothing of A's
    assert client.get(f"/api/patients/{PID}", headers=auth_b).json()["ehr"]["provenance"]["hba1c"]["revision"] == 0
    bad = [{**fields[0], "unit": "g/L"}]
    assert client.post("/api/lab/confirm", json={"patient_id": PID, "fields": bad}, headers=auth).status_code == 422


def test_confirmed_lab_revision_repersonalises_the_twin(client, auth, auth_b) -> None:
    d0 = client.get(f"/api/patients/{PID}", headers=auth).json()
    assert d0["ehr"]["provenance"]["hba1c"] == {"value": 7.4, "source": "persona EHR", "collection_date": None,
                                                "revision": 0}
    f0 = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2"}, headers=auth).json()
    fields = [{"code": "hba1c", "name": "HbA1c", "value": 8.6, "unit": "%", "ref_range": "", "implausible": False,
               "collection_date": "2026-09-28"}]
    assert client.post("/api/lab/confirm", json={"patient_id": PID, "fields": fields}, headers=auth).status_code == 200
    d1 = client.get(f"/api/patients/{PID}", headers=auth).json()
    p = d1["ehr"]["provenance"]["hba1c"]
    assert p["value"] == 8.6 and p["source"] == "lab upload (confirmed)" and p["collection_date"] == "2026-09-28"
    assert p["revision"] == 1 and len(d1["ehr"]["revisions"]) == 1 and d1["hba1c"] == 8.6
    f1 = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2"}, headers=auth).json()
    pi = f1["provenance"]["prior_inputs"]["hba1c"]
    assert f1["provenance"]["inputs_revision"] == 1 and pi["value"] == 8.6 and pi["date"] == "2026-09-28"
    assert f1["forecast_id"] != f0["forecast_id"]  # recomputed (no forced direction or magnitude)
    fb = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2"}, headers=auth_b).json()
    assert fb["provenance"]["inputs_revision"] == 0 and fb["traj"] == f0["traj"]  # other users unaffected
    rc = client.get(f"/api/twin/{PID}/receipt/{f1['forecast_id']}", headers=auth).json()
    hb = next(c for c in rc["claims"] if c["key"] == "hba1c")
    assert hb["source"]["kind"] == "user" and "revision 1" in hb["source"]["ref"]


# ----------------------------------------------------------------------------- what-if: two possible futures
def test_two_futures_share_a_pinned_baseline(client, auth) -> None:
    fc = client.post(f"/api/twin/{PID}/forecast", json={"ladder": "2", "meal": MEAL}, headers=auth).json()
    w1 = client.post(f"/api/twin/{PID}/what_if", json={"ladder": "2", "base_meal": MEAL,
                                                       "scenario": {"walk_min": 15}}, headers=auth).json()
    w2 = client.post(f"/api/twin/{PID}/what_if", json={"ladder": "2", "base_meal": MEAL,
                                                       "scenario": {"carb_scale": 0.5}}, headers=auth).json()
    assert w1["baseline"]["forecast_id"] == w2["baseline"]["forecast_id"] == fc["forecast_id"]
    assert w1["baseline"]["traj"] == w2["baseline"]["traj"] == fc["traj"]
    for w in (w1, w2):
        assert w["label_en"] == "Model simulation — not a proven effect" and w["baseline_pinned"] is True
        assert any("not a proven causal effect" in a for a in w["assumptions_en"])
        assert w["delta_p_high"]["interval_kind"] == "simulation_variability"
    assert any("Walk: 15 min" in a for a in w1["assumptions_en"])
    assert any("x0.5" in a for a in w2["assumptions_en"])
    rc = client.get(f"/api/twin/{PID}/receipt/{w1['scenario']['forecast_id']}", headers=auth).json()
    assert next(c for c in rc["claims"] if c["key"] == "scenario_peak")["status"] == "simulated"
    assert client.get(f"/api/twin/{PID}/explain/{w1['scenario']['forecast_id']}", headers=auth).status_code == 404


# ----------------------------------------------------------------------------- agent claims and confirmation
def test_chat_reply_carries_claims_bound_to_tool_fields(client, auth) -> None:
    r = client.post("/api/agent/chat", json={"patient_id": PID, "text": "how am i now", "lang": "en-US",
                                             "ladder": "2"}, headers=auth).json()
    st = _state(client, auth)
    fields = {c["field"]: c for c in r["claims"]}
    assert fields["get_state.estimate"]["value"] == st["estimate"]
    assert fields["get_state.estimate"]["rendered"] in r["reply"]
    assert fields["get_state.p_high_2h.p"]["value"] == st["forecast"]["p_high"]["p"]
    assert r["pending_action"] is None


def test_meal_pending_action_confirm_via_api(client, auth) -> None:
    import uuid

    from nemotwins.db import PendingAction, User, session

    with session() as s:
        uid = s.query(User).filter(User.username == "TestUser").one().id
        aid = uuid.uuid4().hex
        s.add(PendingAction(id=aid, user_id=uid, persona_id=PID, kind="log_meal", lang="en-US", ladder="2",
                            payload={"name": "2 roti and toor dal", "carbs": 48.0, "t_min": 0.0},
                            summary_en="Log 2 roti and toor dal"))
    c = client.post("/api/agent/confirm", json={"action_id": aid, "confirm": True}, headers=auth).json()
    assert c["intent"] == "log_meal" and "2 roti and toor dal" in c["reply"] and c["grounding"]["passed"]
    meals = [m for m in _state(client, auth)["history"]["meals"] if m.get("source") == "user"]
    assert meals and meals[-1]["carbs"] == 48.0


def test_cancelled_action_does_not_mutate(client, auth) -> None:
    c = client.post("/api/agent/chat", json={"patient_id": PID, "text": "my sugar is 152", "lang": "en-US",
                                             "ladder": "2"}, headers=auth).json()
    before = _state(client, auth)
    x = client.post("/api/agent/confirm", json={"action_id": c["pending_action"]["id"], "confirm": False},
                    headers=auth).json()
    assert x["reply"] == "Okay, I have not added it."
    assert _state(client, auth)["estimate"] == before["estimate"]


# ----------------------------------------------------------------------------- clinician
def test_brief_uses_user_events_clock_and_a_real_walk_simulation(client, auth) -> None:
    client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 60}, headers=auth)
    _assim(client, auth, 210)
    st = _state(client, auth)
    br = client.get(f"/api/doctor/brief/{PID}", headers=auth).json()
    op = br["operational"]
    assert op["estimate"] == st["estimate"] and op["band"] == st["band"]
    assert op["last_reading"]["value"] == 210.0 and op["last_reading_age_h"] == 0.0 and op["data_gap"] is False
    assert br["replay"]["offset_min"] == 60
    d = br["suggestion_details"][0]
    assert d["kind"] == "walk_what_if" and d["scenario"]["walk_min"] == 15.0
    assert d["label_en"] == "Model simulation — not a proven effect"
    text = next(s for s in br["suggestions"] if s.startswith("Twin simulation"))
    assert (f"{d['delta_peak']:+.0f} mg/dL" in text) or ("too little to call" in text)
    s = next(x for x in client.get("/api/doctor/panel", headers=auth).json() if x["id"] == PID)
    assert s["tar_7d_reference"]["label_en"] == "Historical time above 180 (dataset reference CGM, last 7 days)"
    assert s["risk_7d"] == s["tar_7d_reference"]["value"] and s["operational"]["estimate"] == st["estimate"]


def test_review_queue_reasons_and_review_state(client, auth, auth_b) -> None:
    q = client.get("/api/doctor/queue", headers=auth).json()
    assert {x["pid"] for x in q} == {"biman", "lakshmi", "ramesh"}
    for x in q:
        assert {r["kind"] for r in x["reasons"]} <= {"missing_data", "concerning_observation", "model_risk"}
        assert x["review"]["status"] in ("unreviewed", "reviewed", "follow_up") and "freshness" in x
    _assim(client, auth, 62)
    q = {x["pid"]: x for x in client.get("/api/doctor/queue", headers=auth).json()}
    assert any(r["kind"] == "concerning_observation" and "62" in r["detail_en"] for r in q[PID]["reasons"])
    assert q[PID]["reasons"][0]["kind"] == "concerning_observation"
    assert not any(r["kind"] == "missing_data" for r in q[PID]["reasons"])  # fresh reading
    r = client.post(f"/api/doctor/review/{PID}", json={"status": "follow_up", "note": "call tomorrow"}, headers=auth)
    assert r.status_code == 200
    q = {x["pid"]: x for x in client.get("/api/doctor/queue", headers=auth).json()}
    assert q[PID]["review"]["status"] == "follow_up" and q[PID]["review"]["by"] == "TestUser"
    qb = {x["pid"]: x for x in client.get("/api/doctor/queue", headers=auth_b).json()}
    assert qb[PID]["review"]["status"] in ("unreviewed", "reviewed", "follow_up") and qb[PID]["review"]["by"] != "TestUser"
    assert client.post(f"/api/doctor/review/{PID}", json={"status": "done"}, headers=auth).status_code == 422
    client.post(f"/api/doctor/review/{PID}", json={"status": "unreviewed", "note": ""}, headers=auth)


def _masked(engine):
    """A copy of the engine whose persona records have NO reference CGM at all."""
    from nemotwins.twin import engine as ENG

    m = copy.copy(engine)
    m._base = {}
    for (pid, lad, ck), b in list(engine._base.items()):
        if ck:
            continue
        tl = dataclasses.replace(b.tl, cgm=np.full_like(b.tl.cgm, np.nan), cgm_native=np.zeros_like(b.tl.cgm_native))
        m._base[(pid, lad, ck)] = dataclasses.replace(b, tl=tl)
    m._cache, m._live_cache = ENG._LRU(64), ENG._LRU(64)
    m._forecasts = OrderedDict()
    return m


def test_operational_dashboard_survives_without_reference_cgm(client, auth, engine, monkeypatch) -> None:
    import nemotwins.api.main as API

    engine.warm()
    normal = {x["id"]: x for x in client.get("/api/doctor/panel", headers=auth).json()}
    monkeypatch.setattr(API, "get_engine", lambda: _masked(engine))
    panel = client.get("/api/doctor/panel", headers=auth)
    assert panel.status_code == 200
    for x in panel.json():
        assert x["tar_7d_reference"]["value"] is None and x["risk_7d"] is None and x["tir_7d"] is None
        for k in ("estimate", "band", "last_reading_age_h", "p_high_2h", "data_gap"):
            assert x["operational"][k] == normal[x["id"]]["operational"][k], (x["id"], k)
    br = client.get(f"/api/doctor/brief/{PID}", headers=auth)
    assert br.status_code == 200 and br.json()["tir_7d"] is None
    assert br.json()["operational"]["estimate"] == normal[PID]["operational"]["estimate"]
    assert client.get("/api/doctor/queue", headers=auth).status_code == 200
    assert client.get(f"/api/twin/{PID}/state", headers=auth).status_code == 200


def test_clinician_role_is_required(client, auth, monkeypatch) -> None:
    from nemotwins.db import User, session

    with session() as s:
        u = s.query(User).filter(User.username == "Reviewer2").one()
        old = u.roles
        u.roles = "patient"
    try:
        tok = client.post("/api/auth/login", json={"username": "Reviewer2", "password": "Reviewer22"}).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        assert client.get("/api/doctor/queue", headers=h).status_code == 403
        assert client.get("/api/doctor/panel", headers=h).status_code == 403
    finally:
        with session() as s:
            s.query(User).filter(User.username == "Reviewer2").one().roles = old
