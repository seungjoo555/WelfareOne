import type { ServerChatMessage, ServerSessionDetail } from "../api/history";
import type { Conversation } from "../storage/history";
import type { Message } from "../types/chat";
import type { AnswerResult, Intent, PolicyCandidate, PolicyResource, Route } from "../types/contract";

// 서버(Oracle)에 저장된 상담을 화면 상태(Conversation)로 바꾼다.
// 서버는 후보·근거·자료 링크를 JSON 문자열로 저장하므로 읽을 때 파싱하고, 깨진 값은 건너뛴다.

export const SERVER_CONVERSATION_PREFIX = "server-";

function parseJson<T>(text: string | undefined | null, fallback: T): T {
  if (!text) return fallback;
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

interface StoredCandidates {
  local_policies?: PolicyCandidate[];
  national_policies?: PolicyCandidate[];
}

function toMessage(message: ServerChatMessage): Message {
  const id = message.message_id;
  if (message.sender_type !== "assistant") {
    return { id, type: "user_text", text: message.content };
  }
  const candidates = parseJson<StoredCandidates | null>(message.candidates_json, null);
  if (candidates && (candidates.local_policies || candidates.national_policies)) {
    return {
      id,
      type: "ai_candidates",
      // 검색어는 서버에 저장하지 않으므로 비워 둔다(화면은 값이 있을 때만 의도를 표시한다)
      analysis: {
        route: (message.route as Route) ?? "situation_search",
        intents: parseJson<Intent[]>(message.intents_json, []),
        search_query: "",
      },
      local_policies: candidates.local_policies ?? [],
      national_policies: candidates.national_policies ?? [],
    };
  }
  if (message.selected_policy_id) {
    const answer: AnswerResult = {
      answer: message.content,
      policy_id: message.selected_policy_id,
      used_sections: [],
      evidence: parseJson<string[]>(message.evidence_json, []),
      resources: parseJson<PolicyResource[]>(message.resources_json, []),
      grounded: true,
    };
    return { id, type: "ai_answer", answer };
  }
  return { id, type: "ai_text", text: message.content };
}

export function conversationFromServer(detail: ServerSessionDetail): Conversation {
  const { session } = detail;
  const messages: Message[] = [{ id: `opener-${session.session_id}`, type: "ai_opener" }, ...detail.messages.map(toMessage)];

  // 마지막으로 선택한 정책을 현재 정책으로 복원한다(제목은 저장돼 있지 않아 후보 목록에서 찾는다).
  let current: Conversation["current_policy"] = null;
  const lastPolicyId = [...detail.messages].reverse().find((m) => m.selected_policy_id)?.selected_policy_id;
  if (lastPolicyId) {
    const known = messages
      .flatMap((m) => (m.type === "ai_candidates" ? [...m.local_policies, ...m.national_policies] : []))
      .find((p) => p.policy_id === lastPolicyId);
    if (known) current = { policy_id: known.policy_id, title: known.title };
  }

  const created = Date.parse(session.created_at);
  const updated = Date.parse(session.updated_at);
  return {
    id: `${SERVER_CONVERSATION_PREFIX}${session.session_id}`,
    title: session.title,
    created_at: Number.isNaN(created) ? Date.now() : created,
    updated_at: Number.isNaN(updated) ? Date.now() : updated,
    region: { level1: session.region_level1, level2: session.region_level2 || "" },
    age: session.age,
    messages,
    current_policy: current,
  };
}

/** `server-<세션 ID>` 형태의 대화 ID에서 서버 세션 ID를 꺼낸다. 서버에서 온 대화가 아니면 null. */
export function serverSessionIdOf(conversationId: string | null): string | null {
  return conversationId && conversationId.startsWith(SERVER_CONVERSATION_PREFIX)
    ? conversationId.slice(SERVER_CONVERSATION_PREFIX.length)
    : null;
}
