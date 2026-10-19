// 관련도 낮은 후보 접기 규칙 테스트. 실행: cd frontend; npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import { LOW_RELEVANCE_DISTANCE, orderForPaging, splitByRelevance } from "../src/utils/relevance";
import type { PolicyCandidate } from "../src/types/contract";

const policy = (id: string, distance: number): PolicyCandidate => ({
  policy_id: id,
  title: id,
  region_text: "",
  score: 1,
  distance,
  scope: "시군구",
  summary: "",
  metadata: {},
  reasons: [],
});

const ids = (list: PolicyCandidate[]) => list.map((p) => p.policy_id);

test("상황형 질문은 기준 거리를 넘는 후보를 따로 나눈다", () => {
  const { confident, lowRelevance } = splitByRelevance([policy("a", 0.3), policy("b", 0.52), policy("c", 0.45)], true);
  assert.deepEqual(ids(confident), ["a", "c"]);
  assert.deepEqual(ids(lowRelevance), ["b"]);
});

test("기준 거리와 같은 후보는 접지 않는다(경계는 포함)", () => {
  const { confident, lowRelevance } = splitByRelevance(
    [policy("edge", LOW_RELEVANCE_DISTANCE), policy("just-over", LOW_RELEVANCE_DISTANCE + 0.01)],
    true,
  );
  assert.deepEqual(ids(confident), ["edge"]);
  assert.deepEqual(ids(lowRelevance), ["just-over"]);
});

test("정책명을 말한 질문(fold=false)은 거리와 상관없이 모두 보여 준다", () => {
  const all = [policy("a", 0.3), policy("b", 0.58)];
  const { confident, lowRelevance } = splitByRelevance(all, false);
  assert.deepEqual(ids(confident), ["a", "b"]);
  assert.deepEqual(lowRelevance, []);
});

test("서버가 내려준 순서를 유지하고 입력 배열을 바꾸지 않는다", () => {
  const input = [policy("x", 0.6), policy("y", 0.2), policy("z", 0.55), policy("w", 0.4)];
  const copy = [...input];
  const { confident, lowRelevance } = splitByRelevance(input, true);
  assert.deepEqual(ids(confident), ["y", "w"]);
  assert.deepEqual(ids(lowRelevance), ["x", "z"]);
  assert.deepEqual(input, copy);
});

test("distance가 숫자가 아니면(저장된 옛 기록 등) 접지 않는다", () => {
  const broken = { ...policy("n", 0.9), distance: undefined as unknown as number };
  const { confident, lowRelevance } = splitByRelevance([broken], true);
  assert.deepEqual(ids(confident), ["n"]);
  assert.deepEqual(lowRelevance, []);
});

test("서버가 LLM으로 판정한 목록이 있으면 거리는 보지 않고 그 목록만 접는다", () => {
  const list = [policy("near-but-irrelevant", 0.2), policy("far-but-relevant", 0.54), policy("far-and-irrelevant", 0.6)];
  const { confident, lowRelevance } = splitByRelevance(list, true, ["near-but-irrelevant", "far-and-irrelevant"]);
  assert.deepEqual(ids(confident), ["far-but-relevant"]); // 거리가 멀어도 관련 있다고 판정되면 기본 화면에 올라온다
  assert.deepEqual(ids(lowRelevance), ["near-but-irrelevant", "far-and-irrelevant"]);
});

test("판정 결과가 빈 목록이면(모두 관련 있음) 아무것도 접지 않는다", () => {
  const { confident, lowRelevance } = splitByRelevance([policy("a", 0.58), policy("b", 0.2)], true, []);
  assert.deepEqual(ids(confident), ["a", "b"]);
  assert.deepEqual(lowRelevance, []);
});

test("fold=false이면 판정 목록이 있어도 모두 보여 준다", () => {
  const { confident, lowRelevance } = splitByRelevance([policy("a", 0.2)], false, ["a"]);
  assert.deepEqual(ids(confident), ["a"]);
  assert.deepEqual(lowRelevance, []);
});

test("판정 목록이 null이면 거리 규칙을 쓴다(판정 안 함·실패)", () => {
  const { confident, lowRelevance } = splitByRelevance([policy("a", 0.3), policy("b", 0.52)], true, null);
  assert.deepEqual(ids(confident), ["a"]);
  assert.deepEqual(ids(lowRelevance), ["b"]);
});

test("빈 목록도 안전하다", () => {
  assert.deepEqual(splitByRelevance([], true), { confident: [], lowRelevance: [] });
});

test("orderForPaging: 관련 후보가 앞, 관련도 낮은 후보가 뒤에 이어진다(우선순위 유지)", () => {
  const confident = [policy("a", 0.2), policy("b", 0.3)];
  const low = [policy("c", 0.4), policy("d", 0.5)];
  assert.deepEqual(ids(orderForPaging(confident, low, false)), ["a", "b", "c", "d"]);
  assert.deepEqual(ids(orderForPaging(confident, low, true)), ["a", "b", "c", "d"]);
});

test("orderForPaging: 관련 후보가 없으면 낮은 후보는 펼치기 전까지 숨긴다", () => {
  const low = [policy("c", 0.4), policy("d", 0.5)];
  assert.deepEqual(orderForPaging([], low, false), []);
  assert.deepEqual(ids(orderForPaging([], low, true)), ["c", "d"]);
  assert.deepEqual(orderForPaging([], [], true), []);
});
