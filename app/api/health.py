from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.runtime import openclaw_client, supabase_service


router = APIRouter()


@router.get("")
async def health_check() -> dict:
    supabase_health = await supabase_service.check_health()
    openclaw_health = await openclaw_client.check_health()
    try:
        await supabase_service.insert_system_health(
            component="supabase",
            status=supabase_health.get("status", "unknown"),
            details=supabase_health,
        )
        await supabase_service.insert_system_health(
            component="openclaw",
            status=openclaw_health.get("status", "unknown"),
            details=openclaw_health,
        )
    except Exception:
        # Health endpoint must still return status even if persistence fails.
        pass
    overall = "ok"
    if supabase_health.get("status") != "ok" or openclaw_health.get("status") != "ok":
        overall = "degraded"
    return {
        "status": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "components": {
            "supabase": supabase_health,
            "openclaw": openclaw_health,
        },
    }
