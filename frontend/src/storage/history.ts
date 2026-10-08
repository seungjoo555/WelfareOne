// 상담 기록을 localStorage에 보관하는 계층. 화면(React)과 무관한 순수 모듈이라 저장소를 주입해 테스트한다.
//
// 저장 방식
// - 상담마다 키를 따로 둔다: `<ns>.conv.<id>`. 목록용 요약은 `<ns>.index` 한 키에 둔다.
//   (현재 상담 하나만 다시 직렬화하므로 쓰기가 가볍고, 탭이 여러 개여도 서로 덮어쓰지 않는다.)
// - 저장 전에 화면에 쓰지 않는 값(후보의 metadata·reasons)을 비우고 로딩 말풍선은 뺀다.
// - 상한: 상담 MAX_CONVERSATIONS개(오래된 것부터 삭제), 상담당 메시지 MAX_MESSAGES개.
// - 저장 공간이 모자라면(QuotaExceededError) 오래된 상담부터 지워 가며 다시 시도한다.
// - API 키는 여기에 절대 저장하지 않는다(src/utils/apiKey.ts가 따로 관리).

import type { Message } from "../types/chat";
import type { PolicyCandidate, RegionSelection } from "../types/contract";

export const MAX_CONVERSATIONS = 30;
export const MAX_MESSAGES = 200;
const TITLE_MAX_LENGTH = 30;
export const CUSTOM_TITLE_MAX_LENGTH = 40; // 사용자가 직접 고친 제목의 최대 길이
const DEFAULT_TITLE = "새 상담";

export interface StoredPolicy {
  policy_id: string;
  title: string;
}

export interface Conversation {
  id: string;
  title: string;
  title_edited?: boolean; // 사용자가 직접 고친 제목이면 true(저장할 때 자동 제목으로 덮어쓰지 않는다)
  created_at: number;
  updated_at: number;
  region: RegionSelection;
  age: number | null;
  messages: Message[];
  current_policy: StoredPolicy | null;
}

// 사이드바 목록에 쓰는 요약(메시지는 포함하지 않는다)
export interface ConversationSummary {
  id: string;
  title: string;
  title_edited?: boolean;
  updated_at: number;
  region_text: string;
  age: number | null;
}

export type SaveResult = { ok: true } | { ok: false; reason: "quota" | "unavailable" };

const newId = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const regionLabel = (region: RegionSelection): string =>
  [region.level1, region.level2].filter(Boolean).join(" ");

// 첫 질문을 제목으로 쓴다. 질문이 없으면 기본 제목.
export function makeTitle(messages: Message[]): string {
  for (const message of messages) {
    if (message.type === "user_text") {
      const text = message.text.replace(/\s+/g, " ").trim();
      if (!text) return DEFAULT_TITLE;
      return text.length > TITLE_MAX_LENGTH ? `${text.slice(0, TITLE_MAX_LENGTH)}…` : text;
    }
  }
  return DEFAULT_TITLE;
}

export const hasUserMessage = (messages: Message[]): boolean => messages.some((m) => m.type === "user_text");

// 화면에 쓰지 않는 값(metadata, reasons)을 비워 용량을 줄인다. score/distance는 작아서 그대로 둔다.
const slimCandidate = (candidate: PolicyCandidate): PolicyCandidate => ({ ...candidate, metadata: {}, reasons: [] });

function slimMessages(messages: Message[]): Message[] {
  return messages
    .filter((message) => message.type !== "ai_loading")
    .slice(-MAX_MESSAGES)
    .map((message) =>
      message.type === "ai_candidates"
        ? {
            ...message,
            local_policies: message.local_policies.map(slimCandidate),
            national_policies: message.national_policies.map(slimCandidate),
          }
        : message,
    );
}

// ---------------------------------------------------------------- 검증(저장된 값은 믿지 않는다)

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

