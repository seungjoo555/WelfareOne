"""선택된 정책의 원문만 사용해 Gemini 답변을 생성한다."""

from __future__ import annotations

import os
import re

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator

from .config import GEMINI_MODEL, PROJECT_DIR
from .env import load_env_file
from .gemini_retry import call_with_retry
from .models import AnswerResult, PolicyResource, PolicySection


ALLOWED_SECTIONS = {
    "overview",
    "target_criteria",
    "benefit",
    "application",
    "documents",
    "contact_source",
    "administrative",
}


class AnswerGenerationError(RuntimeError):
    """원문 기반 답변 생성을 완료하지 못했을 때 발생한다."""


class _GeminiAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=3000)
    used_sections: list[str] = Field(default_factory=list, max_length=7)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    grounded: bool

    @field_validator("used_sections")
    @classmethod
    def sections_must_be_allowed(cls, values: list[str]) -> list[str]:
        return [value for value in values if value in ALLOWED_SECTIONS]


# 질문 유형(intent)별로 사람들이 보통 알고 싶어 하는 항목과 순서. 프롬프트의 [답변 구성]으로 전달한다.
# 원문에 있는 항목만 답하고, 없으면 '확인되지 않습니다'라고 쓰게 한다(추측 금지 원칙은 그대로).
INTENT_ANSWER_GUIDE: dict[str, tuple[str, list[str]]] = {
    "eligibility": (
        "지원 대상",
        ["누가 대상인가(연령·거주지·소득·재산·취업/학적 상태 등 원문 조건)", "제외 대상 또는 우선 선정 대상", "신청 전에 확인할 점"],
    ),
    "benefit": (
        "지원 내용",
        ["무엇을 지원하는가", "금액·횟수·기간·한도", "지급 방식과 조건"],
    ),
    "application": (
        "신청 방법",
        ["어디서 어떻게 신청하는가(온라인·방문 등)", "신청 절차 순서", "신청 시기"],
    ),
    "administrative": (
        "신청 기간·행정 정보",
        ["신청(접수) 기간", "사업 기간 또는 마감", "상시·연중 여부"],
    ),
    "required_documents": (
        "필요 서류",
        ["제출 서류 목록", "서식·첨부파일", "발급처와 유의사항"],
    ),
    "contact": (
        "문의처",
        ["문의 기관·부서", "전화번호·누리집", "접수 장소"],
    ),
}


def answer_guide(intents: list[str] | None) -> str:
    """질문 유형에 맞는 [답변 구성] 블록을 만든다. 알려진 유형이 없으면 빈 문자열."""
    lines: list[str] = []
    for intent in intents or []:
        entry = INTENT_ANSWER_GUIDE.get(intent)
        if entry is None:
            continue
        title, items = entry
        lines.append(f"- {title}: " + " → ".join(items))
    if not lines:
        return ""
    return (
        "[답변 구성]\n"
        "아래 항목 순서대로 답하세요. 항목명은 **굵게** 쓰고 내용은 그 아래 짧은 불릿으로 쓰세요. "
        "원문에서 확인되는 항목만 쓰고, 확인되지 않는 항목은 항목마다 반복하지 말고 맨 끝에 한 줄"
        "('○○은 제공된 공식 자료에서는 확인되지 않습니다')로 묶으세요. 모든 항목이 확인되지 않으면 그 한 문장만 답하세요. "
        "줄바꿈은 실제 줄바꿈으로 쓰고 백슬래시와 n을 이어 쓴 문자열을 그대로 쓰지 마세요.\n"
        + "\n".join(lines)
    )


