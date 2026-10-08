"""질문 분석 결과 → 검색 → (선택) LLM 관련도 재판정을 하나로 묶은 흐름.

API(`api.py`)와 터미널(`cli.py`)이 같은 흐름을 쓰도록 한곳에 둔다. 검색·판정 로직 자체는
`search_service`, `search_profiles`, `relevance_judge`를 호출만 한다(계약서 16장).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .models import PolicyCandidate, PolicySearchResult, QuestionAnalysis, RegionSelection
from .relevance_judge import POOL_PER_SCOPE, rerank_with_judge
from .search_profiles import SITUATION_RESCUE_MAX_DISTANCE, search_options

# 기존 API 로거 이름을 유지한다(테스트와 운영 로그 필터가 이 이름을 쓴다).
logger = logging.getLogger("welfareone.api")


DEFAULT_TOP_K = 3  # search_policies의 기본 local_top_k/national_top_k와 같다(재판정을 안 쓰는 경로)


@dataclass
class SearchOutcome:
    local_policies: list[PolicyCandidate] = field(default_factory=list)
    national_policies: list[PolicyCandidate] = field(default_factory=list)
    # relevance_checked가 true면 low_relevance_ids만 "관련도 낮음"으로 접고, false면 거리로 접는다
    low_relevance_ids: list[str] = field(default_factory=list)
    relevance_checked: bool = False
    rescued: bool = False  # 하한을 넘는 후보뿐이라 하한을 한 번 완화해 다시 검색한 결과(내부용, API에는 싣지 않는다)


def search_queries(analysis: QuestionAnalysis, question: str) -> list[str]:
    """검색에 쓸 문장 목록. 상황형 질문은 분석기 검색어 외에 원문 질문도 함께 검색한다.

    같은 의도의 질문도 띄어쓰기·어미에 따라 분석기 검색어가 흔들리고("자격증관련 정책 알려줘" → "자격증 관련 정책"),
    임베딩 거리가 크게 달라진다(0.56 대 원문 0.53). 두 결과를 합쳐 정책별로 더 좋은 쪽을 쓰면 분석 결과가
    흔들려도 정답이 사라지지 않는다. 임베딩은 서버 로컬이라 추가 비용이 거의 없다.
    """
    queries = [analysis.search_query.strip()]
    raw = " ".join(question.split())
    if analysis.route == "situation_search" and raw and raw not in queries and len(raw) <= 200:
        queries.append(raw)
    return queries


def _merge_results(results: list[Any], local_k: int, national_k: int) -> Any:
    """여러 검색 결과를 정책별로 점수가 높은 후보 하나만 남겨 합치고, 범위(지자체/중앙)별로 다시 자른다."""
    best: dict[str, dict[str, PolicyCandidate]] = {"local": {}, "national": {}}
    for result in results:
        for scope, items in (("local", result.local_policies), ("national", result.national_policies)):
            for item in items:
                previous = best[scope].get(item.policy_id)
                if previous is None or item.score > previous.score:
                    best[scope][item.policy_id] = item
    local = sorted(best["local"].values(), key=lambda item: -item.score)[:local_k]
    national = sorted(best["national"].values(), key=lambda item: -item.score)[:national_k]
    return PolicySearchResult(local_policies=local, national_policies=national)


def _search(search_service: Any, queries: list[str], region: RegionSelection, kwargs: dict[str, Any]) -> Any:
    if len(queries) == 1:
        return search_service.search_policies(queries[0], region, **kwargs)
    results = [search_service.search_policies(query, region, **kwargs) for query in queries]
    return _merge_results(
        results,
        kwargs.get("local_top_k", DEFAULT_TOP_K),
        kwargs.get("national_top_k", DEFAULT_TOP_K),
    )


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
    situation = analysis.route == "situation_search"
    use_judge = judge is not None and situation
    # 판정할 때는 후보를 넉넉히(범위별 POOL_PER_SCOPE개) 뽑는다
    pool_options = {"local_top_k": POOL_PER_SCOPE, "national_top_k": POOL_PER_SCOPE} if use_judge else {}
    queries = search_queries(analysis, question)
    kwargs: dict[str, Any] = {
        "age": age,
        "include_keywords": analysis.include_keywords,
        "exclude_keywords": analysis.exclude_keywords,
        **search_options(analysis.route),
        **pool_options,
    }
    result = _search(search_service, queries, region, kwargs)

    # 빈 결과 구제: 상황형 질문의 1위가 하한을 아슬아슬하게 넘어 전부 걸러진 경우(예: 거리 0.56 > 하한 0.55)에만
    # 하한을 한 번 완화해 다시 검색한다. 구제된 후보는 판정이 있으면 AI가, 없으면 거리(0.50 초과)가 "관련도 낮음"으로 가른다.
    # 무의미 질문(날씨 등)은 완화해도 후보가 없어 그대로 빈 결과다.
    rescued = False
    if situation and not result.local_policies and not result.national_policies:
        relaxed = {**kwargs, "max_distance": SITUATION_RESCUE_MAX_DISTANCE}
        result = _search(search_service, queries, region, relaxed)
        rescued = bool(result.local_policies or result.national_policies)
        if rescued:
            logger.info("search rescued with relaxed distance limit")
    if not use_judge:
        return SearchOutcome(result.local_policies, result.national_policies, rescued=rescued)

    try:
        # 풀 전체를 내려준다: 관련 판정 후보가 앞, 나머지(관련도 낮음)가 뒤. 화면이 3개씩 다음/이전으로 이어서 보여 준다.
        outcome = rerank_with_judge(
            judge, question, analysis.search_query, result, age, show=POOL_PER_SCOPE, keep_low=POOL_PER_SCOPE
        )
    except Exception as exc:  # noqa: BLE001 - 판정은 부가 단계: 실패하면 거리 기반 결과로 대신한다
        # 질문·키·응답 본문은 남기지 않고 오류 종류만 기록한다
        logger.warning("relevance judge failed (%s); falling back to distance ranking", type(exc).__name__)
        return SearchOutcome(result.local_policies, result.national_policies, rescued=rescued)
    return SearchOutcome(
        outcome.local_policies,
        outcome.national_policies,
        outcome.low_relevance_ids,
        relevance_checked=True,
        rescued=rescued,
    )
