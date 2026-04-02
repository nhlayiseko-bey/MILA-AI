from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class WhatsAppDeliveryError(Exception):
    pass


class WhatsAppService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_message(self, *, recipient_phone: str, text: str) -> dict[str, Any]:
        if not self._settings.whatsapp_access_token:
            raise WhatsAppDeliveryError("WHATSAPP_ACCESS_TOKEN is not configured")
        if not self._settings.whatsapp_phone_number_id:
            raise WhatsAppDeliveryError("WHATSAPP_PHONE_NUMBER_ID is not configured")
        headers = {
            "Authorization": f"Bearer {self._settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "text",
            "text": {"body": text},
        }
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"https://graph.facebook.com/v22.0/{self._settings.whatsapp_phone_number_id}/messages",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            raise WhatsAppDeliveryError(f"WhatsApp API HTTP error {response.status_code}: {response.text}")
        body = response.json()
        if "error" in body:
            error = body["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise WhatsAppDeliveryError(f"WhatsApp API error: {message}")
        return body
