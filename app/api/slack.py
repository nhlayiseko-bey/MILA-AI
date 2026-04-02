from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.core.security import verify_slack_request
from app.models.schemas import Channel
from app.runtime import gateway_processor
from app.utils.logger import get_logger, log_with_fields


router = APIRouter()
logger = get_logger(__name__)


@router.post("")
async def slack_webhook(
    request: Request,
    x_slack_request_timestamp: str | None = Header(default=None),
    x_slack_signature: str | None = Header(default=None),
) -> JSONResponse:
    raw_body = await request.body()
    verify_slack_request(
        raw_body=raw_body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    )
    payload: dict[str, Any] = await request.json()
    if payload.get("type") == "url_verification":
        return JSONResponse(content={"challenge": payload.get("challenge")})

    event = payload.get("event", {})
    if event.get("type") != "message" or event.get("subtype") is not None:
        return JSONResponse(content={"status": "ignored"})
    user_id = event.get("user")
    text = event.get("text", "")
    event_id = payload.get("event_id")
    if not user_id or not event_id:
        return JSONResponse(status_code=400, content={"status": "invalid_payload"})
    metadata = {
        "team_id": payload.get("team_id"),
        "event_time": payload.get("event_time"),
        "channel_id": event.get("channel"),
        "event_ts": event.get("event_ts"),
        "text_length": len(text),
    }
    result = await gateway_processor.process_inbound_message(
        channel=Channel.slack,
        source_event_id=str(event_id),
        external_id=user_id,
        message_text=text,
        event_type="employee_message",
        timestamp=event.get("event_ts"),
        metadata=metadata,
    )
    log_with_fields(
        logger,
        level=20,
        message="slack_event_processed",
        status=result.status,
        duplicate=result.duplicate,
        trigger_event_id=str(result.trigger_event_id) if result.trigger_event_id else None,
    )
    return JSONResponse(content=result.model_dump(mode="json"))
