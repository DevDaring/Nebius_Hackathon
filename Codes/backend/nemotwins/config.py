"""Central configuration (NemoTwins).

Secrets are read from ``Codes/.env`` (never committed) or from the deployment's runtime secret
store. Two user-required variable names are accepted exactly as written:

* ``TOKENFACTORY_2009_API_KEY`` - Nebius Token Factory inference key (backend only).
* ``NEBUIS_CLOUD_API_KEY`` - Nebius AI Cloud credential slot (spelling intentional), interpreted
  through ``NEBIUS_CLOUD_AUTH_MODE``; it never authorises inference and is never sent to the
  frontend or to the agent's tools.

Model calls go to Nebius Token Factory only; no other model provider is configured.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FOOD_DIR = DATA_DIR / "food"
REPORTS_DIR = BACKEND_DIR / "reports"
FIXTURES_DIR = BACKEND_DIR / "fixtures"
MODELS_DIR = BACKEND_DIR / "artifacts"
CAPABILITIES_DIR = BACKEND_DIR / "capabilities"
CACHE_DIR = DATA_DIR / "cache"
TTS_CACHE_DIR = CACHE_DIR / "tts"  # kept for recorded demo audio lookups; no live TTS in NemoTwins
RUNTIME_DIR = CACHE_DIR / "runtime"  # live parse results, per user (gitignored); packaged fixtures stay read-only

# Token Factory model identifiers verified against GET /v1/models for this project's account on
# 2026-10-08 (see capabilities/manifest.json). Override per deployment with the NEMOTRON_* variables.
DEFAULT_CHAT_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_COMPLEX_MODEL = "nvidia/nemotron-3-super-120b-a12b"
# No NVIDIA vision model is offered on Token Factory for this account; this is a non-NVIDIA Token
# Factory model, used only to propose dish candidates that the user confirms.
DEFAULT_VISION_MODEL = "google/gemma-3-27b-it"
DEFAULT_TOKENFACTORY_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
RELEASE_LOCALES = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")

log = logging.getLogger("nemotwins.config")
# Used when JWT_SECRET is unset: random per process (sessions end on restart), never a public default.
_PROCESS_JWT_SECRET = secrets.token_urlsafe(48)


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # "KEY=" in .env must not override a default
        env_ignore_empty=True,
    )

    # --- App ---
    app_name: str = Field("NemoTwins", validation_alias=_alias("APP_NAME"))
    # APP_MODE: live (Token Factory calls) | demo (offline: deterministic templates only).
    # Unset -> live when a Token Factory key is configured, else demo.
    app_mode: str = Field("", validation_alias=_alias("APP_MODE"))
    app_default_locale: str = Field("en-US", validation_alias=_alias("APP_DEFAULT_LOCALE", "DEFAULT_LANGUAGE"))
    app_supported_locales: str = Field(",".join(RELEASE_LOCALES), validation_alias=_alias("APP_SUPPORTED_LOCALES"))
    app_public_url: str = Field("", validation_alias=_alias("APP_PUBLIC_URL"))
    app_environment: str = Field("local", validation_alias=_alias("APP_ENVIRONMENT"))
    git_commit: str = Field("", validation_alias=_alias("GIT_COMMIT"))
    cors_origins: str = Field("http://localhost:5180,http://127.0.0.1:5180", validation_alias=_alias("CORS_ORIGINS"))
    database_url: str = Field(
        "postgresql+psycopg://nemotwins:nemotwins@localhost:5432/nemotwins",
        validation_alias=_alias("DATABASE_URL"),
    )
    jwt_secret: str = Field("", validation_alias=_alias("JWT_SECRET"))
    jwt_secret_generated: bool = False
    jwt_ttl_hours: int = 12

    # Demo login accounts seeded at start-up. Format: "user:password,user:password".
    demo_users: str = Field("TestUser:TestUser11", validation_alias=_alias("DEMO_USERS"))
    # One-click demo sessions: POST /api/auth/demo creates a private throw-away user, so visitors
    # never share replay clocks, readings or meals. Expired demo users (and their data) are purged.
    demo_sessions: bool = Field(True, validation_alias=_alias("DEMO_SESSIONS"))
    demo_session_ttl_hours: int = Field(24, ge=1, le=168, validation_alias=_alias("DEMO_SESSION_TTL_HOURS"))
    rate_demo_session_per_hour: int = Field(6, validation_alias=_alias("RATE_DEMO_SESSION_PER_HOUR"))
    demo_sessions_per_day: int = Field(500, validation_alias=_alias("DEMO_SESSIONS_PER_DAY"))
    # Usernames that also get the "admin" role (developer integration page). Empty = nobody.
    admin_users: str = Field("", validation_alias=_alias("ADMIN_USERS"))
    nemo_fish_enabled: bool = Field(True, validation_alias=_alias("NEMO_FISH_ENABLED"))
    # Raw chat text is not stored in the audit log unless explicitly enabled (tool calls and checks are).
    audit_store_text: bool = Field(False, validation_alias=_alias("AUDIT_STORE_TEXT"))

    # --- Inference: Nebius Token Factory (the only model provider) ---
    ai_provider: str = Field("nebius_tokenfactory", validation_alias=_alias("AI_PROVIDER"))
    tokenfactory_2009_api_key: str = Field("", validation_alias=_alias("TOKENFACTORY_2009_API_KEY"))
    tokenfactory_base_url: str = Field(DEFAULT_TOKENFACTORY_BASE_URL, validation_alias=_alias("TOKENFACTORY_BASE_URL"))
    nemotron_chat_model: str = Field(DEFAULT_CHAT_MODEL, validation_alias=_alias("NEMOTRON_CHAT_MODEL"))
    nemotron_complex_model: str = Field(DEFAULT_COMPLEX_MODEL, validation_alias=_alias("NEMOTRON_COMPLEX_MODEL"))
    nemotron_vision_model: str = Field(DEFAULT_VISION_MODEL, validation_alias=_alias("NEMOTRON_VISION_MODEL"))
    # Retrieval is not used (food lookup is a deterministic table match); kept as a documented slot.
    nemotron_embed_model: str = Field("", validation_alias=_alias("NEMOTRON_EMBED_MODEL"))
    vision_enabled: bool = Field(True, validation_alias=_alias("VISION_ENABLED"))
    # Further reading (Tavily web-search API, not a model): topic-only queries, allowlisted health sites.
    tavily_api_key: str = Field("", validation_alias=_alias("TAVILY_API_KEY", "TAVILY_2009_API_KEY"))
    references_enabled: bool = Field(True, validation_alias=_alias("REFERENCES_ENABLED"))
    # Planner reasoning off by default: measured 2026-10-08, thinking-on planner turns overran 3000 tokens and took
    # 20-100 s; off = ~1 s per call. Deterministic checks + the output rail guard every answer either way.
    nemotron_planner_thinking: bool = Field(False, validation_alias=_alias("NEMOTRON_PLANNER_THINKING"))
    # Which model plans tool calls and writes the explanation: "complex" (NEMOTRON_COMPLEX_MODEL, Nemotron 3 Super)
    # or "chat" (NEMOTRON_CHAT_MODEL, Nemotron 3 Nano). Router and guardrail rails always use the chat model.
    nemotron_planner_model: str = Field("complex", validation_alias=_alias("NEMOTRON_PLANNER_MODEL"))
    nemo_guardrails_enabled: bool = Field(True, validation_alias=_alias("NEMO_GUARDRAILS_ENABLED"))
    # Speech: Token Factory offers no ASR/TTS model, and no other provider may be called.
    nvidia_speech_enabled: bool = Field(False, validation_alias=_alias("NVIDIA_SPEECH_ENABLED"))
    nvidia_speech_endpoint: str = Field("", validation_alias=_alias("NVIDIA_SPEECH_ENDPOINT"))
    nvidia_speech_auth_mode: str = Field("", validation_alias=_alias("NVIDIA_SPEECH_AUTH_MODE"))

    # Deliberate operational bounds (not unlimited defaults).
    llm_max_tool_steps: int = Field(6, ge=1, le=12, validation_alias=_alias("LLM_MAX_TOOL_STEPS"))
    llm_max_retries: int = Field(2, ge=0, le=5, validation_alias=_alias("LLM_MAX_RETRIES"))
    llm_request_timeout_seconds: float = Field(30.0, gt=0, le=120,
                                               validation_alias=_alias("LLM_REQUEST_TIMEOUT_SECONDS", "LLM_TIMEOUT_S"))
    llm_connect_timeout_seconds: float = Field(5.0, gt=0, le=30, validation_alias=_alias("LLM_CONNECT_TIMEOUT_SECONDS"))
    llm_max_concurrent_requests: int = Field(4, ge=1, le=64, validation_alias=_alias("LLM_MAX_CONCURRENT_REQUESTS"))
    # Conservative in-process token quota per UTC day (prompt + completion); 0 = no local quota.
    # A local quota is a guard rail, not a billing cap: Token Factory metering is authoritative.
    daily_inference_token_limit: int = Field(2_000_000, ge=0, validation_alias=_alias("DAILY_INFERENCE_TOKEN_LIMIT"))
    daily_inference_budget_usd: str = Field("", validation_alias=_alias("DAILY_INFERENCE_BUDGET_USD"))
    monthly_cloud_budget_usd: str = Field("", validation_alias=_alias("MONTHLY_CLOUD_BUDGET_USD"))
    eval_max_cases_per_job: int = Field(100, ge=1, le=2000, validation_alias=_alias("EVAL_MAX_CASES_PER_JOB"))

    # --- Nebius AI Cloud (deployment / evaluation administration; never exposed to agent tools) ---
    nebius_cloud_api_key: str = Field("", validation_alias=_alias("NEBUIS_CLOUD_API_KEY"))
    nebius_cloud_auth_mode: str = Field("iam_token", validation_alias=_alias("NEBIUS_CLOUD_AUTH_MODE"))
    nebius_project_id: str = Field("", validation_alias=_alias("NEBIUS_PROJECT_ID"))
    nebius_region: str = Field("", validation_alias=_alias("NEBIUS_REGION"))
    nebius_service_account_id: str = Field("", validation_alias=_alias("NEBIUS_SERVICE_ACCOUNT_ID"))
    nebius_public_key_id: str = Field("", validation_alias=_alias("NEBIUS_PUBLIC_KEY_ID"))
    nebius_private_key_file: str = Field("", validation_alias=_alias("NEBIUS_PRIVATE_KEY_FILE"))
    nebius_credentials_file: str = Field("", validation_alias=_alias("NEBIUS_CREDENTIALS_FILE"))
    nebius_serverless_endpoint_id: str = Field("", validation_alias=_alias("NEBIUS_SERVERLESS_ENDPOINT_ID"))
    nebius_evaluation_job_template: str = Field("", validation_alias=_alias("NEBIUS_EVALUATION_JOB_TEMPLATE"))
    nebius_object_storage_endpoint: str = Field("", validation_alias=_alias("NEBIUS_OBJECT_STORAGE_ENDPOINT"))
    nebius_object_storage_bucket: str = Field("", validation_alias=_alias("NEBIUS_OBJECT_STORAGE_BUCKET"))
    nebius_object_storage_access_key_id: str = Field("", validation_alias=_alias("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID"))
    nebius_object_storage_secret_access_key: str = Field(
        "", validation_alias=_alias("NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY"))

    # --- Ops: per-user rate limits (requests per minute) on endpoints that can cost money in live
    # mode, and hard upload size bounds (bytes are counted while the body is read).
    rate_chat_per_min: int = Field(30, validation_alias=_alias("RATE_CHAT_PER_MIN"))
    rate_stt_per_min: int = Field(12, validation_alias=_alias("RATE_STT_PER_MIN"))
    rate_tts_per_min: int = Field(30, validation_alias=_alias("RATE_TTS_PER_MIN"))
    rate_meal_photo_per_min: int = Field(8, validation_alias=_alias("RATE_MEAL_PHOTO_PER_MIN"))
    rate_lab_parse_per_min: int = Field(8, validation_alias=_alias("RATE_LAB_PARSE_PER_MIN"))
    max_image_bytes: int = Field(12 * 1024 * 1024, validation_alias=_alias("MAX_IMAGE_BYTES"))
    max_audio_bytes: int = Field(10 * 1024 * 1024, validation_alias=_alias("MAX_AUDIO_BYTES"))

    @model_validator(mode="after")
    def _derived(self) -> Settings:
        if not self.jwt_secret.strip():
            self.jwt_secret = _PROCESS_JWT_SECRET
            self.jwt_secret_generated = True
        if not self.app_mode.strip():
            self.app_mode = "live" if self.tokenfactory_2009_api_key.strip() else "demo"
        return self

    @property
    def live(self) -> bool:
        return self.app_mode.strip().lower() == "live"

    @property
    def locales(self) -> tuple[str, ...]:
        wanted = [x.strip() for x in self.app_supported_locales.split(",") if x.strip()]
        return tuple(x for x in wanted if x in RELEASE_LOCALES) or RELEASE_LOCALES

    @property
    def admin_usernames(self) -> set[str]:
        return {u.strip() for u in self.admin_users.split(",") if u.strip()}

    def demo_user_pairs(self) -> list[tuple[str, str]]:
        out = []
        for item in self.demo_users.split(","):
            if ":" in item:
                u, p = item.split(":", 1)
                out.append((u.strip(), p.strip()))
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
