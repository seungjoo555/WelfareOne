// WelfareOne 공통 계약서(docs/function_contracts.md)와 app/models.py 기준 타입.
// 필드명은 계약서의 snake_case를 그대로 쓴다. 임의로 바꾸지 말 것.
// [초안] 표시가 붙은 요청/응답 모양은 FastAPI 담당자와 합의가 필요한 부분이다.

export type SectionKey =
  | "candidate_summary"
  | "overview"
  | "target_criteria"
  | "benefit"
  | "application"
  | "documents"
  | "contact_source"
  | "administrative";

export type Route = "situation_search" | "specific_policy" | "current_policy_question";

export type Intent =
  | "policy_search"
  | "policy_overview"
  | "eligibility"
  | "benefit"
  | "application"
  | "required_documents"
  | "contact"
  | "administrative";

// level2가 없으면 ""(빈 문자열). DB가 광역 정책을 region_level2 == "" 로 저장하고
// 검색 로직(search_service)도 이 값을 기준으로 필터링한다. null이 아니다.
export interface RegionSelection {
  level1: string;
  level2: string;
}

// GET /regions 응답: { "서울특별시": ["관악구", ...], ... }
export type Regions = Record<string, string[]>;

// GET /config: 서버가 키 없이도 AI 요청을 처리하는지(계약서 제안 8-3). 호출에 실패하면 "키 필수"로 본다.
export interface ServerConfig {
  server_llm: boolean;
  server_llm_provider: string | null;
  user_key_provider: string;
}

export interface PolicyCandidate {
  policy_id: string; // 예: "local:WLF00006618"
  title: string;
  region_text: string; // 중앙부처 정책은 빈 문자열일 수 있음
  score: number; // 내부 점수: 화면에 노출하지 않는다
  distance: number; // 내부 점수: 화면에 노출하지 않는다
  scope: string; // "시군구" | "광역" | "시도" | "중앙부처"
  summary: string;
  metadata: Record<string, unknown>;
  reasons: string[];
}

export interface SearchAnalysis {
  route: Route;
  intents: Intent[];
  search_query: string;
}

// [초안] POST /policies/search
export interface SearchRequest {
  question: string;
  region: RegionSelection;
  age: number | null;
}
export interface SearchResponse {
  analysis: SearchAnalysis;
  local_policies: PolicyCandidate[];
  national_policies: PolicyCandidate[];
  // [초안] LLM 관련도 재판정 결과. relevance_checked가 true면 low_relevance_ids에 든 후보만 "관련도 낮음"으로 접고,
  // false(재판정을 안 했거나 실패)면 거리(distance)로 접는다. 옛 서버·저장된 기록에는 없을 수 있다.
  relevance_checked?: boolean;
  low_relevance_ids?: string[];
}

// [초안] GET /policies/{policy_id}  (없으면 404 POLICY_NOT_FOUND)
// title/region_text는 백엔드에 정책 메타데이터 조회 함수가 생기기 전까지 null일 수 있다.
export interface PolicyDetail {
  policy_id: string;
  title: string | null;
  region_text: string | null;
  sections: Partial<Record<SectionKey, string[]>>;
}

export type ResourceType = "attachment" | "website" | "legal_reference";
export interface PolicyResource {
  label: string;
  resource_type: ResourceType;
  url: string;
}

export interface AnswerResult {
  answer: string;
  policy_id: string;
  used_sections: SectionKey[];
  evidence: string[];
  resources: PolicyResource[];
  grounded: boolean;
}

// [초안] POST /policies/{policy_id}/ask
// route가 current_policy_question이 아니면 answer는 null (CLI의 "현재 정책 질문 아님" 분기).
// 화면의 "자주 묻는 질문" 버튼이 보내는 질문 유형(계약서 8장 intent의 일부). 있으면 서버가 질문 분석을 건너뛴다.
export type AskIntent = "eligibility" | "benefit" | "application" | "administrative" | "required_documents" | "contact";
export interface AskRequest {
  question: string;
  policy_title: string | null;
  intent?: AskIntent;
}
export interface AskResponse {
  route: Route;
  intents: Intent[];
  answer: AnswerResult | null;
}

// 계약서 17장 오류 응답 형식
export type ApiErrorCode =
  | "INVALID_REQUEST"
  | "INVALID_REGION"
  | "POLICY_NOT_FOUND"
  | "NO_SEARCH_RESULTS"
  | "LLM_RESPONSE_INVALID"
  | "LLM_RATE_LIMITED"
  | "API_KEY_REQUIRED" // [초안] 사용자 Gemini 키(BYOK)가 없고 서버 키 폴백도 꺼진 경우 (401)
  | "INVALID_API_KEY" // [초안] 사용자 키 형식이 틀렸거나 Gemini가 거부한 경우 (401)
  | "DATABASE_ERROR"
  | "INTERNAL_ERROR";
// 프론트에서만 만드는 오류(서버 응답 없음)
export type ClientErrorCode = "NETWORK_ERROR" | "TIMEOUT";
export type AppErrorCode = ApiErrorCode | ClientErrorCode;

export interface ApiErrorBody {
  error: { code: ApiErrorCode; message: string; details: unknown };
}
