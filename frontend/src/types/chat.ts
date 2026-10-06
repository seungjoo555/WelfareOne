import type { AnswerResult, AppErrorCode, PolicyCandidate, SearchAnalysis } from "./contract";

// 채팅 목록의 모든 항목을 하나의 타입으로 묶는다(type 값으로 종류를 구분).
// 새 화면이 필요하면 여기에 종류를 추가하고 MessageItem에서 렌더링만 붙이면 된다.
export type Message =
  | { id: string; type: "user_text"; text: string }
  | { id: string; type: "ai_opener" }
  | { id: string; type: "ai_text"; text: string }
  | {
      id: string;
      type: "ai_candidates";
      analysis: SearchAnalysis;
      local_policies: PolicyCandidate[];
      national_policies: PolicyCandidate[];
    }
  | { id: string; type: "ai_answer"; answer: AnswerResult }
  | { id: string; type: "ai_notice"; code: "NOT_CURRENT_POLICY" }
  | { id: string; type: "ai_error"; code: AppErrorCode }
  | { id: string; type: "ai_loading" };
