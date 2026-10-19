import re

from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL
from .models import PolicyCandidate, PolicySearchResult, RegionSelection
from .repository import PolicyRepository


# 이 거리보다 먼 후보는 관련 정책이 아니라고 본다(계약서 9장 규칙 5).
# 평가 질문 280개 실측: 정답 정책 거리 p95 0.51·최대 0.675, 무의미 질문 최상위 거리 0.64~0.88.
# 0.60이면 top3 정답 99.2% 보존, 무의미 질문 7개는 모두 빈 결과. 모델·DB를 바꾸면 다시 측정한다.
MAX_DISTANCE = 0.60
# 정책명 단어가 모두 질문에 들어 있으면(_title_bonus 최대값) 거리와 무관하게 남긴다(규칙 6).
TITLE_EXEMPT_BONUS = 0.5


# 질문 분석기가 만든 include/exclude 키워드로 점수를 조금 조정한다(걸러내지는 않는다).
# 평가 질문 75개 실측: 불일치 후보를 제거하면 정답 7%를 잃지만, 아래 가산점은 정답 손실 없이
# top3 진입 69→71, 1위 60→63으로 나아졌다. 값을 키우면 이득이 늘지 않고(0.20/0.10에서 70/63) 위험만 커진다.
KEYWORD_TITLE_WEIGHT = 0.10
KEYWORD_BODY_WEIGHT = 0.05
KEYWORD_MAX_MATCHES = 3  # 키워드가 많아도 가산·감점은 3개까지만 센다
# 분석기가 자주 내놓지만 정책을 구분하지 못하는 일반어. 구분력이 없어 점수에 쓰지 않는다.
GENERIC_KEYWORDS = frozenset({
    "지원", "사업", "정책", "서비스", "관련", "청년", "및", "비용", "부담", "지원금",
    "제도", "혜택", "신청", "대상", "조건", "방법", "가능", "받을", "수급", "신청방법",
})


def _where(*conditions: dict) -> dict:
    valid = [condition for condition in conditions if condition]
    return valid[0] if len(valid) == 1 else {"$and": valid}


def _title_bonus(title: str, question: str) -> tuple[float, list[str]]:
    generic = {"지원", "사업", "정책", "서비스", "관련", "청년", "및"}
    words = [
        word for word in re.findall(r"[가-힣A-Za-z0-9]+", title)
        if len(word) >= 2 and word not in generic
    ]
    matched = [word for word in words if word in question]
    return (0.5 * len(matched) / len(words) if words else 0.0), matched


def _keyword_terms(keywords: list[str] | None) -> list[str]:
    """키워드 구("복지 지원 사업")는 단어로 쪼개고, 짧거나 일반적인 단어와 중복은 뺀다."""
    terms: list[str] = []
    for keyword in keywords or []:
        for word in keyword.split():
            if len(word) >= 2 and word not in GENERIC_KEYWORDS and word not in terms:
                terms.append(word)
    return terms


def _keyword_bonus(title: str, summary: str, terms: list[str]) -> tuple[float, list[str]]:
    """제목에 있으면 KEYWORD_TITLE_WEIGHT, 본문(요약)에만 있으면 KEYWORD_BODY_WEIGHT를 단어당 더한다."""
    in_title = [term for term in terms if term in title]
    in_body = [term for term in terms if term in summary and term not in title]
    bonus = (
        KEYWORD_TITLE_WEIGHT * min(len(in_title), KEYWORD_MAX_MATCHES)
        + KEYWORD_BODY_WEIGHT * min(len(in_body), KEYWORD_MAX_MATCHES)
    )
    return bonus, in_title + in_body


def _age_matches(metadata: dict, age: int | None) -> bool:
    if age is None or metadata.get("age_status") != "exact":
        return True
    minimum = metadata.get("min_age")
    maximum = metadata.get("max_age")
    if isinstance(minimum, (int, float)) and age < minimum:
        return False
    if isinstance(maximum, (int, float)) and age > maximum:
        return False
    return True


