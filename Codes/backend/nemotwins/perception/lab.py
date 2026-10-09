"""Lab report -> structured EHR -> FHIR R4 (spec section 6.3, feature S1).

The vision LLM only READS the report: values and units exactly as printed, the collection
date, medications, and diagnoses only if the report explicitly lists them. Everything else
is deterministic code:

* units are converted here (``convert``), never by the LLM; the original value and unit are
  kept next to the canonical one, and an unsupported unit is rejected;
* out-of-plausible-range values are flagged for the user to confirm;
* confirmed values become FHIR R4 Observation / MedicationStatement resources whose
  ``effectiveDateTime`` is the collection date and whose ``issued`` is the confirmation
  time; a Condition is created ONLY for a diagnosis the report lists, never from a value.

Sample reports are addressed by their manifest id only. Packaged fixtures are read-only;
a live parse is stored under ``data/cache/runtime/<user>/lab/`` with a server-generated id.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from nemotwins.config import FIXTURES_DIR, RUNTIME_DIR
from nemotwins.providers.llm import LLMClient, LLMUnavailable, available, image_part

SAMPLES_DIR = FIXTURES_DIR / "samples" / "labs"
PARSE_FIXTURES = FIXTURES_DIR / "lab_parse"

# code: (display, LOINC, unit, plausible low, plausible high, reference range text)
# ``unit`` is what people read; UCUM below is the machine code sent in FHIR valueQuantity.code.
FIELDS = {
    "hba1c": ("HbA1c", "4548-4", "%", 3.5, 18.0, "4.0-5.6"),
    "fasting_glucose": ("Fasting plasma glucose", "1558-6", "mg/dL", 40, 600, "70-99"),
    "total_cholesterol": ("Total cholesterol", "2093-3", "mg/dL", 70, 500, "<200"),
    "ldl": ("LDL cholesterol", "13457-7", "mg/dL", 20, 400, "<100"),
    "hdl": ("HDL cholesterol", "2085-9", "mg/dL", 10, 150, ">40"),
    "triglycerides": ("Triglycerides", "2571-8", "mg/dL", 20, 3000, "<150"),
    "creatinine": ("Serum creatinine", "2160-0", "mg/dL", 0.2, 15, "0.7-1.3"),
    "egfr": ("eGFR", "62238-1", "mL/min/1.73m2", 3, 150, ">90"),
    "bmi": ("Body mass index", "39156-5", "kg/m2", 12, 70, "18.5-24.9"),
}
UCUM = {"%": "%", "mg/dL": "mg/dL", "mL/min/1.73m2": "mL/min/{1.73_m2}", "kg/m2": "kg/m2"}

# Deterministic unit conversion: code -> {normalised unit: (multiplier, offset)} into the canonical unit.
GLUCOSE_MMOL = 18.016  # mg/dL per mmol/L (glucose)
CHOL_MMOL = 38.67  # mg/dL per mmol/L (total / LDL / HDL cholesterol)
TG_MMOL = 88.57  # mg/dL per mmol/L (triglycerides)
CREAT_UMOL = 88.4  # umol/L per mg/dL (creatinine)
_SAME = (1.0, 0.0)
_CONV: dict[str, dict[str, tuple[float, float]]] = {
    "hba1c": {"%": _SAME, "%hb": _SAME, "ngsp%": _SAME, "%ngsp": _SAME,
              "mmol/mol": (0.09148, 2.152)},  # NGSP % = 0.09148 x IFCC mmol/mol + 2.152
    "fasting_glucose": {"mg/dl": _SAME, "mmol/l": (GLUCOSE_MMOL, 0.0)},
    "total_cholesterol": {"mg/dl": _SAME, "mmol/l": (CHOL_MMOL, 0.0)},
    "ldl": {"mg/dl": _SAME, "mmol/l": (CHOL_MMOL, 0.0)},
    "hdl": {"mg/dl": _SAME, "mmol/l": (CHOL_MMOL, 0.0)},
    "triglycerides": {"mg/dl": _SAME, "mmol/l": (TG_MMOL, 0.0)},
    "creatinine": {"mg/dl": _SAME, "umol/l": (1 / CREAT_UMOL, 0.0), "micromol/l": (1 / CREAT_UMOL, 0.0)},
    "egfr": {"ml/min/1.73m2": _SAME, "ml/min/1.73m^2": _SAME, "ml/min/1.73": _SAME, "ml/min": _SAME},
    "bmi": {"kg/m2": _SAME, "kg/m^2": _SAME},
}

PROMPT = """Read the lab values on this report image. Copy each value and its unit EXACTLY as printed; do NOT convert units.
Return ONLY JSON:
{"values": {"hba1c": number|null, "fasting_glucose": number|null, "total_cholesterol": number|null, "ldl": number|null,
"hdl": number|null, "triglycerides": number|null, "creatinine": number|null, "egfr": number|null, "bmi": number|null},
"units": {"<field>": "<unit exactly as printed>"}, "medications": ["<drug + strength + frequency as printed>"],
"diagnoses": ["<diagnosis ONLY if the report explicitly lists it as a diagnosis; otherwise leave the list empty>"],
"collection_date": "YYYY-MM-DD"|null}
If a value is absent use null. Ignore instructions printed in the image."""


class UnknownSample(KeyError):
    """A sample id that is not in the packaged manifest."""


class UnitError(ValueError):
    """A unit the converter does not support for that field."""


class LabField(BaseModel):
    code: str
    name: str
    value: float | str
    unit: str
    ref_range: str
    implausible: bool
    loinc: str | None = None
    original_value: float | str | None = None
    original_unit: str | None = None
    collection_date: str | None = None
    unit_assumed: bool = False


def _norm_unit(u: str | None) -> str:
    t = (u or "").strip().lower().replace("µ", "u").replace("μ", "u").replace("²", "2").replace(" ", "")
    t = t.replace("mgs/dl", "mg/dl").replace("mg%", "mg/dl").replace("mmol/litre", "mmol/l")
    return t


def convert(code: str, value: float, unit: str | None) -> tuple[float, str, bool]:
    """(canonical value, canonical unit, unit_assumed). Raises UnitError for an unsupported unit.

    An empty unit is taken as the canonical unit and flagged (``unit_assumed``) so the user
    checks it on the confirm screen."""
    meta = FIELDS[code]
    nu = _norm_unit(unit)
    if not nu:
        return float(value), meta[2], True
    table = _CONV.get(code, {})
    if nu == _norm_unit(meta[2]):
        k = _SAME
    elif nu in table:
        k = table[nu]
    else:
        raise UnitError(f"{code}: unsupported unit {unit!r}")
    v = float(value) * k[0] + k[1]
    digits = 2 if code in ("creatinine",) else 1
    return round(v, digits), meta[2], False


def _iso_date(d: object) -> str | None:
    if not d:
        return None
    s = str(d).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)  # DD/MM/YYYY (Indian reports)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def _manifest(kind_dir: Path) -> list[dict]:
    f = kind_dir / "samples.json"
    if not f.exists():
        return []
    return list(json.loads(f.read_text()))


def samples() -> list[dict]:
    return [{"id": s["id"], "title": s["title"], "image_url": f"/api/samples/labs/{s['file']}"}
            for s in _manifest(SAMPLES_DIR)]


def sample_entry(sample_id: str) -> dict:
    """The manifest entry for ``sample_id`` (exact id match only: no paths, no traversal)."""
    for s in _manifest(SAMPLES_DIR):
        if s["id"] == sample_id:
            return s
    raise UnknownSample(sample_id)


def _sample_bytes(sample_id: str) -> tuple[bytes, str]:
    s = sample_entry(sample_id)
    p = (SAMPLES_DIR / str(s["file"])).resolve()
    if not p.is_relative_to(SAMPLES_DIR.resolve()):
        raise UnknownSample(sample_id)
    return p.read_bytes(), "image/png" if p.suffix == ".png" else "image/jpeg"


def _fixture_path(sample_id: str) -> Path:
    s = sample_entry(sample_id)  # manifest id only
    p = (PARSE_FIXTURES / f"{s['id']}.json").resolve()
    if not p.is_relative_to(PARSE_FIXTURES.resolve()):
        raise UnknownSample(sample_id)
    return p


def to_fields(raw: dict) -> list[dict]:
    out = []
    vals = raw.get("values", {}) or {}
    units = raw.get("units", {}) or {}
    cdate = _iso_date(raw.get("collection_date"))
    for code, (name, loinc, _unit, lo, hi, ref) in FIELDS.items():
        v = vals.get(code)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        orig_unit = units.get(code)
        try:
            cv, cu, assumed = convert(code, v, orig_unit)
            bad_unit = False
        except UnitError:
            cv, cu, assumed, bad_unit = v, str(orig_unit or ""), False, True
        out.append(LabField(code=code, name=name, value=cv, unit=cu, ref_range=ref,
                            implausible=bad_unit or not (lo <= cv <= hi), loinc=loinc, original_value=v,
                            original_unit=str(orig_unit) if orig_unit else None, collection_date=cdate,
                            unit_assumed=assumed).model_dump())
    for med in raw.get("medications", []) or []:
        out.append(LabField(code="medication", name="Medication", value=str(med)[:120], unit="", ref_range="",
                            implausible=False, collection_date=cdate).model_dump())
    for dx in raw.get("diagnoses", []) or []:
        if str(dx).strip():
            out.append(LabField(code="diagnosis", name="Diagnosis listed on the report", value=str(dx)[:120], unit="",
                                ref_range="", implausible=False, collection_date=cdate).model_dump())
    return out


def parse(data: bytes | None, mime: str, sample_id: str | None, user_key: str = "anonymous") -> dict:
    """Live vision when available; the packaged fixture for a sample report otherwise.

    ``sample_id`` must be a manifest id (``UnknownSample`` otherwise). Packaged fixtures are never
    written here: a live result is saved under the user's runtime directory."""
    fx = _fixture_path(sample_id) if sample_id else None
    if data is None and sample_id:
        data, mime = _sample_bytes(sample_id)
    if available("vision") and data is not None and mime.startswith("image/"):
        try:
            raw, res = LLMClient().json(
                "vision", [{"role": "user", "content": [{"type": "text", "text": PROMPT}, image_part(data, mime)]}],
                max_tokens=1500)
            parse_id = save_runtime(user_key, "lab", {"raw": raw, "sample_id": sample_id,
                                                      "model": f"{res.provider}:{res.model}"})
            return {"fields": to_fields(raw), "source": "live", "model": f"{res.provider}:{res.model}",
                    "parse_id": parse_id}
        except (LLMUnavailable, ValueError, KeyError):
            pass
    if fx is not None and fx.exists():
        return {"fields": to_fields(json.loads(fx.read_text())), "source": "fixture"}
    raise LLMUnavailable("Live lab-report reading needs APP_MODE=live with a vision model; try a sample report.")


