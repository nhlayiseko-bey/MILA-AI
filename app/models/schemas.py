from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class Channel(str, Enum):
    slack = "slack"
    whatsapp = "whatsapp"
    telegram = "telegram"
    calendar = "calendar"


class EmployeeState(str, Enum):
    idle = "idle"
    prompted = "prompted"
    awaiting = "awaiting"
    scored = "scored"


class DeliveryStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"


class InboundEvent(BaseModel):
    employee_uuid: UUID
    channel: Channel
    event_type: str
    content_hash: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIAnalysisResult(BaseModel):
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    emotion_label: str = Field(min_length=1, max_length=128)
    engagement_level: Literal["low", "med", "high"]
    flag: bool
    flag_reason: str | None = None
    reply_text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_flag_reason(self) -> "AIAnalysisResult":
        if self.flag and not self.flag_reason:
            raise ValueError("flag_reason is required when flag is true")
        return self


class DeliveryResult(BaseModel):
    status: DeliveryStatus
    provider_message_id: str | None = None
    provider_response: dict[str, Any] | None = None
    error_message: str | None = None


class TriggerGenerationRequest(BaseModel):
    employee_uuid: UUID
    channel: Literal["slack", "whatsapp", "telegram"]
    prompt_text: str = Field(min_length=1, max_length=2000)
    event_type: str = Field(default="scheduled_prompt", min_length=1, max_length=120)
    source_event_id: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoreProcessingRequest(BaseModel):
    employee_uuid: UUID
    trigger_event_uuid: UUID | None = None
    triggered_rule_id: str | None = Field(default=None, max_length=120)
    result: AIAnalysisResult


class ConsentLogRequest(BaseModel):
    employee_uuid: UUID
    consent_given: bool
    source_channel: Literal["slack", "whatsapp", "dashboard", "web", "internal"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalendarWebhookPayload(BaseModel):
    employee_uuid: UUID
    event_count: int = Field(ge=0, le=200)
    total_duration_minutes: int = Field(ge=0, le=24 * 60)
    back_to_back: bool = False
    source: str = Field(default="google_calendar", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_raw_calendar_content(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden_fields = {"summary", "description", "attendees", "meeting_notes", "body"}
        if forbidden_fields.intersection(set(value.keys())):
            raise ValueError("raw calendar content is not allowed in metadata")
        return value


class WebhookProcessResult(BaseModel):
    status: str
    trigger_event_id: UUID | None = None
    employee_uuid: UUID | None = None
    duplicate: bool = False
