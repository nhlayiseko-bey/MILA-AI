from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.schemas import AIAnalysisResult
from app.services.supabase import SupabaseService


def _severity_from_result(result: AIAnalysisResult) -> str:
    if result.sentiment_score <= -0.7:
        return "high"
    if result.sentiment_score <= -0.4:
        return "medium"
    return "low"


class ScoringService:
    def __init__(self, supabase_service: SupabaseService) -> None:
        self._supabase = supabase_service

    async def persist_analysis_result(
        self,
        *,
        employee_uuid: UUID,
        result: AIAnalysisResult,
        trigger_event_uuid: UUID | None = None,
        triggered_rule_id: str | None = None,
    ) -> dict[str, Any]:
        processed = await self._supabase.insert_processed_event(
            employee_uuid=employee_uuid,
            result=result,
            trigger_event_uuid=trigger_event_uuid,
            triggered_rule_id=triggered_rule_id,
        )
        score = await self._supabase.insert_score(employee_uuid=employee_uuid, result=result)
        flag = None
        if result.flag:
            flag = await self._supabase.insert_flag(
                employee_uuid=employee_uuid,
                score_uuid=UUID(score["id"]),
                severity=_severity_from_result(result),
                reason=result.flag_reason or "Flag raised by analysis pipeline",
            )
        return {
            "processed_event": processed,
            "score": score,
            "flag": flag,
        }
