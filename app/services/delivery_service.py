from __future__ import annotations

from app.models.schemas import Channel, DeliveryResult, DeliveryStatus
from app.services.slack_service import SlackDeliveryError, SlackService
from app.services.telegram_service import TelegramDeliveryError, TelegramService
from app.services.whatsapp_service import WhatsAppDeliveryError, WhatsAppService


class DeliveryService:
    def __init__(
        self,
        slack_service: SlackService,
        whatsapp_service: WhatsAppService,
        telegram_service: TelegramService,
    ) -> None:
        self._slack_service = slack_service
        self._whatsapp_service = whatsapp_service
        self._telegram_service = telegram_service

    async def send_reply(self, *, channel: Channel, recipient_id: str, text: str) -> DeliveryResult:
        try:
            if channel == Channel.slack:
                result = await self._slack_service.send_message(recipient_id=recipient_id, text=text)
                return DeliveryResult(
                    status=DeliveryStatus.delivered,
                    provider_message_id=result.get("ts"),
                    provider_response=result,
                )
            if channel == Channel.whatsapp:
                result = await self._whatsapp_service.send_message(recipient_phone=recipient_id, text=text)
                provider_message_id = None
                messages = result.get("messages")
                if isinstance(messages, list) and messages:
                    provider_message_id = messages[0].get("id")
                return DeliveryResult(
                    status=DeliveryStatus.delivered,
                    provider_message_id=provider_message_id,
                    provider_response=result,
                )
            if channel == Channel.telegram:
                result = await self._telegram_service.send_message(chat_id=recipient_id, text=text)
                provider_message_id = None
                message = result.get("result")
                if isinstance(message, dict):
                    message_id = message.get("message_id")
                    if message_id is not None:
                        provider_message_id = str(message_id)
                return DeliveryResult(
                    status=DeliveryStatus.delivered,
                    provider_message_id=provider_message_id,
                    provider_response=result,
                )
            return DeliveryResult(
                status=DeliveryStatus.failed,
                error_message=f"Unsupported delivery channel: {channel.value}",
            )
        except (SlackDeliveryError, WhatsAppDeliveryError, TelegramDeliveryError) as exc:
            return DeliveryResult(
                status=DeliveryStatus.failed,
                error_message=str(exc),
            )
