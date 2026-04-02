from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx

from app.config import Settings
from app.models.schemas import AIAnalysisResult


class OpenClawServiceError(Exception):
    pass


class OpenClawClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _headers(self, employee_uuid: UUID) -> dict[str, str]:
        if not self._settings.openclaw_gateway_token:
            raise OpenClawServiceError("OPENCLAW_GATEWAY_TOKEN is not configured")
        headers = {
            "Authorization": f"Bearer {self._settings.openclaw_gateway_token}",
            "x-openclaw-session-key": str(employee_uuid),
            "Content-Type": "application/json",
        }
        if self._settings.openclaw_agent_id:
            headers["x-openclaw-agent-id"] = self._settings.openclaw_agent_id
        return headers

    async def check_health(self) -> dict[str, Any]:
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self._settings.openclaw_base_url.rstrip('/')}{self._settings.openclaw_health_path}",
                )
            if response.status_code >= 400:
                return {"status": "failed", "code": response.status_code, "body": response.text}
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    async def _chat_completion(
        self,
        *,
        employee_uuid: UUID,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self._settings.openclaw_request_timeout_seconds)
        payload = {"model": "openclaw", "messages": messages}
        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self._settings.openclaw_base_url.rstrip('/')}{self._settings.openclaw_chat_path}",
                        headers=self._headers(employee_uuid),
                        json=payload,
                    )
                if response.status_code >= 500:
                    raise OpenClawServiceError(
                        f"OpenClaw server error {response.status_code}: {response.text}",
                    )
                if response.status_code >= 400:
                    raise OpenClawServiceError(
                        f"OpenClaw request failed {response.status_code}: {response.text}",
                    )
                body = response.json()
                if "choices" not in body:
                    raise OpenClawServiceError("OpenClaw response missing choices")
                return body
            except httpx.ReadTimeout as exc:
                raise OpenClawServiceError(
                    "OpenClaw timed out while generating a response",
                ) from exc
            except (httpx.RequestError, OpenClawServiceError) as exc:
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise
        if last_error:
            raise last_error
        raise OpenClawServiceError("Unknown OpenClaw failure")

    @staticmethod
    def _extract_content(response_payload: dict[str, Any]) -> str:
        try:
            return response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenClawServiceError("Invalid OpenClaw response payload") from exc

    async def analyze_message(
        self,
        *,
        employee_uuid: UUID,
        user_text: str,
        channel: str,
        metadata: dict[str, Any],
    ) -> AIAnalysisResult:
        prompt = {
            "channel": channel,
            "metadata": metadata,
            "message": user_text,
            "schema": {
                "sentiment_score": "float [-1,1]",
                "emotion_label": "string",
                "engagement_level": "low|med|high",
                "flag": "boolean",
                "flag_reason": "string|null",
                "reply_text": "string",
            },
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only JSON with keys: sentiment_score, emotion_label, engagement_level, "
                    "flag, flag_reason, reply_text. No markdown."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ]
        response_payload = await self._chat_completion(employee_uuid=employee_uuid, messages=messages)
        content = self._extract_content(response_payload).strip()
        if content.startswith("```"):
            content = content.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenClawServiceError("OpenClaw did not return valid JSON") from exc
        return AIAnalysisResult.model_validate(parsed)
