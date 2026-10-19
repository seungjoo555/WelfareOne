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
import { orderForPaging, splitByRelevance } from "../../utils/relevance";
import { CandidateCard } from "./CandidateCard";

interface Props {
  title: string;
  policies: PolicyCandidate[];
  selectedPolicyId: string | null;
  onSelect: (policy: PolicyCandidate) => void;
  emptyText?: string; // 보여 줄 후보가 없을 때의 안내(기본: 관련도가 높은 정책을 찾지 못했어요)
  foldLowRelevance?: boolean; // 상황형 질문이면 true: 관련도가 낮은 후보는 관련 후보 뒤에 이어 붙인다
  lowRelevanceIds?: readonly string[] | null; // 서버가 LLM으로 판정한 "관련도 낮음" 후보(없으면 거리로 가른다)
}

// 지자체/중앙부처 정책은 하나의 순위로 섞지 않는다(계약서 9장).
// 후보는 우선순위 순서(관련 있음 → 관련도 낮음)로 3개씩 쪽을 넘겨 본다. 그룹마다 쪽을 따로 관리한다.
// 관련 있는 후보가 하나도 없으면 관련도 낮은 후보는 처음에는 숨기고, 눌러야 같은 방식으로 펼쳐진다.
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
  const [lowExpanded, setLowExpanded] = useState(false);
  const [requestedPage, setPage] = useState(0);
  const ordered = orderForPaging(confident, lowRelevance, lowExpanded);
  const lowIds = new Set(lowRelevance.map((policy) => policy.policy_id));
  const page = clampPage(requestedPage, ordered.length);
  const pages = pageCount(ordered.length);
  const visible = pageSlice(ordered, page);
  const pageHasLow = visible.some((policy) => lowIds.has(policy.policy_id));
  const hiddenLowOnly = confident.length === 0 && lowRelevance.length > 0 && !lowExpanded;

  return (
    <section className="candidate-group" aria-label={title}>
      <h3>{title}</h3>
      {confident.length === 0 && <p className="muted">{emptyText}</p>}
      {hiddenLowOnly && (
        <button type="button" className="link-btn low-relevance-toggle" onClick={() => setLowExpanded(true)}>
          {lowRelevanceSummary(lowRelevance.length)}
        </button>
      )}
      {visible.length > 0 && (
        <>
          {pageHasLow && <p className="low-relevance-note">{LOW_RELEVANCE_NOTE}</p>}
          <div className="candidate-list">
            {visible.map((policy) => (
              <CandidateCard
                key={policy.policy_id}
                policy={policy}
                selected={policy.policy_id === selectedPolicyId}
                lowRelevance={lowIds.has(policy.policy_id)}
                onSelect={onSelect}
              />
            ))}
          </div>
        </>
      )}
      {needsPager(ordered.length) && (
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
    </section>
  );
}
