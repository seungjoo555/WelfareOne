import assert from "node:assert/strict";
import { test } from "node:test";
import { PAGE_SIZE, clampPage, needsPager, pageCount, pageSlice } from "../src/utils/paging";

const items = (n: number) => Array.from({ length: n }, (_, i) => i + 1);

test("쪽 수: 3개씩 올림, 비어 있으면 0", () => {
  assert.equal(PAGE_SIZE, 3);
  assert.equal(pageCount(0), 0);
  assert.equal(pageCount(1), 1);
  assert.equal(pageCount(3), 1);
  assert.equal(pageCount(4), 2);
  assert.equal(pageCount(8), 3);
});

test("pageSlice: 우선순위 순서를 유지하며 3개씩 자른다", () => {
  const list = items(8);
  assert.deepEqual(pageSlice(list, 0), [1, 2, 3]);
  assert.deepEqual(pageSlice(list, 1), [4, 5, 6]);
  assert.deepEqual(pageSlice(list, 2), [7, 8]);
});

test("pageSlice: 범위를 벗어난 쪽은 가까운 쪽으로 보정한다", () => {
  const list = items(4);
  assert.deepEqual(pageSlice(list, 99), [4]);
  assert.deepEqual(pageSlice(list, -5), [1, 2, 3]);
  assert.deepEqual(pageSlice([], 3), []);
});

test("clampPage: NaN·소수·후보 감소에도 안전하다", () => {
  assert.equal(clampPage(Number.NaN, 8), 0);
  assert.equal(clampPage(1.9, 8), 1);
  assert.equal(clampPage(2, 2), 0); // 후보가 2개로 줄면 첫 쪽
  assert.equal(clampPage(5, 0), 0);
});

test("needsPager: 3개 이하면 버튼을 그리지 않는다", () => {
  assert.equal(needsPager(0), false);
  assert.equal(needsPager(3), false);
  assert.equal(needsPager(4), true);
});
