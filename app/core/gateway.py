from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.state_machine import InvalidStateTransition
from app.models.schemas import (
    AIAnalysisResult,
    CalendarWebhookPayload,
    Channel,
    ConsentLogRequest,
    DeliveryStatus,
    EmployeeState,
    TriggerGenerationRequest,
    WebhookProcessResult,
)
from app.services.delivery_service import DeliveryService
from app.services.employee_service import EmployeeService
from app.services.event_normalizer import (
    normalize_message_event,
    normalize_structured_event,
    normalize_telegram_update,
)
from app.services.openclaw import OpenClawClient
from app.services.scoring_service import ScoringService
from app.services.supabase import SupabaseService
from app.utils.logger import get_logger, log_with_fields


logger = get_logger(__name__)


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted_keys = {"text", "message", "content", "body"}
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in redacted_keys:
            sanitized[key] = "[redacted]"
            continue
        if isinstance(value, dict):
            sanitized[key] = _sanitize_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class GatewayProcessor:
    def __init__(
        self,
        *,
        supabase_service: SupabaseService,
        employee_service: EmployeeService,
        delivery_service: DeliveryService,
        openclaw_client: OpenClawClient,
        scoring_service: ScoringService,
    ) -> None:
        self._supabase = supabase_service
        self._employee_service = employee_service
        self._delivery = delivery_service
        self._openclaw = openclaw_client
        self._scoring = scoring_service
        self._inbound_locks: dict[str, asyncio.Lock] = {}

    async def _reset_employee_after_failed_inbound(
        self,
        *,
        employee_uuid: UUID,
        channel: Channel,
        trigger_event_id: str,
        source_event_id: str,
    ) -> None:
        try:
            recovered_state = await self._employee_service.reset_after_inbound_failure(employee_uuid)
            log_with_fields(
                logger,
                level=30,
                message="employee_cycle_reset_after_failed_inbound",
                employee_uuid=str(employee_uuid),
                channel=channel.value,
                trigger_event_id=trigger_event_id,
                source_event_id=source_event_id,
                recovered_state=recovered_state.value,
            )
        except Exception as exc:
            log_with_fields(
                logger,
                level=40,
                message="employee_cycle_reset_failed",
                employee_uuid=str(employee_uuid),
                channel=channel.value,
                trigger_event_id=trigger_event_id,
                source_event_id=source_event_id,
                error=str(exc),
            )

    async def handle_inbound_event(self, normalized_event: dict[str, Any]) -> WebhookProcessResult:
        channel = Channel(normalized_event["channel"])
        metadata = {
            "source_user_id": normalized_event.get("source_user_id"),
            "channel_id": normalized_event.get("channel_id"),
            "content_hash": normalized_event.get("content_hash"),
            "raw_payload_keys": sorted((normalized_event.get("raw_payload") or {}).keys()),
        }
        return await self.process_inbound_message(
            channel=channel,
            source_event_id=str(normalized_event["source_event_id"]),
            external_id=str(normalized_event["channel_id"]),
            message_text=normalized_event["message_text"],
            event_type=normalized_event.get("event_type", "employee_message"),
            timestamp=normalized_event.get("timestamp"),
            metadata=metadata,
        )

    async def handle_telegram_update(self, payload: dict[str, Any]) -> None:
        normalized = normalize_telegram_update(payload)
        if normalized is None:
            log_with_fields(
                logger,
                level=20,
                message="telegram_update_ignored",
                reason="unsupported_update_type",
                payload_keys=sorted(payload.keys()),
            )
            return
        log_with_fields(
            logger,
            level=20,
            message="telegram_event_normalized",
            source_event_id=normalized.get("source_event_id"),
            channel_id=normalized.get("channel_id"),
            source_user_id=normalized.get("source_user_id"),
        )
        await self.handle_inbound_event(normalized)

    async def process_inbound_message(
        self,
        *,
        channel: Channel,
        source_event_id: str,
        external_id: str,
        message_text: str,
        event_type: str,
        timestamp: str | int | float | None,
        metadata: dict[str, Any],
    ) -> WebhookProcessResult:
        employee = await self._employee_service.resolve_by_channel_identifier(channel, external_id)
        if employee is None:
            if channel == Channel.telegram and settings.enable_test_employee_fallback:
                employee = await self._supabase.get_or_create_telegram_test_employee(external_id)
                if employee is not None:
                    log_with_fields(
                        logger,
                        level=30,
                        message="telegram_test_employee_fallback_used",
                        channel=channel.value,
                        external_id=external_id,
                        employee_uuid=employee.get("id"),
                    )
            if employee is None:
                log_with_fields(
                    logger,
                    level=30,
                    message="employee_resolution_failed",
                    channel=channel.value,
                    external_id=external_id,
                )
                await self._supabase.insert_dead_letter(
                    source=f"{channel.value}_webhook",
                    source_event_id=source_event_id,
                    payload=_sanitize_payload(metadata),
                    error_message="employee_not_found",
                )
                return WebhookProcessResult(status="employee_not_found")

        employee_uuid = UUID(employee["id"])
        employee_lock = self._inbound_locks.setdefault(str(employee_uuid), asyncio.Lock())
        if employee_lock.locked():
            log_with_fields(
                logger,
                level=20,
                message="employee_inbound_waiting_for_active_cycle",
                employee_uuid=str(employee_uuid),
                channel=channel.value,
                source_event_id=source_event_id,
            )

        async with employee_lock:
            return await self._process_inbound_message_for_employee(
                employee=employee,
                employee_uuid=employee_uuid,
                channel=channel,
                source_event_id=source_event_id,
                external_id=external_id,
                message_text=message_text,
                event_type=event_type,
                timestamp=timestamp,
                metadata=metadata,
            )

    async def _process_inbound_message_for_employee(
        self,
        *,
        employee: dict[str, Any],
        employee_uuid: UUID,
        channel: Channel,
        source_event_id: str,
        external_id: str,
        message_text: str,
        event_type: str,
        timestamp: str | int | float | None,
        metadata: dict[str, Any],
    ) -> WebhookProcessResult:
        normalized = normalize_message_event(
            employee_uuid=employee_uuid,
            channel=channel,
            event_type=event_type,
            message_text=message_text,
            timestamp=timestamp,
            metadata=metadata,
        )
        trigger_event, inserted = await self._supabase.insert_trigger_event(
            event=normalized,
            company_id=UUID(employee["company_id"]),
            source_event_id=source_event_id,
            delivery_status=DeliveryStatus.pending,
        )
        if not inserted:
            log_with_fields(
                logger,
                level=20,
                message="duplicate_inbound_event",
                channel=channel.value,
                source_event_id=source_event_id,
                employee_uuid=str(employee_uuid),
            )
            return WebhookProcessResult(
                status="duplicate",
                duplicate=True,
                trigger_event_id=UUID(trigger_event["id"]),
                employee_uuid=employee_uuid,
            )

        try:
            await self._employee_service.move_to_awaiting_for_inbound(employee_uuid)
            log_with_fields(
                logger,
                level=20,
                message="openclaw_request_started",
                employee_uuid=str(employee_uuid),
                channel=channel.value,
                trigger_event_id=trigger_event["id"],
            )
            analysis = await self._openclaw.analyze_message(
                employee_uuid=employee_uuid,
                user_text=message_text,
                channel=channel.value,
                metadata=metadata,
            )
            log_with_fields(
                logger,
                level=20,
                message="openclaw_request_completed",
                employee_uuid=str(employee_uuid),
                channel=channel.value,
                trigger_event_id=trigger_event["id"],
                flag=analysis.flag,
                sentiment_score=analysis.sentiment_score,
            )
            await self._scoring.persist_analysis_result(
                employee_uuid=employee_uuid,
                result=analysis,
                trigger_event_uuid=UUID(trigger_event["id"]),
                triggered_rule_id=event_type,
            )
            await self._employee_service.complete_scoring(employee_uuid)
            delivery = await self._delivery.send_reply(
                channel=channel,
                recipient_id=external_id,
                text=analysis.reply_text,
            )
            await self._supabase.update_trigger_delivery(
                UUID(trigger_event["id"]),
                delivery_status=delivery.status,
                provider_message_id=delivery.provider_message_id,
                error_message=delivery.error_message,
            )
            await self._supabase.insert_system_log(
                level="info" if delivery.status == DeliveryStatus.delivered else "error",
                component="delivery",
                message="delivery_result",
                metadata={
                    "employee_uuid": str(employee_uuid),
                    "channel": channel.value,
                    "trigger_event_id": trigger_event["id"],
                    "delivery_status": delivery.status.value,
                    "provider_message_id": delivery.provider_message_id,
                    "provider_response": delivery.provider_response,
                    "error_message": delivery.error_message,
                },
            )
            if delivery.status == DeliveryStatus.delivered:
                await self._employee_service.close_cycle_if_delivered(employee_uuid)
            else:
                await self._reset_employee_after_failed_inbound(
                    employee_uuid=employee_uuid,
                    channel=channel,
                    trigger_event_id=trigger_event["id"],
                    source_event_id=source_event_id,
                )
                await self._supabase.insert_system_log(
                    level="error",
                    component="delivery",
                    message="Failed to deliver outbound response",
                    metadata={
                        "employee_uuid": str(employee_uuid),
                        "channel": channel.value,
                        "trigger_event_id": trigger_event["id"],
                        "error_message": delivery.error_message,
                    },
                )
            return WebhookProcessResult(
                status="processed",
                trigger_event_id=UUID(trigger_event["id"]),
                employee_uuid=employee_uuid,
            )
        except InvalidStateTransition as exc:
            await self._supabase.update_trigger_delivery(
                UUID(trigger_event["id"]),
                delivery_status=DeliveryStatus.failed,
                error_message=str(exc),
            )
            await self._supabase.insert_dead_letter(
                source=f"{channel.value}_webhook",
                source_event_id=source_event_id,
                payload=_sanitize_payload(metadata),
                error_message=str(exc),
            )
            await self._reset_employee_after_failed_inbound(
                employee_uuid=employee_uuid,
                channel=channel,
                trigger_event_id=trigger_event["id"],
                source_event_id=source_event_id,
            )
            return WebhookProcessResult(
                status="invalid_state_transition",
                trigger_event_id=UUID(trigger_event["id"]),
                employee_uuid=employee_uuid,
            )
        except Exception as exc:
            await self._supabase.update_trigger_delivery(
                UUID(trigger_event["id"]),
                delivery_status=DeliveryStatus.failed,
                error_message=str(exc),
            )
            await self._supabase.insert_dead_letter(
                source=f"{channel.value}_webhook",
                source_event_id=source_event_id,
                payload=_sanitize_payload(metadata),
                error_message=str(exc),
            )
            await self._reset_employee_after_failed_inbound(
                employee_uuid=employee_uuid,
                channel=channel,
                trigger_event_id=trigger_event["id"],
                source_event_id=source_event_id,
            )
            raise

    async def process_calendar_metadata(
        self,
        *,
        payload: CalendarWebhookPayload,
        source_event_id: str,
    ) -> WebhookProcessResult:
        employee = await self._employee_service.get_by_uuid(payload.employee_uuid)
        if employee is None:
            await self._supabase.insert_dead_letter(
                source="calendar_webhook",
                source_event_id=source_event_id,
                payload=payload.model_dump(mode="json"),
                error_message="employee_not_found",
            )
            return WebhookProcessResult(status="employee_not_found")

        derived_metadata = {
            "event_count": payload.event_count,
            "total_duration_minutes": payload.total_duration_minutes,
            "back_to_back": payload.back_to_back,
            "source": payload.source,
            "metadata": payload.metadata,
        }
        normalized = normalize_structured_event(
            employee_uuid=payload.employee_uuid,
            channel=Channel.calendar,
            event_type="workload_metadata",
            payload_for_hash=derived_metadata,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=derived_metadata,
        )
        trigger_event, inserted = await self._supabase.insert_trigger_event(
            event=normalized,
            company_id=UUID(employee["company_id"]),
            source_event_id=source_event_id,
            delivery_status=DeliveryStatus.delivered,
        )
        if not inserted:
            return WebhookProcessResult(
                status="duplicate",
                duplicate=True,
                trigger_event_id=UUID(trigger_event["id"]),
                employee_uuid=payload.employee_uuid,
            )
        max_daily_minutes = 480
        load_ratio = min(1.0, payload.total_duration_minutes / max_daily_minutes)
        await self._supabase.insert_meeting_load_score(
            employee_uuid=payload.employee_uuid,
            meeting_load_score=round(load_ratio, 4),
        )
        if payload.back_to_back and payload.event_count >= 5:
            await self._supabase.insert_flag(
                employee_uuid=payload.employee_uuid,
                score_uuid=None,
                severity="medium",
                reason="High workload pattern detected from calendar metadata",
            )
        return WebhookProcessResult(
            status="processed",
            trigger_event_id=UUID(trigger_event["id"]),
            employee_uuid=payload.employee_uuid,
        )

    async def create_trigger_and_deliver(
        self,
        *,
        request: TriggerGenerationRequest,
    ) -> WebhookProcessResult:
        employee = await self._employee_service.get_by_uuid(request.employee_uuid)
        if employee is None:
            return WebhookProcessResult(status="employee_not_found")
        channel = Channel(request.channel)
        if channel == Channel.slack:
            recipient = employee.get("slack_user_id")
        elif channel == Channel.whatsapp:
            recipient = employee.get("whatsapp_phone")
        else:
            recipient = employee.get("telegram_chat_id")
        if not recipient:
            return WebhookProcessResult(status="missing_channel_identifier", employee_uuid=request.employee_uuid)
        try:
            await self._employee_service.transition_state(request.employee_uuid, EmployeeState.prompted)
        except InvalidStateTransition:
            return WebhookProcessResult(
                status="invalid_state_transition",
                employee_uuid=request.employee_uuid,
            )
        normalized = normalize_message_event(
            employee_uuid=request.employee_uuid,
            channel=channel,
            event_type=request.event_type,
            message_text=request.prompt_text,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=request.metadata,
        )
        source_event_id = request.source_event_id or f"internal-{datetime.now(UTC).timestamp()}"
        trigger_event, inserted = await self._supabase.insert_trigger_event(
            event=normalized,
            company_id=UUID(employee["company_id"]),
            source_event_id=source_event_id,
            delivery_status=DeliveryStatus.pending,
        )
        if not inserted:
            return WebhookProcessResult(
                status="duplicate",
                duplicate=True,
                trigger_event_id=UUID(trigger_event["id"]),
                employee_uuid=request.employee_uuid,
            )
        delivery = await self._delivery.send_reply(
            channel=channel,
            recipient_id=recipient,
            text=request.prompt_text,
        )
        await self._supabase.update_trigger_delivery(
            UUID(trigger_event["id"]),
            delivery_status=delivery.status,
            provider_message_id=delivery.provider_message_id,
            error_message=delivery.error_message,
        )
        return WebhookProcessResult(
            status="processed" if delivery.status == DeliveryStatus.delivered else "delivery_failed",
            trigger_event_id=UUID(trigger_event["id"]),
            employee_uuid=request.employee_uuid,
        )

    async def process_score_result(
        self,
        *,
        employee_uuid: UUID,
        result: AIAnalysisResult,
        trigger_event_uuid: UUID | None,
        triggered_rule_id: str | None,
    ) -> dict[str, Any]:
        persisted = await self._scoring.persist_analysis_result(
            employee_uuid=employee_uuid,
            result=result,
            trigger_event_uuid=trigger_event_uuid,
            triggered_rule_id=triggered_rule_id,
        )
        try:
            await self._employee_service.complete_scoring(employee_uuid)
            await self._employee_service.close_cycle_if_delivered(employee_uuid)
        except InvalidStateTransition:
            await self._supabase.insert_system_log(
                level="warning",
                component="state_machine",
                message="score processing completed without state transition",
                metadata={"employee_uuid": str(employee_uuid)},
            )
        return persisted

    async def record_consent(self, *, request: ConsentLogRequest) -> dict[str, Any]:
        employee = await self._employee_service.get_by_uuid(request.employee_uuid)
        if employee is None:
            raise ValueError(f"employee {request.employee_uuid} not found")
        return (
            await self._supabase.insert_consent_log(
                employee_uuid=request.employee_uuid,
                consent_given=request.consent_given,
                source_channel=request.source_channel,
                metadata=request.metadata,
            )
            or {}
        )
