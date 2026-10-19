import assert from "node:assert/strict";
import { test } from "node:test";
import { QUICK_QUESTIONS } from "../src/constants/quickQuestions";

// 계약서 8장 intent 중 서버(/ask)가 버튼 질문으로 받는 값
const ALLOWED = ["eligibility", "benefit", "application", "administrative", "required_documents", "contact"];

test("자주 묻는 질문 버튼은 6개이고 지원 대상이 맨 앞이다", () => {
  assert.equal(QUICK_QUESTIONS.length, 6);
  assert.equal(QUICK_QUESTIONS[0].label, "지원 대상");
});

test("id·글자·질문 문장이 겹치지 않는다", () => {
  for (const key of ["id", "label", "question"] as const) {
    const values = QUICK_QUESTIONS.map((q) => q[key]);
    assert.equal(new Set(values).size, values.length, key);
  }
});

test("모든 버튼의 intent는 서버가 받는 값이고 서로 다른 유형이다", () => {
  for (const q of QUICK_QUESTIONS) assert.ok(ALLOWED.includes(q.intent), q.intent);
  assert.equal(new Set(QUICK_QUESTIONS.map((q) => q.intent)).size, QUICK_QUESTIONS.length);
});

test("질문 문장은 비어 있지 않고 서버 질문 길이 제한(500자) 안이다", () => {
  for (const q of QUICK_QUESTIONS) {
    assert.ok(q.question.trim().length > 0 && q.question.length <= 500);
  }
});