SYSTEM_INSTRUCTION = """
당신은 대한민국 청년 복지정책 안내 시스템의 답변 생성기입니다.
반드시 제공된 하나의 정책 원문만 사용하여 사용자의 질문에 한국어로 답하세요.

[답변 원칙]
1. 제공된 원문에 없는 사실, 금액, 날짜, 나이, 자격, 서류, 링크를 만들지 마세요.
2. 질문에 여러 의도가 있으면 확인 가능한 각 항목에 모두 답하세요.
3. 공식 원문에서 확인되지 않는 항목은 '제공된 공식 자료에서는 확인되지 않습니다'라고 명시하세요.
4. 신청 자격은 최종 확정하지 말고, 원문상 조건을 설명하세요.
5. 서로 모순되는 원문이 있으면 임의로 하나를 선택하지 말고 차이를 알리세요.
6. 답변은 간결하고 읽기 쉽게 작성하세요.
7. evidence에는 답변을 직접 뒷받침하는 원문 구절만 넣으세요.
8. used_sections에는 실제 답변 근거로 사용한 섹션명만 넣으세요.
9. 답변의 핵심 주장 전체가 원문으로 뒷받침되면 grounded=true입니다.
10. 원문이 없거나 질문에 답할 근거가 없으면 grounded=false입니다.
11. [답변 구성]이 주어지면 그 순서를 따라 항목마다 굵은 소제목과 짧은 불릿으로 정리하세요. 핵심만 쓰고, 확인되지 않는 항목은 반복해서 나열하지 마세요.
""".strip()


def select_contexts(
    contexts: list[PolicySection],
    requested_sections: list[str] | None,
) -> list[PolicySection]:
    """요청한 섹션만 원래 순서대로 선택하고 중복 레코드를 제거한다."""
    requested = set(requested_sections or ALLOWED_SECTIONS)
    selected: list[PolicySection] = []
    seen: set[tuple[str, int, str]] = set()
    for context in contexts:
        if context.section not in requested or context.section not in ALLOWED_SECTIONS:
            continue
        key = (context.section, context.chunk_index, context.document.strip())
        if not key[2] or key in seen:
            continue
        seen.add(key)
        selected.append(context)
    return selected


