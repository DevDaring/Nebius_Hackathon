"""NemoTwins provider layer: Token Factory adapter, Cloud auth adapter, capability endpoints.

No network: httpx is replaced by a fake; the Cloud SDK is never reached."""

from __future__ import annotations

import httpx
import pytest

from nemotwins.config import Settings, get_settings
from nemotwins.providers import llm as LLM
from nemotwins.providers import nebius_cloud as NC

OK_BODY = {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 5, "completion_tokens": 1}}


class _Resp:
    def __init__(self, status: int, body: dict | None = None) -> None:
        self.status_code, self._body = status, body or {}
        self.headers = {"x-request-id": "req-test"}

    def json(self) -> dict:
        return self._body


@pytest.fixture
def live(monkeypatch):
    """Live mode with a fake key; restores the cached settings afterwards."""
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("TOKENFACTORY_2009_API_KEY", "tf-fake-key-for-tests")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setattr(LLM.time, "sleep", lambda s: None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_post(monkeypatch, responses: list):
    calls: list[dict] = []

    def post(url, json, headers, timeout):  # noqa: A002 - mirrors httpx.post
        calls.append({"url": url, "body": json, "auth": headers.get("Authorization", "")})
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(LLM.httpx, "post", post)
    return calls


@pytest.mark.parametrize("raw", ["https://api.tokenfactory.nebius.com/v1/", "https://api.tokenfactory.nebius.com/v1",
                                 "https://api.tokenfactory.nebius.com", "https://api.tokenfactory.nebius.com/v1/v1/"])
def test_base_url_has_exactly_one_v1(monkeypatch, raw) -> None:
    monkeypatch.setenv("TOKENFACTORY_BASE_URL", raw)
    get_settings.cache_clear()
    try:
        assert LLM.base_url() == "https://api.tokenfactory.nebius.com/v1"
    finally:
        get_settings.cache_clear()


def test_roles_use_configured_nvidia_models() -> None:
    s = Settings(_env_file=None)
    assert s.nemotron_chat_model.startswith("nvidia/") and s.nemotron_complex_model.startswith("nvidia/")
    assert LLM.is_nvidia("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B") and not LLM.is_nvidia("google/gemma-3-27b-it")


def test_build_body_json_modes() -> None:
    b = LLM.build_body("m", [], None, True, 0.1, 100)
    assert b["response_format"] == {"type": "json_object"} and "tools" not in b
    sch = {"title": "x", "type": "object", "properties": {}}
    b = LLM.build_body("m", [], [{"type": "function"}], False, 0.1, 100, sch)
    assert b["response_format"]["type"] == "json_schema" and b["tool_choice"] == "auto"


def test_demo_mode_never_calls(monkeypatch) -> None:
    monkeypatch.setenv("APP_MODE", "demo")
    get_settings.cache_clear()
    try:
        calls = _fake_post(monkeypatch, [])
        with pytest.raises(LLM.LLMUnavailable) as e:
            LLM.LLMClient().chat("planner", [{"role": "user", "content": "hi"}])
        assert e.value.category == "demo_mode" and calls == []
    finally:
        get_settings.cache_clear()


def test_only_tokenfactory_is_called(live, monkeypatch) -> None:
    calls = _fake_post(monkeypatch, [_Resp(200, OK_BODY)])
    res = LLM.LLMClient().chat("planner", [{"role": "user", "content": "hi"}])
    assert res.text == "OK" and res.request_id == "req-test" and res.usage["prompt_tokens"] == 5
    assert calls[0]["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert calls[0]["body"]["model"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert calls[0]["auth"] == "Bearer tf-fake-key-for-tests"


def test_transient_errors_are_retried(live, monkeypatch) -> None:
    calls = _fake_post(monkeypatch, [_Resp(429), httpx.ReadTimeout("t"), _Resp(200, OK_BODY)])
    res = LLM.LLMClient().chat("router", [{"role": "user", "content": "hi"}])
    assert res.attempts == 3 and len(calls) == 3


def test_auth_errors_are_not_retried(live, monkeypatch) -> None:
    calls = _fake_post(monkeypatch, [_Resp(401), _Resp(200, OK_BODY)])
    with pytest.raises(LLM.LLMUnavailable) as e:
        LLM.LLMClient().chat("router", [{"role": "user", "content": "hi"}])
    assert e.value.category == "auth" and len(calls) == 1


def test_truncated_answer_is_invalid_response(live, monkeypatch) -> None:
    cut = {"choices": [{"message": {"content": "Here's a thinking"}, "finish_reason": "length"}]}
    _fake_post(monkeypatch, [_Resp(200, cut), _Resp(200, cut)])
    with pytest.raises(LLM.LLMUnavailable) as e:
        LLM.LLMClient().chat("router", [{"role": "user", "content": "hi"}])
    assert e.value.category == "invalid_response"


def test_local_token_quota(live, monkeypatch) -> None:
    monkeypatch.setenv("DAILY_INFERENCE_TOKEN_LIMIT", "1")
    get_settings.cache_clear()
    LLM.METER.day_tokens = 5
    try:
        with pytest.raises(LLM.LLMUnavailable) as e:
            LLM.LLMClient().chat("router", [{"role": "user", "content": "hi"}])
        assert e.value.category == "local_quota"
    finally:
        LLM.METER.day_tokens = 0


def test_cloud_modes_without_network(monkeypatch) -> None:
    monkeypatch.setenv("NEBUIS_CLOUD_API_KEY", "")
    monkeypatch.setenv("NEBIUS_CLOUD_AUTH_MODE", "iam_token")
    get_settings.cache_clear()
    try:
        d = NC.describe()
        assert d["status"] == "not_configured" and not d["configured"]
        monkeypatch.setenv("NEBUIS_CLOUD_API_KEY", "iam-token-test")
        get_settings.cache_clear()
        d = NC.describe()
        assert d["configured"] and "iam-token-test" not in str(d)
        monkeypatch.setenv("NEBIUS_CLOUD_AUTH_MODE", "service_account")
        get_settings.cache_clear()
        d = NC.describe()
        assert not d["configured"] and "NEBIUS_SERVICE_ACCOUNT_ID" in d["detail"]
        monkeypatch.setenv("NEBIUS_CLOUD_AUTH_MODE", "api_key_guess")
        get_settings.cache_clear()
        assert NC.describe()["status"] == "error"
    finally:
        get_settings.cache_clear()


def test_capabilities_public_and_secret_free(client) -> None:
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["app_name"] == "NemoTwins"
    assert body["locales"] == ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"]
    assert body["features"]["speech"]["enabled"] is False
    assert body["inference"]["provider"] == "nebius_tokenfactory"
    key = get_settings().tokenfactory_2009_api_key
    assert not key or key not in r.text


def test_speech_is_unavailable(client, auth) -> None:
    r = client.post("/api/speech/tts", json={"text": "hola", "lang": "es-ES"}, headers=auth)
    assert r.status_code == 501 and r.json()["detail"]["code"] == "speech_unavailable"
    r = client.post("/api/speech/stt", headers=auth)
    assert r.status_code == 501


def test_admin_page_requires_admin_role(client, auth, auth_b) -> None:
    assert client.get("/api/admin/integrations", headers=auth).status_code == 403
    r = client.get("/api/admin/integrations", headers=auth_b)
    assert r.status_code == 200
    body = r.json()
    assert {"manifest", "usage", "cloud", "deployment", "evaluation_jobs", "guardrails"} <= set(body)
    s = get_settings()
    for secret in (s.tokenfactory_2009_api_key, s.nebius_cloud_api_key, s.jwt_secret):
        assert not secret or secret not in r.text


def test_guardrails_library_does_not_log_conversation_text() -> None:
    import logging

    import nemotwins.guardrails  # noqa: F401 - import applies the cap

    for name in ("nemoguardrails.colang.v1_0.runtime.runtime", "nemoguardrails.rails.llm.llmrails"):
        assert not logging.getLogger(name).isEnabledFor(logging.INFO)
