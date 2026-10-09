"""providers/llm.py: Token Factory request bodies, response parsing and retry on bad answers (no network)."""

from __future__ import annotations

import json

import pytest

from nemotwins.providers import llm as L


def test_body_is_plain_openai_compatible() -> None:
    b = L.build_body("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", [], None, True, 0.2, 300)
    assert b["max_tokens"] == 300 and b["temperature"] == 0.2
    assert b["response_format"] == {"type": "json_object"}
    assert "reasoning" not in b and "max_completion_tokens" not in b


def _resp(content: str | None, finish: str = "stop", tool_calls: list | None = None) -> dict:
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "tool_calls": tool_calls}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def test_parse_response_rejects_length_and_empty() -> None:
    with pytest.raises(RuntimeError, match="length"):
        L.parse_response(_resp("Your peak may", "length"), "p", "m", 1)
    with pytest.raises(RuntimeError, match="empty"):
        L.parse_response(_resp(""), "p", "m", 1)
    ok = L.parse_response(_resp(None, "tool_calls", [{"id": "1", "function": {"name": "get_state",
                                                                              "arguments": "{}"}}]), "p", "m", 1)
    assert ok.tool_calls[0]["name"] == "get_state"


def test_reasoning_field_is_never_used() -> None:
    data = _resp("Final answer.")
    data["choices"][0]["message"]["reasoning_content"] = "hidden chain of thought"
    assert L.parse_response(data, "p", "m", 1).text == "Final answer."


class _R:
    def __init__(self, data: dict, status: int = 200) -> None:
        self._d, self.status_code, self.text = data, status, json.dumps(data)
        self.headers = {"x-request-id": "rid"}

    def json(self) -> dict:
        return self._d


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("TOKENFACTORY_2009_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    L.get_settings.cache_clear()
    yield
    L.get_settings.cache_clear()


def test_retries_once_on_a_bad_answer(monkeypatch, live, caplog) -> None:
    sent: list[dict] = []
    answers = [_resp("not json at all"), _resp('{"intent": "state"}')]

    def post(url, json=None, headers=None, timeout=None):  # noqa: A002 - httpx signature
        sent.append(json)
        return _R(answers[len(sent) - 1])

    monkeypatch.setattr(L.httpx, "post", post)
    data, res = L.LLMClient().json("router", [{"role": "user", "content": "hi"}], max_tokens=40)
    assert data == {"intent": "state"} and res.provider == "nebius_tokenfactory" and res.attempts == 2
    assert {b["model"] for b in sent} == {"nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"}
    assert sent[0]["max_tokens"] == 300  # router floor despite max_tokens=40
    assert "not json at all" not in caplog.text  # failures are logged without content


def test_invalid_responses_stop_after_one_retry(monkeypatch, live) -> None:
    calls = []
    monkeypatch.setattr(L.httpx, "post", lambda *a, **k: calls.append(1) or _R(_resp("")))
    with pytest.raises(L.LLMUnavailable) as e:
        L.LLMClient().chat("router", [{"role": "user", "content": "hi"}])
    assert e.value.category == "invalid_response" and len(calls) == 2
