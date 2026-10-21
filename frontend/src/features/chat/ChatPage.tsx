import { useEffect, useMemo, useState } from "react";
import { askPolicy, askPolicyInSession, searchPolicies, searchPoliciesInSession } from "../../api/policies";
import { ApiClientError, toErrorCode } from "../../api/client";
import { conversationFromServer } from "../../utils/serverHistory";
import { USE_MOCK } from "../../config";
import { DISCLAIMER, SERVICE_NAME } from "../../constants/text";
import type { ConversationState, Action } from "../../state/conversation";
import { uid } from "../../state/conversation";
import type { AskIntent, PolicyCandidate } from "../../types/contract";
import { loadApiKey } from "../../utils/apiKey";
import type { ConversationHistory } from "../../state/useConversationHistory";
import { ApiKeyDialog } from "../settings/ApiKeyDialog";
import { ThemeToggle } from "../settings/ThemeToggle";
import { ChatInput } from "./ChatInput";
import { ConversationList } from "./ConversationList";
import { CurrentPolicyBar } from "./CurrentPolicyBar";
import { MessageList } from "./MessageList";
import { getAuthToken, getMe, removeAuthToken, UserProfile } from "../../api/auth";
import { createServerSession, fetchServerSessions, fetchServerSessionDetail, ServerSessionSummary } from "../../api/history";
import { CommonLoginModal } from "../portal/CommonLoginModal";

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
  const hasKey = useMemo(() => loadApiKey() !== null, [keyVersion]);

  // 회원 인증 상태
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [serverSessions, setServerSessions] = useState<ServerSessionSummary[]>([]);
  const [activeServerSessionId, setActiveServerSessionId] = useState<string | null>(null);

  // 초기 마운트 시 로그인 확인
  useEffect(() => {
    getMe().then((profile) => {
      if (profile) {
        setUser(profile);
        fetchServerSessions().then(setServerSessions).catch(() => {});
      }
    });
  }, []);

  const refreshSessions = () => {
    if (user) {
      fetchServerSessions().then(setServerSessions).catch(() => {});
    }
  };

  // 로그인 상태에서 AI 요청이 거치는 기록 서버 상담 세션. 대화(conversation_id)가 바뀌면 새로 만든다.
  const [serverSession, setServerSession] = useState<{ conversationId: string; sessionId: string } | null>(null);
  const activeSessionId =
    serverSession && serverSession.conversationId === (state.conversation_id ?? "") ? serverSession.sessionId : null;

  // 기록 서버가 안 되어도 검색은 계속되도록 실패하면 null을 돌려준다(그 경우 기존처럼 FastAPI로 바로 보낸다).
  const ensureServerSession = async (firstQuestion: string): Promise<string | null> => {
    if (USE_MOCK || !user || !region || !getAuthToken()) return null;
    if (activeSessionId) return activeSessionId;
    try {
      const created = await createServerSession({
        region_level1: region.level1,
        region_level2: region.level2,
        age,
        title: firstQuestion.slice(0, 30),
      });
      setServerSession({ conversationId: state.conversation_id ?? "", sessionId: created.session_id });
      return created.session_id;
    } catch {
      return null;
    }
  };

  // 기록 서버 경로로 보냈다가 서버 쪽 사유로 거절되면 FastAPI 직접 호출로 한 번 더 보낸다(기록만 건너뛰고 검색은 계속된다).
  // - UNAUTHORIZED: 로그인 토큰이 만료·거부됨 → 로그아웃 처리
  // - SESSION_NOT_FOUND / FORBIDDEN: 기록 서버의 상담 세션을 쓸 수 없음 → 세션 연결을 끊고 다음 질문에서 새로 만든다
  // 키 오류(API_KEY_REQUIRED, INVALID_API_KEY)나 한도 초과는 FastAPI가 준 오류이므로 그대로 보여 준다.
  const viaServer = async <T,>(run: () => Promise<T>, direct: () => Promise<T>): Promise<T> => {
    try {
      return await run();
    } catch (error) {
      if (error instanceof ApiClientError) {
        if (error.code === "UNAUTHORIZED") {
          removeAuthToken();
          setUser(null);
          setServerSession(null);
          return direct();
        }
        if (error.code === "SESSION_NOT_FOUND" || error.code === "FORBIDDEN") {
          setServerSession(null);
          return direct();
        }
      }
      throw error;
    }
  };

  const send = async (text: string, intent?: AskIntent) => {
    if (!region || pending) return;
    dispatch({ type: "USER_SEND", text });
    try {
      const sessionId = await ensureServerSession(text);
      const token = getAuthToken();
      const server = sessionId !== null && token !== null ? { sessionId, token } : null;
      if (current_policy) {
        const askBody = {
          question: text,
          policy_title: current_policy.title,
          ...(intent ? { intent } : {}), // 자주 묻는 질문 버튼이면 질문 유형을 함께 보낸다
        };
        const policyId = current_policy.policy_id;
        const res = server
          ? await viaServer(() => askPolicyInSession(server.sessionId, policyId, askBody, server.token), () => askPolicy(policyId, askBody))
          : await askPolicy(policyId, askBody);
        if (res.route !== "current_policy_question" || !res.answer) {
          dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_notice", code: "NOT_CURRENT_POLICY" } });
        } else {
          dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_answer", answer: res.answer } });
        }
      } else {
        const searchBody = { question: text, region, age };
        const res = server
          ? await viaServer(() => searchPoliciesInSession(server.sessionId, searchBody, server.token), () => searchPolicies(searchBody))
          : await searchPolicies(searchBody);
        dispatch({
          type: "RESOLVE",
          message: {
            id: uid(),
            type: "ai_candidates",
            analysis: res.analysis,
            local_policies: res.local_policies,
            national_policies: res.national_policies,
            relevance_checked: res.relevance_checked,
            low_relevance_ids: res.low_relevance_ids,
          },
        });
      }
      refreshSessions();
    } catch (error) {
      const code = toErrorCode(error);
      dispatch({ type: "RESOLVE", message: { id: uid(), type: "ai_error", code } });
      if (code === "API_KEY_REQUIRED") setKeyDialog({ open: true, reason: "required" });
      if (code === "INVALID_API_KEY") setKeyDialog({ open: true, reason: "invalid" });
    }
  };

  // 사이드바에서 서버 상담을 고르면 저장된 대화를 불러오고, 이어서 질문하면 같은 세션에 기록한다.
  const handleSelectServerSession = async (sessionId: string) => {
    try {
      const detail = await fetchServerSessionDetail(sessionId);
      const conversation = conversationFromServer(detail);
      dispatch({ type: "LOAD", conversation });
      setServerSession({ conversationId: conversation.id, sessionId });
      setActiveServerSessionId(sessionId);
      setSidebarOpen(false);
    } catch (e: any) {
      alert("상담 기록 로드 실패: " + e.message);
    }
  };

  const regionLabel = region ? [region.level1, region.level2].filter(Boolean).join(" ") : "";

  return (
    <div className={`app${sidebarOpen ? " sidebar-open" : ""}`}>
      <aside className="sidebar">
        {/* 상단 브랜드: 비로그인(WelfareOne) vs 로그인(사용자 이름 + 로그아웃) */}
        {!user ? (
          <div className="brand">{SERVICE_NAME}</div>
        ) : (
          <div
            className="brand user-brand"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              paddingRight: "8px",
            }}
          >
            <span style={{ fontSize: "16px", fontWeight: "bold", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={user.email}>
              👤 {user.nickname} 님
            </span>
            <button
              type="button"
              className="btn small"
              style={{ fontSize: "11px", padding: "2px 8px", background: "none", border: "1px solid var(--border-color, #d1d5db)" }}
              onClick={() => {
                removeAuthToken();
                setUser(null);
                setServerSessions([]);
                setActiveServerSessionId(null);
              }}
            >
              로그아웃
            </button>
          </div>
        )}

        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            dispatch({ type: "NEW_CHAT" });
            setActiveServerSessionId(null);
            setSidebarOpen(false);
          }}
        >
          + 새 상담
        </button>

        {/* 이전 대화 목록: 비로그인(LocalStorage) vs 로그인(Oracle DB 세션 목록) */}
        {!user ? (
          <ConversationList history={history} disabled={pending} onSelected={() => setSidebarOpen(false)} />
        ) : (
          <nav className="history" aria-label="클라우드 상담 기록">
            <h2 className="history-heading">저장된 대화 기록 (Oracle DB)</h2>
            {serverSessions.length === 0 ? (
              <p className="muted history-empty">저장된 상담 기록이 없습니다.</p>
            ) : (
              <ul className="history-list">
                {serverSessions.map((s) => {
                  const active = s.session_id === activeServerSessionId;
                  return (
                    <li key={s.session_id} className={`history-item${active ? " active" : ""}`}>
                      <button
                        type="button"
                        className="history-open"
                        disabled={pending}
                        title={s.title}
                        onClick={() => handleSelectServerSession(s.session_id)}
                      >
                        <span className="history-title">{s.title}</span>
                        <span className="history-meta">
                          {s.region_level1} {s.region_level2}
                          {s.age === null ? "" : ` · ${s.age}세`}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </nav>
        )}

        {/* 사이드바 하단: 비로그인(로그인/가입 버튼) vs 로그인(클라우드 보관 배너) */}
        {!user ? (
          <div style={{ padding: "12px", borderTop: "1px solid var(--border-color, #e5e7eb)" }}>
            <button
              type="button"
              className="btn"
              style={{
                width: "100%",
                background: "#059669",
                color: "white",
                fontWeight: "bold",
                padding: "8px",
                borderRadius: "8px",
              }}
              onClick={() => setAuthModalOpen(true)}
            >
              로그인 / 회원가입
            </button>
          </div>
        ) : (
          <div style={{ padding: "10px 14px", fontSize: "11px", color: "var(--text-muted, #6b7280)", borderTop: "1px solid var(--border-color, #e5e7eb)" }}>
            ☁️ 상담 기록이 Oracle DB에 안전하게 보관 중입니다.
          </div>
        )}

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
            API 키{hasKey || user?.has_api_key ? " ✓" : ""}
          </button>
        </header>

        {current_policy && (
          <CurrentPolicyBar
            policy={current_policy}
            onClear={() => dispatch({ type: "CLEAR_POLICY" })}
            pending={pending}
            onAsk={send}
          />
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

      {/* API 키 설정 다이얼로그 */}
      <ApiKeyDialog
        open={keyDialog.open}
        reason={keyDialog.reason}
        onClose={() => setKeyDialog({ open: false, reason: null })}
        onChange={() => setKeyVersion((v) => v + 1)}
      />

      {/* 공통 로그인/회원가입/비회원 시작 2단 모달 */}
      <CommonLoginModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onLoginSuccess={(loggedUser) => {
          setUser(loggedUser);
          fetchServerSessions().then(setServerSessions).catch(() => {});
        }}
        onGuestStart={(newRegion, newAge) => {
          dispatch({ type: "START", region: newRegion, age: newAge });
        }}
      />
    </div>
  );
}