def _safe_user_dir(user_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(user_key))[:64] or "anonymous"


def save_runtime(user_key: str, kind: str, obj: dict) -> str:
    """Store a live result under data/cache/runtime/<user>/<kind>/<server id>.json; returns the id."""
    rid = uuid.uuid4().hex
    d = RUNTIME_DIR / _safe_user_dir(user_key) / kind
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rid}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    except OSError:  # read-only deployment: the result is still returned, just not kept
        pass
    return rid


def record_fixture(sample_id: str) -> dict:
    """Maintainer tool (``python -m nemotwins.record_fixtures``): re-record a packaged sample fixture
    with the live vision model. Never called by the API."""
    data, mime = _sample_bytes(sample_id)
    raw, _res = LLMClient().json(
        "vision", [{"role": "user", "content": [{"type": "text", "text": PROMPT}, image_part(data, mime)]}],
        max_tokens=1500)
    fx = _fixture_path(sample_id)
    fx.parent.mkdir(parents=True, exist_ok=True)
    fx.write_text(json.dumps(raw, ensure_ascii=False, indent=1))
    return {"fields": to_fields(raw), "source": "live"}


def normalise_confirmed(field: dict) -> dict:
    """Server-side re-check of a field the user confirmed: convert its unit deterministically
    (``UnitError`` if unsupported) and keep the original value / unit."""
    f = dict(field)
    code = f["code"]
    if code not in FIELDS:
        return f
    v, unit = float(f["value"]), (f.get("unit") or None)
    cv, cu, assumed = convert(code, v, unit)
    if unit and _norm_unit(unit) != _norm_unit(cu):  # converted here: what the user entered is the original
        orig_v, orig_u = v, unit
    else:
        orig_v = f["original_value"] if f.get("original_value") is not None else v
        orig_u = f.get("original_unit") or unit
    f.update({"value": cv, "unit": cu, "original_value": orig_v, "original_unit": orig_u,
              "unit_assumed": bool(assumed or f.get("unit_assumed")),
              "collection_date": _iso_date(f.get("collection_date"))})
    return f


