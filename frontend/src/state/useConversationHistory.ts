import { useCallback, useEffect, useRef, useState } from "react";
import { CONFIRM_DELETE_ALL, CONFIRM_DELETE_ONE } from "../constants/text";
import { historyStore } from "../storage";
import { hasUserMessage, makeTitle } from "../storage/history";
import type { ConversationSummary } from "../storage/history";
import { initialState, stateFromConversation } from "./conversation";
import type { Action, ConversationState } from "./conversation";

// 앱을 열 때: 마지막으로 보던 상담을 복원하고, 없으면 가장 최근 상담, 그것도 없으면 시작 화면.
export function loadInitialState(): ConversationState {
  const activeId = historyStore.getActiveId();
  const active = activeId ? historyStore.load(activeId) : null;
  if (active) return stateFromConversation(active);
  for (const item of historyStore.list()) {
    const conversation = historyStore.load(item.id);
    if (conversation) return stateFromConversation(conversation);
  }
  return initialState;
}

export interface ConversationHistory {
  items: ConversationSummary[];
  activeId: string | null;
  saveError: "quota" | "unavailable" | null;
  select: (id: string) => void;
  rename: (id: string, title: string) => void;
  remove: (id: string) => void;
  clearAll: () => void;
}

// 대화 상태를 localStorage에 저장하고, 사이드바 목록·전환·삭제를 제공한다.
export function useConversationHistory(state: ConversationState, dispatch: React.Dispatch<Action>): ConversationHistory {
  const [items, setItems] = useState<ConversationSummary[]>(() => historyStore.list());
  const [saveError, setSaveError] = useState<"quota" | "unavailable" | null>(null);
  // 마지막으로 저장했거나 불러온 messages 배열. 같은 배열이면 다시 저장하지 않는다(열어 보기만 해서 순서가 바뀌지 않게).
  const savedMessages = useRef(state.messages);

  useEffect(() => {
    const { conversation_id, created_at, region, age, messages, current_policy } = state;
    if (!conversation_id || created_at === null || !region) return;
    if (messages === savedMessages.current) return;
    savedMessages.current = messages;
    if (!hasUserMessage(messages)) return; // 질문이 없는 상담은 기록하지 않는다
    const result = historyStore.save({
      id: conversation_id,
      title: makeTitle(messages),
      created_at,
      updated_at: Date.now(),
      region,
      age,
      messages,
      current_policy,
    });
    setSaveError(result.ok ? null : result.reason);
    setItems(historyStore.list());
  }, [state]);

  // 새로고침 뒤 마지막으로 보던 상담을 다시 열기 위해 현재 상담 id를 기억한다.
  useEffect(() => {
    if (state.conversation_id) historyStore.setActiveId(state.conversation_id);
  }, [state.conversation_id]);

  // 다른 탭에서 기록이 바뀌면 목록을 다시 읽는다.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith(historyStore.namespace)) setItems(historyStore.list());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // 응답을 기다리는 중에는 전환·삭제를 막는다(답변이 엉뚱한 상담에 붙는 것을 방지).
  const select = useCallback(
    (id: string) => {
      if (state.pending || id === state.conversation_id) return;
      const conversation = historyStore.load(id);
      if (!conversation) {
        historyStore.remove(id);
        setItems(historyStore.list());
        return;
      }
      savedMessages.current = conversation.messages;
      dispatch({ type: "LOAD", conversation });
    },
    [state.pending, state.conversation_id, dispatch],
  );

  // 상담 제목 수정. 응답 흐름과 무관하므로 응답을 기다리는 중에도 허용한다. 저장하지 못하면 기존 제목을 그대로 둔다.
  const rename = useCallback((id: string, title: string) => {
    const result = historyStore.rename(id, title);
    setSaveError(result === null ? "unavailable" : null);
    setItems(historyStore.list());
  }, []);

  const remove = useCallback(
    (id: string) => {
      if (state.pending || !window.confirm(CONFIRM_DELETE_ONE)) return;
      historyStore.remove(id);
      setItems(historyStore.list());
      if (id === state.conversation_id) dispatch({ type: "NEW_CHAT" });
    },
    [state.pending, state.conversation_id, dispatch],
  );

  const clearAll = useCallback(() => {
    if (state.pending || !window.confirm(CONFIRM_DELETE_ALL)) return;
    historyStore.clear();
    setItems([]);
    setSaveError(null);
    dispatch({ type: "NEW_CHAT" });
  }, [state.pending, dispatch]);

  return { items, activeId: state.conversation_id, saveError, select, rename, remove, clearAll };
}