def _build_contents(
    question: str,
    policy_id: str,
    policy_title: str | None,
    contexts: list[PolicySection],
    intents: list[str] | None = None,
) -> str:
    blocks = []
    for number, context in enumerate(contexts, start=1):
        blocks.append(
            f"[근거 {number} | section={context.section} | "
            f"chunk_index={context.chunk_index}]\n{context.document.strip()}"
        )
    joined = "\n\n".join(blocks)
    guide = answer_guide(intents)
    guide_block = f"{guide}\n\n" if guide else ""
    return (
        f"정책 ID: {policy_id}\n"
        f"정책명: {policy_title or '원문에서 확인'}\n"
        f"사용자 질문: {question.strip()}\n\n"
        f"{guide_block}"
        f"공식 정책 원문:\n{joined}"
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def _resource_type(section: str, url: str) -> str:
    lowered = url.lower()
    if section == "documents" or any(
        marker in lowered
        for marker in ("download", "file", "atcfl", ".hwp", ".pdf", ".doc", ".zip")
    ):
        return "attachment"
    if "law.go.kr" in lowered:
        return "legal_reference"
    return "website"


def _resource_label(lines: list[str], line_index: int, resource_type: str) -> str:
    nearby = lines[line_index + 1:line_index + 4] + lines[max(0, line_index - 2):line_index]
    for line in nearby:
        if "wlfareInfoReldNm:" in line:
            label = line.split("wlfareInfoReldNm:", 1)[1].strip()
            if label:
                return label
    return "첨부파일 다운로드" if resource_type == "attachment" else "관련 웹사이트"


def extract_resources(contexts: list[PolicySection]) -> list[PolicyResource]:
    """LLM 판단 없이 공식 원문에서 URL과 표시명을 직접 추출한다."""
    resources: list[PolicyResource] = []
    seen_urls: set[str] = set()
    for context in contexts:
        lines = [line.strip() for line in context.document.splitlines() if line.strip()]
        for line_index, line in enumerate(lines):
            for match in URL_PATTERN.finditer(line):
                url = match.group(0).rstrip(".,;)。、")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                kind = _resource_type(context.section, url)
                resources.append(
                    PolicyResource(
                        label=_resource_label(lines, line_index, kind),
                        resource_type=kind,
                        url=url,
                    )
                )
    return resources


class AnswerService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = GEMINI_MODEL,
        max_retries: int = 3,
    ) -> None:
        load_env_file(PROJECT_DIR / ".env")
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise AnswerGenerationError(
                "GEMINI_API_KEY가 없습니다. 프로젝트의 .env 파일을 확인해주세요."
            )
        self.client = genai.Client(api_key=resolved_key)
        self.model = model
        self.max_retries = max(1, max_retries)

    def generate_answer(
        self,
        question: str,
        policy_id: str,
        contexts: list[PolicySection],
        requested_sections: list[str] | None = None,
        policy_title: str | None = None,
        intents: list[str] | None = None,
    ) -> AnswerResult:
        question = question.strip()
        policy_id = policy_id.strip()
        if not question:
            raise ValueError("question은 빈 문자열일 수 없습니다.")
        if not policy_id:
            raise ValueError("policy_id는 빈 문자열일 수 없습니다.")

        selected = select_contexts(contexts, requested_sections)
        if not selected:
            return AnswerResult(
                answer="제공된 공식 자료에서는 질문에 답할 정보를 확인할 수 없습니다.",
                policy_id=policy_id,
                grounded=False,
            )

        contents = _build_contents(question, policy_id, policy_title, selected, intents)
        def call() -> _GeminiAnswer:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=_GeminiAnswer,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
            )
            parsed = response.parsed
            if parsed is None:
                return _GeminiAnswer.model_validate_json(response.text)
            if not isinstance(parsed, _GeminiAnswer):
                return _GeminiAnswer.model_validate(parsed)
            return parsed

        try:
            parsed = call_with_retry(call, self.max_retries)
            resource_sections = {
                "application", "documents", "contact_source", "administrative"
            }
            include_policy_resources = bool(
                resource_sections.intersection(requested_sections or [])
            )
            return self._to_result(
                parsed,
                policy_id,
                selected,
                resource_contexts=contexts if include_policy_resources else selected,
            )
        except Exception as exc:
            raise AnswerGenerationError(
                f"Gemini 답변 생성에 실패했습니다: {exc}"
            ) from exc

    @staticmethod
    def _to_result(
        parsed: _GeminiAnswer,
        policy_id: str,
        contexts: list[PolicySection],
        resource_contexts: list[PolicySection] | None = None,
    ) -> AnswerResult:
        available_sections = {context.section for context in contexts}
        used_sections = [
            section for section in parsed.used_sections
            if section in available_sections
        ]
        source_text = _normalize_text(" ".join(item.document for item in contexts))
        evidence: list[str] = []
        for value in parsed.evidence:
            cleaned = value.strip()
            if (
                cleaned
                and _normalize_text(cleaned) in source_text
                and cleaned not in evidence
            ):
                evidence.append(cleaned)
        grounded = bool(parsed.grounded and used_sections and evidence)
        return AnswerResult(
            answer=parsed.answer.strip(),
            policy_id=policy_id,
            used_sections=used_sections,
            evidence=evidence,
            resources=extract_resources(resource_contexts or contexts),
            grounded=grounded,
        )


def generate_answer(
    question: str,
    policy_id: str,
    contexts: list[PolicySection],
    requested_sections: list[str] | None = None,
    policy_title: str | None = None,
    intents: list[str] | None = None,
) -> AnswerResult:
    """공통 계약서에 정의된 간편 호출 함수."""
    return AnswerService().generate_answer(
        question=question,
        policy_id=policy_id,
        contexts=contexts,
        requested_sections=requested_sections,
        policy_title=policy_title,
        intents=intents,
    )
