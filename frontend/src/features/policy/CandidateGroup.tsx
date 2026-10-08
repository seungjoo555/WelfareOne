import { useState } from "react";
import {
  EMPTY_GROUP_TEXT,
  LOW_RELEVANCE_NOTE,
  PAGER_NEXT,
  PAGER_PREV,
  lowRelevanceSummary,
  pagerLabel,
  pagerStatus,
} from "../../constants/text";
import type { PolicyCandidate } from "../../types/contract";
import { clampPage, needsPager, pageCount, pageSlice } from "../../utils/paging";
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
  // 보이는 후보는 우선순위 순서대로 3개씩 쪽을 넘겨 본다. 지자체/중앙부처 그룹마다 쪽을 따로 관리한다.
  const [requestedPage, setPage] = useState(0);
  const page = clampPage(requestedPage, confident.length);
  const pages = pageCount(confident.length);

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
      {confident.length === 0 ? <p className="muted">{emptyText}</p> : cards(pageSlice(confident, page))}
      {needsPager(confident.length) && (
        <div className="candidate-pager" role="group" aria-label={pagerLabel(title)}>
          <button type="button" className="pager-btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
            {PAGER_PREV}
          </button>
          <span className="pager-status" aria-live="polite">
            {pagerStatus(page + 1, pages)}
          </span>
          <button type="button" className="pager-btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
            {PAGER_NEXT}
          </button>
        </div>
      )}
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
