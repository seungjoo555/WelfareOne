import { useState } from "react";
import type { CurrentPolicy } from "../../state/conversation";
import { RawSectionsTab } from "../policy/RawSectionsTab";

interface Props {
  policy: CurrentPolicy;
  onClear: () => void;
}

export function CurrentPolicyBar({ policy, onClear }: Props) {
  const [showRaw, setShowRaw] = useState(false);
  return (
    <div className="policy-bar">
      <div className="policy-bar-row">
        <span className="policy-bar-title">
          현재 정책 · <strong>{policy.title}</strong>
        </span>
        <span className="policy-bar-actions">
          <button type="button" className="btn small" aria-expanded={showRaw} onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "원문 닫기" : "원문 보기"}
          </button>
          <button type="button" className="btn small" onClick={onClear}>
            다른 정책 찾기
          </button>
        </span>
      </div>
      {showRaw && <RawSectionsTab policyId={policy.policy_id} />}
    </div>
  );
}
