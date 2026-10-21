import assert from "node:assert/strict";
import test from "node:test";
import type { ServerChatMessage, ServerSessionDetail } from "../src/api/history";
import { conversationFromServer, serverSessionIdOf } from "../src/utils/serverHistory";

const policy = (id: string, title: string) => ({
  policy_id: id,
  title,
  region_text: "서울특별시 관악구",
  score: 1,
  distance: 0.3,
  scope: "시군구",
  summary: "요약",
  metadata: {},
  reasons: [],
  reranker_score: null,
});

const msg = (partial: Partial<ServerChatMessage> & Pick<ServerChatMessage, "message_id" | "sender_type" | "content">): ServerChatMessage => ({
  session_id: "s1",
  created_at: "2026-10-21T00:00:00Z",
  ...partial,
});

const detail = (messages: ServerChatMessage[]): ServerSessionDetail => ({
  session: {
    session_id: "s1",
    title: "월세 상담",
    region_level1: "서울특별시",
    region_level2: "관악구",
    age: 24,
    created_at: "2026-10-21T00:00:00Z",
    updated_at: "2026-10-21T00:10:00Z",
  },
  messages,
});

test("상담 정보와 지역·나이·제목을 그대로 옮기고 첫 줄에 안내 말풍선을 둔다", () => {
  const conversation = conversationFromServer(detail([]));
  assert.equal(conversation.id, "server-s1");
  assert.equal(conversation.title, "월세 상담");
  assert.deepEqual(conversation.region, { level1: "서울특별시", level2: "관악구" });
  assert.equal(conversation.age, 24);
  assert.equal(conversation.messages[0].type, "ai_opener");
});

test("질문은 user_text, 후보 응답은 ai_candidates로 복원한다", () => {
  const candidates = JSON.stringify({ local_policies: [policy("local:1", "청년 월세 지원")], national_policies: [] });
  const conversation = conversationFromServer(
    detail([
      msg({ message_id: "m1", sender_type: "user", content: "월세가 부담돼요" }),
      msg({ message_id: "m2", sender_type: "assistant", content: "후보 1건", route: "situation_search", intents_json: '["policy_search"]', candidates_json: candidates }),
    ]),
  );
  const [, question, answer] = conversation.messages;
  assert.deepEqual(question, { id: "m1", type: "user_text", text: "월세가 부담돼요" });
  assert.equal(answer.type, "ai_candidates");
  if (answer.type === "ai_candidates") {
    assert.equal(answer.local_policies[0].title, "청년 월세 지원");
    assert.deepEqual(answer.analysis.intents, ["policy_search"]);
    assert.equal(answer.analysis.route, "situation_search");
  }
});

test("정책 답변은 ai_answer로 복원하고 근거·자료 링크를 되살린다", () => {
  const conversation = conversationFromServer(
    detail([
      msg({
        message_id: "m3",
        sender_type: "assistant",
        content: "19~39세 대상입니다.",
        route: "current_policy_question",
        selected_policy_id: "local:1",
        evidence_json: '["19~39세"]',
        resources_json: '[{"label":"신청서","resource_type":"attachment","url":"https://example.com/a.pdf"}]',
      }),
    ]),
  );
  const answer = conversation.messages[1];
  assert.equal(answer.type, "ai_answer");
  if (answer.type === "ai_answer") {
    assert.equal(answer.answer.policy_id, "local:1");
    assert.deepEqual(answer.answer.evidence, ["19~39세"]);
    assert.equal(answer.answer.resources[0].url, "https://example.com/a.pdf");
  }
});

test("깨진 JSON은 오류 없이 빈 값으로 처리한다", () => {
  const conversation = conversationFromServer(
    detail([msg({ message_id: "m4", sender_type: "assistant", content: "답", selected_policy_id: "local:1", evidence_json: "{깨짐", resources_json: "[" })]),
  );
  const answer = conversation.messages[1];
  assert.equal(answer.type, "ai_answer");
  if (answer.type === "ai_answer") {
    assert.deepEqual(answer.answer.evidence, []);
    assert.deepEqual(answer.answer.resources, []);
  }
});

test("후보도 정책도 없는 응답은 일반 텍스트로 복원한다", () => {
  const conversation = conversationFromServer(detail([msg({ message_id: "m5", sender_type: "assistant", content: "안내 문구" })]));
  assert.deepEqual(conversation.messages[1], { id: "m5", type: "ai_text", text: "안내 문구" });
});

test("마지막에 고른 정책을 후보 목록에서 제목을 찾아 현재 정책으로 복원한다", () => {
  const candidates = JSON.stringify({ local_policies: [policy("local:1", "청년 월세 지원")], national_policies: [] });
  const conversation = conversationFromServer(
    detail([
      msg({ message_id: "m1", sender_type: "assistant", content: "후보", candidates_json: candidates }),
      msg({ message_id: "m2", sender_type: "user", content: "대상은?", selected_policy_id: "local:1" }),
    ]),
  );
  assert.deepEqual(conversation.current_policy, { policy_id: "local:1", title: "청년 월세 지원" });
});

test("제목을 알 수 없는 정책은 현재 정책을 비워 둔다", () => {
  const conversation = conversationFromServer(detail([msg({ message_id: "m2", sender_type: "user", content: "q", selected_policy_id: "local:9" })]));
  assert.equal(conversation.current_policy, null);
});

test("serverSessionIdOf: 서버에서 온 대화 ID만 세션 ID로 돌려준다", () => {
  assert.equal(serverSessionIdOf("server-abc"), "abc");
  assert.equal(serverSessionIdOf("local-uuid"), null);
  assert.equal(serverSessionIdOf(null), null);
});
