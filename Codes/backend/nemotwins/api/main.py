"""FastAPI app: REST API for the NemoTwins frontend (docs/API_CONTRACT.md v3 + docs/API_CONTRACT_AGENT.md v4).

All model calls go to Nebius Token Factory (NVIDIA Nemotron first); the numerical twin engine is the
source of every glucose number.

Run: ``uvicorn nemotwins.api.main:app --port 8000``
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from nemotwins import food
from nemotwins import guardrails as GR
from nemotwins.agent import orchestrator as ORCH
from nemotwins.agent import safety
from nemotwins.agent.orchestrator import Agent
from nemotwins.api import receipt as RC
from nemotwins.api import schemas as S
from nemotwins.auth import (
    authenticate,
    create_demo_user,
    current_user,
    make_token,
    purge_demo_users,
    user_json,
)
from nemotwins.config import CAPABILITIES_DIR, FIXTURES_DIR, REPORTS_DIR, get_settings
from nemotwins.db import (
    AuditLog,
    CovariateRevision,
    DoctorReview,
    FhirResource,
    PendingAction,
    ReplayClock,
    TwinEvent,
    User,
    init_db,
    ping,
    session,
)
from nemotwins.perception import lab as LAB
from nemotwins.perception import meal as MEAL
from nemotwins.providers import llm as LLM
from nemotwins.providers import nebius_cloud as NC
from nemotwins.providers import speech
from nemotwins.providers import tavily as TV
from nemotwins.providers.llm import LLMUnavailable
from nemotwins.twin import personas as PS
from nemotwins.twin.engine import LADDERS, MAX_OFFSET_MIN, REVISION_FIELDS, get_engine

log = logging.getLogger("nemotwins.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

IST = ZoneInfo("Asia/Kolkata")
# Release languages = the languages the NVIDIA Nemotron 3 Nano model card lists as supported (English, Spanish,
# French, German, Italian, Japanese). Any other requested code is answered in English.
LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
DEFAULT_LANG = "en-US"
STALE_WINDOW_MIN = 30.0
MMOL_TO_MGDL = 18.016


def clean(o: Any) -> Any:
    """JSON-safe copy: NaN/inf -> null, numpy scalars/arrays -> Python."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, np.generic):
        return clean(o.item())
    if isinstance(o, datetime):
        return o.isoformat(timespec="seconds")
    return o


