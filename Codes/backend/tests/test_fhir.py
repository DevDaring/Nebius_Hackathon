"""Lab report -> FHIR: the Bundle from perception/lab.py validates against the FHIR models.

fhir.resources ships R5 (default), R4B and STU3 models; R4B (4.3) is the published
technical correction of R4 and has identical Bundle / Patient / Observation / Condition /
MedicationStatement structure, so it is the R4-family validator used here.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fhir.resources")

from fhir.resources.R4B import get_fhir_model_class  # noqa: E402
from fhir.resources.R4B.bundle import Bundle  # noqa: E402

from nemotwins.perception import lab as LAB  # noqa: E402
from nemotwins.twin import personas as PS  # noqa: E402

RAW = {
    "values": {"hba1c": 7.8, "fasting_glucose": 148, "total_cholesterol": 196, "ldl": 118, "hdl": 41,
               "triglycerides": 176, "creatinine": 1.02, "egfr": 84},
    "units": {"hba1c": "%", "fasting_glucose": "mg/dL", "egfr": "mL/min/1.73m²"},
    "medications": ["Metformin 500 mg twice daily", "Telmisartan 40 mg once daily"],
    "collection_date": "2026-09-28",
}


@pytest.fixture(scope="module")
def bundle() -> dict:
    persona = {**PS.BY_ID["biman"], "sex": "M"}
    fields = LAB.to_fields(RAW)
    _bundle_id, resources = LAB.to_fhir(persona, fields)
    return LAB.bundle(persona, resources, bundle_id="test-bundle")


def test_fields_extracted_with_loinc_and_flags() -> None:
    fields = LAB.to_fields({"values": {"hba1c": 7.8, "fasting_glucose": 2000}, "medications": []})
    by = {f["code"]: f for f in fields}
    assert by["hba1c"]["loinc"] == "4548-4" and not by["hba1c"]["implausible"]
    assert by["fasting_glucose"]["implausible"]  # 2000 mg/dL is out of the plausible range


def test_bundle_is_valid_fhir(bundle: dict) -> None:
    b = Bundle.model_validate(bundle)
    assert b.type == "collection"
    assert len(b.entry) == 1 + 8 + 2  # patient + 8 observations + 2 medications; NO condition from a value


def test_every_entry_validates_as_its_resource_type(bundle: dict) -> None:
    kinds = {}
    for e in bundle["entry"]:
        res = e["resource"]
        cls = get_fhir_model_class(res["resourceType"])
        cls.model_validate(res)
        kinds[res["resourceType"]] = kinds.get(res["resourceType"], 0) + 1
    assert kinds == {"Patient": 1, "Observation": 8, "MedicationStatement": 2}


def test_observation_codes_and_units(bundle: dict) -> None:
    obs = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    hba1c = next(o for o in obs if o["code"]["coding"][0]["code"] == "4548-4")
    assert hba1c["valueQuantity"]["value"] == 7.8 and hba1c["valueQuantity"]["unit"] == "%"
    assert all(o["code"]["coding"][0]["system"] == "http://loinc.org" for o in obs)
    egfr = next(o for o in obs if o["code"]["coding"][0]["code"] == "62238-1")
    assert egfr["valueQuantity"]["code"] == "mL/min/{1.73_m2}"  # UCUM code; unit text stays human-readable
    assert egfr["valueQuantity"]["system"] == "http://unitsofmeasure.org"


def test_patient_urn_uuid_and_references(bundle: dict) -> None:
    import uuid

    first = bundle["entry"][0]
    assert first["resource"]["resourceType"] == "Patient"
    patient_urn = first["fullUrl"]
    u = uuid.UUID(patient_urn.removeprefix("urn:uuid:"))
    assert patient_urn.startswith("urn:uuid:") and u.version == 4
    assert first["resource"]["identifier"][0]["value"] == "biman"
    for e in bundle["entry"]:
        assert e["fullUrl"].startswith("urn:uuid:")
        uuid.UUID(e["fullUrl"].removeprefix("urn:uuid:"))  # a real uuid, not a persona id
        if "subject" in e["resource"]:
            assert e["resource"]["subject"]["reference"] == patient_urn
    assert len({e["fullUrl"] for e in bundle["entry"]}) == len(bundle["entry"])


def test_hex_ids_become_canonical_urns() -> None:
    persona = {**PS.BY_ID["biman"], "sex": "M"}
    old = {"resourceType": "Observation", "id": "0123456789abcdef0123456789abcdef", "status": "final",
           "code": {"text": "x"}, "subject": {"reference": "Patient/biman"}}
    b = LAB.bundle(persona, [old])
    assert b["entry"][1]["fullUrl"] == "urn:uuid:01234567-89ab-cdef-0123-456789abcdef"
    Bundle.model_validate(b)


def test_high_hba1c_alone_does_not_invent_a_diagnosis(bundle: dict) -> None:
    """HbA1c 7.8 % is above 6.5 %, but the report lists no diagnosis: no Condition, no diagnosis-source note."""
    assert not [e for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition"]
    assert "existing diagnosis" not in str(bundle)


def test_listed_diagnosis_becomes_an_unconfirmed_condition_with_its_source() -> None:
    persona = {**PS.BY_ID["biman"], "sex": "M"}
    fields = LAB.to_fields({**RAW, "diagnoses": ["Type 2 diabetes mellitus"]})
    _bid, res = LAB.to_fhir(persona, fields)
    cond = [r for r in res if r["resourceType"] == "Condition"]
    assert len(cond) == 1 and cond[0]["code"]["text"] == "Type 2 diabetes mellitus"
    assert cond[0]["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    assert "Listed as a diagnosis on the uploaded report" in cond[0]["note"][0]["text"]
    assert "not a diagnosis by NemoTwins" in cond[0]["note"][0]["text"]
    Bundle.model_validate(LAB.bundle(persona, res))


def test_collection_date_is_the_effective_time_and_confirmation_is_issued(bundle: dict) -> None:
    obs = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    assert obs and all(o["effectiveDateTime"] == "2026-09-28" for o in obs)
    assert all(o["issued"] != o["effectiveDateTime"] and o["issued"].startswith("20") for o in obs)


EQUIV = [  # (code, value in canonical unit, same quantity in another supported unit)
    ("hba1c", (7.0, "%"), (53.0, "mmol/mol")),
    ("fasting_glucose", (126.0, "mg/dL"), (7.0, "mmol/L")),
    ("total_cholesterol", (193.0, "mg/dL"), (5.0, "mmol/L")),
    ("ldl", (116.0, "mg/dL"), (3.0, "mmol/l")),
    ("hdl", (38.7, "mg/dL"), (1.0, "mmol/L")),
    ("triglycerides", (177.1, "mg/dL"), (2.0, "mmol/L")),
    ("creatinine", (1.0, "mg/dL"), (88.4, "µmol/L")),
    ("creatinine", (1.13, "mg/dL"), (100.0, "umol/l")),
]


@pytest.mark.parametrize("code,canon,other", EQUIV)
def test_equivalent_inputs_in_supported_units_export_equivalent_quantities(code, canon, other) -> None:
    persona = {**PS.BY_ID["biman"], "sex": "M"}
    out = []
    for value, unit in (canon, other):
        raw = {"values": {code: value}, "units": {code: unit}, "collection_date": "2026-09-28"}
        fields = LAB.to_fields(raw)
        _bid, res = LAB.to_fhir(persona, fields)
        out.append(res[0]["valueQuantity"])
        assert res[0]["effectiveDateTime"] == "2026-09-28"
    assert out[0]["unit"] == out[1]["unit"] == LAB.FIELDS[code][2]
    assert out[0]["code"] == out[1]["code"]
    tol = 0.02 if code == "creatinine" else 0.6  # rounding of the printed values only
    assert out[1]["value"] == pytest.approx(out[0]["value"], abs=tol)


def test_original_value_and_unit_are_kept() -> None:
    f = LAB.to_fields({"values": {"hba1c": 53}, "units": {"hba1c": "mmol/mol"}, "collection_date": "28/09/2026"})[0]
    assert f["value"] == 7.0 and f["unit"] == "%" and f["original_value"] == 53.0 and f["original_unit"] == "mmol/mol"
    assert f["collection_date"] == "2026-09-28"  # DD/MM/YYYY (Indian reports) parsed deterministically
    persona = {**PS.BY_ID["biman"], "sex": "M"}
    _bid, res = LAB.to_fhir(persona, [f])
    assert "Reported as 53.0 mmol/mol; converted to 7.0 %" in res[0]["note"][1]["text"]


def test_confirm_reconverts_a_user_edited_unit_and_rejects_unknown_units() -> None:
    g = LAB.normalise_confirmed({"code": "fasting_glucose", "value": 7.0, "unit": "mmol/L"})
    assert g["value"] == 126.1 and g["unit"] == "mg/dL" and g["original_value"] == 7.0 and g["original_unit"] == "mmol/L"
    with pytest.raises(LAB.UnitError):
        LAB.normalise_confirmed({"code": "hba1c", "value": 7.0, "unit": "g/L"})
    bad = LAB.to_fields({"values": {"ldl": 3.0}, "units": {"ldl": "furlongs"}})[0]
    assert bad["implausible"] is True  # flagged for the user, never silently relabelled
