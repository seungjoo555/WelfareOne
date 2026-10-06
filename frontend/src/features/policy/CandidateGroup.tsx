import type { PolicyCandidate } from "../../types/contract";
import { CandidateCard } from "./CandidateCard";

interface Props {
  title: string;
  policies: PolicyCandidate[];
  selectedPolicyId: string | null;
  onSelect: (policy: PolicyCandidate) => void;
}

// 지자체/중앙부처 정책은 하나의 순위로 섞지 않는다(계약서 9장).
export function CandidateGroup({ title, policies, selectedPolicyId, onSelect }: Props) {
  return (
    <section className="candidate-group" aria-label={title}>
      <h3>{title}</h3>
      {policies.length === 0 ? (
        <p className="muted">관련 정책을 찾지 못했습니다.</p>
      ) : (
        <div className="candidate-list">
          {policies.map((policy) => (
            <CandidateCard
              key={policy.policy_id}
              policy={policy}
              selected={policy.policy_id === selectedPolicyId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </section>
  );
}
