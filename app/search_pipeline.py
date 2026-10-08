"""질문 분석 결과 → 검색 → (선택) LLM 관련도 재판정을 하나로 묶은 흐름.

API(`api.py`)와 터미널(`cli.py`)이 같은 흐름을 쓰도록 한곳에 둔다. 검색·판정 로직 자체는
`search_service`, `search_profiles`, `relevance_judge`를 호출만 한다(계약서 16장).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .models import PolicyCandidate, QuestionAnalysis, RegionSelection
from .relevance_judge import POOL_PER_SCOPE, rerank_with_judge
from .search_profiles import search_options

# 기존 API 로거 이름을 유지한다(테스트와 운영 로그 필터가 이 이름을 쓴다).
logger = logging.getLogger("welfareone.api")



@dataclass
class SearchOutcome:
    local_policies: list[PolicyCandidate] = field(default_factory=list)
    national_policies: list[PolicyCandidate] = field(default_factory=list)
    # relevance_checked가 true면 low_relevance_ids만 "관련도 낮음"으로 접고, false면 거리로 접는다
    low_relevance_ids: list[str] = field(default_factory=list)
    relevance_checked: bool = False


def run_search(
    analysis: QuestionAnalysis,
    search_service: Any,
    region: RegionSelection,
    age: int | None,
    question: str,
    judge: Any | None = None,
) -> SearchOutcome:
    """검색하고, `judge`가 있으며 상황형 질문이면 후보를 LLM으로 다시 판정한다.

    판정이 실패해도 오류가 아니라 거리 기반 결과(후보 풀 전체, 거리순)로 대신하고 `relevance_checked=False`를 돌려준다.
    검색 결과가 없는 것도 오류가 아니라 빈 목록이다(계약서 9장 검색 규칙 5).
    """
    use_judge = judge is not None and analysis.route == "situation_search"
    # 판정할 때는 후보를 넉넉히(범위별 POOL_PER_SCOPE개) 뽑는다
    pool_options = {"local_top_k": POOL_PER_SCOPE, "national_top_k": POOL_PER_SCOPE} if use_judge else {}
    result = search_service.search_policies(
        analysis.search_query,
        region,
        age=age,
        include_keywords=analysis.include_keywords,
        exclude_keywords=analysis.exclude_keywords,
        **search_options(analysis.route),
        **pool_options,
    )
    if not use_judge:
        return SearchOutcome(result.local_policies, result.national_policies)

    try:
        # 풀 전체를 내려준다: 관련 판정 후보가 앞, 나머지(관련도 낮음)가 뒤. 화면이 3개씩 다음/이전으로 이어서 보여 준다.
        outcome = rerank_with_judge(
            judge, question, analysis.search_query, result, age, show=POOL_PER_SCOPE, keep_low=POOL_PER_SCOPE
        )
    except Exception as exc:  # noqa: BLE001 - 판정은 부가 단계: 실패하면 거리 기반 결과로 대신한다
        # 질문·키·응답 본문은 남기지 않고 오류 종류만 기록한다
        logger.warning("relevance judge failed (%s); falling back to distance ranking", type(exc).__name__)
        return SearchOutcome(result.local_policies, result.national_policies)
    return SearchOutcome(
        outcome.local_policies,
        outcome.national_policies,
        outcome.low_relevance_ids,
        relevance_checked=True,
    )
