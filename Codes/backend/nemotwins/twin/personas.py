"""Three clearly-labelled synthetic composite demo personas (spec section 5.2).

Each persona = a real open CGMacros T2D trajectory (CGM, logged meal macros,
wearable activity) + an invented Indian name, city, occupation and EHR narrative.
Age, sex, BMI and HbA1c are kept from the source participant so the twin's
EHR-conditioned prior matches the trajectory.
"""

from __future__ import annotations

PERSONAS: list[dict] = [
    {
        "id": "biman",
        "source_pid": "cgm038",
        "name": "Biman Bakshi",
        "avatar_initials": "BB",
        "city": "Kolkata",
        "occupation": "Sweet-shop owner",
        "language": "en-US",
        "diabetes_years": 6,
        "medications": ["Metformin 500 mg twice daily"],
        "conditions": ["Type 2 diabetes", "Hypertension"],
        "ldl": 118,
        "egfr": 84,
        "story_en": "Runs a sweet shop near Gariahat; long hours, late dinners of rice and macher jhol.",
    },
    {
        "id": "lakshmi",
        "source_pid": "cgm005",
        "name": "Lakshmi Gowda",
        "avatar_initials": "LG",
        "city": "Mysuru",
        "occupation": "School teacher",
        "language": "en-US",
        "diabetes_years": 3,
        "medications": ["Metformin 500 mg once daily"],
        "conditions": ["Type 2 diabetes"],
        "ldl": 104,
        "egfr": 96,
        "story_en": "Teaches mathematics; ragi mudde at lunch, walks to school most mornings.",
    },
    {
        "id": "ramesh",
        "source_pid": "cgm046",
        "name": "Ramesh Chandra Srivastava",
        "avatar_initials": "RS",
        "city": "Lucknow",
        "occupation": "Railway booking clerk",
        "language": "en-US",
        "diabetes_years": 9,
        "medications": ["Metformin 1000 mg twice daily", "Glimepiride 1 mg once daily"],
        "conditions": ["Type 2 diabetes", "Dyslipidaemia"],
        "ldl": 132,
        "egfr": 71,
        "story_en": "Works shifts at Charbagh station; evening chai with biscuits, parathas at breakfast, late dinners after duty.",
    },
]

BY_ID = {p["id"]: p for p in PERSONAS}
CALIB_DAYS = 5.0
NOW_DAY = 7  # demo "now" is on day 7 of the record ...
NOW_HOUR = 19.5  # ... at 19:30, just before dinner
SLEEP_WINDOW = ("23:00", "06:30")
