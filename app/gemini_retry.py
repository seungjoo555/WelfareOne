"""Gemini 호출의 공통 재시도 규칙. 분석기와 답변 서비스가 함께 쓴다."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from google.genai import errors

from .llm_client import LLMError

T = TypeVar("T")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def call_with_retry(action: Callable[[], T], max_retries: int) -> T:
    """`action`을 실행한다. 재시도 가능한 API 오류(429/5xx)만 1초, 2초… 쉬며 다시 시도한다.

    마지막 시도까지 실패하거나 재시도 대상이 아닌 오류가 나면 그 예외를 그대로 다시 던진다.
    (호출한 쪽이 서비스별 오류 형식으로 바꾼다.)
    """
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        try:
            return action()
        except (LLMError, errors.APIError) as exc:
            if getattr(exc, "code", None) not in RETRYABLE_STATUS or attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")  # pragma: no cover
