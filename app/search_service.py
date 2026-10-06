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
    ) -> PolicySearchResult:
        """max_distance보다 먼 후보는 제외한다. None이면 거리 제한 없이 개수를 채운다(튜닝·평가용)."""
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
                score = semantic_score + float(scope["bonus"]) + bonus
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
