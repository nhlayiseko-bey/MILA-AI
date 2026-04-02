from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.schemas import Channel, InboundEvent


def _hash_text(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return digest


def _normalize_timestamp(timestamp: str | int | float | None) -> datetime:
    if timestamp is None:
        return datetime.now(UTC)
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(float(timestamp), UTC)
    raw = str(timestamp).strip()
    if raw.isdigit():
        return datetime.fromtimestamp(float(raw), UTC)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def normalize_message_event(
    *,
    employee_uuid: UUID,
    channel: Channel,
    event_type: str,
    message_text: str,
    timestamp: str | int | float | None,
    metadata: dict[str, Any] | None = None,
) -> InboundEvent:
    safe_metadata = metadata or {}
    content_hash = _hash_text(message_text)
    return InboundEvent(
        employee_uuid=employee_uuid,
        channel=channel,
        event_type=event_type,
        content_hash=content_hash,
        timestamp=_normalize_timestamp(timestamp),
        metadata=safe_metadata,
    )


def normalize_structured_event(
    *,
    employee_uuid: UUID,
    channel: Channel,
    event_type: str,
    payload_for_hash: dict[str, Any],
    timestamp: str | int | float | None,
    metadata: dict[str, Any] | None = None,
) -> InboundEvent:
    serialized = json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=True)
    return InboundEvent(
        employee_uuid=employee_uuid,
        channel=channel,
        event_type=event_type,
        content_hash=_hash_text(serialized),
        timestamp=_normalize_timestamp(timestamp),
        metadata=metadata or {},
    )


def normalize_telegram_update(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    message_id = message.get("message_id")
    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_id = chat.get("id")
    source_user_id = sender.get("id")
    timestamp = message.get("date")

    if message_id is None or chat_id is None or source_user_id is None:
        return None

    normalized_timestamp = _normalize_timestamp(timestamp).isoformat()
    composite_source_event_id = f"{chat_id}:{message_id}"

    return {
        "channel": Channel.telegram.value,
        "event_type": "message",
        "source_event_id": composite_source_event_id,
        "source_user_id": str(source_user_id),
        "channel_id": str(chat_id),
        "message_text": text,
        "content_hash": _hash_text(text),
        "timestamp": normalized_timestamp,
        "raw_payload": payload,
    }
