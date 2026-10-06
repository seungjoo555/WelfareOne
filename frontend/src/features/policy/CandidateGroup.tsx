import { EMPTY_GROUP_TEXT, LOW_RELEVANCE_NOTE, lowRelevanceSummary } from "../../constants/text";
import type { PolicyCandidate } from "../../types/contract";
import { splitByRelevance } from "../../utils/relevance";
import { CandidateCard } from "./CandidateCard";

interface Props {
  title: string;
  policies: PolicyCandidate[];
  selectedPolicyId: string | null;
  onSelect: (policy: PolicyCandidate) => void;
  emptyText?: string; // 보여 줄 후보가 없을 때의 안내(기본: 관련도가 높은 정책을 찾지 못했어요)
  foldLowRelevance?: boolean; // 상황형 질문이면 true: 관련도가 낮은 후보는 접어 둔다
  lowRelevanceIds?: readonly string[] | null; // 서버가 LLM으로 판정한 "관련도 낮음" 후보(없으면 거리로 접는다)
}

// 지자체/중앙부처 정책은 하나의 순위로 섞지 않는다(계약서 9장).
export function CandidateGroup({
  title,
  policies,
  selectedPolicyId,
  onSelect,
  emptyText = EMPTY_GROUP_TEXT,
  foldLowRelevance = false,
  lowRelevanceIds = null,
}: Props) {
  const { confident, lowRelevance } = splitByRelevance(policies, foldLowRelevance, lowRelevanceIds);

  const cards = (list: PolicyCandidate[]) => (
    <div className="candidate-list">
      {list.map((policy) => (
        <CandidateCard
          key={policy.policy_id}
          policy={policy}
          selected={policy.policy_id === selectedPolicyId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );

  return (
    <section className="candidate-group" aria-label={title}>
      <h3>{title}</h3>
      {confident.length === 0 ? <p className="muted">{emptyText}</p> : cards(confident)}
      {lowRelevance.length > 0 && (
        <details className="low-relevance">
          <summary>{lowRelevanceSummary(lowRelevance.length)}</summary>
          <p className="low-relevance-note">{LOW_RELEVANCE_NOTE}</p>
          {cards(lowRelevance)}
        </details>
      )}
    </section>
  );
}
