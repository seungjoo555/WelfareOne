import { useState } from "react";
import type { CurrentPolicy } from "../../state/conversation";
import type { AskIntent } from "../../types/contract";
import { QuickQuestions } from "../policy/QuickQuestions";
import { RawSectionsTab } from "../policy/RawSectionsTab";

interface Props {
  policy: CurrentPolicy;
  onClear: () => void;
  pending: boolean;
  onAsk: (question: string, intent: AskIntent) => void;
}

export function CurrentPolicyBar({ policy, onClear, pending, onAsk }: Props) {
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
      <QuickQuestions disabled={pending} onAsk={onAsk} compact />
      {showRaw && <RawSectionsTab policyId={policy.policy_id} />}
    </div>
  );
}
