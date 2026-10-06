import type { AppErrorCode } from "../types/contract";

// 서버는 한국어 문구를 내려주지 않는다(계약서 17장). 사용자 문구는 여기서 만든다.
export const ERROR_MESSAGES: Record<AppErrorCode, string> = {
  INVALID_REQUEST: "요청 형식이 올바르지 않아요. 입력 내용을 확인해 주세요.",
  INVALID_REGION: "선택한 지역을 확인할 수 없어요. 지역을 다시 선택해 주세요.",
  POLICY_NOT_FOUND: "정책을 찾을 수 없어요. 다른 정책을 선택해 주세요.",
  NO_SEARCH_RESULTS: "조건에 맞는 정책 후보를 찾지 못했어요. 표현을 바꿔 다시 질문해 보세요.",
  LLM_RESPONSE_INVALID: "AI 응답을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
  LLM_RATE_LIMITED: "요청이 많아 잠시 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
  API_KEY_REQUIRED: "Gemini API 키가 필요해요. 위쪽의 'API 키' 버튼에서 본인 키를 입력한 뒤 다시 질문해 주세요.",
  INVALID_API_KEY: "입력한 Gemini API 키를 사용할 수 없어요. 'API 키' 버튼에서 키를 확인한 뒤 다시 질문해 주세요.",
  DATABASE_ERROR: "정책 데이터를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.",
  INTERNAL_ERROR: "서버에서 문제가 발생했어요. 잠시 후 다시 시도해 주세요.",
  NETWORK_ERROR: "서버에 연결하지 못했어요. 네트워크와 서버 실행 상태를 확인해 주세요.",
  TIMEOUT: "응답이 너무 오래 걸리고 있어요. 잠시 후 다시 시도해 주세요.",
};

export const SERVICE_NAME = "WelfareOne";

export const OPENER_TEXT =
  "안녕하세요, WelfareOne입니다. 선택하신 지역과 나이를 기준으로 청년 복지정책을 찾아 드려요. " +
  "궁금한 상황이나 정책 이름을 편하게 입력해 주세요.";

// 실제 DB로 검색해 서울 강남구·28세 기준 상위 결과가 질문과 맞는 것을 확인한 질문이다.
// (면접 준비 비용 질문은 관련 정책이 상위에 나오지 않아 교통비 질문으로 교체했다.)
export const EXAMPLE_QUESTIONS = [
  "월세가 부담돼요",
  "대중교통비를 지원해 주는 정책이 있나요?",
  "출산 후 산후조리 비용 지원이 궁금해요",
];

export const DISCLAIMER =
  "WelfareOne은 공개 정책 원문에 근거한 예비 안내입니다. 실제 지원 여부는 해당 기관에서 최종 확인해 주세요.";

export const CRITERIA_NOTICE =
  "※ 자격 조건은 공식 원문이며, 아직 자동 자격 판정은 지원하지 않습니다.";

export const MAX_QUESTION_LENGTH = 500;
