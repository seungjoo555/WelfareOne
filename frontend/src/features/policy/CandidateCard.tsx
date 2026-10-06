import type { PolicyCandidate } from "../../types/contract";
import { pickSummary } from "../../utils/summary";

interface Props {
  policy: PolicyCandidate;
  selected: boolean;
  onSelect: (policy: PolicyCandidate) => void;
}

// score/distance/reasons는 내부 진단 값이라 화면에 보여주지 않는다.
// (reasons는 "벡터 유사도 0.700", "검색 범위 시군구" 같은 개발용 문구다.)
export function CandidateCard({ policy, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      className={`candidate${selected ? " selected" : ""}`}
      aria-pressed={selected}
      onClick={() => onSelect(policy)}
    >
      <span className="candidate-top">
        <strong>{policy.title}</strong>
        {policy.scope && <span className="badge">{policy.scope}</span>}
      </span>
      <span className="candidate-region">{policy.region_text || "중앙부처"}</span>
      {policy.summary && <span className="candidate-summary">{pickSummary(policy.summary)}</span>}
    </button>
  );
}
