import type { Intent, SectionKey } from "../types/contract";

// 원문 보기에서 보여줄 섹션과 순서 (app/cli.py의 show_policy_detail과 동일)
export const SECTION_ORDER: SectionKey[] = [
  "overview",
  "target_criteria",
  "benefit",
  "application",
  "documents",
  "contact_source",
];

// app/cli.py의 SECTION_LABELS 기준
export const SECTION_LABELS: Record<SectionKey, string> = {
  candidate_summary: "후보 요약",
  overview: "정책 개요",
  target_criteria: "지원 대상 및 선정 조건",
  benefit: "지원 내용",
  application: "신청 방법",
  documents: "필요 서류",
  contact_source: "문의처 및 출처",
  administrative: "행정 정보",
};

export const INTENT_LABELS: Record<Intent, string> = {
  policy_search: "정책 찾기",
  policy_overview: "정책 개요",
  eligibility: "지원 대상",
  benefit: "지원 내용",
  application: "신청 방법",
  required_documents: "필요 서류",
  contact: "문의처",
  administrative: "행정 정보",
};
