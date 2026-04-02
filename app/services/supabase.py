from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.config import Settings
from app.models.schemas import AIAnalysisResult, Channel, DeliveryStatus, InboundEvent


class SupabaseServiceError(Exception):
    pass


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_rest_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
        if not self._settings.supabase_url or not self._settings.supabase_service_role_key:
            raise SupabaseServiceError("Supabase URL or service role key not configured")
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method,
                        f"{self._base_rest_url}/{table}",
                        headers=headers,
                        params=params,
                        json=payload,
                    )
                if response.status_code >= 500:
                    raise SupabaseServiceError(
                        f"Supabase server error {response.status_code}: {response.text}",
                    )
                if response.status_code >= 400:
                    raise SupabaseServiceError(
                        f"Supabase request failed {response.status_code}: {response.text}",
                    )
                if response.text.strip() == "":
                    return None
                return response.json()
            except (httpx.RequestError, SupabaseServiceError) as exc:
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise
        if last_error:
            raise last_error
        raise SupabaseServiceError("Unknown Supabase request failure")

    @staticmethod
    def _as_rows(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        return []

    async def check_health(self) -> dict[str, Any]:
        try:
            await self._request("GET", "employees", params={"select": "id", "limit": 1})
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    async def get_employee_by_channel_identifier(
        self,
        channel: Channel,
        external_id: str,
    ) -> dict[str, Any] | None:
        channel_field = {
            Channel.slack: "slack_user_id",
            Channel.whatsapp: "whatsapp_phone",
            Channel.telegram: "telegram_chat_id",
        }.get(channel)
        if channel_field is None:
            return None
        rows = self._as_rows(await self._request(
            "GET",
            "employees",
            params={"select": "*", channel_field: f"eq.{external_id}", "limit": 1},
        ))
        return rows[0] if rows else None

    async def get_or_create_telegram_test_employee(self, chat_id: str) -> dict[str, Any] | None:
        existing = await self.get_employee_by_channel_identifier(Channel.telegram, chat_id)
        if existing is not None:
            return existing
        if not self._settings.test_company_id:
            return None
        rows = self._as_rows(await self._request(
            "POST",
            "employees",
            payload={
                "company_id": self._settings.test_company_id,
                "name": f"Telegram Test User {chat_id}",
                "telegram_chat_id": chat_id,
                "current_state": "idle",
                "channel_preference": "telegram",
                "consent_given": False,
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def get_employee_by_uuid(self, employee_uuid: UUID) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "GET",
            "employees",
            params={"select": "*", "id": f"eq.{employee_uuid}", "limit": 1},
        ))
        return rows[0] if rows else None

    async def update_employee_state(self, employee_uuid: UUID, new_state: str) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "PATCH",
            "employees",
            params={"id": f"eq.{employee_uuid}", "select": "*"},
            payload={
                "current_state": new_state,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def insert_trigger_event(
        self,
        *,
        event: InboundEvent,
        company_id: UUID,
        source_event_id: str | None,
        delivery_status: DeliveryStatus = DeliveryStatus.pending,
        provider_message_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        payload = {
            "employee_uuid": str(event.employee_uuid),
            "company_id": str(company_id),
            "source_event_id": source_event_id,
            "channel": event.channel.value,
            "event_type": event.event_type,
            "content_hash": event.content_hash,
            "metadata": event.metadata,
            "delivery_status": delivery_status.value,
            "provider_message_id": provider_message_id,
            "created_at": event.timestamp.isoformat(),
        }
        rows = self._as_rows(await self._request(
            "POST",
            "trigger_events",
            params={"on_conflict": "channel,source_event_id"},
            payload=payload,
            prefer="resolution=ignore-duplicates,return=representation",
        ))
        if rows:
            return rows[0], True
        if source_event_id is None:
            raise SupabaseServiceError("Trigger event insert returned no row without source_event_id")
        existing = await self.get_trigger_event_by_source_event_id(event.channel, source_event_id)
        if existing is None:
            raise SupabaseServiceError("Trigger event conflict occurred but existing row not found")
        return existing, False

    async def get_trigger_event_by_source_event_id(
        self,
        channel: Channel,
        source_event_id: str,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "GET",
            "trigger_events",
            params={
                "select": "*",
                "channel": f"eq.{channel.value}",
                "source_event_id": f"eq.{source_event_id}",
                "limit": 1,
            },
        ))
        return rows[0] if rows else None

    async def update_trigger_delivery(
        self,
        trigger_event_uuid: UUID,
        *,
        delivery_status: DeliveryStatus,
        provider_message_id: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "PATCH",
            "trigger_events",
            params={"id": f"eq.{trigger_event_uuid}", "select": "*"},
            payload={
                "delivery_status": delivery_status.value,
                "provider_message_id": provider_message_id,
                "delivery_error": error_message,
                "delivery_updated_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def insert_processed_event(
        self,
        *,
        employee_uuid: UUID,
        result: AIAnalysisResult,
        trigger_event_uuid: UUID | None = None,
        triggered_rule_id: str | None = None,
        processed_at: datetime | None = None,
    ) -> dict[str, Any]:
        payload = {
            "trigger_event_uuid": str(trigger_event_uuid) if trigger_event_uuid else None,
            "employee_uuid": str(employee_uuid),
            "sentiment_score": result.sentiment_score,
            "emotion_label": result.emotion_label,
            "engagement_level": result.engagement_level,
            "flag": result.flag,
            "flag_reason": result.flag_reason,
            "reply_text": result.reply_text,
            "triggered_rule_id": triggered_rule_id,
            "processed_at": (processed_at or datetime.now(UTC)).isoformat(),
        }
        rows = self._as_rows(await self._request(
            "POST",
            "processed_events",
            payload=payload,
            prefer="return=representation",
        ))
        if not rows:
            raise SupabaseServiceError("Processed event insert returned no rows")
        return rows[0]

    async def insert_score(
        self,
        *,
        employee_uuid: UUID,
        result: AIAnalysisResult,
    ) -> dict[str, Any]:
        mood_score = round((result.sentiment_score + 1.0) * 50.0, 2)
        payload = {
            "employee_uuid": str(employee_uuid),
            "mood_score": mood_score,
            "flag_raised": result.flag,
            "computed_at": datetime.now(UTC).isoformat(),
        }
        rows = self._as_rows(await self._request(
            "POST",
            "scores",
            payload=payload,
            prefer="return=representation",
        ))
        if not rows:
            raise SupabaseServiceError("Score insert returned no rows")
        return rows[0]

    async def insert_meeting_load_score(
        self,
        *,
        employee_uuid: UUID,
        meeting_load_score: float,
    ) -> dict[str, Any]:
        payload = {
            "employee_uuid": str(employee_uuid),
            "meeting_load_score": meeting_load_score,
            "computed_at": datetime.now(UTC).isoformat(),
        }
        rows = self._as_rows(await self._request(
            "POST",
            "scores",
            payload=payload,
            prefer="return=representation",
        ))
        if not rows:
            raise SupabaseServiceError("Meeting load score insert returned no rows")
        return rows[0]

    async def insert_flag(
        self,
        *,
        employee_uuid: UUID,
        score_uuid: UUID | None,
        severity: str,
        reason: str,
    ) -> dict[str, Any]:
        payload = {
            "employee_uuid": str(employee_uuid),
            "score_uuid": str(score_uuid) if score_uuid else None,
            "severity": severity,
            "reason": reason,
            "resolution_status": "open",
            "created_at": datetime.now(UTC).isoformat(),
        }
        rows = self._as_rows(await self._request(
            "POST",
            "flags",
            payload=payload,
            prefer="return=representation",
        ))
        if not rows:
            raise SupabaseServiceError("Flag insert returned no rows")
        return rows[0]

    async def insert_dead_letter(
        self,
        *,
        source: str,
        source_event_id: str | None,
        payload: dict[str, Any],
        error_message: str,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "POST",
            "dead_letter_queue",
            payload={
                "source": source,
                "source_event_id": source_event_id,
                "payload": payload,
                "error_message": error_message,
                "created_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def insert_consent_log(
        self,
        *,
        employee_uuid: UUID,
        consent_given: bool,
        source_channel: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "POST",
            "consent_logs",
            payload={
                "employee_uuid": str(employee_uuid),
                "consent_given": consent_given,
                "source_channel": source_channel,
                "metadata": metadata or {},
                "recorded_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def insert_system_log(
        self,
        *,
        level: str,
        component: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "POST",
            "system_logs",
            payload={
                "level": level,
                "component": component,
                "message": message,
                "metadata": metadata or {},
                "created_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None

    async def insert_system_health(
        self,
        *,
        component: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self._as_rows(await self._request(
            "POST",
            "system_health",
            payload={
                "component": component,
                "status": status,
                "details": details or {},
                "checked_at": datetime.now(UTC).isoformat(),
            },
            prefer="return=representation",
        ))
        return rows[0] if rows else None
