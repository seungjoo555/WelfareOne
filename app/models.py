from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegionSelection:
    level1: str
    level2: str = ""

    @property
    def label(self) -> str:
        return " ".join(value for value in (self.level1, self.level2) if value)


@dataclass
class PolicyCandidate:
    policy_id: str
    title: str
    region_text: str
    score: float
    distance: float
    scope: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class PolicySection:
    section: str
    chunk_index: int
    document: str


@dataclass
class PolicySearchResult:
    """화면과 API에서 지자체·중앙부처 정책을 분리해 전달한다."""

    local_policies: list[PolicyCandidate] = field(default_factory=list)
    national_policies: list[PolicyCandidate] = field(default_factory=list)


@dataclass
class QuestionAnalysis:
    """Gemini가 반환하는 질문 분석 결과의 공통 형식."""

    route: str
    policy_name: str | None
    search_query: str
    intent: str
    intents: list[str] = field(default_factory=list)
    requested_sections: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class PolicyResource:
    """정책 원문에서 직접 추출한 외부 자료 또는 연락처."""

    label: str
    resource_type: str
    url: str


@dataclass
class AnswerResult:
    """선택된 정책의 공식 원문을 근거로 생성한 답변."""

    answer: str
    policy_id: str
    used_sections: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    resources: list[PolicyResource] = field(default_factory=list)
    grounded: bool = False
