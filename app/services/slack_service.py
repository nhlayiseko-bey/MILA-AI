from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class SlackDeliveryError(Exception):
    pass


class SlackService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_message(self, *, recipient_id: str, text: str) -> dict[str, Any]:
        if not self._settings.slack_bot_token:
            raise SlackDeliveryError("SLACK_BOT_TOKEN is not configured")
        headers = {
            "Authorization": f"Bearer {self._settings.slack_bot_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "channel": recipient_id,
            "text": text,
        }
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post("https://slack.com/api/chat.postMessage", json=payload, headers=headers)
        if response.status_code >= 400:
            raise SlackDeliveryError(f"Slack API HTTP error {response.status_code}: {response.text}")
        body = response.json()
        if not body.get("ok"):
            raise SlackDeliveryError(f"Slack API error: {body.get('error', 'unknown')}")
        return body
