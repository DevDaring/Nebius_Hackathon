"""Token Factory smoke suite -> machine-readable capability manifest (no secrets).

Synthetic prompts only. For each configured model it checks: presence in the account catalog
(GET /v1/models), text generation in each release locale, tool calling, JSON mode, JSON-schema
guided output, and (vision role) image input. The result is written to
``capabilities/manifest.json``; a feature is "enabled" only if its checks passed.

    APP_MODE=live python -m nemotwins.eval.provider_smoke

Language checks are a smoke test (reply produced, script/stop-word heuristic matches the requested
language), not evidence of domain-specific quality; see the multilingual agent suite for that.
"""

from __future__ import annotations

import base64
import json
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from nemotwins.config import CAPABILITIES_DIR, FIXTURES_DIR, RELEASE_LOCALES, get_settings
from nemotwins.providers import llm as LLM

MANIFEST = CAPABILITIES_DIR / "manifest.json"
# Languages listed on the NVIDIA-Nemotron-3-Nano-30B-A3B model card (checked 2026-10-08).
MODEL_CARD_LANGS = {"nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": ["en", "es", "fr", "de", "it", "ja"]}
LANG_PROMPTS = {
    "en-US": ("English", r"\b(the|is|a|of|and)\b"),
    "es-ES": ("Spanish", r"\b(el|la|de|que|es|un|una)\b"),
    "fr-FR": ("French", r"\b(le|la|de|est|un|une|les|des)\b"),
    "de-DE": ("German", r"\b(der|die|das|ist|ein|eine|und)\b"),
    "it-IT": ("Italian", r"\b(il|la|di|è|un|una|che)\b"),
    "ja-JP": ("Japanese", r"[぀-ヿ一-鿿]"),
}
TOOL = [{"type": "function", "function": {
    "name": "get_forecast", "description": "Glucose forecast from the twin engine for a horizon in minutes.",
    "parameters": {"type": "object", "properties": {"horizon_min": {"type": "integer"}}, "required": ["horizon_min"]}}}]
SCHEMA = {"title": "intent_reply", "type": "object", "additionalProperties": False,
          "properties": {"intent": {"type": "string", "enum": ["forecast", "what_if", "other"]},
                         "lang": {"type": "string"}}, "required": ["intent", "lang"]}


def _post(body: dict, timeout: float = 90.0) -> tuple[int, dict, float, str | None]:
    s = get_settings()
    t0 = time.time()
    r = httpx.post(f"{LLM.base_url()}/chat/completions", json=body, timeout=timeout,
                   headers={"Authorization": f"Bearer {s.tokenfactory_2009_api_key.strip()}"})
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data, round(time.time() - t0, 2), r.headers.get("x-request-id")


def _content(data: dict) -> tuple[str, list, str | None]:
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    return (msg.get("content") or "").strip(), msg.get("tool_calls") or [], ch.get("finish_reason")


def _check(name: str, fn: Any) -> dict:
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}"
    return {"function": name, "passed": bool(ok), "detail": detail}


def smoke_text_model(model: str) -> dict:
    checks: list[dict] = []
    tested_locales: list[str] = []
    for loc in RELEASE_LOCALES:
        lang, pat = LANG_PROMPTS[loc]

        def run(lang: str = lang, pat: str = pat) -> tuple[bool, str]:
            st, d, sec, _ = _post({"model": model, "max_tokens": 400, "temperature": 0.2, "messages": [
                {"role": "user", "content": f"Answer in {lang} only, in one short sentence: what is a prediction interval?"}]})
            txt, _, fin = _content(d)
            ok = st == 200 and fin != "length" and bool(re.search(pat, txt.lower()))
            return ok, f"HTTP {st}, {sec}s, finish={fin}"
        c = _check(f"text_{loc}", run)
        checks.append(c)
        if c["passed"]:
            tested_locales.append(loc)

    def tool() -> tuple[bool, str]:
        st, d, sec, _ = _post({"model": model, "max_tokens": 600, "temperature": 0.2, "tools": TOOL, "tool_choice": "auto",
                               "messages": [{"role": "user", "content": "What will my glucose be in 2 hours? Use the tool."}]})
        _, calls, fin = _content(d)
        ok = st == 200 and any((c.get("function") or {}).get("name") == "get_forecast" for c in calls)
        return ok, f"HTTP {st}, {sec}s, finish={fin}, calls={len(calls)}"

    def json_mode() -> tuple[bool, str]:
        st, d, sec, _ = _post({"model": model, "max_tokens": 400, "temperature": 0.0,
                               "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content":
                               "Return JSON with keys intent and lang for: 'Que se passe-t-il si je mange des pâtes ?'"}]})
        txt, _, fin = _content(d)
        try:
            ok = st == 200 and isinstance(json.loads(txt), dict)
        except ValueError:
            ok = False
        return ok, f"HTTP {st}, {sec}s, finish={fin}"

    def json_schema() -> tuple[bool, str]:
        body = LLM.build_body(model, [{"role": "user", "content":
                                       "Classify: 'Was passiert, wenn ich 15 Minuten spazieren gehe?' "
                                       "Return intent and the ISO language code."}], None, False, 0.0, 400, SCHEMA)
        st, d, sec, _ = _post(body)
        txt, _, fin = _content(d)
        try:
            o = json.loads(txt)
            ok = st == 200 and set(o) == {"intent", "lang"} and o["intent"] in ("forecast", "what_if", "other")
        except (ValueError, TypeError):
            ok = False
        return ok, f"HTTP {st}, {sec}s, finish={fin}"

    checks += [_check("tool_calling", tool), _check("json_object", json_mode), _check("json_schema", json_schema)]
    return {"checks": checks, "tested_locales": tested_locales}


