"""config.py: empty .env values never override defaults; JWT secret is never a public default."""

from __future__ import annotations

from nemotwins.config import Settings


def test_empty_values_are_ignored(monkeypatch) -> None:
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "")
    monkeypatch.setenv("NEMOTRON_CHAT_MODEL", "")
    s = Settings(_env_file=None)
    assert s.llm_request_timeout_seconds == 30.0
    assert s.nemotron_chat_model == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def test_other_provider_keys_are_not_read(monkeypatch) -> None:
    """NemoTwins calls models only through Token Factory: old provider keys have no settings field."""
    monkeypatch.setenv("Open_AI_2009_Key", "other-provider-test-value")
    monkeypatch.setenv("OPENROUTER_API_KEY_1", "other-provider-test-value")
    s = Settings(_env_file=None)
    assert "other-provider-test-value" not in s.model_dump_json()


def test_app_mode_defaults_from_tokenfactory_key(monkeypatch) -> None:
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("TOKENFACTORY_2009_API_KEY", raising=False)
    assert Settings(_env_file=None).app_mode == "demo"
    monkeypatch.setenv("TOKENFACTORY_2009_API_KEY", "tf-test")
    assert Settings(_env_file=None).app_mode == "live"
    monkeypatch.setenv("APP_MODE", "demo")
    assert Settings(_env_file=None).app_mode == "demo"


def test_unset_jwt_secret_is_random_not_public(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    a = Settings(_env_file=None)
    assert a.jwt_secret_generated and len(a.jwt_secret) >= 32
    assert a.jwt_secret != "dev-only-change-me-nemotwins"
    monkeypatch.setenv("JWT_SECRET", "")
    assert Settings(_env_file=None).jwt_secret_generated


def test_explicit_jwt_secret_is_used(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "explicit-test-secret")
    s = Settings(_env_file=None)
    assert s.jwt_secret == "explicit-test-secret" and not s.jwt_secret_generated


def test_nebius_credentials_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("TOKENFACTORY_2009_API_KEY", "tokenfactory-test-key")
    monkeypatch.setenv("NEBUIS_CLOUD_API_KEY", "cloud-test-key")
    s = Settings(_env_file=None)
    assert s.tokenfactory_2009_api_key == "tokenfactory-test-key"
    assert s.nebius_cloud_api_key == "cloud-test-key"
