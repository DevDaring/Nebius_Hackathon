"""Nebius Token Factory adapter: the only language-model route in NemoTwins.

Token Factory exposes an OpenAI-compatible Chat Completions API. This module talks to it over
plain HTTPS (httpx); no request ever goes to any other model provider. The credential is read from
``TOKENFACTORY_2009_API_KEY`` explicitly.

Roles map to configured model identifiers (never hard-coded in callers):

    router, planner, guardrails  -> NEMOTRON_CHAT_MODEL     (NVIDIA Nemotron 3 Nano)
    complex                      -> NEMOTRON_COMPLEX_MODEL  (NVIDIA Nemotron 3 Super)
    vision                       -> NEMOTRON_VISION_MODEL   (no NVIDIA vision model on Token Factory;
                                                             a non-NVIDIA Token Factory model, labelled)

Operational behaviour: bounded concurrency, connect/read timeouts, retry with exponential backoff
for transient failures only (timeouts, 429, 5xx), no retry on authentication or request errors,
a conservative local daily token quota, and per-call metering (model, request id, latency, token
usage, error category). Request and response content is never logged.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from nemotwins.config import get_settings

log = logging.getLogger("nemotwins.llm")

PROVIDER = "nebius_tokenfactory"
ROLES = ("router", "planner", "complex", "vision", "guardrails", "translator")
NVIDIA_PREFIX = "nvidia/"
# Kept for code that still names providers (eval scripts, fixtures): one provider only.
PROVIDERS = {"tokenfactory": ("https://api.tokenfactory.nebius.com/v1", "tokenfactory_2009_api_key")}


class LLMUnavailable(RuntimeError):
    """No model call could be served (demo mode, not configured, quota, or every attempt failed)."""

    def __init__(self, message: str, category: str = "unavailable") -> None:
        super().__init__(message)
        self.category = category


@dataclass
class LLMResult:
    text: str
    tool_calls: list[dict]
    provider: str
    model: str
    latency_ms: int
    raw: dict
    parsed: Any = None
    request_id: str | None = None
    usage: dict = field(default_factory=dict)
    attempts: int = 1


# ----------------------------------------------------------------------------- configuration
def base_url() -> str:
    """Configured base URL normalised to exactly one trailing ``/v1`` (prevents ``/v1/v1``)."""
    url = (get_settings().tokenfactory_base_url or "").strip().rstrip("/")
    while url.endswith("/v1/v1"):
        url = url[:-3]
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def model_for(role: str) -> str:
    s = get_settings()
    if role == "complex":
        return s.nemotron_complex_model.strip() or s.nemotron_chat_model.strip()
    if role == "vision":
        return s.nemotron_vision_model.strip() if s.vision_enabled else ""
    return s.nemotron_chat_model.strip()


def is_nvidia(model: str) -> bool:
    return model.lower().startswith(NVIDIA_PREFIX)


def configured() -> bool:
    s = get_settings()
    return s.ai_provider.strip().lower() == PROVIDER and bool(s.tokenfactory_2009_api_key.strip())


def available(role: str) -> bool:
    """True when a live call for ``role`` would be attempted (live mode, key and model configured)."""
    return get_settings().live and configured() and bool(model_for(role))


def _role_chain(role: str) -> list[tuple[str, str]]:
    """Compatibility helper for evaluation scripts: [(provider, model)] or []."""
    m = model_for(role)
    return [("tokenfactory", m)] if configured() and m else []


def image_part(data: bytes, mime: str = "image/jpeg") -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}


# Each role gets at least this many output tokens (reasoning-capable models need headroom).
# Nemotron 3 reasons before answering by default, and reasoning tokens count against max_tokens (measured
# 2026-10-08: ~300 reasoning tokens for a one-line answer). Classification roles switch thinking off
# (chat_template_kwargs.enable_thinking=false, accepted by Token Factory); the planner keeps it (better tool
# choice) with a larger budget. The reasoning text itself is never read or shown.
ROLE_MIN_TOKENS = {"router": 300, "planner": 3000, "complex": 4000, "vision": 1500, "guardrails": 200,
                   "translator": 800}
ROLE_THINKING = {"router": False, "guardrails": False, "translator": False, "planner": True, "complex": True}


def thinking_for(role: str) -> bool | None:
    """None = do not send the switch (non-Nemotron models). Planner and complex follow NEMOTRON_PLANNER_THINKING."""
    if role in ("planner", "complex"):
        return bool(get_settings().nemotron_planner_thinking)
    return ROLE_THINKING.get(role)


# ----------------------------------------------------------------------------- metering
class Meter:
    """In-process usage counters for the admin page (no content, no secrets)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "lock", threading.Lock()):
            self.since = datetime.now(UTC)
            self.requests = 0
            self.errors: dict[str, int] = {}
            self.by_model: dict[str, dict[str, int]] = {}
            self.latencies: deque[int] = deque(maxlen=500)
            self.day = datetime.now(UTC).date()
            self.day_tokens = 0
            self.last_ok: dict[str, Any] | None = None
            self.last_error: dict[str, Any] | None = None

    def _roll_day(self) -> None:
        today = datetime.now(UTC).date()
        if today != self.day:
            self.day, self.day_tokens = today, 0

    def quota_left(self) -> bool:
        limit = get_settings().daily_inference_token_limit
        with self.lock:
            self._roll_day()
            return limit <= 0 or self.day_tokens < limit

    def ok(self, model: str, latency_ms: int, usage: dict, request_id: str | None, role: str) -> None:
        pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        with self.lock:
            self._roll_day()
            self.requests += 1
            m = self.by_model.setdefault(model, {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
            m["requests"] += 1
            m["prompt_tokens"] += pt
            m["completion_tokens"] += ct
            self.day_tokens += pt + ct
            self.latencies.append(latency_ms)
            self.last_ok = {"model": model, "role": role, "latency_ms": latency_ms, "request_id": request_id,
                            "at": datetime.now(UTC).isoformat(timespec="seconds")}

    def error(self, model: str, category: str, role: str) -> None:
        with self.lock:
            self.requests += 1
            self.errors[category] = self.errors.get(category, 0) + 1
            self.last_error = {"model": model, "role": role, "category": category,
                               "at": datetime.now(UTC).isoformat(timespec="seconds")}

    def snapshot(self) -> dict:
        with self.lock:
            lat = sorted(self.latencies)

            def pct(q: float) -> int | None:
                return lat[min(len(lat) - 1, int(q * len(lat)))] if lat else None

            return {"since": self.since.isoformat(timespec="seconds"), "requests": self.requests,
                    "errors": dict(self.errors),
                    "prompt_tokens": sum(m["prompt_tokens"] for m in self.by_model.values()),
                    "completion_tokens": sum(m["completion_tokens"] for m in self.by_model.values()),
                    "by_model": {k: dict(v) for k, v in self.by_model.items()},
                    "latency_ms": {"p50": pct(0.5), "p95": pct(0.95), "n": len(lat)},
                    "today_tokens": self.day_tokens,
                    "daily_token_limit": get_settings().daily_inference_token_limit,
                    "last_ok": self.last_ok, "last_error": self.last_error}


METER = Meter()
_SEM_LOCK = threading.Lock()
_SEM: tuple[int, threading.BoundedSemaphore] | None = None


def _semaphore() -> threading.BoundedSemaphore:
    global _SEM
    n = get_settings().llm_max_concurrent_requests
    with _SEM_LOCK:
        if _SEM is None or _SEM[0] != n:
            _SEM = (n, threading.BoundedSemaphore(n))
        return _SEM[1]


# ----------------------------------------------------------------------------- request building
def build_body(model: str, messages: list[dict], tools: list[dict] | None, json_mode: bool,
               temperature: float, max_tokens: int, json_schema: dict | None = None,
               thinking: bool | None = None, tool_choice: str = "auto") -> dict[str, Any]:
    """Request body for Token Factory Chat Completions (pure function, unit-tested)."""
    body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens,
                            "temperature": temperature}
    if thinking is not None and is_nvidia(model):
        body["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice in ("auto", "required", "none") else "auto"
    if json_schema is not None:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": json_schema.get("title", "reply"), "schema": json_schema,
                                                   "strict": True}}
    elif json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def _category(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "quota"
    if status in (400, 404, 413, 422):
        return "invalid_request"
    return "server"


RETRYABLE = {"timeout", "quota", "server", "network"}


class LLMClient:
    def __init__(self, timeout_s: float | None = None) -> None:
        s = get_settings()
        self.timeout = httpx.Timeout(timeout_s or s.llm_request_timeout_seconds, connect=s.llm_connect_timeout_seconds)

    def chat(
        self,
        role: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 900,
        parse: Callable[[str], Any] | None = None,
        json_schema: dict | None = None,
        tool_choice: str = "auto",
    ) -> LLMResult:
        """One Token Factory call with bounded retries. Raises ``LLMUnavailable`` (with ``category``)
        when the call cannot be served. An answer cut off by the token limit, an empty answer, or one
        that ``parse`` rejects counts as ``invalid_response`` (retried once like a transient error)."""
        s = get_settings()
        if not s.live:
            raise LLMUnavailable("APP_MODE=demo: live model calls are disabled (templates are used)", "demo_mode")
        if not configured():
            raise LLMUnavailable("Token Factory is not configured (TOKENFACTORY_2009_API_KEY / AI_PROVIDER)",
                                 "not_configured")
        model = model_for(role)
        if not model:
            raise LLMUnavailable(f"No Token Factory model configured for role '{role}'", "not_configured")
        if not METER.quota_left():
            METER.error(model, "local_quota", role)
            raise LLMUnavailable("Local daily inference token quota reached", "local_quota")
        max_tokens = max(max_tokens, ROLE_MIN_TOKENS.get(role, 0))
        body = build_body(model, messages, tools, json_mode, temperature, max_tokens, json_schema,
                          thinking_for(role), tool_choice)
        headers = {"Authorization": f"Bearer {s.tokenfactory_2009_api_key.strip()}"}
        url = f"{base_url()}/chat/completions"
        attempts = 1 + s.llm_max_retries
        last_cat, last_msg = "unavailable", ""
        for attempt in range(attempts):
            t0 = time.time()
            cat = None
            try:
                with _semaphore():
                    r = httpx.post(url, json=body, headers=headers, timeout=self.timeout)
                rid = r.headers.get("x-request-id")
                if r.status_code >= 400:
                    cat = _category(r.status_code)
                    raise RuntimeError(f"HTTP {r.status_code}")
                data = r.json()
                res = parse_response(data, PROVIDER, model, int((time.time() - t0) * 1000))
                res.request_id, res.attempts = rid, attempt + 1
                res.usage = dict(data.get("usage") or {})
                if parse is not None:
                    try:
                        res.parsed = parse(res.text)
                    except (ValueError, TypeError, KeyError) as exc:
                        cat = "invalid_response"
                        raise RuntimeError(f"unparseable answer ({type(exc).__name__})") from None
                METER.ok(model, res.latency_ms, res.usage, rid, role)
                return res
            except httpx.TimeoutException:
                cat = "timeout"
                last_msg = "timeout"
            except httpx.TransportError as exc:
                cat = "network"
                last_msg = type(exc).__name__
            except Exception as exc:  # noqa: BLE001 - categorised below, never logged with content
                cat = cat or "invalid_response"
                last_msg = str(exc)[:120]
            last_cat = cat
            METER.error(model, cat, role)
            log.warning("tokenfactory %s role=%s attempt=%d/%d failed: %s (%s)", model, role, attempt + 1, attempts,
                        cat, last_msg)
            retryable = cat in RETRYABLE or (cat == "invalid_response" and attempt == 0)
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(min(8.0, 0.5 * 2 ** attempt) + random.uniform(0, 0.25))
        raise LLMUnavailable(f"Token Factory call failed: {last_cat} ({last_msg})", last_cat)

    def json(self, role: str, messages: list[dict], **kw: Any) -> tuple[dict, LLMResult]:
        """Chat in JSON mode; a reply that is not a JSON object counts as an invalid response."""
        res = self.chat(role, messages, json_mode=True, parse=_parse_object, **kw)
        return res.parsed, res


def parse_response(data: dict, prov: str, model: str, latency_ms: int) -> LLMResult:
    """Chat Completions JSON -> LLMResult; raises on a truncated or empty answer.

    Only the final ``content`` is used; any separate reasoning field is ignored (never shown)."""
    choice = data["choices"][0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": tc.get("id"), "name": fn.get("name"), "args": args if isinstance(args, dict) else {}})
    if choice.get("finish_reason") == "length" and not calls:
        raise RuntimeError("answer cut off by the token limit (finish_reason=length)")
    if not str(text).strip() and not calls:
        raise RuntimeError("empty answer")
    return LLMResult(str(text).strip(), calls, prov, model, latency_ms, data)


def _parse_object(text: str) -> dict:
    out = parse_json(text)
    if not isinstance(out, dict):
        raise ValueError("JSON answer is not an object")
    return out


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start: end + 1]
    return json.loads(text)


def health_check(timeout_s: float = 20.0) -> dict:
    """Minimal live inference check for the admin page (a 1-token-ish synthetic prompt)."""
    t0 = time.time()
    model = model_for("router")
    try:
        res = LLMClient(timeout_s=timeout_s).chat(
            "router", [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=300)
        return {"ok": True, "model": res.model, "latency_ms": res.latency_ms, "request_id": res.request_id,
                "checked_at": datetime.now(UTC).isoformat(timespec="seconds"), "error_category": None}
    except LLMUnavailable as exc:
        return {"ok": False, "model": model or None, "latency_ms": int((time.time() - t0) * 1000),
                "checked_at": datetime.now(UTC).isoformat(timespec="seconds"), "error_category": exc.category}
