"""Gemini를 이용해 사용자 질문을 검색 가능한 구조로 변환한다."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, field_validator

from .config import GEMINI_MODEL, PROJECT_DIR
from .models import QuestionAnalysis


ROUTES = {
    "situation_search",
    "specific_policy",
    "current_policy_question",
}

INTENT_SECTIONS: dict[str, list[str]] = {
    "policy_search": ["candidate_summary"],
    "policy_overview": ["overview"],
    "eligibility": ["target_criteria"],
    "benefit": ["benefit"],
    "application": ["application", "administrative"],
    "required_documents": ["documents", "application"],
    "contact": ["contact_source"],
    "administrative": ["administrative", "contact_source"],
}


class QuestionAnalysisError(RuntimeError):
    """질문 분석을 완료하지 못했을 때 발생한다."""


class _GeminiAnalysis(BaseModel):
    route: Literal[
        "situation_search",
        "specific_policy",
        "current_policy_question",
    ]
    policy_name: str | None = None
    search_query: str = Field(min_length=1, max_length=200)
    intent: Literal[
        "policy_search",
        "policy_overview",
        "eligibility",
        "benefit",
        "application",
        "required_documents",
        "contact",
        "administrative",
    ]
    intents: list[
        Literal[
            "policy_search",
            "policy_overview",
            "eligibility",
            "benefit",
            "application",
            "required_documents",
            "contact",
            "administrative",
        ]
    ] = Field(min_length=1, max_length=3)
    include_keywords: list[str] = Field(default_factory=list, max_length=8)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("policy_name", mode="before")
    @classmethod
    def empty_policy_name_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


# 같은 질문이 실행마다 다른 검색어로 분석되는 것을 줄이기 위해 고정한다(temperature=0만으로는 흔들렸다).
ANALYZER_SEED = 0

SYSTEM_INSTRUCTION = """
당신은 대한민국 청년 복지정책 검색 시스템의 질문 분석기입니다.
사용자의 질문을 답하지 말고 검색과 대화 분기에 필요한 구조만 반환하세요.

[route 규칙]
- situation_search: 생활 상황이나 필요를 말하며 알맞은 정책 추천을 요청함
- specific_policy: 특정 정책의 이름을 직접 언급했으며 아직 선택된 정책이 없음
- current_policy_question: 이미 선택된 정책이 있고 그 정책에 관한 후속 질문임
- current_policy_id가 있더라도 사용자가 명백히 다른 정책명을 말하면 specific_policy

[intent 규칙]
- policy_search: 상황에 맞는 정책 추천이나 후보 검색
- policy_overview: 특정 정책의 전체적인 설명
- eligibility: 지원 대상, 선정 기준, 신청 자격, 받을 수 있는지
- benefit: 지원 금액, 물품, 서비스 등 혜택
- application: 신청 방법, 신청 절차, 접수 기간
- required_documents: 제출 서류, 필요 서류, 준비물
- contact: 문의처, 담당 기관, 전화번호, 공식 링크
- administrative: 시행 기간, 사업 기간, 수정일 등 행정 정보
- intent에는 질문에서 가장 중요한 대표 의도 하나를 기록
- intents에는 질문에 포함된 모든 의도를 중요도 순서로 기록하되 최대 3개
- intent는 반드시 intents의 첫 번째 값과 같아야 함
- 정책 추천 질문은 intents를 ["policy_search"]로만 반환
- 같은 정책의 지원 내용과 신청 방법처럼 복수 의도는 함께 반환
- 서로 다른 정책이나 서로 다른 지원 분야를 한 질문에서 요청해도 임의로 하나를 만들거나 합치지 않음

[search_query 규칙]
- 사용자의 핵심 상황과 원하는 지원을 보존한 짧은 한국어 검색 문장으로 작성
- 특정 정책명이 있으면 정확히 보존
- 사용자가 말하지 않은 지역, 나이, 소득, 직업, 혼인 상태를 만들지 않음
- '서울'을 '서울특별시'처럼 바꾸는 지역 정규화는 여기서 하지 않음
- 구어체·감정·상태 표현만 있는 질문(예: '배고파', '춥다', '막막해')은, 그 상황에서 필요한 지원 분야를 정책 용어로 풀어 쓴다. 예: '배고파' → '무료 급식 식사 지원', '집이 없어요' → '주거 지원 임시 거처'
- 질문의 핵심 상황(예: '배고파')을 버리고 일부 단어(예: '점심 추천')만 남기지 않는다
- '청년 복지 정책'처럼 질문과 무관한 일반 검색어로 대체하지 않는다
- 부정 표현은 제거하지 말고 exclude_keywords에도 핵심 제외 개념을 기록

