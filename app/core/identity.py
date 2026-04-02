from __future__ import annotations

from app.models.schemas import Channel
from app.services.supabase import SupabaseService


async def resolve_identity(
    supabase_service: SupabaseService,
    channel: Channel,
    identifier: str,
) -> dict | None:
    return await supabase_service.get_employee_by_channel_identifier(channel, identifier)
