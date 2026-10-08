// 상담 기록 저장 계층 테스트. 실행: cd frontend; npm test  (node 내장 테스트 러너 사용, 추가 의존성 없음)
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MAX_CONVERSATIONS,
  MAX_MESSAGES,
  createHistoryStore,
  hasUserMessage,
  makeTitle,
} from "../src/storage/history";
import type { Conversation } from "../src/storage/history";
import type { Message } from "../src/types/chat";
import type { PolicyCandidate } from "../src/types/contract";

// 용량 제한을 흉내 내는 가짜 localStorage (키+값 글자 수 합계가 capacity를 넘으면 QuotaExceededError)
class FakeStorage implements Storage {
  private data = new Map<string, string>();
  constructor(private capacity = Infinity) {}
  get length() {
    return this.data.size;
  }
  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    const next = new Map(this.data).set(key, value);
    let size = 0;
    for (const [k, v] of next) size += k.length + v.length;
    if (size > this.capacity) throw new DOMException("full", "QuotaExceededError");
    this.data = next;
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
  clear() {
    this.data.clear();
  }
  keys() {
    return [...this.data.keys()];
  }
}

const NS = "t";
const candidate = (id: string): PolicyCandidate => ({
  policy_id: id,
  title: `정책 ${id}`,
  region_text: "서울특별시 강남구",
  score: 1,
  distance: 0.3,
  scope: "시군구",
  summary: "요약",
  metadata: { big: "x".repeat(500) },
  reasons: ["벡터 유사도 0.7"],
});

const conv = (id: string, updated_at: number, messages?: Message[]): Conversation => ({
  id,
  title: `상담 ${id}`,
  created_at: updated_at,
  updated_at,
  region: { level1: "서울특별시", level2: "강남구" },
  age: 28,
  messages: messages ?? [
    { id: `${id}-m1`, type: "ai_opener" },
    { id: `${id}-m2`, type: "user_text", text: "월세가 부담돼요" },
    { id: `${id}-m3`, type: "ai_text", text: "답변" },
  ],
  current_policy: null,
});

test("저장한 상담을 그대로 불러온다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  const saved = conv("a", 100);
  assert.deepEqual(store.save(saved), { ok: true });
  assert.deepEqual(store.load("a"), saved);
});

test("저장 전에 로딩 말풍선과 후보의 metadata·reasons를 제거한다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  const messages: Message[] = [
    { id: "1", type: "user_text", text: "질문" },
    {
      id: "2",
      type: "ai_candidates",
      analysis: { route: "situation_search", intents: ["policy_search"], search_query: "q" },
      local_policies: [candidate("local:1")],
      national_policies: [candidate("national:2")],
    },
    { id: "3", type: "ai_loading" },
  ];
  store.save(conv("a", 100, messages));
  const loaded = store.load("a")!;
  assert.equal(loaded.messages.some((m) => m.type === "ai_loading"), false);
  const found = loaded.messages.find((m) => m.type === "ai_candidates");
  assert.ok(found && found.type === "ai_candidates");
  assert.deepEqual(found.local_policies[0].metadata, {});
  assert.deepEqual(found.national_policies[0].reasons, []);
  assert.equal(found.local_policies[0].title, "정책 local:1"); // 화면에 쓰는 값은 유지
});

test("목록은 최근 수정 순이고 삭제하면 본문과 목록에서 모두 사라진다", () => {
  const storage = new FakeStorage();
  const store = createHistoryStore(storage, NS);
  store.save(conv("old", 100));
  store.save(conv("new", 300));
  store.save(conv("mid", 200));
  assert.deepEqual(store.list().map((i) => i.id), ["new", "mid", "old"]);
  store.remove("mid");
  assert.deepEqual(store.list().map((i) => i.id), ["new", "old"]);
  assert.equal(store.load("mid"), null);
  assert.equal(storage.keys().some((k) => k.endsWith(".conv.mid")), false);
});