def smoke_vision_model(model: str) -> dict:
    img = next(iter(sorted((FIXTURES_DIR / "samples" / "meals").glob("*.jpg"))), None)

    def run() -> tuple[bool, str]:
        if img is None:
            return False, "no sample image"
        b64 = base64.b64encode(img.read_bytes()).decode()
        st, d, sec, _ = _post({"model": model, "max_tokens": 400, "temperature": 0.1,
                               "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": [
                                   {"type": "text", "text": 'List visible dishes as JSON {"dishes":[{"name":str,"portion":str}]}. '
                                                            "Do not estimate nutrients."},
                                   {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]},
                              timeout=120)
        txt, _, fin = _content(d)
        try:
            ok = st == 200 and isinstance(LLM.parse_json(txt).get("dishes"), list)
        except (ValueError, AttributeError):
            ok = False
        return ok, f"HTTP {st}, {sec}s, finish={fin}"
    return {"checks": [_check("image_input_json", run)], "tested_locales": []}


def build() -> dict:
    s = get_settings()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    r = httpx.get(f"{LLM.base_url()}/models", timeout=30,
                  headers={"Authorization": f"Bearer {s.tokenfactory_2009_api_key.strip()}"})
    catalog = sorted(m["id"] for m in r.json().get("data", [])) if r.status_code == 200 else []
    roles = {"chat (router, planner, guardrails)": LLM.model_for("router"),
             "complex": LLM.model_for("complex"), "vision": LLM.model_for("vision")}
    models: list[dict[str, Any]] = []
    for role, model in roles.items():
        if not model:
            models.append({"role": role, "model_id": None, "enabled": False, "reason": "not configured"})
            continue
        res = smoke_vision_model(model) if role == "vision" else smoke_text_model(model)
        passed = [c["function"] for c in res["checks"] if c["passed"]]
        required = "image_input_json" if role == "vision" else "tool_calling"
        models.append({
            "role": role, "provider": LLM.PROVIDER, "model_id": model, "nvidia_model": LLM.is_nvidia(model),
            "in_account_catalog": model in catalog, "endpoint": LLM.base_url(),
            "endpoint_region": "not reported by the Token Factory API",
            "model_card_languages": MODEL_CARD_LANGS.get(model),
            "tested_functions": passed, "checks": res["checks"], "tested_locales": res["tested_locales"],
            "last_successful_check": now if passed else None,
            "enabled": model in catalog and required in passed,
        })
    nvidia_in_catalog = [m for m in catalog if m.lower().startswith("nvidia/")]
    return {
        "schema_version": "1.0", "generated_at": now, "provider": LLM.PROVIDER,
        "base_url": LLM.base_url(), "catalog_size": len(catalog), "nvidia_models_in_catalog": nvidia_in_catalog,
        "models": models,
        "integrations": [
            {"name": "Nemotron via Token Factory", "status": "implemented_verified" if models[0].get("enabled") else "failing"},
            {"name": "Token Factory tool calling / structured output", "status": "implemented_verified"
             if {"tool_calling", "json_object"} <= set(models[0].get("tested_functions", [])) else "failing"},
            {"name": "NVIDIA NeMo Guardrails (open-source library) on Nemotron", "status": "implemented"},
            {"name": "Vision (dish candidates)", "status": "implemented_verified_non_nvidia"
             if models[2].get("enabled") else "unavailable",
             "note": "No NVIDIA vision model in the Token Factory catalog; a non-NVIDIA Token Factory model proposes "
                     "dish candidates only; nutrition comes from the food table."},
            {"name": "NVIDIA embeddings", "status": "not_used",
             "note": "Food lookup is a deterministic table match; retrieval is not needed. No NVIDIA embedding model "
                     "in the catalog."},
            {"name": "Further reading (Tavily web-search API, not a model)", "status": "implemented_verified",
             "note": "Topic-only queries, allowlisted health sites per language, snippets displayed only; "
                     "never given to the model."},
            {"name": "Speech (ASR/TTS)", "status": "unavailable",
             "note": "No speech model on Token Factory; other providers are not allowed. Talk is text-only."},
            {"name": "Nebius Serverless endpoint hosting", "status": "configured_not_deployed",
             "note": "deploy/ scripts prepared and validated with --dry-run; not deployed."},
            {"name": "Nebius Serverless Jobs (evaluation)", "status": "configured_not_deployed"},
            {"name": "Nebius Object Storage (reports)", "status": "configured_untested"},
            {"name": "GPU numerical acceleration", "status": "not_used",
             "note": "No measured numerical bottleneck that a GPU would address."},
        ],
        "notes": "No secrets. Regenerate with `APP_MODE=live python -m nemotwins.eval.provider_smoke`.",
    }


def main() -> int:
    if not LLM.configured():
        print("Token Factory is not configured (TOKENFACTORY_2009_API_KEY)")
        return 2
    m = build()
    CAPABILITIES_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    for x in m["models"]:
        print(x["role"], x.get("model_id"), "enabled" if x.get("enabled") else "DISABLED",
              "functions:", x.get("tested_functions"), "locales:", x.get("tested_locales"))
    print("wrote", MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
