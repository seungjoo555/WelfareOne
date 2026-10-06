import {
  EMPTY_LOCAL_BUT_NATIONAL_TEXT,
  EMPTY_NATIONAL_BUT_LOCAL_TEXT,
  ERROR_MESSAGES,
  INTERRUPTED_NOTICE,
  OPENER_TEXT,
} from "../../constants/text";
import { INTENT_LABELS } from "../../constants/sections";
import type { Message } from "../../types/chat";
import type { PolicyCandidate } from "../../types/contract";
import { AnswerBubble } from "../policy/AnswerBubble";
import { CandidateGroup } from "../policy/CandidateGroup";
import { ExampleChips } from "./ExampleChips";

export interface MessageActions {
  selectedPolicyId: string | null;
  pending: boolean;
  onSend: (text: string) => void;
  onSelectPolicy: (policy: PolicyCandidate) => void;
  onClearPolicy: () => void;
}

function AiRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="row ai">
      <div className="avatar" aria-hidden="true">
        W
      </div>
      <div className="bubble ai">{children}</div>
    </div>
  );
}

export function MessageItem({ message, actions }: { message: Message; actions: MessageActions }) {
  switch (message.type) {
    case "user_text":
      return (
        <div className="row user">
          <div className="bubble user">{message.text}</div>
        </div>
      );
    case "ai_opener":
      return (
        <AiRow>
          <p>{OPENER_TEXT}</p>
          <p className="muted">이렇게 물어보세요!</p>
          <ExampleChips disabled={actions.pending} onPick={actions.onSend} />
        </AiRow>
      );
    case "ai_text":
      return (
        <AiRow>
          <p>{message.text}</p>
        </AiRow>
      );
    case "ai_candidates": {
      const empty = message.local_policies.length === 0 && message.national_policies.length === 0;
      return (
        <AiRow>
          <p className="muted">
            이렇게 이해했어요 · 검색어 “{message.analysis.search_query}”
            {message.analysis.intents.length > 0 &&
              ` · ${message.analysis.intents.map((i) => INTENT_LABELS[i]).join(", ")}`}
          </p>
          {empty ? (
            <p>조건에 맞는 정책 후보를 찾지 못했어요. 표현을 바꿔 다시 질문해 보세요.</p>
          ) : (
            <>
              <CandidateGroup
                title="내 지역 정책"
                policies={message.local_policies}
                selectedPolicyId={actions.selectedPolicyId}
                onSelect={actions.onSelectPolicy}
                emptyText={message.national_policies.length > 0 ? EMPTY_LOCAL_BUT_NATIONAL_TEXT : undefined}
              />
              <CandidateGroup
                title="중앙부처 정책"
                policies={message.national_policies}
                selectedPolicyId={actions.selectedPolicyId}
                onSelect={actions.onSelectPolicy}
                emptyText={message.local_policies.length > 0 ? EMPTY_NATIONAL_BUT_LOCAL_TEXT : undefined}
              />
            </>
          )}
        </AiRow>
      );
    }
    case "ai_answer":
      return (
        <AiRow>
          <AnswerBubble answer={message.answer} />
        </AiRow>
      );
    case "ai_notice":
      if (message.code === "INTERRUPTED") {
        return (
          <AiRow>
            <p className="warning" role="status">{INTERRUPTED_NOTICE}</p>
          </AiRow>
        );
      }
      return (
        <AiRow>
          <p>현재 선택한 정책에 대한 질문으로 확인되지 않았어요. 다른 정책을 찾으려면 아래 버튼을 눌러 주세요.</p>
          <button type="button" className="btn small" onClick={actions.onClearPolicy}>
            다른 정책 찾기
          </button>
        </AiRow>
      );
    case "ai_error":
      return (
        <AiRow>
          <p className="error-text" role="alert">
            {ERROR_MESSAGES[message.code]}
          </p>
        </AiRow>
      );
    case "ai_loading":
      return (
        <AiRow>
          <span className="dots" role="status" aria-label="답변을 준비하는 중">
            <i />
            <i />
            <i />
          </span>
        </AiRow>
      );
  }
}
