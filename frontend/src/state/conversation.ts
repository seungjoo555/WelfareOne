import type { Conversation } from "../storage/history";
import type { Message } from "../types/chat";
import type { RegionSelection } from "../types/contract";

// 계약서 14장 ConversationState와 같은 모양(region, age, current_policy_id, ...)으로 시작한다.
// 나중에 FastAPI 세션(session_id) 방식으로 바꿔도 이 구조를 거의 그대로 쓸 수 있다.

export interface CurrentPolicy {
  policy_id: string;
  title: string;
}

export interface ConversationState {
  phase: "start" | "chat";
  // 상담 기록(localStorage) 저장·복원에 쓰는 식별자. 질문이 없는 상담은 저장하지 않는다.
  conversation_id: string | null;
  created_at: number | null;
  region: RegionSelection | null;
  age: number | null;
  messages: Message[];
  current_policy: CurrentPolicy | null;
  pending: boolean;
}

export const initialState: ConversationState = {
  phase: "start",
  conversation_id: null,
  created_at: null,
  region: null,
  age: null,
  messages: [],
  current_policy: null,
  pending: false,
};

// 저장된 상담을 화면 상태로 바꾼다. messages는 같은 배열을 그대로 쓴다(저장 여부를 참조 비교로 판단).
export function stateFromConversation(conversation: Conversation): ConversationState {
  return {
    phase: "chat",
    conversation_id: conversation.id,
    created_at: conversation.created_at,
    region: conversation.region,
    age: conversation.age,
    messages: conversation.messages,
    current_policy: conversation.current_policy,
    pending: false,
  };
}

export const uid = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const opener = (): Message => ({ id: uid(), type: "ai_opener" });

export type Action =
  | { type: "START"; region: RegionSelection; age: number | null }
  | { type: "EDIT_CONDITIONS" }
  | { type: "CANCEL_EDIT" }
  | { type: "NEW_CHAT" }
  | { type: "LOAD"; conversation: Conversation } // 저장된 상담으로 전환
  | { type: "USER_SEND"; text: string }
  | { type: "RESOLVE"; message: Message } // 로딩 말풍선을 실제 응답으로 교체
  | { type: "SELECT_POLICY"; policy: CurrentPolicy }
  | { type: "CLEAR_POLICY" };

export function conversationReducer(state: ConversationState, action: Action): ConversationState {
  switch (action.type) {
    case "START":
      // 지역·나이가 바뀌면 이전 후보와 선택 정책은 의미가 없으므로 새 상담으로 시작한다.
      // 이전 상담은 기록에 그대로 남는다(질문이 있었던 경우).
      return {
        phase: "chat",
        conversation_id: uid(),
        created_at: Date.now(),
        region: action.region,
        age: action.age,
        messages: [opener()],
        current_policy: null,
        pending: false,
      };
    case "EDIT_CONDITIONS":
      return { ...state, phase: "start" };
    case "CANCEL_EDIT":
      return { ...state, phase: state.region ? "chat" : "start" };
    case "NEW_CHAT":
      // 지역·나이는 유지하고 새 상담을 만든다. 이전 상담은 기록에 남는다.
      return {
        ...state,
        conversation_id: uid(),
        created_at: Date.now(),
        messages: [opener()],
        current_policy: null,
        pending: false,
      };
    case "LOAD":
      return stateFromConversation(action.conversation);
    case "USER_SEND":
      return {
        ...state,
        pending: true,
        messages: [
          ...state.messages,
          { id: uid(), type: "user_text", text: action.text },
          { id: uid(), type: "ai_loading" },
        ],
      };
    case "RESOLVE":
      return {
        ...state,
        pending: false,
        messages: [...state.messages.filter((m) => m.type !== "ai_loading"), action.message],
      };
    case "SELECT_POLICY":
      return {
        ...state,
        current_policy: action.policy,
        messages: [
          ...state.messages,
          { id: uid(), type: "ai_policy_selected", policy_title: action.policy.title },
        ],
      };
    case "CLEAR_POLICY":
      return {
        ...state,
        current_policy: null,
        messages: [
          ...state.messages,
          { id: uid(), type: "ai_text", text: "다른 정책을 찾아볼게요. 상황이나 정책 이름을 입력해 주세요." },
        ],
      };
  }
}