class PolicySearchService:
    def __init__(self, repository: PolicyRepository) -> None:
        self.repository = repository
        self.embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)

    def _scopes(self, region: RegionSelection) -> list[dict]:
        scopes = []
        if region.level2:
            scopes.append({
                "name": "시군구",
                "bonus": 0.60,
                "where": _where(
                    {"section": {"$eq": "candidate_summary"}},
                    {"source": {"$eq": "local"}},
                    {"region_level1": {"$eq": region.level1}},
                    {"region_level2": {"$eq": region.level2}},
                ),
            })
            scopes.append({
                "name": "광역",
                "bonus": 0.35,
                "where": _where(
                    {"section": {"$eq": "candidate_summary"}},
                    {"source": {"$eq": "local"}},
                    {"region_level1": {"$eq": region.level1}},
                    {"region_level2": {"$eq": ""}},
                ),
            })
        else:
            scopes.append({
                "name": "시도",
                "bonus": 0.35,
                "where": _where(
                    {"section": {"$eq": "candidate_summary"}},
                    {"source": {"$eq": "local"}},
                    {"region_level1": {"$eq": region.level1}},
                ),
            })
        scopes.append({
            "name": "중앙부처",
            "bonus": 0.10,
            "where": _where(
                {"section": {"$eq": "candidate_summary"}},
                {"source": {"$eq": "national"}},
            ),
        })
        return scopes

    def search_policies(
        self,
        question: str,
        region: RegionSelection,
        age: int | None = None,
        local_top_k: int = 3,
        national_top_k: int = 3,
        per_scope: int = 30,
        max_distance: float | None = MAX_DISTANCE,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        region_bonus_scale: float = 1.0,
    ) -> PolicySearchResult:
        """max_distance보다 먼 후보는 제외한다. None이면 거리 제한 없이 개수를 채운다(튜닝·평가용).

        include_keywords가 정책명·요약에 있으면 점수를 올리고, exclude_keywords가 있으면 내린다(계약서 9장 규칙 8).
        후보를 걸러내지는 않고 순서만 바꾼다.
        region_bonus_scale은 시군구/광역 가산점에 곱하는 비율이다(기본 1.0, 0이면 거리 중심 정렬).
        """
        include_terms = _keyword_terms(include_keywords)
        exclude_terms = _keyword_terms(exclude_keywords)
        vector = self.embedder.encode(
            question,
            prompt_name="query",
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        candidates: dict[str, PolicyCandidate] = {}

        for scope in self._scopes(region):
            result = self.repository.vector_query(vector, scope["where"], per_scope)
            for document, metadata, distance in zip(
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ):
                if not _age_matches(metadata, age):
                    continue
                policy_id = str(metadata.get("policy_id", ""))
                title = str(metadata.get("title", ""))
                if not policy_id or not title:
                    continue
                semantic_score = 1.0 - float(distance)
                bonus, matched = _title_bonus(title, question)
                if (
                    max_distance is not None
                    and float(distance) > max_distance
                    and bonus < TITLE_EXEMPT_BONUS
                ):
                    continue
                include_bonus, include_matched = _keyword_bonus(title, document, include_terms)
                exclude_penalty, exclude_matched = _keyword_bonus(title, document, exclude_terms)
                score = (
                    semantic_score
                    + float(scope["bonus"]) * region_bonus_scale
                    + bonus
                    + include_bonus
                    - exclude_penalty
                )
                item = PolicyCandidate(
                    policy_id=policy_id,
                    title=title,
                    region_text=str(metadata.get("region_text", "")),
                    score=score,
                    distance=float(distance),
                    scope=str(scope["name"]),
                    summary=document,
                    metadata=metadata,
                    reasons=[
                        f"벡터 유사도 {semantic_score:.3f}",
                        f"검색 범위 {scope['name']}",
                        *(["정책명 단어 " + ", ".join(matched)] if matched else []),
                        *(["포함 키워드 " + ", ".join(include_matched)] if include_matched else []),
                        *(["제외 키워드 " + ", ".join(exclude_matched)] if exclude_matched else []),
                    ],
                )
                previous = candidates.get(policy_id)
                if previous is None or item.score > previous.score:
                    candidates[policy_id] = item

        ranked = sorted(candidates.values(), key=lambda item: -item.score)
        local_policies = [
            item for item in ranked
            if item.metadata.get("source") == "local"
        ][:local_top_k]
        national_policies = [
            item for item in ranked
            if item.metadata.get("source") == "national"
        ][:national_top_k]
        return PolicySearchResult(
            local_policies=local_policies,
            national_policies=national_policies,
        )

    def search(
        self,
        question: str,
        region: RegionSelection,
        age: int | None = None,
        top_k: int = 5,
        per_scope: int = 30,
    ) -> list[PolicyCandidate]:
        """기존 호출과 평가 코드의 호환성을 위한 통합 목록 검색."""
        result = self.search_policies(
            question=question,
            region=region,
            age=age,
            local_top_k=top_k,
            national_top_k=top_k,
            per_scope=per_scope,
        )
        return sorted(
            result.local_policies + result.national_policies,
            key=lambda item: -item.score,
        )[:top_k]
