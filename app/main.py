from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import calendar, health, internal, slack, telegram, whatsapp
from app.config import settings
from app.runtime import supabase_service
from app.utils.logger import configure_logging, get_logger, log_with_fields


configure_logging(logging.INFO)
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_with_fields(
        logger,
        level=logging.ERROR,
        message="unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    try:
        await supabase_service.insert_system_log(
            level="error",
            component="api",
            message="Unhandled exception",
            metadata={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc),
            },
        )
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"status": "error", "detail": "internal_server_error"})


app.include_router(slack.router, prefix="/webhook/slack", tags=["webhook"])
app.include_router(whatsapp.router, prefix="/webhook/whatsapp", tags=["webhook"])
app.include_router(calendar.router, prefix="/webhook/calendar", tags=["webhook"])
app.include_router(telegram.router, prefix="/webhook/telegram", tags=["webhook"])
app.include_router(internal.router, prefix="/internal", tags=["internal"])
app.include_router(health.router, prefix="/health", tags=["health"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "running", "service": settings.app_name}