class SafeJSONResponse(JSONResponse):
    """Never fails on NaN/inf (sent as null) and keeps Indic text readable."""

    def render(self, content: Any) -> bytes:
        return json.dumps(clean(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    threading.Thread(target=lambda: get_engine().warm(), daemon=True).start()
    yield


TAGS = [
    {"name": "twin", "description": "Twin API (spec section 4.6): the only source of glucose numbers."},
    {"name": "auth"}, {"name": "patients"}, {"name": "food & meals"}, {"name": "agent & speech"},
    {"name": "lab & FHIR"}, {"name": "doctor"}, {"name": "trust"}, {"name": "demo"},
]

app = FastAPI(
    title="NemoTwins API",
    version="1.1.0",
    description=("NemoTwins - explore your glucose patterns, understand the uncertainty. A multilingual glucose "
                 "digital twin (research prototype) whose assistant runs on NVIDIA Nemotron via "
                 "Nebius Token Factory and only explains engine-computed values. Not a "
                 "medical device. No insulin or medicine dose recommendations. P(<70) is reported but NOT validated "
                 "(too few low-glucose events in the training data). What-ifs are model simulations, not proven "
                 "effects."),
    default_response_class=SafeJSONResponse,
    openapi_tags=TAGS,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=exc)
    return SafeJSONResponse({"detail": "Internal error. Please try again."}, status_code=500)


app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


# ----------------------------------------------------------------------------- upload bounds
def _upload_limits() -> dict[str, int]:
    st = get_settings()
    return {"/api/meal/photo": st.max_image_bytes, "/api/lab/parse": st.max_image_bytes,
            "/api/speech/stt": st.max_audio_bytes}


class BodyLimitMiddleware:
    """Hard request-size bound on upload endpoints: rejects a declared Content-Length over the limit
    and counts body bytes as they arrive (413 as soon as the limit is passed), so an oversized
    upload is never read into memory or a temp file in full."""

    SLACK = 64 * 1024  # multipart framing around the file

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        limit = _upload_limits().get(scope.get("path", ""))
        if not limit:
            await self.app(scope, receive, send)
            return
        limit += self.SLACK
        headers = dict(scope.get("headers") or [])
        cl = headers.get(b"content-length")
        if cl is not None and cl.isdigit() and int(cl) > limit:
            await _send_413(send)
            return
        seen = 0

        async def limited() -> dict:
            nonlocal seen
            msg = await receive()
            if msg.get("type") == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise HTTPException(413, "Upload too large")
            return msg

        await self.app(scope, limited, send)


async def _send_413(send: Callable) -> None:
    body = json.dumps({"detail": "Upload too large"}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


app.add_middleware(BodyLimitMiddleware)


async def _read_bounded(f: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await f.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"Upload too large (max {max_bytes // (1024 * 1024)} MB)")
        chunks.append(chunk)
    return b"".join(chunks)


# ----------------------------------------------------------------------------- rate limits
class _RateLimiter:
    """Sliding window (one minute by default) per (user or client key, endpoint). In-process (one API
    process per deployment)."""

    def __init__(self) -> None:
        self.hits: dict[tuple[int | str, str], deque[float]] = {}
        self.lock = threading.Lock()

    def check(self, key: int | str, name: str, limit: int, now: float | None = None, window: float = 60.0) -> float | None:
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.hits.setdefault((key, name), deque())
            while q and now - q[0] >= window:
                q.popleft()
            if limit > 0 and len(q) >= limit:
                return max(1.0, window - (now - q[0]))
            q.append(now)
            return None

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


RATE = _RateLimiter()


def rate_limited(name: str) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        per_min = int(getattr(get_settings(), f"rate_{name}_per_min"))
        wait = RATE.check(user.id, name, per_min)
        if wait is not None:
            raise HTTPException(429, f"Too many requests; try again in {math.ceil(wait)} s",
                                headers={"Retry-After": str(math.ceil(wait))})
        return user
    return dep


_agent: Agent | None = None


def agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(get_engine())
    return _agent


# ----------------------------------------------------------------------------- helpers
def _persona(pid: str) -> dict:
    p = PS.BY_ID.get(pid)
    if not p:
        raise HTTPException(404, "Unknown patient")
    return p


def _ladder(ladder: str) -> str:
    if ladder not in LADDERS:
        raise HTTPException(422, f"ladder must be one of {LADDERS}")
    return ladder


def _lang(lang: str | None) -> str:
    """A release language, else English (unsupported codes map to English)."""
    if lang in LANGS:
        return lang
    short = (lang or "").split("-")[0].lower()
    return next((code for code in LANGS if code.split("-")[0] == short and short != "en"), DEFAULT_LANG)


def require_clinician(user: User = Depends(current_user)) -> User:
    if "clinician" not in (user.roles or "").split(","):
        raise HTTPException(403, "Clinician role required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if "admin" not in (user.roles or "").split(","):
        raise HTTPException(403, "Admin role required")
    return user


LadderQ = Literal["full", "4", "2", "1", "0"]


@dataclass
class UCtx:
    """Everything user-specific the twin needs for one persona."""

    events: list[dict]
    offset: int
    rev: dict | None
    revisions: list[dict]


def _event_dict(r: TwinEvent) -> dict:
    p = dict(r.payload or {})
    t_min = r.t_min if r.t_min is not None else float(p.get("t_min", 0.0) or 0.0)
    return {"kind": r.kind, **p, "t_min": float(t_min), "source": r.source or p.get("source", "manual"),
            "id": r.id}


def _uctx(user: User, pid: str) -> UCtx:
    with session() as s:
        rows = s.scalars(select(TwinEvent).where(TwinEvent.user_id == user.id, TwinEvent.persona_id == pid)
                         .order_by(TwinEvent.id)).all()
        clock = s.get(ReplayClock, (user.id, pid))
        revs = s.scalars(select(CovariateRevision).where(CovariateRevision.user_id == user.id,
                                                         CovariateRevision.persona_id == pid)
                         .order_by(CovariateRevision.revision)).all()
        events = [_event_dict(r) for r in rows]
        offset = int(clock.offset_min) if clock else 0
        revisions = [{"revision": r.revision, "fields": r.fields, "bundle_id": r.bundle_id,
                      "created_at": r.created_at.isoformat(timespec="seconds") if r.created_at else None} for r in revs]
    events.sort(key=lambda e: (e["t_min"], e["id"]))
    return UCtx(events, offset, _effective_rev(revisions), revisions)


def _effective_rev(revisions: list[dict]) -> dict | None:
    """Latest confirmed value per model-supported field across this user's revisions."""
    fields: dict[str, dict] = {}
    for r in revisions:
        for k, v in (r["fields"] or {}).items():
            if k in REVISION_FIELDS:
                fields[k] = {**v, "revision": r["revision"]}
    if not fields:
        return None
    return {"revision": max(r["revision"] for r in revisions), "fields": fields}


def _eng_events(u: UCtx) -> list[dict]:
    """What the engine sees (no DB ids)."""
    return [{k: v for k, v in e.items() if k != "id"} for e in u.events]


def _set_offset(user: User, pid: str, offset: int) -> None:
    with session() as s:
        c = s.get(ReplayClock, (user.id, pid))
        if c is None:
            s.add(ReplayClock(user_id=user.id, persona_id=pid, offset_min=int(offset)))
        else:
            c.offset_min = int(offset)


def _add_event(user: User, pid: str, ev: dict, *, observed_at: datetime | None = None, unit: str | None = None,
               idempotency_key: str | None = None) -> int:
    payload = {k: v for k, v in ev.items() if k not in ("kind", "id")}
    with session() as s:
        row = TwinEvent(user_id=user.id, persona_id=pid, kind=ev["kind"], payload=payload,
                        t_min=float(ev.get("t_min", 0.0)), observed_at=observed_at,
                        received_at=datetime.now(UTC), source=ev.get("source"), unit=unit,
                        idempotency_key=idempotency_key)
        s.add(row)
        s.flush()
        return int(row.id)


# Forecast ownership: a forecast id is readable only by the (user, persona) it was issued to.
_OWNERS: OrderedDict[str, set[tuple[int, str]]] = OrderedDict()
_OWN_LOCK = threading.Lock()


def _own(user: User, pid: str, *fids: str | None) -> None:
    with _OWN_LOCK:
        for fid in fids:
            if not fid:
                continue
            _OWNERS.setdefault(fid, set()).add((user.id, pid))
            _OWNERS.move_to_end(fid)
        while len(_OWNERS) > 20000:
            _OWNERS.popitem(last=False)


def _owned(user: User, pid: str, fid: str) -> bool:
    with _OWN_LOCK:
        return (user.id, pid) in _OWNERS.get(fid, set())


def _state(user: User, pid: str, ladder: str, u: UCtx | None = None, reveal: bool = False) -> dict:
    u = u or _uctx(user, pid)
    st = get_engine().state(pid, ladder, _eng_events(u), reveal=reveal, offset=u.offset, rev=u.rev)
    _own(user, pid, st["forecast"]["forecast_id"])
    return st


# ----------------------------------------------------------------------------- patients helpers
def _cov(p: dict) -> Any:
    e = get_engine()
    return e.cov.loc[e.cov.pid == p["source_pid"]].iloc[0]


def _operational(user: User, p: dict, u: UCtx | None = None) -> dict:
    """Operational dashboard numbers: only what the twin has (readings the user / sensor ladder
    provided, the twin's estimate and forecast). Never the hidden reference CGM."""
    st = _state(user, p["id"], "2", u)
    last = st["last_observation"]
    age = st["freshness"]["hours_since_reading"] if last else None
    return {"estimate": st["estimate"], "band": st["band"], "last_reading_age_h": age,
            "last_reading": last, "p_high_2h": st["forecast"]["p_high"]["p"],
            "p_high_2h_validated": True, "data_gap": bool(last is None or st["freshness"]["label"] == "stale"),
            "freshness": st["freshness"], "replay_now": st["now"], "forecast_id": st["forecast"]["forecast_id"],
            "source": "twin estimate from available readings (sensor ladder 2/day + user readings)"}


TAR_LABEL = "Historical time above 180 (dataset reference CGM, last 7 days)"


def _summary(p: dict, user: User, u: UCtx | None = None) -> dict:
    e = get_engine()
    u = u or _uctx(user, p["id"])
    cov = _cov(p)
    s7 = e.summary_7d(p["id"], offset=u.offset)
    hba1c = float(cov["hba1c"])
    if u.rev and "hba1c" in u.rev["fields"]:
        hba1c = float(u.rev["fields"]["hba1c"]["value"])
    r3 = lambda v: None if v is None else round(float(v), 3)  # noqa: E731
    return {
        "id": p["id"], "name": p["name"], "age": int(cov["age"]), "sex": cov["sex"], "city": p["city"],
        "occupation": p["occupation"], "language": p["language"], "synthetic": True,
        "source_note": f"Synthetic composite: open CGMacros participant trajectory ({p['source_pid']}) + invented name and EHR",
        "hba1c": hba1c, "risk_7d": r3(s7["tar_7d"]), "tir_7d": r3(s7["tir_7d"]),
        "risk_7d_note": "Historical time above 180 from the dataset reference CGM (same value as tar_7d_reference); "
                        "not a forecast.",
        "tar_7d_reference": {"value": r3(s7["tar_7d"]), "label_en": TAR_LABEL},
        "operational": _operational(user, p, u),
        "sparkline": s7["sparkline"], "avatar_initials": p["avatar_initials"],
    }


def _detail(p: dict, user: User, u: UCtx | None = None) -> dict:
    e = get_engine()
    u = u or _uctx(user, p["id"])
    cov = _cov(p)
    b = e.base(p["id"], "2")
    prov: dict[str, dict] = {}
    base_vals = {"hba1c": float(cov["hba1c"]), "bmi": round(float(cov["bmi"]), 1)}
    for k, v in base_vals.items():
        prov[k] = {"value": v, "source": "persona EHR", "collection_date": None, "revision": 0}
    for k, f in (u.rev or {}).get("fields", {}).items():
        prov[k] = {"value": f.get("value"), "source": "lab upload (confirmed)",
                   "collection_date": f.get("collection_date"), "revision": f.get("revision"),
                   "original_value": f.get("original_value"), "original_unit": f.get("original_unit")}
    return {**_summary(p, user, u), "ehr": {
        "bmi": prov["bmi"]["value"], "diabetes_years": p["diabetes_years"], "medications": p["medications"],
        "fasting_glucose": float(cov["fasting_glucose"]) if cov["fasting_glucose"] == cov["fasting_glucose"] else None,
        "ldl": p["ldl"], "egfr": p["egfr"], "conditions": p["conditions"], "hba1c": prov["hba1c"]["value"],
        "provenance": prov, "revisions": u.revisions},
        "calibration": {"cgm_days": PS.CALIB_DAYS, "start": e._fmt(p["id"], b.tl.t[0]),
                        "end": e._fmt(p["id"], b.tl.t[b.calib_end - 1])},
        "sleep_window": {"start": PS.SLEEP_WINDOW[0], "end": PS.SLEEP_WINDOW[1]}, "story_en": p["story_en"]}


# ----------------------------------------------------------------------------- auth / health
class LoginIn(BaseModel):
    username: str
    password: str


@app.get("/api/health", tags=["demo"])
def health() -> dict:
    """Liveness (no external calls): process up, inference mode and configured chat model."""
    st = get_settings()
    return {"ok": True, "app": st.app_name, "mode": "live" if st.live else "demo",
            "inference": {"provider": LLM.PROVIDER, "configured": LLM.configured(),
                          "chat_model": LLM.model_for("router") or None}}


def _vision_status() -> dict:
    model = LLM.model_for("vision")
    if not get_settings().vision_enabled or not model:
        return {"enabled": False, "model": None, "nvidia": False, "provider": LLM.PROVIDER,
                "reason": "Photo recognition is switched off (VISION_ENABLED / NEMOTRON_VISION_MODEL)."}
    if not LLM.available("vision"):
        return {"enabled": False, "model": model, "nvidia": LLM.is_nvidia(model), "provider": LLM.PROVIDER,
                "reason": "Live inference is off (demo mode or no Token Factory key); sample photos use recorded results."}
    return {"enabled": True, "model": model, "nvidia": LLM.is_nvidia(model), "provider": LLM.PROVIDER,
            "reason": None if LLM.is_nvidia(model) else
            "Suggests dish names from the photo for you to confirm; nutrition comes from the food table."}


@app.get("/api/capabilities", tags=["demo"], summary="Public feature status (no secrets): locales, models, features")
def capabilities() -> dict:
    st = get_settings()
    gr = GR.status()
    return {
        "app_name": st.app_name, "schema_version": "1.0", "locales": list(st.locales),
        "default_locale": _lang(st.app_default_locale), "mode": "live" if st.live else "demo",
        "inference": {"provider": LLM.PROVIDER, "chat_model": LLM.model_for("router") or None,
                      "planner_model": LLM.model_for(ORCH.PLANNER_ROLE()) or None,
                      "complex_model": LLM.model_for("complex") or None, "available": LLM.available("router")},
        "features": {
            "vision": _vision_status(),
            "speech": speech.status(),
            "guardrails": {"enabled": gr["enabled"], "engine": gr["engine"], "model": gr["model"],
                           "reason": None if gr["enabled"] else
                           "Guardrails need live inference (NEMO_GUARDRAILS_ENABLED and a Token Factory key)."},
            "fish": {"enabled": bool(st.nemo_fish_enabled)},
            "references": {"enabled": TV.available(), "provider": "tavily", "kind": "web search API (no model)",
                           "reason": None if TV.available() else
                           "Further reading needs live mode and a Tavily key (TAVILY_API_KEY)."},
        },
    }


def _eval_jobs() -> list[dict]:
    out = []
    for name, fname in (("numerical_regression", "regression/compare_baseline_2026-10-08_latest.json"),
                        ("multilingual_agent_suite", "agent_multilingual.json"),
                        ("provider_smoke", "../capabilities/manifest.json")):
        p = (REPORTS_DIR / fname).resolve()
        if p.exists():
            try:
                d = json.loads(p.read_text())
            except ValueError:
                d = {}
            out.append({"name": name, "status": "completed", "report": p.name,
                        "generated_at": d.get("generated_at")})
        else:
            out.append({"name": name, "status": "not_run", "report": None, "generated_at": None})
    return out


@app.get("/api/admin/integrations", tags=["demo"],
         summary="Developer integration status (admin role): models, capabilities, health, redacted usage")
def admin_integrations(probe: int = 0, user: User = Depends(require_admin)) -> dict:
    """``probe=1`` runs one live inference health call and one read-only Cloud identity check."""
    st = get_settings()
    try:
        manifest = json.loads((CAPABILITIES_DIR / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {"note": "capabilities/manifest.json not generated yet (python -m nemotwins.eval.provider_smoke)"}
    m = LLM.METER.snapshot()
    health_now = LLM.health_check() if probe else {"ok": None, "model": LLM.model_for("router") or None,
                                                  "last_ok": m["last_ok"], "last_error": m["last_error"],
                                                  "checked_at": None, "error_category": None}
    return clean({
        "manifest": manifest, "capabilities": capabilities(), "inference_health": health_now,
        "usage": {k: v for k, v in m.items() if k not in ("last_ok", "last_error")},
        "guardrails": GR.status(),
        "references": TV.status(),
        "cloud": NC.check() if probe else NC.last(),
        "deployment": {"version": app.version, "git_commit": st.git_commit or None,
                       "environment": st.app_environment, "public_url": st.app_public_url or None},
        "evaluation_jobs": _eval_jobs(),
    })


@app.get("/api/ready", tags=["demo"])
def ready() -> JSONResponse:
    """Readiness: database reachable AND twin model warm (persona states, explainer, default states)."""
    db_ok = ping()
    from nemotwins.twin import engine as ENG

    model_ok = bool(ENG._ENGINE is not None and ENG._ENGINE.warm_done)
    ok = db_ok and model_ok
    return SafeJSONResponse({"ready": ok, "db": db_ok, "model": model_ok}, status_code=200 if ok else 503)


@app.post("/api/auth/login", tags=["auth"])
def login(body: LoginIn) -> dict:
    u = authenticate(body.username.strip(), body.password)
    if not u:
        raise HTTPException(401, "Username or password did not match")
    return {"access_token": make_token(u), "user": user_json(u)}


@app.post("/api/auth/demo", tags=["auth"], summary="One-click demo: a fresh private session on the synthetic personas")
def demo_session(request: Request) -> dict:
    """Creates a throw-away user so each visitor gets their own replay clocks, readings and meals.

    Limited per client address (the real address, forwarded by the reverse proxy) and per day;
    demo users older than DEMO_SESSION_TTL_HOURS are deleted together with their data."""
    st = get_settings()
    if not st.demo_sessions:
        raise HTTPException(404, "Demo sessions are disabled")
    client = (request.client.host if request.client else "") or "unknown"
    for key, limit, window in ((f"ip:{client}", st.rate_demo_session_per_hour, 3600.0), ("all", st.demo_sessions_per_day, 86400.0)):
        wait = RATE.check(key, "demo_session", limit, window=window)
        if wait is not None:
            raise HTTPException(429, "Too many demo sessions right now; please use the jury account",
                                headers={"Retry-After": str(math.ceil(wait))})
    purge_demo_users(st.demo_session_ttl_hours)
    u = create_demo_user()
    return {"access_token": make_token(u, ttl_hours=st.demo_session_ttl_hours), "user": user_json(u)}


@app.get("/api/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)) -> dict:
    return user_json(user)


# ----------------------------------------------------------------------------- patients
@app.get("/api/patients", tags=["patients"])
def patients(user: User = Depends(current_user)) -> list[dict]:
    return clean([_summary(p, user) for p in PS.PERSONAS])


@app.get("/api/patients/{pid}", tags=["patients"])
def patient(pid: str, user: User = Depends(current_user)) -> dict:
    return clean(_detail(_persona(pid), user))


# ----------------------------------------------------------------------------- twin
@app.get("/api/twin/{pid}/state", tags=["twin"], response_model=S.TwinState, response_model_exclude_unset=True,
         summary="get_state: current estimate, 90% band, freshness, history, 4-h forecast, next best prick, replay clock")
def twin_state(pid: str, ladder: LadderQ = "2", reveal: int = 0, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    return clean(_state(user, pid, _ladder(ladder), reveal=bool(reveal)))


class MealItemIn(BaseModel):
    food_id: str
    units: float = Field(1.0, ge=0, le=20)

    @field_validator("food_id")
    @classmethod
    def _known(cls, v: str) -> str:
        if food.get(v) is None:
            raise ValueError(f"unknown food_id {v!r}")
        return v


class MealIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    carbs: float = Field(ge=0, le=400)
    carbs_sd: float | None = Field(None, ge=0, le=200)
    fibre: float | None = Field(None, ge=0, le=100)
    protein: float | None = Field(None, ge=0, le=200)
    fat: float | None = Field(None, ge=0, le=200)
    minutes_from_now: float | None = Field(0, ge=0, le=240)
    items: list[MealItemIn] | None = None


class ForecastIn(BaseModel):
    ladder: LadderQ = "2"
    horizon_min: int = Field(240, ge=30, le=240)
    meal: MealIn | None = None


@app.post("/api/twin/{pid}/forecast", tags=["twin"], response_model=S.Forecast, response_model_exclude_unset=True,
          summary="forecast: 4-h trajectory quantiles, P(>180) with held-out reliability, P(<70, not validated), drivers")
def twin_forecast(pid: str, body: ForecastIn, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    u = _uctx(user, pid)
    meal = body.meal.model_dump(exclude_none=True) if body.meal else None
    fc = get_engine().forecast(pid, _ladder(body.ladder), _eng_events(u), meal, body.horizon_min, offset=u.offset,
                               rev=u.rev)
    _own(user, pid, fc["forecast_id"])
    return clean(fc)


class SwapIn(BaseModel):
    model_config = {"populate_by_name": True}
    from_: str = Field(alias="from")
    to: str
    from_qty: float = Field(1.0, gt=0, le=20)
    to_qty: float = Field(1.0, gt=0, le=20)


class ScenarioIn(BaseModel):
    carb_scale: float | None = Field(None, ge=0, le=3)
    swap: SwapIn | None = None
    walk_min: float | None = Field(None, ge=0, le=120)
    walk_after_min: float | None = Field(None, ge=0, le=180)
    shift_min: float | None = Field(None, ge=-240, le=240)
    label: str | None = None


def _scenario_dict(sc: ScenarioIn, base: dict) -> dict:
    """Scenario fields for the engine; a food swap becomes carb/fibre/fat/protein deltas."""
    scen = sc.model_dump(exclude_none=True)
    scen.pop("swap", None)
    swap = sc.swap
    if swap is not None:
        a, b = food.get(swap.from_), food.get(swap.to)
        if a is None or b is None:
            raise HTTPException(422, "Unknown food in swap")
        fq, tq = swap.from_qty, swap.to_qty
        units = 1.0
        for it in base.get("items") or []:
            if it.get("food_id") == swap.from_:
                units = float(it.get("units", 1))
        k = units / fq
        scen["carb_delta"] = k * (tq * b["carbs_g"] - fq * a["carbs_g"])
        scen["fibre_delta"] = k * (tq * b["fibre_g"] - fq * a["fibre_g"])
        scen["fat_delta"] = k * (tq * b["fat_g"] - fq * a["fat_g"])
        scen["protein_delta"] = k * (tq * b["protein_g"] - fq * a["protein_g"])
    return scen


class BodyIn(BaseModel):
    ladder: LadderQ = "2"
    meal: MealIn | None = None
    scenario: ScenarioIn | None = None


class WhatIfIn(BaseModel):
    ladder: LadderQ = "2"
    base_meal: MealIn
    scenario: ScenarioIn


@app.post("/api/twin/{pid}/what_if", tags=["twin"], response_model=S.WhatIf, response_model_exclude_unset=True,
          summary="what_if: pinned baseline vs scenario on the same particles; a model simulation, not a proven effect")
def twin_what_if(pid: str, body: WhatIfIn, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    base = body.base_meal.model_dump(exclude_none=True)
    scen = _scenario_dict(body.scenario, base)
    u = _uctx(user, pid)
    w = get_engine().what_if(pid, _ladder(body.ladder), _eng_events(u), base, scen, offset=u.offset, rev=u.rev)
    _own(user, pid, w["baseline"]["forecast_id"], w["scenario"]["forecast_id"])
    return clean(w)


@app.post("/api/twin/{pid}/body", tags=["twin"], response_model=S.BodyView,
          summary="body: per-organ glucose flows of the physiology model (simulated) for the 3-D body view")
def twin_body(pid: str, body: BodyIn, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    meal = body.meal.model_dump(exclude_none=True) if body.meal else None
    if body.scenario is not None and meal is None:
        raise HTTPException(422, "A scenario needs the meal it changes (meal).")
    scen = _scenario_dict(body.scenario, meal or {}) if body.scenario is not None else None
    u = _uctx(user, pid)
    out = get_engine().body(pid, _ladder(body.ladder), _eng_events(u), meal, scen, offset=u.offset, rev=u.rev)
    _own(user, pid, out["baseline"]["forecast_id"],
         *([out["scenario"]["forecast_id"]] if out.get("scenario") else []))
    return clean(out)


@app.get("/api/twin/{pid}/next_best_prick", tags=["twin"], response_model=S.NextBestPrick,
         response_model_exclude_unset=True,
         summary="next_best_prick (experimental): best time in the next 24 h, expected % variance reduction, reason")
def twin_nbp(pid: str, ladder: LadderQ = "2", user: User = Depends(current_user)) -> Any:
    _persona(pid)
    u = _uctx(user, pid)
    return clean(get_engine().next_best_prick(pid, _ladder(ladder), _eng_events(u), offset=u.offset, rev=u.rev))


class AssimilateIn(BaseModel):
    ladder: LadderQ = "2"
    value: float = Field(gt=0, le=1000)
    unit: Literal["mg/dL", "mmol/L"]
    observed_at: str | None = Field(None, max_length=40)
    at: str | None = Field(None, max_length=40, description="alias of observed_at")
    idempotency_key: str | None = Field(None, min_length=1, max_length=80)
    symptoms: str | None = Field(None, max_length=300)


def _parse_observed(pid: str, raw: str | None, offset: int) -> tuple[float, datetime]:
    """Replay time (t_min) of an observation. Naive ISO strings are local (Asia/Kolkata) on the replay
    clock the API shows; aware ones are converted. 422 stale_observation if more than 30 min away."""
    e = get_engine()
    if not raw:
        return float(offset), e.display_time(pid, offset).replace(tzinfo=IST)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, {"code": "bad_observed_at", "message": "observed_at must be an ISO-8601 time"}) from None
    local = dt.astimezone(IST).replace(tzinfo=None) if dt.tzinfo else dt
    t_min = e.offset_of(pid, local)
    if abs(t_min - offset) > STALE_WINDOW_MIN:
        raise HTTPException(422, {"code": "stale_observation",
                                  "message": ("observed_at is more than 30 minutes from the replay time now; an old "
                                              "reading cannot be added as a current one.")})
    t_min = min(t_min, float(offset))  # a slightly future time is placed at 'now'
    return round(t_min / 5.0) * 5.0, local.replace(tzinfo=IST)


def _to_mgdl(value: float, unit: str) -> float:
    mg = float(value) * MMOL_TO_MGDL if unit == "mmol/L" else float(value)
    mg = round(mg, 1)
    if not 20 <= mg <= 600:
        raise HTTPException(422, {"code": "implausible_value",
                                  "message": "Glucose must be between 20 and 600 mg/dL (1.1 to 33.3 mmol/L)."})
    return mg


def _assimilate(user: User, pid: str, ladder: str, mg: float, unit: str, original: float, t_min: float,
                observed_at: datetime, source: str, lang: str, symptoms: str | None, key: str | None,
                u: UCtx | None = None) -> dict:
    """The one path for a measured reading (manual entry, replay reveal): twin update + the shared
    safety policy. The reading is stored even when extreme; the safety result comes first."""
    u = u or _uctx(user, pid)
    e = get_engine()
    if key:
        dup = next((x for x in u.events if x.get("idempotency_key") == key), None)
        if dup is None:
            with session() as s:
                row = s.scalar(select(TwinEvent).where(TwinEvent.user_id == user.id, TwinEvent.persona_id == pid,
                                                       TwinEvent.idempotency_key == key))
                dup = _event_dict(row) if row else None
        if dup is not None:
            prior = [{k: v for k, v in x.items() if k != "id"} for x in u.events if x["id"] < dup["id"]]
            out = e.assimilate(pid, ladder, prior, float(dup["value"]), offset=u.offset, rev=u.rev,
                               t_min=float(dup["t_min"]), source=str(dup.get("source", source)))
            out["safety"] = safety.assess_reading(float(dup["value"]), dup.get("symptoms"), lang)
            out["duplicate"] = True
            _own(user, pid, out["state"]["forecast"]["forecast_id"])
            return out
    out = e.assimilate(pid, ladder, _eng_events(u), mg, offset=u.offset, rev=u.rev, t_min=t_min, source=source)
    out["safety"] = safety.assess_reading(mg, symptoms, lang)
    ev = {"kind": "reading", "value": mg, "t_min": t_min, "source": source, "unit": unit, "original_value": original,
          "observed_at": observed_at.isoformat(timespec="minutes"), "idempotency_key": key,
          "symptoms": (symptoms or "")[:300] or None}
    try:
        _add_event(user, pid, ev, observed_at=observed_at, unit=unit, idempotency_key=key)
    except IntegrityError:  # a concurrent duplicate with the same idempotency key won the race
        out["duplicate"] = True
    else:
        out["duplicate"] = False
    out["observation"] = {"value_mg_dl": mg, "unit": unit, "original_value": original,
                          "observed_at": observed_at.isoformat(timespec="minutes"), "t_min": t_min, "source": source,
                          "received_at": datetime.now(UTC).isoformat(timespec="seconds")}
    _own(user, pid, out["state"]["forecast"]["forecast_id"])
    return out


@app.post("/api/twin/{pid}/assimilate", tags=["twin"], response_model=S.Assimilation,
          response_model_exclude_unset=True,
          summary="assimilate: add a measured reading (unit required); shared safety result + signed band changes")
def twin_assimilate(pid: str, body: AssimilateIn, lang: str = DEFAULT_LANG, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    u = _uctx(user, pid)
    mg = _to_mgdl(body.value, body.unit)
    t_min, observed = _parse_observed(pid, body.observed_at or body.at, u.offset)
    return clean(_assimilate(user, pid, _ladder(body.ladder), mg, body.unit, body.value, t_min, observed, "manual",
                             _lang(lang), body.symptoms, body.idempotency_key, u))


class AdvanceIn(BaseModel):
    ladder: LadderQ = "2"
    minutes: int = Field(ge=15, le=240)


@app.post("/api/twin/{pid}/advance", tags=["twin"], response_model=S.TwinState, response_model_exclude_unset=True,
          summary="advance: move this user's replay clock; the twin follows the record's meals, activity and the "
                  "ladder's scheduled readings")
def twin_advance(pid: str, body: AdvanceIn, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    u = _uctx(user, pid)
    new = int(min(MAX_OFFSET_MIN, u.offset + int(round(body.minutes / 5.0)) * 5))
    _set_offset(user, pid, new)
    u.offset = new
    return clean(_state(user, pid, _ladder(body.ladder), u))


class RevealIn(BaseModel):
    ladder: LadderQ = "2"
    assimilate: bool = False


@app.post("/api/twin/{pid}/reveal", tags=["twin"], summary="reveal: show the dataset reference CGM at the replay now "
          "('watch the twin learn'); optionally assimilate it")
def twin_reveal(pid: str, body: RevealIn, lang: str = DEFAULT_LANG, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    ladder = _ladder(body.ladder)
    u = _uctx(user, pid)
    e = get_engine()
    ref = e.reference_at(pid, u.offset)
    if ref is None:
        raise HTTPException(404, {"code": "no_reference", "message": "The record has no reference CGM at this time."})
    st = _state(user, pid, ladder, u)
    before = {"estimate": st["estimate"], "band": st["band"], "forecast_peak": st["forecast"]["peak"],
              "p_high": st["forecast"]["p_high"], "forecast_id": st["forecast"]["forecast_id"]}
    after = None
    if body.assimilate:
        observed = e.display_time(pid, ref["t_min"]).replace(tzinfo=IST)
        after = _assimilate(user, pid, ladder, float(ref["value"]), "mg/dL", float(ref["value"]), float(ref["t_min"]),
                            observed, "replay", _lang(lang), None, f"reveal-{ladder}-{u.offset}", u)
    return clean({"reference": {"t": ref["t"], "value": ref["value"],
                                "source_en": "Dataset reference CGM — hidden from the twin until revealed"},
                  "before": before, "after": after})


@app.get("/api/twin/{pid}/outlook_90d", tags=["twin"], response_model=S.Outlook, response_model_exclude_unset=True,
         summary="outlook_90d: projected time in range and eHbA1c (a projection, not a prediction)")
def twin_outlook(pid: str, ladder: LadderQ = "2", user: User = Depends(current_user)) -> Any:
    _persona(pid)
    u = _uctx(user, pid)
    return clean(get_engine().outlook_90d(pid, _ladder(ladder), _eng_events(u), offset=u.offset, rev=u.rev))


@app.get("/api/twin/{pid}/explain/{forecast_id}", tags=["twin"], response_model=S.Explanation,
         response_model_exclude_unset=True,
         summary="explain: ranked physiology drivers and learned (SHAP) drivers, reported separately")
def twin_explain(pid: str, forecast_id: str, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    ctx = get_engine().forecast_context(forecast_id)
    if not _owned(user, pid, forecast_id) or ctx is None or ctx.get("pid") != pid:
        raise HTTPException(404, "Forecast not found for this patient; request a new forecast")
    ex = get_engine().explain(forecast_id)
    if ex is None:
        raise HTTPException(404, "No explanation for this forecast (what-if scenarios are explained by their assumptions)")
    with session() as s:
        last = s.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.persona_id == pid)
                         .order_by(AuditLog.id.desc()).limit(1)).first()
        if last:
            ex["tool_calls"] = last.tool_calls
    return clean(ex)


@app.get("/api/twin/{pid}/receipt/{forecast_id}", tags=["twin"],
         summary="receipt: the evidence behind one forecast (claims with status and source); ?format=md downloads it")
def twin_receipt(pid: str, forecast_id: str, lang: str = DEFAULT_LANG,
                 format: Literal["json", "md"] = Query("json"),  # noqa: A002 - public query name
                 user: User = Depends(current_user)) -> Any:
    p = _persona(pid)
    e = get_engine()
    ctx = e.forecast_context(forecast_id)
    if not _owned(user, pid, forecast_id) or ctx is None or ctx.get("pid") != pid:
        raise HTTPException(404, "Forecast not found for this patient; request a new forecast")
    r = RC.build(e, ctx, forecast_id, p, _lang(lang))
    if format == "md":
        return Response(RC.markdown(r), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="receipt_{pid}_{forecast_id}.md"'})
    return clean(r)


@app.post("/api/twin/{pid}/reset", tags=["twin"], response_model=S.Ok, response_model_exclude_unset=True,
          summary="reset: forget this user's readings, meals, pending chat actions and replay clock for the persona")
def twin_reset(pid: str, labs: int = 0, user: User = Depends(current_user)) -> Any:
    _persona(pid)
    with session() as s:
        s.execute(delete(TwinEvent).where(TwinEvent.user_id == user.id, TwinEvent.persona_id == pid))
        s.execute(delete(ReplayClock).where(ReplayClock.user_id == user.id, ReplayClock.persona_id == pid))
        s.execute(delete(PendingAction).where(PendingAction.user_id == user.id, PendingAction.persona_id == pid))
        if labs:
            s.execute(delete(CovariateRevision).where(CovariateRevision.user_id == user.id,
                                                      CovariateRevision.persona_id == pid))
            s.execute(delete(FhirResource).where(FhirResource.user_id == user.id, FhirResource.persona_id == pid))
    return {"ok": True}


# ----------------------------------------------------------------------------- food & meals
@app.get("/api/food/search", tags=["food & meals"])
def food_search(q: str = "", lang: str = DEFAULT_LANG, user: User = Depends(current_user)) -> list[dict]:
    return food.search(q, lang)


@app.get("/api/food/swaps", tags=["food & meals"])
def food_swaps(lang: str = DEFAULT_LANG, user: User = Depends(current_user)) -> list[dict]:
    """Curated swaps with ``label`` in the requested language (``label_en`` always included)."""
    return food.swaps_localised(lang)


@app.get("/api/meal/samples", tags=["food & meals"])
def meal_samples(user: User = Depends(current_user)) -> list[dict]:
    return MEAL.samples()


@app.post("/api/meal/photo", tags=["food & meals"])
async def meal_photo(image: UploadFile | None = File(None), sample_id: str | None = Form(None, max_length=80),
                     lang: str = Form(DEFAULT_LANG), user: User = Depends(rate_limited("meal_photo"))) -> dict:
    data, mime = None, "image/jpeg"
    if image is not None:
        data = await _read_bounded(image, get_settings().max_image_bytes)
        mime = image.content_type or mime
    if data is not None and not mime.startswith("image/"):
        raise HTTPException(415, "Please upload an image (JPEG, PNG or WebP).")
    vs = _vision_status()
    if data is not None and not vs["enabled"]:
        raise HTTPException(503, {"code": "vision_unavailable", "message": vs["reason"]})
    try:
        out = MEAL.parse(data, mime, sample_id, _lang(lang), user_key=str(user.id))
    except LAB.UnknownSample:
        raise HTTPException(404, "Unknown sample id") from None
    except LLMUnavailable as exc:
        raise HTTPException(503, {"code": "vision_unavailable", "message": str(exc)}) from exc
    if out.get("source") == "live":
        out["recognition"] = {"model": vs["model"], "nvidia": vs["nvidia"], "provider": LLM.PROVIDER,
                              "note": "Dish candidates only; confirm them. Nutrition comes from the food table."}
    else:
        out["recognition"] = {"model": out.get("model"), "nvidia": False, "provider": "recorded fixture",
                              "note": "Recorded result for this sample photo, not a live call."}
    return out


def _sample_files(kind: str) -> set[str]:
    d = FIXTURES_DIR / "samples" / kind / "samples.json"
    try:
        return {str(s["file"]) for s in json.loads(d.read_text())}
    except (OSError, ValueError, KeyError):
        return set()


@app.get("/api/samples/{kind}/{name}", tags=["demo"])
def sample_file(kind: str, name: str) -> FileResponse:
    if kind not in ("meals", "labs") or name not in _sample_files(kind):
        raise HTTPException(404)
    p = FIXTURES_DIR / "samples" / kind / name
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)


# ----------------------------------------------------------------------------- agent & speech
class ChatIn(BaseModel):
    patient_id: str
    text: str = Field(min_length=1, max_length=600)
    lang: str = DEFAULT_LANG
    ladder: LadderQ = "2"
    skip_slots: list[Literal["portion", "unit", "time", "food"]] = Field(default_factory=list, max_length=4)


def _cached_audio(text: str, lang: str, synthesize: bool) -> str | None:
    """No server audio in NemoTwins: Token Factory has no speech model and no other provider may be
    called, so replies carry ``audio_url = null``."""
    return None


def _store_pending(user: User, pid: str, out: dict, lang: str, ladder: str) -> None:
    pa = out.get("pending_action")
    if not pa:
        out["pending_action"] = None
        return
    aid = uuid.uuid4().hex
    with session() as s:
        s.add(PendingAction(id=aid, user_id=user.id, persona_id=pid, kind=pa["kind"], payload=pa["payload"],
                            summary_en=pa["summary_en"], lang=lang, ladder=ladder))
    out["pending_action"] = {"id": aid, "kind": pa["kind"], "summary_en": pa["summary_en"],
                             "payload": {k: v for k, v in pa["payload"].items() if k != "symptoms_text"}}


def _redact(text: str) -> str:
    """Raw conversation text is not stored unless AUDIT_STORE_TEXT=true (health data minimisation)."""
    if get_settings().audit_store_text:
        return text
    return f"[not stored: {len(text or '')} chars, sha256 {hashlib.sha256((text or '').encode()).hexdigest()[:12]}]"


def _audit(user: User, pid: str, lang: str, text: str, out: dict) -> None:
    with session() as s:
        s.add(AuditLog(user_id=user.id, persona_id=pid, lang=lang, request_text=_redact(text),
                       reply_text=_redact(out["reply"]), intent=out["intent"], tool_calls=_jsonable(out["tool_calls"]),
                       grounding=_jsonable(out["grounding"]), safety=_jsonable(out["safety"]),
                       source=str(out["source"])[:20]))


@app.post("/api/agent/chat", tags=["agent & speech"], response_model=S.AgentReply, response_model_exclude_unset=True)
def agent_chat(body: ChatIn, user: User = Depends(rate_limited("chat"))) -> Any:
    p = _persona(body.patient_id)
    lang = _lang(body.lang)
    ladder = _ladder(body.ladder)
    u = _uctx(user, p["id"])
    out = agent().handle(body.text, lang, p["id"], ladder, _eng_events(u), offset=u.offset, rev=u.rev,
                         skip_slots=list(body.skip_slots))
    out.pop("new_events", None)  # chat never mutates; mutations go through /api/agent/confirm
    _store_pending(user, p["id"], out, lang, ladder)
    for c in out["tool_calls"]:
        fid = (c.get("output") or {}).get("forecast_id") if isinstance(c.get("output"), dict) else None
        _own(user, p["id"], fid)
    out["audio_url"] = _cached_audio(out["reply"], lang, synthesize=get_settings().live)
    _audit(user, p["id"], lang, body.text, out)
    return clean(out)


class ConfirmIn(BaseModel):
    action_id: str = Field(min_length=1, max_length=40)
    confirm: bool
    lang: str | None = None


@app.post("/api/agent/confirm", tags=["agent & speech"], response_model=S.AgentReply, response_model_exclude_unset=True,
          summary="confirm or cancel a pending chat action (log a reading / meal) through the shared safety policy")
def agent_confirm(body: ConfirmIn, user: User = Depends(current_user)) -> Any:
    with session() as s:
        pa = s.get(PendingAction, body.action_id)
        if pa is None or pa.user_id != user.id or pa.status != "pending":
            raise HTTPException(404, "No such pending action")
        action = {"kind": pa.kind, "payload": dict(pa.payload or {})}
        pid, lang, ladder = pa.persona_id, _lang(body.lang or pa.lang), pa.ladder
        pa.status = "done" if body.confirm else "cancelled"
    u = _uctx(user, pid)
    out = agent().confirm(action, body.confirm, lang, pid, ladder, _eng_events(u), offset=u.offset, rev=u.rev)
    out = agent().decorate_confirm(out, pid, ladder, _eng_events(u), lang)
    for ev in out.pop("new_events", []):
        observed = get_engine().display_time(pid, float(ev.get("t_min", u.offset))).replace(tzinfo=IST)
        unit = "mg/dL" if ev["kind"] == "reading" else None
        _add_event(user, pid, {**ev, "observed_at": observed.isoformat(timespec="minutes")}, observed_at=observed,
                   unit=unit)
    a = out.pop("assimilation", None)
    if a:
        out["width_change"] = a.get("width_change")
        _own(user, pid, a["state"]["forecast"]["forecast_id"])
    out["pending_action"] = None
    out["audio_url"] = _cached_audio(out["reply"], lang, synthesize=get_settings().live)
    _audit(user, pid, lang, f"[confirm {action['kind']}: {body.confirm}]", out)
    return clean(out)


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(clean(x), default=str))


def _speech_501() -> HTTPException:
    return HTTPException(501, {"code": "speech_unavailable", "message": speech.REASON})


@app.post("/api/speech/stt", tags=["agent & speech"], summary="Unavailable in NemoTwins (no Token Factory speech model)")
async def speech_stt(user: User = Depends(rate_limited("stt"))) -> dict:
    raise _speech_501()


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    lang: str = DEFAULT_LANG


@app.post("/api/speech/tts", tags=["agent & speech"], response_class=Response,
          summary="Unavailable in NemoTwins (no Token Factory speech model)")
def speech_tts(body: TTSIn, user: User = Depends(rate_limited("tts"))) -> Response:
    raise _speech_501()




@app.get("/api/demo/voice_samples", tags=["agent & speech"])
def voice_samples(user: User = Depends(current_user)) -> list[dict]:
    """Voice samples: none (no Token Factory speech model)."""
    return []


# ----------------------------------------------------------------------------- lab & FHIR
@app.get("/api/lab/samples", tags=["lab & FHIR"])
def lab_samples(user: User = Depends(current_user)) -> list[dict]:
    return LAB.samples()


@app.post("/api/lab/parse", tags=["lab & FHIR"])
async def lab_parse(file: UploadFile | None = File(None), sample_id: str | None = Form(None, max_length=80),
                    user: User = Depends(rate_limited("lab_parse"))) -> dict:
    data, mime = None, "image/jpeg"
    if file is not None:
        mime = file.content_type or mime
        if mime == "application/pdf":
            raise HTTPException(415, "Please upload a photo or screenshot of the report (PDF reading is not enabled)")
        data = await _read_bounded(file, get_settings().max_image_bytes)
    try:
        return LAB.parse(data, mime, sample_id, user_key=str(user.id))
    except LAB.UnknownSample:
        raise HTTPException(404, "Unknown sample id") from None
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


class LabFieldIn(BaseModel):
    code: str = Field(max_length=40)
    name: str = Field("", max_length=120)
    value: float | str
    unit: str = Field("", max_length=40)
    ref_range: str = Field("", max_length=60)
    implausible: bool = False
    loinc: str | None = None
    original_value: float | str | None = None
    original_unit: str | None = Field(None, max_length=40)
    collection_date: str | None = Field(None, max_length=30)
    unit_assumed: bool = False

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float | str) -> float | str:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("value must be a finite number")
        if isinstance(v, str) and len(v) > 200:
            raise ValueError("value too long")
        return v


class LabConfirmIn(BaseModel):
    patient_id: str
    fields: list[LabFieldIn] = Field(max_length=50)


@app.post("/api/lab/confirm", tags=["lab & FHIR"])
def lab_confirm(body: LabConfirmIn, user: User = Depends(current_user)) -> dict:
    """Store the user-confirmed FHIR resources AND, for model-supported fields (HbA1c, BMI), a covariate
    revision that re-personalises this user's twin (EHR-conditioned prior -> CEM calibration)."""
    p = _persona(body.patient_id)
    fields: list[dict] = []
    for f in (x.model_dump() for x in body.fields):
        if f["code"] in LAB.FIELDS:
            try:
                f["value"] = float(f["value"])
                f = LAB.normalise_confirmed(f)
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, f"{f['code']}: {exc}" if isinstance(exc, LAB.UnitError)
                                    else f"{f['code']}: value must be a number") from None
        fields.append(f)
    confirmed_at = datetime.now(UTC).isoformat(timespec="seconds")
    bundle_id, res = LAB.to_fhir({**p, "sex": _cov(p)["sex"]}, fields, confirmed_at=confirmed_at)
    rev_fields = {f["code"]: {"value": f["value"], "unit": f["unit"], "original_value": f.get("original_value"),
                              "original_unit": f.get("original_unit"), "collection_date": f.get("collection_date"),
                              "confirmed_at": confirmed_at}
                  for f in fields if f["code"] in REVISION_FIELDS and not f.get("implausible")}
    revision = None
    with session() as s:
        for r in res:
            s.add(FhirResource(id=r["id"], user_id=user.id, persona_id=p["id"], resource_type=r["resourceType"],
                               bundle_id=bundle_id, resource=r))
        if rev_fields:
            n = s.scalar(select(func.max(CovariateRevision.revision)).where(
                CovariateRevision.user_id == user.id, CovariateRevision.persona_id == p["id"])) or 0
            s.add(CovariateRevision(user_id=user.id, persona_id=p["id"], revision=int(n) + 1, fields=rev_fields,
                                    bundle_id=bundle_id))
            revision = {"revision": int(n) + 1, "fields": rev_fields}
    if revision:
        rev = _uctx(user, p["id"]).rev
        if rev:  # build the re-personalised twin in the background (default ladder first)
            threading.Thread(target=_warm_revision, args=(p["id"], rev), daemon=True).start()
    return clean({"bundle_id": bundle_id, "resource_count": len(res), "revision": revision,
                  "repersonalising": bool(revision),
                  "note": ("HbA1c / BMI changes re-personalise the twin (EHR-conditioned prior, then CEM calibration). "
                           "Other fields are stored and exported only.")})


def _warm_revision(pid: str, rev: dict) -> None:
    try:
        get_engine().warm_revision(pid, rev, ("2", "full", "4", "1", "0"))
    except Exception:  # noqa: BLE001 - background warm-up; the request path builds lazily anyway
        log.exception("revision warm-up failed")


@app.get("/api/fhir/{pid}/bundle", tags=["lab & FHIR"])
def fhir_bundle(pid: str, user: User = Depends(current_user)) -> JSONResponse:
    p = _persona(pid)
    with session() as s:
        rows = s.scalars(select(FhirResource).where(FhirResource.persona_id == pid, FhirResource.user_id == user.id)
                         .order_by(FhirResource.created_at)).all()
        resources = [r.resource for r in rows]
    b = LAB.bundle({**p, "sex": _cov(p)["sex"]}, resources)
    return SafeJSONResponse(b, headers={"Content-Disposition": f'attachment; filename="{pid}_fhir_bundle.json"'})


# ----------------------------------------------------------------------------- doctor
@app.get("/api/doctor/panel", tags=["doctor"])
def doctor_panel(user: User = Depends(require_clinician)) -> list[dict]:
    rows = [_summary(p, user) for p in PS.PERSONAS]
    return clean(sorted(rows, key=lambda s: -(s["risk_7d"] if s["risk_7d"] is not None else -1.0)))


def _walk_suggestion(pid: str, u: UCtx) -> tuple[str | None, dict | None]:
    """'15-minute walk after the usual dinner' from an actual what-if tool result, or nothing."""
    e = get_engine()
    carbs = e.usual_meal_carbs(pid)
    if carbs < 10:
        return None, None
    base = {"name": "usual dinner", "carbs": carbs}
    scen = {"walk_min": 15.0, "walk_after_min": 15.0, "label": "15-minute walk after the usual dinner"}
    w = e.what_if(pid, "2", _eng_events(u), base, scen, offset=u.offset, rev=u.rev)
    dp, ci = w["delta_peak"], w["delta_peak_ci"]
    detail = {"kind": "walk_what_if", "base_meal": base, "scenario": scen, "delta_peak": dp,
              "delta_peak_ci": {"lo": ci["lo"], "hi": ci["hi"]}, "delta_p_high": w["delta_p_high"],
              "too_small_to_call": w["too_small_to_call"], "label_en": w["label_en"],
              "assumptions_en": w["assumptions_en"], "baseline_forecast_id": w["baseline"]["forecast_id"],
              "scenario_forecast_id": w["scenario"]["forecast_id"]}
    if w["too_small_to_call"]:
        text = (f"Twin simulation: a 15-minute walk after the usual dinner (about {carbs:.0f} g carbohydrate) changes "
                "the expected peak too little to call. Model simulation, not a proven effect.")
    else:
        text = (f"Twin simulation: a 15-minute walk after the usual dinner (about {carbs:.0f} g carbohydrate) changes "
                f"the expected 2-hour peak by {dp:+.0f} mg/dL (simulation interval {ci['lo']:+.0f} to {ci['hi']:+.0f}). "
                "Model simulation, not a proven effect; consider discussing post-meal walks.")
    return text, detail


@app.get("/api/doctor/brief/{pid}", tags=["doctor"])
def doctor_brief(pid: str, user: User = Depends(require_clinician)) -> dict:
    p = _persona(pid)
    e = get_engine()
    u = _uctx(user, pid)
    s7 = e.summary_7d(pid, offset=u.offset)
    v = s7["values"]
    hypo = int(((v[1:] < 70) & (v[:-1] >= 70)).sum()) if len(v) > 1 else None
    hyper = int(((v[1:] > 250) & (v[:-1] <= 250)).sum()) if len(v) > 1 else None
    # The patient's own next 4 h with no new meal (no invented meal), from this user's events and clock.
    fc = e.forecast(pid, "2", _eng_events(u), None, with_drivers=True, offset=u.offset, rev=u.rev)
    _own(user, pid, fc["forecast_id"])
    top_d = fc["drivers"][0] if fc["drivers"] else None
    top = top_d["label_en"] if top_d else ""
    sugg = []
    if s7["tar_7d"] is not None and s7["tar_7d"] > 0.25:
        sugg.append("Historical time above 180 (reference CGM, last 7 days) exceeds 25%: review meal carbohydrate "
                    "distribution, especially dinner.")
    if hypo:
        sugg.append("Low readings recorded: review with the patient before any medication change.")
    walk_text, walk_detail = _walk_suggestion(pid, u)
    if walk_text:
        sugg.append(walk_text)
    op = _operational(user, p, u)
    r1 = lambda x: None if x is None else round(float(x), 1)  # noqa: E731
    r3 = lambda x: None if x is None else round(float(x), 3)  # noqa: E731
    r2 = lambda x: None if x is None else round(float(x), 2)  # noqa: E731
    return clean({"patient": _detail(p, user, u), "tir_7d": r3(s7["tir_7d"]), "mean_glucose": r1(s7["mean"]),
                  "gmi": r2(s7["gmi"]), "hypo_events_7d": hypo, "hyper_events_7d": hyper,
                  "reference_note": "tir_7d, mean_glucose, gmi, event counts and daily_profile are HISTORICAL "
                                    "statistics from the dataset reference CGM (hidden from the sparse twin).",
                  "daily_profile": e.daily_profile(pid, offset=u.offset), "top_driver": top,
                  "top_driver_detail": top_d and {"name": top_d["name"], "contribution": top_d["contribution"],
                                                  "source": top_d["source"],
                                                  "basis": "largest driver of the twin's 4-hour forecast with no new meal",
                                                  "forecast_id": fc["forecast_id"]},
                  "operational": op, "replay": e.replay_info(pid, u.offset),
                  "suggestions": sugg, "suggestion_details": [walk_detail] if walk_detail else [],
                  "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                  "disclaimer": "Decision support only. Not a medical device. Clinical judgement required."})


def _reasons(p: dict, user: User, u: UCtx) -> tuple[list[dict], dict]:
    op = _operational(user, p, u)
    reasons: list[dict] = []
    if op["data_gap"]:
        age = op["last_reading_age_h"]
        reasons.append({"kind": "missing_data", "detail_en": (f"No glucose reading for {age:.1f} h on the replay clock."
                                                              if age is not None else "No glucose reading yet.")})
    recent = [e for e in u.events if e["kind"] == "reading" and u.offset - float(e["t_min"]) <= 24 * 60]
    for e in recent[-3:]:
        lvl = safety.reading_level(float(e["value"]))
        if lvl != "ok":
            reasons.append({"kind": "concerning_observation",
                            "detail_en": f"Reading of {float(e['value']):.0f} mg/dL ({lvl.replace('_', ' ')}), "
                                         f"entered via {e.get('source', 'manual')}."})
    ph = op["p_high_2h"]
    if ph is not None and ph >= 0.5:
        reasons.append({"kind": "model_risk", "detail_en": f"Twin estimates P(>180 in the next 2 h) = {ph:.2f} "
                                                           "(held-out reliability in the forecast receipt)."})
    return reasons, op


@app.get("/api/doctor/queue", tags=["doctor"])
def doctor_queue(user: User = Depends(require_clinician)) -> list[dict]:
    with session() as s:
        reviews = {r.persona_id: r for r in s.scalars(select(DoctorReview).where(DoctorReview.user_id == user.id)).all()}
        rv = {pid: {"status": r.status, "note": r.note, "at": r.at.isoformat(timespec="seconds") if r.at else None,
                    "by": r.by} for pid, r in reviews.items()}
    out = []
    order = {"concerning_observation": 0, "model_risk": 1, "missing_data": 2}
    for p in PS.PERSONAS:
        u = _uctx(user, p["id"])
        reasons, op = _reasons(p, user, u)
        out.append({"pid": p["id"], "name": p["name"], "reasons": reasons, "freshness": op["freshness"],
                    "operational": op,
                    "review": rv.get(p["id"], {"status": "unreviewed", "note": "", "at": None, "by": None})})
    out.sort(key=lambda r: (min([order[x["kind"]] for x in r["reasons"]] or [9]), -len(r["reasons"])))
    return clean(out)


class ReviewIn(BaseModel):
    status: Literal["unreviewed", "reviewed", "follow_up"]
    note: str = Field("", max_length=1000)


@app.post("/api/doctor/review/{pid}", tags=["doctor"])
def doctor_review(pid: str, body: ReviewIn, user: User = Depends(require_clinician)) -> dict:
    _persona(pid)
    now = datetime.now(UTC)
    with session() as s:
        r = s.get(DoctorReview, (user.id, pid))
        if r is None:
            s.add(DoctorReview(user_id=user.id, persona_id=pid, status=body.status, note=body.note, by=user.username,
                               at=now))
        else:
            r.status, r.note, r.by, r.at = body.status, body.note, user.username, now
    return {"pid": pid, "review": {"status": body.status, "note": body.note, "at": now.isoformat(timespec="seconds"),
                                   "by": user.username}}


# ----------------------------------------------------------------------------- trust
REPORT_TITLES = {
    "summary": "Headline results", "sensor_ladder": "Sensor-ladder ablation", "calibration_length": "Calibration length",
    "baselines": "Baselines", "nbp_value": "Next-best-prick value", "transfer": "Cross-population transfer",
    "subgroups": "Subgroup audit", "calibration_curve": "Calibration curves", "error_grid": "Clarke error grid",
    "agent_multilingual": "Multilingual Nemotron agent suite",
}


@app.get("/api/reports", tags=["trust"])
def reports(user: User = Depends(current_user)) -> list[dict]:
    out = []
    for name, title in REPORT_TITLES.items():
        p = REPORTS_DIR / f"{name}.json"
        if p.exists():
            out.append({"name": name, "title": title,
                        "generated_at": json.loads(p.read_text()).get("generated_at", "")})
    return out


@app.get("/api/reports/{name}", tags=["trust"])
def report(name: str, user: User = Depends(current_user)) -> JSONResponse:
    if name not in REPORT_TITLES:
        raise HTTPException(404)
    p = REPORTS_DIR / f"{name}.json"
    if not p.exists():
        raise HTTPException(404, "Report not yet generated")
    return SafeJSONResponse(json.loads(p.read_text()))


@app.get("/api/reports/figures/{name}", tags=["trust"])
def report_figure(name: str) -> FileResponse:
    figs = REPORTS_DIR / "figures"
    p = (figs / name).resolve()
    if "/" in name or "\\" in name or not p.is_relative_to(figs.resolve()) or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)


# ----------------------------------------------------------------------------- demo
TOUR = [
    {"id": "stage", "title_en": "Meet the twin", "route": "/", "action": "river",
     "body_en": "This is a synthetic persona's glucose twin on a replay clock. Dots are measured readings; the curve is "
                "the twin's estimate and its forecast for the next 4 hours with an uncertainty band (retrospectively "
                "evaluated to 2 hours, exploratory after)."},
    {"id": "ladder", "title_en": "After a 5-day CGM calibration wear", "route": "/", "action": "ladder",
     "body_en": "Switch from full CGM to 2 finger-pricks a day. The forecast keeps working; the band widens to stay honest."},
    {"id": "prick", "title_en": "Add a reading", "route": "/", "action": "add-reading",
     "body_en": "Enter a measured finger-prick with its unit. Safety comes first; then see how the band changes "
                "(it can narrow or, after a surprise, widen)."},
    {"id": "meal", "title_en": "Meal to forecast", "route": "/meal", "action": "meal-samples",
     "body_en": "Pick or enter a meal. Confirm the dishes, then compare two possible futures (an exploratory simulation)."},
    {"id": "voice", "title_en": "Ask in your language", "route": "/talk", "action": "voice-orb",
     "body_en": "Ask in English, Spanish, French, German, Italian or Japanese. NVIDIA Nemotron on Nebius Token Factory "
                "picks the twin's tools; every number in the answer comes from the twin."},
]


@app.get("/api/demo/tour", tags=["demo"])
def tour(user: User = Depends(current_user)) -> dict:
    return {"steps": TOUR}


# ----------------------------------------------------------------------------- single-container web serving
# In the Nebius serverless image the built frontend is copied to STATIC_DIR and served here, so one
# endpoint (one managed HTTPS URL) hosts both the SPA and /api. Unset in local dev and docker compose.
_STATIC = Path(os.environ["STATIC_DIR"]).resolve() if os.environ.get("STATIC_DIR") else None
if _STATIC is not None and (_STATIC / "index.html").is_file():
    STATIC_ROOT: Path = _STATIC
    _SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(404)
        target = (STATIC_ROOT / path).resolve()
        if path and target.is_file() and target.is_relative_to(STATIC_ROOT):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(target, headers={**_SECURITY_HEADERS, "Cache-Control": cache})
        return FileResponse(STATIC_ROOT / "index.html", headers={**_SECURITY_HEADERS, "Cache-Control": "no-cache"})


__all__ = ["app", "clean", "RATE"]
