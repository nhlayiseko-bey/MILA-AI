from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx

from app.config import Settings
from app.models.schemas import AIAnalysisResult


class OpenClawServiceError(Exception):
    pass


class OpenAIFallbackError(Exception):
    pass


class KimiFallbackError(Exception):
    pass


class OpenClawClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _has_openai_fallback(self) -> bool:
        return bool(self._settings.openai_api_key)

    def _has_kimi_fallback(self) -> bool:
        return bool(self._settings.kimi_api_key)

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

    @staticmethod
    def _provider_headers(
        *,
        api_key: str,
        env_var_name: str,
        error_type: type[Exception],
    ) -> dict[str, str]:
        if not api_key:
            raise error_type(f"{env_var_name} is not configured")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _openai_headers(self) -> dict[str, str]:
        return self._provider_headers(
            api_key=self._settings.openai_api_key,
            env_var_name="OPENAI_API_KEY",
            error_type=OpenAIFallbackError,
        )

    def _kimi_headers(self) -> dict[str, str]:
        return self._provider_headers(
            api_key=self._settings.kimi_api_key,
            env_var_name="KIMI_API_KEY",
            error_type=KimiFallbackError,
        )

    async def _check_openclaw_health(self) -> dict[str, Any]:
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

    async def _check_openai_compatible_health(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/models",
                    headers=headers,
                )
            if response.status_code >= 400:
                return {"status": "failed", "code": response.status_code, "body": response.text}
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    async def _check_openai_health(self) -> dict[str, Any]:
        return await self._check_openai_compatible_health(
            base_url=self._settings.openai_base_url,
            headers=self._openai_headers(),
        )

    async def _check_kimi_health(self) -> dict[str, Any]:
        return await self._check_openai_compatible_health(
            base_url=self._settings.kimi_base_url,
            headers=self._kimi_headers(),
        )

    async def check_health(self) -> dict[str, Any]:
        openclaw_health = await self._check_openclaw_health()
        if openclaw_health.get("status") == "ok":
            return {
                "status": "ok",
                "provider": "openclaw",
                "fallback_configured": self._has_openai_fallback() or self._has_kimi_fallback(),
            }
        openai_health: dict[str, Any] | None = None
        kimi_health: dict[str, Any] | None = None
        if self._has_openai_fallback():
            openai_health = await self._check_openai_health()
            if openai_health.get("status") == "ok":
                return {
                    "status": "ok",
                    "provider": "openai_fallback",
                    "fallback_configured": True,
                    "openclaw": openclaw_health,
                    "openai": openai_health,
                }
        if self._has_kimi_fallback():
            kimi_health = await self._check_kimi_health()
            if kimi_health.get("status") == "ok":
                result = {
                    "status": "ok",
                    "provider": "kimi_fallback",
                    "fallback_configured": True,
                    "openclaw": openclaw_health,
                    "kimi": kimi_health,
                }
                if openai_health is not None:
                    result["openai"] = openai_health
                return result
        if not self._has_openai_fallback() and not self._has_kimi_fallback():
            return {
                "status": "failed",
                "provider": "openclaw",
                "fallback_configured": False,
                "openclaw": openclaw_health,
            }
        result = {
            "status": "failed",
            "provider": "openclaw",
            "fallback_configured": True,
            "openclaw": openclaw_health,
        }
        if openai_health is not None:
            result["openai"] = openai_health
        if kimi_health is not None:
            result["kimi"] = kimi_health
        return result

    async def _chat_completion_openclaw(
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
            except httpx.RequestError as exc:
                last_error = OpenClawServiceError(str(exc))
                if attempt >= self._settings.max_retries:
                    raise last_error from exc
            except OpenClawServiceError as exc:
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise
        if last_error:
            raise last_error
        raise OpenClawServiceError("Unknown OpenClaw failure")

    async def _chat_completion_openai(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        return await self._chat_completion_openai_compatible(
            provider_name="OpenAI fallback",
            error_type=OpenAIFallbackError,
            base_url=self._settings.openai_base_url,
            headers=self._openai_headers(),
            model=self._settings.openai_model,
            timeout_seconds=self._settings.openai_request_timeout_seconds,
            messages=messages,
        )

    async def _chat_completion_kimi(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        return await self._chat_completion_openai_compatible(
            provider_name="Kimi fallback",
            error_type=KimiFallbackError,
            base_url=self._settings.kimi_base_url,
            headers=self._kimi_headers(),
            model=self._settings.kimi_model,
            timeout_seconds=self._settings.kimi_request_timeout_seconds,
            messages=messages,
        )

    async def _chat_completion_openai_compatible(
        self,
        *,
        provider_name: str,
        error_type: type[Exception],
        base_url: str,
        headers: dict[str, str],
        model: str,
        timeout_seconds: float,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(timeout_seconds)
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                if response.status_code >= 500:
                    raise error_type(
                        f"{provider_name} server error {response.status_code}: {response.text}",
                    )
                if response.status_code >= 400:
                    raise error_type(
                        f"{provider_name} request failed {response.status_code}: {response.text}",
                    )
                body = response.json()
                if "choices" not in body:
                    raise error_type(f"{provider_name} response missing choices")
                return body
            except httpx.ReadTimeout as exc:
                raise error_type(
                    f"{provider_name} timed out while generating a response",
                ) from exc
            except httpx.RequestError as exc:
                last_error = error_type(str(exc))
                if attempt >= self._settings.max_retries:
                    raise last_error from exc
            except error_type as exc:  # type: ignore[misc]
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise
        if last_error:
            raise last_error
        raise error_type(f"Unknown {provider_name} failure")

    @staticmethod
    def _extract_content(response_payload: dict[str, Any], *, provider_name: str) -> str:
        try:
            return response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenClawServiceError(f"Invalid {provider_name} response payload") from exc

    @staticmethod
    def _parse_analysis_result(content: str, *, provider_name: str) -> AIAnalysisResult:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise OpenClawServiceError(f"{provider_name} did not return valid JSON") from exc
        return AIAnalysisResult.model_validate(parsed)

    @staticmethod
    def _build_messages(
        *,
        user_text: str,
        channel: str,
        metadata: dict[str, Any],
    ) -> list[dict[str, str]]:
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
        return [
            {
                "role": "system",
                "content": (
                    "Return only JSON with keys: sentiment_score, emotion_label, engagement_level, "
                    "flag, flag_reason, reply_text. No markdown."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ]

    async def analyze_message(
        self,
        *,
        employee_uuid: UUID,
        user_text: str,
        channel: str,
        metadata: dict[str, Any],
    ) -> AIAnalysisResult:
        messages = self._build_messages(
            user_text=user_text,
            channel=channel,
            metadata=metadata,
        )
        try:
            response_payload = await self._chat_completion_openclaw(
                employee_uuid=employee_uuid,
                messages=messages,
            )
            content = self._extract_content(response_payload, provider_name="OpenClaw")
            return self._parse_analysis_result(content, provider_name="OpenClaw")
        except OpenClawServiceError as openclaw_exc:
            errors = [f"OpenClaw failed: {openclaw_exc}"]
            if not self._has_openai_fallback() and not self._has_kimi_fallback():
                raise OpenClawServiceError(errors[0]) from openclaw_exc
            try:
                if self._has_openai_fallback():
                    response_payload = await self._chat_completion_openai(messages=messages)
                    content = self._extract_content(response_payload, provider_name="OpenAI fallback")
                    return self._parse_analysis_result(content, provider_name="OpenAI fallback")
            except (OpenAIFallbackError, OpenClawServiceError) as openai_exc:
                errors.append(f"OpenAI fallback failed: {openai_exc}")
            try:
                if self._has_kimi_fallback():
                    response_payload = await self._chat_completion_kimi(messages=messages)
                    content = self._extract_content(response_payload, provider_name="Kimi fallback")
                    return self._parse_analysis_result(content, provider_name="Kimi fallback")
            except (KimiFallbackError, OpenClawServiceError) as kimi_exc:
                errors.append(f"Kimi fallback failed: {kimi_exc}")
            raise OpenClawServiceError("; ".join(errors))
