import { useState } from "react";
import { EMPTY_GROUP_TEXT } from "../../constants/text";
import type { PolicyCandidate } from "../../types/contract";
import { CandidateCard } from "./CandidateCard";

const PAGE_SIZE = 3;

interface Props {
  title: string;
  policies: PolicyCandidate[];
  selectedPolicyId: string | null;
  onSelect: (policy: PolicyCandidate) => void;
  emptyText?: string; // 비었을 때 보여 줄 안내(기본: 관련 정책을 찾지 못했습니다)
}

// 지자체/중앙부처 정책은 하나의 순위로 섞지 않는다(계약서 9장).
export function CandidateGroup({ title, policies, selectedPolicyId, onSelect, emptyText = EMPTY_GROUP_TEXT }: Props) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(policies.length / PAGE_SIZE);
  const safePage = Math.min(page, Math.max(0, pageCount - 1));
  const visiblePolicies = policies.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <section className="candidate-group" aria-label={title}>
      <h3>{title}</h3>
      {policies.length === 0 ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <>
          <div className="candidate-list">
            {visiblePolicies.map((policy) => (
              <CandidateCard
                key={policy.policy_id}
                policy={policy}
                selected={policy.policy_id === selectedPolicyId}
                onSelect={onSelect}
              />
            ))}
          </div>
          {pageCount > 1 && (
            <div className="candidate-pagination" aria-label={`${title} 페이지 이동`}>
              {safePage > 0 && (
                <button type="button" className="btn small" onClick={() => setPage(safePage - 1)}>
                  이전 정책
                </button>
              )}
              <span className="candidate-page-status">
                {safePage + 1} / {pageCount}
              </span>
              {safePage < pageCount - 1 && (
                <button type="button" className="btn small" onClick={() => setPage(safePage + 1)}>
                  관련 정책 더보기
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
