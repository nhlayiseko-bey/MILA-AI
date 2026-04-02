from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.runtime import gateway_processor
from app.utils.logger import get_logger, log_with_fields


router = APIRouter()
logger = get_logger(__name__)
_inflight_tasks: set[asyncio.Task[None]] = set()


def _schedule_telegram_update(payload: dict[str, Any]) -> None:
    task = asyncio.create_task(_process_telegram_update(payload))
    _inflight_tasks.add(task)
    task.add_done_callback(_inflight_tasks.discard)


async def _process_telegram_update(payload: dict[str, Any]) -> None:
    try:
        await gateway_processor.handle_telegram_update(payload)
    except Exception as exc:
        log_with_fields(
            logger,
            level=40,
            message="telegram_update_processing_failed",
            error=str(exc),
            has_message=bool(payload.get("message")),
        )


@router.post("")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    expected_secret = settings.telegram_webhook_secret
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram webhook secret is not configured",
        )
    if x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram secret token",
        )

    payload: dict[str, Any] = await request.json()
    _schedule_telegram_update(payload)

    log_with_fields(
        logger,
        level=20,
        message="telegram_update_received",
        has_message=bool(payload.get("message")),
    )
    return JSONResponse(content={"ok": True})