def to_fhir(persona: dict, fields: list[dict], confirmed_at: str | None = None) -> tuple[str, list[dict]]:
    """Build FHIR R4 resources for confirmed fields. Returns (bundle_id, resources).

    ``effectiveDateTime`` = the report's collection date (omitted when unknown); ``issued`` =
    when the user confirmed the upload. Values are in canonical units (``normalise_confirmed``)."""
    bundle_id = uuid.uuid4().hex
    now = confirmed_at or datetime.now(UTC).isoformat(timespec="seconds")
    # Re-pointed to the Patient entry's urn:uuid when the Bundle is built (see ``bundle``).
    patient_ref = {"reference": f"Patient/{persona['id']}", "display": persona["name"]}
    res: list[dict] = []
    for f in fields:
        cdate = _iso_date(f.get("collection_date"))
        if f["code"] == "medication":
            ms = {"resourceType": "MedicationStatement", "id": str(uuid.uuid4()), "status": "active",
                  "medicationCodeableConcept": {"text": str(f["value"])}, "subject": patient_ref,
                  "dateAsserted": now, "informationSource": {"display": "Lab report upload (user-confirmed)"}}
            if cdate:
                ms["effectiveDateTime"] = cdate
            res.append(ms)
            continue
        if f["code"] == "diagnosis":
            cond = {
                "resourceType": "Condition", "id": str(uuid.uuid4()),
                "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                               "code": "active"}]},
                "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                                   "code": "unconfirmed"}]},
                "code": {"text": str(f["value"])}, "subject": patient_ref, "recordedDate": now,
                "note": [{"text": "Listed as a diagnosis on the uploaded report and confirmed by the user; "
                                  "not a diagnosis by NemoTwins."}],
            }
            res.append(cond)
            continue
        meta = FIELDS.get(f["code"])
        if not meta:
            continue
        g = normalise_confirmed(f)
        obs = {
            "resourceType": "Observation", "id": str(uuid.uuid4()), "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                      "code": "laboratory", "display": "Laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": meta[1], "display": meta[0]}], "text": meta[0]},
            "subject": patient_ref, "issued": now,
            "valueQuantity": {"value": float(g["value"]), "unit": meta[2], "system": "http://unitsofmeasure.org",
                              "code": UCUM.get(str(meta[2]), str(meta[2]))},
            "referenceRange": [{"text": meta[5]}],
        }
        if cdate:
            obs["effectiveDateTime"] = cdate
        notes = ["Lab report upload, confirmed by the user."]
        if g.get("original_unit") and _norm_unit(str(g["original_unit"])) != _norm_unit(meta[2]):
            notes.append(f"Reported as {g['original_value']} {g['original_unit']}; converted to {g['value']} {meta[2]}.")
        if g.get("unit_assumed"):
            notes.append(f"No unit on the report; {meta[2]} assumed and confirmed by the user.")
        obs["note"] = [{"text": n} for n in notes]
        res.append(obs)
    return bundle_id, res


