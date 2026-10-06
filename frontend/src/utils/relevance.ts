import type { PolicyCandidate } from "../types/contract";

// 상황형 질문의 후보 중 거리(distance)가 이 값보다 먼 것은 "관련도 낮음"으로 접어 둔다.
// 백엔드 app/search_profiles.py의 SITUATION_CONFIDENT_DISTANCE와 같은 값이어야 한다.
// (2026-10-06 측정: 0.50 이하에서 지자체 정밀도 58%, 중앙부처 48%. 0.55까지 넓히면 관련 정책 재현율이 91~98%)
export const LOW_RELEVANCE_DISTANCE = 0.5;

// 접을 후보를 가린다. 서버가 내려준 순서는 그대로 유지한다.
// - fold=false(정책명을 말한 질문): 거리와 상관없이 모두 보여 준다.
// - lowRelevanceIds가 있으면(서버가 LLM으로 관련도를 판정함): 그 목록에 든 후보만 접는다. 거리는 보지 않는다.
// - lowRelevanceIds가 null이면(판정을 안 했거나 실패): 거리가 LOW_RELEVANCE_DISTANCE를 넘는 후보를 접는다.
export function splitByRelevance(
  policies: PolicyCandidate[],
  fold: boolean,
  lowRelevanceIds: readonly string[] | null = null,
): { confident: PolicyCandidate[]; lowRelevance: PolicyCandidate[] } {
  if (!fold) return { confident: policies, lowRelevance: [] };
  const lowIds = lowRelevanceIds === null ? null : new Set(lowRelevanceIds);
  const isLow = (policy: PolicyCandidate) =>
    lowIds !== null
      ? lowIds.has(policy.policy_id)
      : typeof policy.distance === "number" && policy.distance > LOW_RELEVANCE_DISTANCE;
  return {
    confident: policies.filter((policy) => !isLow(policy)),
    lowRelevance: policies.filter(isLow),
  };
}
