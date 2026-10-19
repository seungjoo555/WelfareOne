"""LLM 호출의 공통 인터페이스. 질문 분석·관련도 판정·답변 서비스는 공급자(Gemini, Qwen 등)를 모르고 이것만 쓴다.

서비스가 하는 일은 "시스템 지침 + 질문을 보내 스키마에 맞는 JSON을 받는 것" 하나뿐이다. 공급자별 요청 형식과
오류 형식은 이 모듈 안에서만 다루고, 밖으로는 `LLMError`(HTTP 상태 비슷한 `code` 포함)로 통일해 내보낸다.
(계약서 제안 8장 참고. 공급자 선택 규칙은 api.py가 정한다.)
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .config import GEMINI_MODEL

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """공급자 호출 실패. `code`는 HTTP 상태(429, 503 등)이고 알 수 없으면 None이다."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class LLMClient(Protocol):
    model: str  # 기본 모델명

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        model: str | None = None,
        seed: int | None = None,
        timeout_ms: int | None = None,
    ) -> T:
        """`schema`(pydantic)에 맞는 JSON 응답을 받아 검증한 객체로 돌려준다. 실패하면 LLMError 또는 검증 예외."""
        ...


class GeminiClient:
    """Google Gemini. 사용자 본인 키(BYOK)와 서버 키 모두 이 클래스로 만든다."""

    def __init__(self, api_key: str, model: str = GEMINI_MODEL) -> None:
        self.model = model
        self._client = genai.Client(api_key=api_key)

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        model: str | None = None,
        seed: int | None = None,
        timeout_ms: int | None = None,
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            seed=seed,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(timeout=timeout_ms) if timeout_ms else None,
        )
        try:
            response = self._client.models.generate_content(
                model=model or self.model, contents=prompt, config=config
            )
        except errors.APIError as exc:
            raise LLMError(str(exc), getattr(exc, "code", None)) from exc
        parsed = response.parsed
        if parsed is None:
            return schema.model_validate_json(response.text)
        if not isinstance(parsed, schema):
            return schema.model_validate(parsed)
        return parsed
