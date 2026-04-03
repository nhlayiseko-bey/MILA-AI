from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    request_timeout_seconds: float
    max_retries: int
    internal_api_key: str
    slack_signing_secret: str
    slack_bot_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_webhook_verify_token: str
    whatsapp_app_secret: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_bot_username: str
    calendar_webhook_secret: str
    openclaw_base_url: str
    openclaw_chat_path: str
    openclaw_health_path: str
    openclaw_gateway_token: str
    openclaw_agent_id: str
    openclaw_request_timeout_seconds: float
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_request_timeout_seconds: float
    kimi_api_key: str
    kimi_base_url: str
    kimi_model: str
    kimi_request_timeout_seconds: float
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    allow_unverified_local_webhooks: bool
    enable_test_employee_fallback: bool
    test_company_id: str


def get_settings() -> Settings:
    return Settings(
        app_name=_read_env("APP_NAME", "human-purpose-gateway"),
        environment=_read_env("APP_ENV", "development"),
        request_timeout_seconds=float(_read_env("REQUEST_TIMEOUT_SECONDS", "15")),
        max_retries=int(_read_env("MAX_RETRIES", "3")),
        internal_api_key=_read_env("INTERNAL_API_KEY"),
        slack_signing_secret=_read_env("SLACK_SIGNING_SECRET"),
        slack_bot_token=_read_env("SLACK_BOT_TOKEN"),
        whatsapp_access_token=_read_env("WHATSAPP_ACCESS_TOKEN"),
        whatsapp_phone_number_id=_read_env("WHATSAPP_PHONE_NUMBER_ID"),
        whatsapp_webhook_verify_token=_read_env("WHATSAPP_WEBHOOK_VERIFY_TOKEN"),
        whatsapp_app_secret=_read_env("WHATSAPP_APP_SECRET"),
        telegram_bot_token=_read_env("TELEGRAM_BOT_TOKEN"),
        telegram_webhook_secret=_read_env("TELEGRAM_WEBHOOK_SECRET"),
        telegram_bot_username=_read_env("TELEGRAM_BOT_USERNAME"),
        calendar_webhook_secret=_read_env("CALENDAR_WEBHOOK_SECRET"),
        openclaw_base_url=_read_env("OPENCLAW_BASE_URL", "http://127.0.0.1:18789"),
        openclaw_chat_path=_read_env("OPENCLAW_CHAT_PATH", "/v1/chat/completions"),
        openclaw_health_path=_read_env("OPENCLAW_HEALTH_PATH", "/health"),
        openclaw_gateway_token=_read_env("OPENCLAW_GATEWAY_TOKEN"),
        openclaw_agent_id=_read_env("OPENCLAW_AGENT_ID", "main"),
        openclaw_request_timeout_seconds=float(
            _read_env("OPENCLAW_REQUEST_TIMEOUT_SECONDS", "300"),
        ),
        openai_api_key=_read_env("OPENAI_API_KEY"),
        openai_base_url=_read_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=_read_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_request_timeout_seconds=float(
            _read_env("OPENAI_REQUEST_TIMEOUT_SECONDS", "120"),
        ),
        kimi_api_key=_read_env("KIMI_API_KEY"),
        kimi_base_url=_read_env("KIMI_BASE_URL", "https://api.moonshot.ai/v1"),
        kimi_model=_read_env("KIMI_MODEL", "kimi-k2.5"),
        kimi_request_timeout_seconds=float(
            _read_env("KIMI_REQUEST_TIMEOUT_SECONDS", "120"),
        ),
        supabase_url=_read_env("SUPABASE_URL"),
        supabase_service_role_key=_read_env("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_anon_key=_read_env("SUPABASE_ANON_KEY"),
        allow_unverified_local_webhooks=_read_bool("ALLOW_UNVERIFIED_LOCAL_WEBHOOKS", False),
        enable_test_employee_fallback=_read_bool("ENABLE_TEST_EMPLOYEE_FALLBACK", False),
        test_company_id=_read_env("TEST_COMPANY_ID"),
    )


settings = get_settings()