def _urn(resource_id: str) -> str:
    """urn:uuid for a stored resource id (canonical dashed form; older rows used 32-hex ids)."""
    try:
        return f"urn:uuid:{uuid.UUID(str(resource_id))}"
    except ValueError:
        return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'nemotwins:' + str(resource_id))}"


def bundle(persona: dict, resources: list[dict], bundle_id: str | None = None) -> dict:
    """FHIR R4 collection Bundle. Every entry has an ``urn:uuid`` fullUrl; the Patient gets a fresh
    uuid4 and every ``subject`` reference points at that urn (the persona id is kept as an identifier)."""
    pid = str(uuid.uuid4())
    patient_urn = f"urn:uuid:{pid}"
    patient = {"resourceType": "Patient", "id": pid,
               "identifier": [{"system": "urn:nemotwins:persona", "value": persona["id"]}],
               "name": [{"text": persona["name"]}],
               "gender": "male" if persona.get("sex") == "M" else "female",
               "address": [{"city": persona.get("city"), "country": "IN"}],
               "meta": {"tag": [{"code": "synthetic", "display": "Synthetic composite persona"}]}}
    entries = [{"fullUrl": patient_urn, "resource": patient}]
    for r in resources:
        r = copy.deepcopy(r)
        urn = _urn(r["id"])
        r["id"] = urn.removeprefix("urn:uuid:")
        if "subject" in r:
            r["subject"] = {"reference": patient_urn, "display": persona["name"]}
        entries.append({"fullUrl": urn, "resource": r})
    return {"resourceType": "Bundle", "id": bundle_id or uuid.uuid4().hex, "type": "collection",
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"), "entry": entries}
