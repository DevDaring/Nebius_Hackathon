"""NVIDIA NeMo Guardrails around the NemoTwins agent.

Input rail (``self check input``): medication-dose requests, diagnosis requests, prompt injection,
attempts to make the assistant invent numbers. Output rail (``self check output``): dose advice,
diagnosis, unsupported certainty, what-ifs presented as proven effects, medical claims outside the
twin's evidence. Both run on NVIDIA Nemotron through the Nebius Token Factory OpenAI-compatible
endpoint (open-source library, not a hosted NVIDIA microservice).

Deterministic checks stay authoritative for numbers, ids, units and validation status: a rail can
block a reply but can never approve a value the numeric verifier rejected.

All rail calls run on one dedicated event loop thread, so the library's shared async HTTP client is
never used from two loops. A rail failure (timeout, quota, network) returns ``unavailable``; the
caller then relies on the deterministic checks alone and reports the status. Nothing is logged
except the rail name, status and latency.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any

from nemotwins.config import get_settings
from nemotwins.providers import llm as LLM

log = logging.getLogger("nemotwins.guardrails")
# The library logs full user and bot messages at INFO (event traces). Health conversations must not reach the
# server logs, so its loggers are capped at WARNING regardless of the application's log level.
for _name in ("nemoguardrails", "nemoguardrails.colang", "nemoguardrails.rails", "nemoguardrails.actions",
              "nemoguardrails.llm"):
    logging.getLogger(_name).setLevel(logging.WARNING)
CONFIG_DIR = Path(__file__).with_name("config")
REFUSAL_MARKERS = ("I'm sorry, I can't respond to that",)
TIMEOUT_S = 20.0


class _Guard:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rails: Any = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.init_error: str | None = None
        self.stats: dict[str, Any] = {"input": {"passed": 0, "blocked": 0, "unavailable": 0},
                                      "output": {"passed": 0, "blocked": 0, "unavailable": 0}, "last": None}

    # ---------------------------------------------------------------- lifecycle
    def enabled(self) -> bool:
        s = get_settings()
        return bool(s.nemo_guardrails_enabled) and LLM.available("guardrails")

    def _ensure(self) -> bool:
        if self.rails is not None:
            return True
        with self.lock:
            if self.rails is not None:
                return True
            try:
                from nemoguardrails import LLMRails, RailsConfig

                cfg = RailsConfig.from_path(str(CONFIG_DIR))
                s = get_settings()
                for m in cfg.models:
                    m.model = LLM.model_for("guardrails")
                    m.parameters = {"base_url": LLM.base_url(), "api_key": s.tokenfactory_2009_api_key.strip(),
                                    "temperature": 0.0, "max_tokens": 300,
                                    "chat_template_kwargs": {"enable_thinking": False},
                                    "timeout": s.llm_request_timeout_seconds}
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="guardrails-loop", daemon=True).start()
                self.loop = loop
                self.rails = LLMRails(cfg)
                self.init_error = None
                return True
            except Exception as exc:  # noqa: BLE001 - library missing / bad config: report, do not crash chat
                self.init_error = type(exc).__name__
                log.warning("guardrails init failed: %s", self.init_error)
                return False

    # ---------------------------------------------------------------- checks
    def _run(self, which: str, messages: list[dict]) -> dict:
        t0 = time.time()
        if not self.enabled():
            return {"status": "not_run", "rail": which, "latency_ms": 0}
        if not self._ensure():
            return self._record(which, "unavailable", t0, reason=self.init_error)
        try:
            coro = self.rails.generate_async(messages=messages, options={"rails": [which],
                                                                         "log": {"activated_rails": True,
                                                                                 "llm_calls": True}})
            assert self.loop is not None
            res = asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - timeout / provider error
            return self._record(which, "unavailable", t0, reason=type(exc).__name__)
        stopped = any(getattr(a, "stop", False) for a in (res.log.activated_rails if res.log else []))
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        for c in (res.log.llm_calls if res.log else []) or []:
            usage["prompt_tokens"] += int(getattr(c, "prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(getattr(c, "completion_tokens", 0) or 0)
        LLM.METER.ok(LLM.model_for("guardrails"), int((time.time() - t0) * 1000), usage, None, f"guardrails_{which}")
        return self._record(which, "blocked" if stopped else "passed", t0)

    def _record(self, which: str, status: str, t0: float, reason: str | None = None) -> dict:
        out = {"status": status, "rail": which, "latency_ms": int((time.time() - t0) * 1000)}
        if reason:
            out["reason"] = reason
        with self.lock:
            self.stats[which][status] = self.stats[which].get(status, 0) + 1
            self.stats["last"] = {"rail": which, "status": status, "latency_ms": out["latency_ms"]}
        if status == "unavailable":
            log.warning("guardrail %s unavailable (%s)", which, reason)
        return out

    def check_input(self, text: str) -> dict:
        return self._run("input", [{"role": "user", "content": text}])

    def check_output(self, user_text: str, reply: str) -> dict:
        return self._run("output", [{"role": "user", "content": user_text},
                                    {"role": "assistant", "content": reply}])

    def status(self) -> dict:
        with self.lock:
            stats = {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.stats.items()}
        return {"enabled": self.enabled(), "engine": "nemoguardrails", "model": LLM.model_for("guardrails") or None,
                "initialised": self.rails is not None, "init_error": self.init_error, "stats": stats}


GUARD = _Guard()


def check_input(text: str) -> dict:
    return GUARD.check_input(text)


def check_output(user_text: str, reply: str) -> dict:
    return GUARD.check_output(user_text, reply)


def status() -> dict:
    return GUARD.status()
