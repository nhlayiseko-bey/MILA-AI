from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.security import verify_whatsapp_handshake_token, verify_whatsapp_request
from app.models.schemas import Channel
from app.runtime import gateway_processor
from app.utils.logger import get_logger, log_with_fields


router = APIRouter()
logger = get_logger(__name__)


@router.get("")
async def whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode != "subscribe":
        return JSONResponse(status_code=400, content={"status": "invalid_mode"})
    verify_whatsapp_handshake_token(hub_verify_token)
    return PlainTextResponse(content=hub_challenge or "")


@router.post("")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    raw_body = await request.body()
    verify_whatsapp_request(raw_body=raw_body, signature=x_hub_signature_256)
    payload: dict[str, Any] = await request.json()
    results: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                message_type = message.get("type")
                if message_type != "text":
                    continue
                message_id = message.get("id")
                external_id = message.get("from")
                text = message.get("text", {}).get("body", "")
                if not message_id or not external_id:
                    continue
                metadata = {
                    "wa_business_phone_id": value.get("metadata", {}).get("phone_number_id"),
                    "wa_display_phone": value.get("metadata", {}).get("display_phone_number"),
                    "text_length": len(text),
                    "message_type": message_type,
                }
                result = await gateway_processor.process_inbound_message(
                    channel=Channel.whatsapp,
                    source_event_id=str(message_id),
                    external_id=external_id,
                    message_text=text,
                    event_type="employee_message",
                    timestamp=message.get("timestamp"),
                    metadata=metadata,
                )
                results.append(result.model_dump(mode="json"))
    log_with_fields(
        logger,
        level=20,
        message="whatsapp_event_processed",
        processed_count=len(results),
    )
    return JSONResponse(content={"status": "ok", "results": results})
