import type { AskIntent } from "../types/contract";

// 정책을 선택한 뒤 버튼 한 번으로 물어볼 수 있는 "자주 묻는 질문".
// 순서는 팀 평가 질문 280개의 키워드 빈도(지원 대상 > 지원 내용 > 문의처·신청 방법·신청 기간)를 참고했고,
// 신청 때 꼭 필요한 필요 서류는 빈도가 낮아도 포함했다.
// intent는 계약서 8장의 값이다. 서버는 intent가 있으면 질문 분석을 건너뛰고 그 유형으로 바로 답한다.
export interface QuickQuestion {
  id: string;
  label: string; // 버튼에 보이는 글자
  question: string; // 대화에 사용자 말풍선으로 남는 문장
  intent: AskIntent;
}

export const QUICK_QUESTIONS: readonly QuickQuestion[] = [
  { id: "eligibility", label: "지원 대상", question: "지원 대상이 어떻게 되나요?", intent: "eligibility" },
  { id: "benefit", label: "지원 내용·금액", question: "어떤 지원을 얼마나 받을 수 있나요?", intent: "benefit" },
  { id: "application", label: "신청 방법", question: "신청은 어떻게 하나요?", intent: "application" },
  { id: "period", label: "신청 기간", question: "신청 기간은 언제인가요?", intent: "administrative" },
  { id: "documents", label: "필요 서류", question: "신청할 때 필요한 서류는 무엇인가요?", intent: "required_documents" },
  { id: "contact", label: "문의처", question: "문의는 어디로 하면 되나요?", intent: "contact" },
];
