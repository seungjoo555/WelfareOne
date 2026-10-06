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
  region: RegionSelection | null;
  age: number | null;
  messages: Message[];
  current_policy: CurrentPolicy | null;
  pending: boolean;
}

export const initialState: ConversationState = {
  phase: "start",
  region: null,
  age: null,
  messages: [],
  current_policy: null,
  pending: false,
};

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
  | { type: "USER_SEND"; text: string }
  | { type: "RESOLVE"; message: Message } // 로딩 말풍선을 실제 응답으로 교체
  | { type: "SELECT_POLICY"; policy: CurrentPolicy }
  | { type: "CLEAR_POLICY" };

export function conversationReducer(state: ConversationState, action: Action): ConversationState {
  switch (action.type) {
    case "START":
      // 지역·나이가 바뀌면 이전 후보와 선택 정책은 의미가 없으므로 모두 초기화한다.
      return {
        phase: "chat",
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
      return { ...state, messages: [opener()], current_policy: null, pending: false };
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
          {
            id: uid(),
            type: "ai_text",
            text: `‘${action.policy.title}’ 정책을 선택했어요. 지원 대상, 신청 방법 등 궁금한 점을 질문해 보세요.`,
          },
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