test("상담이 상한을 넘으면 가장 오래된 것부터 지운다", () => {
  const storage = new FakeStorage();
  const store = createHistoryStore(storage, NS);
  for (let i = 0; i < MAX_CONVERSATIONS + 2; i++) store.save(conv(`c${i}`, 1000 + i));
  const ids = store.list().map((item) => item.id);
  assert.equal(ids.length, MAX_CONVERSATIONS);
  assert.equal(ids.includes("c0"), false);
  assert.equal(ids.includes("c1"), false);
  assert.equal(ids[0], `c${MAX_CONVERSATIONS + 1}`);
  assert.equal(storage.keys().filter((k) => k.includes(".conv.")).length, MAX_CONVERSATIONS); // 고아 키가 남지 않는다
});

test("상담당 메시지는 최근 MAX_MESSAGES개만 남긴다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  const many: Message[] = Array.from({ length: MAX_MESSAGES + 50 }, (_, i) => ({ id: `m${i}`, type: "ai_text", text: `${i}` }));
  store.save(conv("a", 1, many));
  const loaded = store.load("a")!;
  assert.equal(loaded.messages.length, MAX_MESSAGES);
  assert.equal(loaded.messages[loaded.messages.length - 1].id, `m${MAX_MESSAGES + 49}`);
});

test("저장 공간이 모자라면 오래된 상담부터 지우고 새 상담을 저장한다", () => {
  const sample = JSON.stringify(conv("x", 1)).length;
  const store = createHistoryStore(new FakeStorage(sample * 3 + 400), NS);
  store.save(conv("a", 100));
  store.save(conv("b", 200));
  store.save(conv("c", 300));
  const result = store.save(conv("d", 400));
  assert.deepEqual(result, { ok: true });
  const ids = store.list().map((i) => i.id);
  assert.ok(ids.includes("d"));
  assert.equal(ids.includes("a"), false); // 가장 오래된 상담이 밀려났다
});

test("지울 상담이 없는데도 공간이 모자라면 quota 실패를 알린다", () => {
  const store = createHistoryStore(new FakeStorage(50), NS);
  assert.deepEqual(store.save(conv("a", 1)), { ok: false, reason: "quota" });
  assert.deepEqual(store.list(), []);
});

test("손상된 JSON과 형식이 틀린 값은 예외 없이 무시하고 정리한다", () => {
  const storage = new FakeStorage();
  const store = createHistoryStore(storage, NS);
  store.save(conv("good", 100));
  storage.setItem(`${NS}.conv.bad`, "{not json");
  storage.setItem(`${NS}.conv.wrong`, JSON.stringify({ id: "wrong", messages: "x" }));
  storage.setItem(`${NS}.index`, JSON.stringify([{ id: "bad", title: "t", updated_at: 1, region_text: "", age: null }, { nope: 1 }]));
  // 목록은 본문 키가 있는지만 본다. 형식이 틀린 인덱스 항목({nope:1})은 걸러진다.
  assert.deepEqual(store.list().map((i) => i.id), ["bad"]);
  assert.equal(store.load("bad"), null); // 열어 보면 손상을 확인하고 지운다
  assert.equal(store.load("wrong"), null);
  assert.equal(storage.getItem(`${NS}.conv.bad`), null);
  assert.deepEqual(store.list().map((i) => i.id), []);
  storage.setItem(`${NS}.index`, "{broken");
  assert.deepEqual(store.list(), []);
});

test("답이 오기 전에 닫힌 상담은 불러올 때 중단 안내를 붙인다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  store.save(conv("a", 1, [{ id: "1", type: "user_text", text: "질문" }, { id: "2", type: "ai_loading" }]));
  const loaded = store.load("a")!;
  const last = loaded.messages[loaded.messages.length - 1];
  assert.equal(last.type, "ai_notice");
  assert.equal(last.type === "ai_notice" && last.code, "INTERRUPTED");
});

test("저장소를 쓸 수 없으면(null) 예외 없이 동작한다", () => {
  const store = createHistoryStore(null, NS);
  assert.deepEqual(store.save(conv("a", 1)), { ok: false, reason: "unavailable" });
  assert.deepEqual(store.list(), []);
  assert.equal(store.load("a"), null);
  assert.equal(store.getActiveId(), null);
  store.remove("a");
  store.clear();
});

