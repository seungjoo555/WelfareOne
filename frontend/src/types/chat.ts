import type { AnswerResult, AppErrorCode, PolicyCandidate, SearchAnalysis } from "./contract";

// 채팅 목록의 모든 항목을 하나의 타입으로 묶는다(type 값으로 종류를 구분).
// 새 화면이 필요하면 여기에 종류를 추가하고 MessageItem에서 렌더링만 붙이면 된다.
export type Message =
  | { id: string; type: "user_text"; text: string }
  | { id: string; type: "ai_opener" }
  | { id: string; type: "ai_text"; text: string }
  // 정책을 선택한 직후 안내. 자주 묻는 질문 버튼이 함께 나온다(예전 기록에는 같은 문구의 ai_text로 남아 있다).
  | { id: string; type: "ai_policy_selected"; policy_title: string }
  | {
      id: string;
      type: "ai_candidates";
      analysis: SearchAnalysis;
      local_policies: PolicyCandidate[];
      national_policies: PolicyCandidate[];
      relevance_checked?: boolean; // contract.ts SearchResponse 참고
      low_relevance_ids?: string[];
    }
  | { id: string; type: "ai_answer"; answer: AnswerResult }
  // INTERRUPTED: 응답을 받기 전에 페이지가 닫힌 저장된 상담을 다시 열었을 때 붙이는 안내
  | { id: string; type: "ai_notice"; code: "NOT_CURRENT_POLICY" | "INTERRUPTED" }
  | { id: string; type: "ai_error"; code: AppErrorCode }
  | { id: string; type: "ai_loading" };
