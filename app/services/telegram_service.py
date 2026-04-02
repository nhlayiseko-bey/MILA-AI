from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class TelegramDeliveryError(Exception):
    pass


class TelegramService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        if not self._settings.telegram_bot_token:
            raise TelegramDeliveryError("TELEGRAM_BOT_TOKEN is not configured")

        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        endpoint = (
            "https://api.telegram.org/"
            f"bot{self._settings.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload)

        if response.status_code >= 400:
            raise TelegramDeliveryError(
                f"Telegram API HTTP error {response.status_code}: {response.text}",
            )

        body = response.json()
        if not body.get("ok", False):
            description = body.get("description", "unknown")
            raise TelegramDeliveryError(f"Telegram API error: {description}")
        return body
