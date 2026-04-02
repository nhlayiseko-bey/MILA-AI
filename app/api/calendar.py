from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.core.security import verify_calendar_secret
from app.models.schemas import CalendarWebhookPayload
from app.runtime import gateway_processor


router = APIRouter()


@router.post("")
async def calendar_webhook(
    request: Request,
    x_calendar_webhook_secret: str | None = Header(default=None),
) -> JSONResponse:
    verify_calendar_secret(x_calendar_webhook_secret)
    payload_data: dict[str, Any]
    try:
        payload_data = await request.json()
    except Exception:
        payload_data = {}
    source_event_id = request.headers.get("x-goog-message-number") or str(uuid4())
    if not payload_data:
        # Minimal Google webhook ping mode: no meeting content is accepted/stored.
        return JSONResponse(
            content={
                "status": "accepted",
                "source_event_id": source_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    forbidden_top_level = {"summary", "description", "attendees", "body", "meeting_notes"}
    if forbidden_top_level.intersection(set(payload_data.keys())):
        return JSONResponse(
            status_code=400,
            content={"status": "rejected", "reason": "raw_calendar_content_not_allowed"},
        )
    payload = CalendarWebhookPayload.model_validate(payload_data)
    result = await gateway_processor.process_calendar_metadata(
        payload=payload,
        source_event_id=source_event_id,
    )
    return JSONResponse(content=result.model_dump(mode="json"))