function isMessage(value: unknown): value is Message {
  return isRecord(value) && typeof value.id === "string" && typeof value.type === "string";
}

function isConversation(value: unknown): value is Conversation {
  if (!isRecord(value) || !isRecord(value.region)) return false;
  const policy = value.current_policy;
  return (
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.created_at === "number" &&
    typeof value.updated_at === "number" &&
    typeof value.region.level1 === "string" &&
    typeof value.region.level2 === "string" &&
    (value.age === null || typeof value.age === "number") &&
    Array.isArray(value.messages) &&
    value.messages.every(isMessage) &&
    (policy === null || (isRecord(policy) && typeof policy.policy_id === "string" && typeof policy.title === "string"))
  );
}

function isSummary(value: unknown): value is ConversationSummary {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.updated_at === "number" &&
    typeof value.region_text === "string" &&
    (value.age === null || typeof value.age === "number")
  );
}

function isQuotaError(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === "QuotaExceededError" || error.name === "NS_ERROR_DOM_QUOTA_REACHED" || error.code === 22 || error.code === 1014)
  );
}

// ---------------------------------------------------------------- 저장소

export function createHistoryStore(storage: Storage | null, namespace: string) {
  const indexKey = `${namespace}.index`;
  const activeKey = `${namespace}.active`;
  const convPrefix = `${namespace}.conv.`;
  const convKey = (id: string) => convPrefix + id;

  function readJson(key: string): unknown {
    try {
      const raw = storage?.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null; // 손상된 JSON은 없는 값으로 취급한다
    }
  }

  const byNewest = (a: ConversationSummary, b: ConversationSummary) => b.updated_at - a.updated_at;

  function readIndex(): ConversationSummary[] {
    const raw = readJson(indexKey);
    return Array.isArray(raw) ? raw.filter(isSummary) : [];
  }

  function writeIndex(items: ConversationSummary[]): void {
    storage?.setItem(indexKey, JSON.stringify(items));
  }

  function removeQuietly(key: string): void {
    try {
      storage?.removeItem(key);
    } catch {
      // 지울 수 없으면 둔다
    }
  }

  // 상담 본문이 사라진 인덱스 항목은 목록에서 뺀다(다른 탭이 지웠거나 저장이 중간에 끊긴 경우).
  function list(): ConversationSummary[] {
    if (!storage) return [];
    const index = readIndex();
    const alive = index.filter((item) => {
      try {
        return storage.getItem(convKey(item.id)) !== null;
      } catch {
        return false;
      }
    });
    if (alive.length !== index.length) {
      try {
        writeIndex(alive);
      } catch {
        // 인덱스를 고치지 못해도 목록은 보여 줄 수 있다
      }
    }
    return alive.sort(byNewest);
  }

  function remove(id: string): void {
    if (!storage) return;
    removeQuietly(convKey(id));
    try {
      writeIndex(readIndex().filter((item) => item.id !== id));
    } catch {
      // 다음 list() 호출 때 정리된다
    }
    if (getActiveId() === id) removeQuietly(activeKey);
  }

  function load(id: string): Conversation | null {
    const raw = readJson(convKey(id));
    if (!isConversation(raw) || raw.id !== id) {
      if (raw !== null || storage?.getItem(convKey(id)) != null) remove(id); // 손상된 상담은 정리한다
      return null;
    }
    const last = raw.messages[raw.messages.length - 1];
    if (last && last.type === "user_text") {
      // 응답을 받기 전에 페이지가 닫힌 상담: 답이 없다는 안내를 붙인다
      return { ...raw, messages: [...raw.messages, { id: newId(), type: "ai_notice", code: "INTERRUPTED" }] };
    }
    return raw;
  }

  function save(conversation: Conversation): SaveResult {
    if (!storage) return { ok: false, reason: "unavailable" };
    // 사용자가 고친 제목은 자동 제목(첫 질문)으로 덮어쓰지 않는다.
    const previous = readJson(convKey(conversation.id));
    const keepTitle = isConversation(previous) && previous.title_edited === true;
    const stored: Conversation = {
      ...conversation,
      title: keepTitle ? previous.title : conversation.title,
      ...(keepTitle ? { title_edited: true } : {}),
      messages: slimMessages(conversation.messages),
    };
    const payload = JSON.stringify(stored);
    const summary: ConversationSummary = {
      id: stored.id,
      title: stored.title,
      ...(stored.title_edited ? { title_edited: true } : {}),
      updated_at: stored.updated_at,
      region_text: regionLabel(stored.region),
      age: stored.age,
    };

    // 공간이 모자라면 (저장 중인 상담을 뺀) 가장 오래된 상담부터 지우고 다시 시도한다.
    for (let attempt = 0; attempt <= MAX_CONVERSATIONS + 1; attempt++) {
      try {
        storage.setItem(convKey(stored.id), payload);
        const index = [summary, ...readIndex().filter((item) => item.id !== stored.id)].sort(byNewest);
        for (const dropped of index.splice(MAX_CONVERSATIONS)) removeQuietly(convKey(dropped.id));
        writeIndex(index);
        return { ok: true };
      } catch (error) {
        if (!isQuotaError(error)) return { ok: false, reason: "unavailable" };
        const victim = readIndex()
          .filter((item) => item.id !== stored.id)
          .sort(byNewest)
          .pop();
        if (!victim) {
          removeQuietly(convKey(stored.id));
          return { ok: false, reason: "quota" };
        }
        removeQuietly(convKey(victim.id));
        try {
          writeIndex(readIndex().filter((item) => item.id !== victim.id));
        } catch {
          // 다음 반복에서 다시 정리한다
        }
      }
    }
    return { ok: false, reason: "quota" };
  }

  // 상담 제목을 바꾼다. 공백을 정리해 최대 CUSTOM_TITLE_MAX_LENGTH자로 자르고, 비우면 자동 제목(첫 질문)으로 되돌린다.
  // updated_at은 그대로 둬서 목록 순서가 바뀌지 않는다. 성공하면 새 제목, 상담이 없거나 저장할 수 없으면 null.
  function rename(id: string, title: string): string | null {
    if (!storage) return null;
    const raw = readJson(convKey(id));
    if (!isConversation(raw) || raw.id !== id) return null;
    const cleaned = title.replace(/\s+/g, " ").trim().slice(0, CUSTOM_TITLE_MAX_LENGTH);
    const edited = cleaned !== "";
    const nextTitle = edited ? cleaned : makeTitle(raw.messages);
    const { title_edited: _previous, ...rest } = raw;
    const next: Conversation = { ...rest, title: nextTitle, ...(edited ? { title_edited: true } : {}) };
    try {
      storage.setItem(convKey(id), JSON.stringify(next));
      const index = readIndex().map((item) => {
        if (item.id !== id) return item;
        const { title_edited: _old, ...summary } = item;
        return { ...summary, title: nextTitle, ...(edited ? { title_edited: true } : {}) };
      });
      writeIndex(index);
    } catch {
      return null; // 저장 공간 문제 등: 제목은 그대로 둔다
    }
    return nextTitle;
  }

  function clear(): void {
    if (!storage) return;
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key && (key.startsWith(convPrefix) || key === indexKey || key === activeKey)) keys.push(key);
    }
    keys.forEach(removeQuietly);
  }

  function getActiveId(): string | null {
    try {
      return storage?.getItem(activeKey) || null;
    } catch {
      return null;
    }
  }

  function setActiveId(id: string): void {
    try {
      storage?.setItem(activeKey, id);
    } catch {
      // 마지막 상담 복원만 안 될 뿐이다
    }
  }

  return { list, load, save, rename, remove, clear, getActiveId, setActiveId, namespace };
}

export type HistoryStore = ReturnType<typeof createHistoryStore>;
