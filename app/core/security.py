from __future__ import annotations

import hashlib
import hmac
import time
from fastapi import Header, HTTPException, status

from app.config import settings


MAX_SLACK_CLOCK_SKEW_SECONDS = 60 * 5


def _hmac_sha256(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return digest


def verify_slack_request(raw_body: bytes, timestamp: str | None, signature: str | None) -> None:
    if settings.allow_unverified_local_webhooks:
        return
    if not settings.slack_signing_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Slack signing secret missing")
    if not timestamp or not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Slack signature headers")
    now = int(time.time())
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack timestamp header") from exc
    if abs(now - ts) > MAX_SLACK_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Slack request expired")
    base_string = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode("utf-8")
    expected_signature = "v0=" + _hmac_sha256(settings.slack_signing_secret, base_string)
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")


def verify_whatsapp_request(raw_body: bytes, signature: str | None) -> None:
    if settings.allow_unverified_local_webhooks:
        return
    if not settings.whatsapp_app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WhatsApp app secret missing",
        )
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing WhatsApp signature header",
        )
    expected_signature = "sha256=" + _hmac_sha256(settings.whatsapp_app_secret, raw_body)
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WhatsApp signature")


def verify_whatsapp_handshake_token(token: str | None) -> None:
    if settings.allow_unverified_local_webhooks:
        return
    if not settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp verify token missing")
    if token != settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid verify token")


def verify_calendar_secret(secret: str | None) -> None:
    if settings.allow_unverified_local_webhooks:
        return
    if not settings.calendar_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Calendar webhook secret missing",
        )
    if secret != settings.calendar_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid calendar secret")


def verify_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if not settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal API key missing")
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
