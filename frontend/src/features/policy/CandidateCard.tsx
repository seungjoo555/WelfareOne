import { LOW_RELEVANCE_BADGE } from "../../constants/text";
import type { PolicyCandidate } from "../../types/contract";
import { pickSummary } from "../../utils/summary";

interface Props {
  policy: PolicyCandidate;
  selected: boolean;
  lowRelevance?: boolean; // 관련도가 낮은 후보면 배지를 붙인다(관련 후보 뒤에 이어질 때 구분용)
  onSelect: (policy: PolicyCandidate) => void;
}

// score/distance/reasons는 내부 진단 값이라 화면에 보여주지 않는다.
// (reasons는 "벡터 유사도 0.700", "검색 범위 시군구" 같은 개발용 문구다.)
export function CandidateCard({ policy, selected, lowRelevance = false, onSelect }: Props) {
  return (
    <button
      type="button"
      className={`candidate${selected ? " selected" : ""}${lowRelevance ? " low" : ""}`}
      aria-pressed={selected}
      onClick={() => onSelect(policy)}
    >
      <span className="candidate-top">
        <strong>{policy.title}</strong>
        <span className="candidate-badges">
          {lowRelevance && <span className="badge badge-low">{LOW_RELEVANCE_BADGE}</span>}
          {policy.scope && <span className="badge">{policy.scope}</span>}
        </span>
      </span>
      <span className="candidate-region">{policy.region_text || "중앙부처"}</span>
      {policy.summary && <span className="candidate-summary">{pickSummary(policy.summary)}</span>}
    </button>
  );
}