[기타 규칙]
- policy_name은 실제로 언급된 정책명 또는 명백한 정책명 구절만 기록
- '월세 지원', '취업 지원' 같은 일반 분야 표현은 policy_name이 아님
- include_keywords와 exclude_keywords는 각각 중복 없이 8개 이하
- confidence는 분석 확신도를 0~1로 표시
""".strip()


def _load_env_file(path: Path) -> None:
    """추가 패키지 없이 프로젝트의 .env 값을 환경변수에 읽는다."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _clean_words(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        word = value.strip()
        if word and word not in result:
            result.append(word)
    return result[:8]


class QuestionAnalyzer:
    """Gemini 호출과 결과 검증을 담당하는 서비스."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = GEMINI_MODEL,
        max_retries: int = 3,
        seed: int | None = ANALYZER_SEED,
    ) -> None:
        self.seed = seed
        _load_env_file(PROJECT_DIR / ".env")
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise QuestionAnalysisError(
                "GEMINI_API_KEY가 없습니다. 프로젝트의 .env 파일에 "
                "GEMINI_API_KEY=발급받은키 형식으로 입력해주세요."
            )
        self.client = genai.Client(api_key=resolved_key)
        self.model = model
        self.max_retries = max(1, max_retries)

    def analyze_question(
        self,
        question: str,
        current_policy_id: str | None = None,
        current_policy_title: str | None = None,
    ) -> QuestionAnalysis:
        question = question.strip()
        if not question:
            raise ValueError("question은 빈 문자열일 수 없습니다.")

        context = (
            f"선택된 정책 ID: {current_policy_id or '없음'}\n"
            f"선택된 정책명: {current_policy_title or '없음'}\n"
            f"사용자 질문: {question}"
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=context,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0,
                        seed=self.seed,
                        response_mime_type="application/json",
                        response_schema=_GeminiAnalysis,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True,
                        ),
                    ),
                )
                parsed = response.parsed
                if parsed is None:
                    parsed = _GeminiAnalysis.model_validate_json(response.text)
                elif not isinstance(parsed, _GeminiAnalysis):
                    parsed = _GeminiAnalysis.model_validate(parsed)
                return self._to_result(parsed, current_policy_id, question)
            except errors.APIError as exc:
                last_error = exc
                status = getattr(exc, "code", None)
                retryable = status in {429, 500, 502, 503, 504}
                if not retryable or attempt == self.max_retries - 1:
                    break
                time.sleep(2 ** attempt)
            except Exception as exc:
                last_error = exc
                break

        raise QuestionAnalysisError(
            f"Gemini 질문 분석에 실패했습니다: {last_error}"
        ) from last_error

    @staticmethod
    def _to_result(
        parsed: _GeminiAnalysis,
        current_policy_id: str | None,
        question: str = "",
    ) -> QuestionAnalysis:
        route = parsed.route
        # 현재 정책이 없는데 후속 질문으로 잘못 분류한 결과는 코드에서 보정한다.
        if route == "current_policy_question" and not current_policy_id:
            route = "specific_policy" if parsed.policy_name else "situation_search"

        intents = _normalize_intents(parsed.intent, parsed.intents, question)
        intent = intents[0]
        sections = _sections_for_intents(intents)
        return QuestionAnalysis(
            route=route,
            policy_name=parsed.policy_name.strip() if parsed.policy_name else None,
            search_query=parsed.search_query.strip(),
            intent=intent,
            intents=intents,
            requested_sections=sections,
            include_keywords=_clean_words(parsed.include_keywords),
            exclude_keywords=_clean_words(parsed.exclude_keywords),
            confidence=float(parsed.confidence),
        )


def _normalize_intents(
    primary: str,
    values: list[str],
    question: str = "",
) -> list[str]:
    """대표 의도를 첫 항목으로 두고 중복을 제거한다."""
    result: list[str] = []
    for value in [primary, *values]:
        if value in INTENT_SECTIONS and value not in result:
            result.append(value)
    document_terms = ("신청서", "제출서류", "제출 서류", "필요서류", "필요 서류", "서식", "첨부파일", "첨부 파일")
    download_terms = ("다운로드", "내려받", "파일 링크")
    if (
        any(term in question for term in document_terms)
        or any(term in question for term in download_terms)
    ) and "required_documents" not in result:
        if len(result) >= 3:
            result = result[:2]
        result.append("required_documents")
    return result[:3] or ["policy_search"]


def _sections_for_intents(intents: list[str]) -> list[str]:
    """복수 의도에 필요한 DB 섹션의 순서를 유지하며 합집합을 만든다."""
    sections: list[str] = []
    for intent in intents:
        for section in INTENT_SECTIONS[intent]:
            if section not in sections:
                sections.append(section)
    return sections


_default_analyzer: QuestionAnalyzer | None = None


def analyze_question(
    question: str,
    current_policy_id: str | None = None,
    current_policy_title: str | None = None,
) -> QuestionAnalysis:
    """공통 계약서에 정의된 간편 호출 함수."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = QuestionAnalyzer()
    return _default_analyzer.analyze_question(
        question=question,
        current_policy_id=current_policy_id,
        current_policy_title=current_policy_title,
    )
