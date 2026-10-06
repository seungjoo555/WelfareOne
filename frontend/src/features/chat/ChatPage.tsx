import { useMemo, useState } from "react";
import { askPolicy, searchPolicies } from "../../api/policies";
import { toErrorCode } from "../../api/client";
import { USE_MOCK } from "../../config";
import { DISCLAIMER, SERVICE_NAME } from "../../constants/text";
import type { ConversationState, Action } from "../../state/conversation";
import { uid } from "../../state/conversation";
import type { PolicyCandidate } from "../../types/contract";
import { loadApiKey } from "../../utils/apiKey";
import type { ConversationHistory } from "../../state/useConversationHistory";
import { ApiKeyDialog } from "../settings/ApiKeyDialog";
import { ThemeToggle } from "../settings/ThemeToggle";
import { ChatInput } from "./ChatInput";
import { ConversationList } from "./ConversationList";
import { CurrentPolicyBar } from "./CurrentPolicyBar";
import { MessageList } from "./MessageList";

interface Props {
  state: ConversationState;
  dispatch: React.Dispatch<Action>;
  history: ConversationHistory;
}

export function ChatPage({ state, dispatch, history }: Props) {
  const { region, age, current_policy, messages, pending } = state;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [keyDialog, setKeyDialog] = useState<{ open: boolean; reason: "required" | "invalid" | null }>({
    open: false,
    reason: null,
  });
  const [keyVersion, setKeyVersion] = useState(0);
  // 저장소 값은 keyVersion이 바뀔 때(저장·삭제 후)만 다시 읽는다
  const hasKey = useMemo(() => loadApiKey() !== null, [keyVersion]);

  const send = async (text: string) => {
    if (!region || pending) return;
    dispatch({ type: "USER_SEND", text });
    try {
      if (current_policy) {
        const res = await askPolicy(current_policy.policy_id, {
          question: text,
          policy_title: current_policy.title,
        });
        if (res.route !== "current_policy_question" || !res.answer) {
          dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_notice", code: "NOT_CURRENT_POLICY" } });
        } else {
          dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_answer", answer: res.answer } });
        }
      } else {
        const res = await searchPolicies({ question: text, region, age });
        dispatch({
          type: "RESOLVE",
          message: {
            id: uid(),
            type: "ai_candidates",
            analysis: res.analysis,
            local_policies: res.local_policies,
            national_policies: res.national_policies,
          },
        });
      }
    } catch (error) {
      const code = toErrorCode(error);
      dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_error", code } });
      // 키 문제면 입력 창을 바로 열어 준다. 입력 후 사용자가 질문을 다시 보낸다.
      if (code === "API_KEY_REQUIRED") setKeyDialog({ open: true, reason: "required" });
      if (code === "INVALID_API_KEY") setKeyDialog({ open: true, reason: "invalid" });
    }
  };

  const regionLabel = region ? [region.level1, region.level2].filter(Boolean).join(" ") : "";

  return (
    <div className={`app${sidebarOpen ? " sidebar-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">{SERVICE_NAME}</div>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            dispatch({ type: "NEW_CHAT" });
            setSidebarOpen(false);
          }}
        >
          + 새 상담
        </button>
        <ConversationList history={history} disabled={pending} onSelected={() => setSidebarOpen(false)} />
        <div className="sidebar-bottom">
          <ThemeToggle />
        </div>
      </aside>

      <section className="main">
        <header className="header">
          <button
            type="button"
            className="btn icon sidebar-toggle"
            aria-label="사이드바 열기/닫기"
            onClick={() => setSidebarOpen((v) => !v)}
          >
            ☰
          </button>
          <h1>{SERVICE_NAME}</h1>
          {USE_MOCK && <span className="badge mock">MOCK</span>}
          <span className="conditions">
            {regionLabel} · {age === null ? "나이 미입력" : `${age}세`}
          </span>
          <button type="button" className="btn small" onClick={() => dispatch({ type: "EDIT_CONDITIONS" })}>
            수정
          </button>
          <button
            type="button"
            className="btn small"
            onClick={() => setKeyDialog({ open: true, reason: null })}
          >
            API 키{hasKey ? " ✓" : ""}
          </button>
        </header>

        {current_policy && (
          <CurrentPolicyBar policy={current_policy} onClear={() => dispatch({ type: "CLEAR_POLICY" })} />
        )}

        <MessageList
          messages={messages}
          actions={{
            selectedPolicyId: current_policy?.policy_id ?? null,
            pending,
            onSend: send,
            onSelectPolicy: (policy: PolicyCandidate) =>
              dispatch({ type: "SELECT_POLICY", policy: { policy_id: policy.policy_id, title: policy.title } }),
            onClearPolicy: () => dispatch({ type: "CLEAR_POLICY" }),
          }}
        />

        <footer className="footer">
          <ChatInput
            disabled={pending}
            placeholder={
              current_policy ? "이 정책에 대해 질문하세요" : "상황이나 정책 이름을 입력하세요"
            }
            onSend={send}
          />
          <p className="notice">{DISCLAIMER}</p>
        </footer>
      </section>

      <ApiKeyDialog
        open={keyDialog.open}
        reason={keyDialog.reason}
        onClose={() => setKeyDialog({ open: false, reason: null })}
        onChange={() => setKeyVersion((v) => v + 1)}
      />
    </div>
  );
}
