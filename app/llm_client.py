"""LLM 호출의 공통 인터페이스. 질문 분석·관련도 판정·답변 서비스는 공급자(Gemini, Qwen 등)를 모르고 이것만 쓴다.

서비스가 하는 일은 "시스템 지침 + 질문을 보내 스키마에 맞는 JSON을 받는 것" 하나뿐이다. 공급자별 요청 형식과
오류 형식은 이 모듈 안에서만 다루고, 밖으로는 `LLMError`(HTTP 상태 비슷한 `code` 포함)로 통일해 내보낸다.
(계약서 제안 8장 참고. 공급자 선택 규칙은 api.py가 정한다.)
"""

from __future__ import annotations

from typing import Protocol, TypeVar

import httpx
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


class QwenClient:
    """서버가 띄운 Qwen 등 OpenAI 호환 서버(LM Studio, Ollama, vLLM)를 부르는 클라이언트.

    JSON 스키마를 요청에 실어 서버가 스키마대로만 생성하게 한다(제약 디코딩, 계약서 제안 8-6).
    그래도 스키마·허용값 검증에 실패하면 오류 내용을 알려 주고 1회만 다시 요청한다.
    """

    VALIDATION_RETRIES = 1
    # 추론(thinking) 모델은 생각 토큰만 쓰고 답이 비거나 수십 배 느려진다(LM Studio gemma-4-12b 실측: 56초 → 3.5초).
    # 질문 분석·판정·답변은 추론이 필요 없으므로 기본으로 끈다. 서버가 모르는 필드면 무시된다. {}를 넘기면 보내지 않는다.
    DEFAULT_EXTRA_BODY = {"reasoning_effort": "none"}

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        extra_body: dict | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._extra_body = dict(self.DEFAULT_EXTRA_BODY) if extra_body is None else extra_body
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
        )

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
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        last_error: Exception | None = None
        for _ in range(self.VALIDATION_RETRIES + 1):
            content = self._complete(messages, schema, model or self.model, seed, timeout_ms)
            try:
                return schema.model_validate_json(content)
            except ValueError as exc:  # pydantic ValidationError 포함
                last_error = exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "방금 응답이 요구한 JSON 스키마와 허용값에 맞지 않았습니다. 오류: "
                        f"{str(exc)[:300]}\n지침을 지켜 JSON만 다시 응답하세요.",
                    },
                ]
        raise LLMError(f"Qwen 응답이 스키마 검증을 통과하지 못했습니다: {str(last_error)[:200]}") from last_error

    def _complete(
        self, messages: list[dict], schema: type[BaseModel], model: str, seed: int | None, timeout_ms: int | None
    ) -> str:
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True, "schema": schema.model_json_schema()},
            },
            **self._extra_body,
        }
        if seed is not None:
            body["seed"] = seed
        try:
            response = self._http.post(
                "/chat/completions", json=body, timeout=timeout_ms / 1000 if timeout_ms else httpx.USE_CLIENT_DEFAULT
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Qwen 서버 오류 {exc.response.status_code}", exc.response.status_code) from exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise LLMError(f"Qwen 서버에 연결하지 못했습니다: {type(exc).__name__}", 503) from exc
        except (KeyError, IndexError, ValueError, httpx.HTTPError) as exc:
            raise LLMError(f"Qwen 서버 응답 형식이 올바르지 않습니다: {type(exc).__name__}") from exc