test("clear는 이 이름 공간의 키만 지운다(다른 키와 API 키는 유지)", () => {
  const storage = new FakeStorage();
  const store = createHistoryStore(storage, NS);
  store.save(conv("a", 1));
  store.setActiveId("a");
  storage.setItem(`${NS}.conv.orphan`, "{}");
  storage.setItem("welfareone.gemini_api_key", "secret");
  storage.setItem("welfareone.theme", "dark");
  store.clear();
  assert.deepEqual(storage.keys().sort(), ["welfareone.gemini_api_key", "welfareone.theme"]);
});

test("마지막으로 연 상담 id를 기억한다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  assert.equal(store.getActiveId(), null);
  store.setActiveId("a");
  assert.equal(store.getActiveId(), "a");
  store.remove("a");
  assert.equal(store.getActiveId(), null);
});

test("제목은 첫 질문을 공백 정리 후 30자로 자른다", () => {
  assert.equal(makeTitle([{ id: "1", type: "ai_opener" }]), "새 상담");
  assert.equal(makeTitle([{ id: "1", type: "user_text", text: "  월세가\n  부담돼요 " }]), "월세가 부담돼요");
  const long = makeTitle([{ id: "1", type: "user_text", text: "가".repeat(40) }]);
  assert.equal(long, `${"가".repeat(30)}…`);
  assert.equal(hasUserMessage([{ id: "1", type: "ai_opener" }]), false);
  assert.equal(hasUserMessage([{ id: "1", type: "user_text", text: "a" }]), true);
});

test("rename: 제목을 바꾸고 목록·본문에 반영하며 순서(updated_at)는 유지한다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  store.save(conv("a", 100));
  store.save(conv("b", 200));
  assert.equal(store.rename("a", "  내 월세   상담  "), "내 월세 상담");
  assert.equal(store.load("a")?.title, "내 월세 상담");
  assert.equal(store.load("a")?.title_edited, true);
  const items = store.list();
  assert.deepEqual(items.map((i) => i.id), ["b", "a"]); // 순서 그대로
  assert.equal(items.find((i) => i.id === "a")?.title, "내 월세 상담");
  assert.equal(items.find((i) => i.id === "a")?.updated_at, 100);
});

test("rename: 고친 제목은 같은 상담을 다시 저장해도 자동 제목으로 덮어쓰이지 않는다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  store.save(conv("a", 100));
  store.rename("a", "내 제목");
  store.save({ ...conv("a", 300), title: "월세가 부담돼요" }); // 앱이 저장할 때는 자동 제목을 넘긴다
  assert.equal(store.load("a")?.title, "내 제목");
  assert.equal(store.list()[0].title, "내 제목");
  assert.equal(store.list()[0].updated_at, 300); // 새 메시지가 있으면 순서는 올라간다
});

test("rename: 비우면 자동 제목(첫 질문)으로 되돌리고, 이후 자동 제목이 다시 갱신된다", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  store.save(conv("a", 100));
  store.rename("a", "내 제목");
  assert.equal(store.rename("a", "   "), "월세가 부담돼요");
  assert.equal(store.load("a")?.title_edited, undefined);
  store.save({ ...conv("a", 200), title: "다른 자동 제목" });
  assert.equal(store.load("a")?.title, "다른 자동 제목");
});

test("rename: 최대 40자로 자르고, 없는 상담이나 저장소 없음은 null", () => {
  const store = createHistoryStore(new FakeStorage(), NS);
  store.save(conv("a", 100));
  assert.equal(store.rename("a", "가".repeat(60)), "가".repeat(40));
  assert.equal(store.rename("none", "제목"), null);
  assert.equal(createHistoryStore(null, NS).rename("a", "제목"), null);
});

test("rename: 저장 공간이 모자라면 제목을 바꾸지 않고 null", () => {
  const probe = new FakeStorage();
  createHistoryStore(probe, NS).save(conv("a", 100));
  const size = probe.keys().reduce((sum, k) => sum + k.length + (probe.getItem(k)?.length ?? 0), 0);
  const storage = new FakeStorage(size); // 이미 가득 찬 저장소
  const store = createHistoryStore(storage, NS);
  store.save(conv("a", 100));
  assert.equal(store.rename("a", "아주 긴 새 제목 ".repeat(3)), null);
  assert.equal(store.load("a")?.title, "상담 a");
});
