// BYOK: 사용자가 입력한 Gemini API 키를 이 브라우저에만 저장한다.
// - 기본은 sessionStorage(탭을 닫으면 삭제), "기억하기"를 고르면 localStorage(이 브라우저에 유지).
// - 키는 정책 검색·질문 요청의 헤더(X-Gemini-Api-Key)로만 서버에 전달된다. URL·본문·로그에 넣지 않는다.
// - 저장소 접근은 막힌 환경(사생활 보호 모드 등)에서 예외가 나므로 항상 try/catch로 감싼다.

export const API_KEY_HEADER = "X-Gemini-Api-Key";

const STORAGE_KEY = "welfareone.gemini_api_key";

export type KeyStorage = "session" | "local";

export interface StoredKey {
  key: string;
  storage: KeyStorage;
}

function area(kind: KeyStorage): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function read(kind: KeyStorage): string | null {
  try {
    return area(kind)?.getItem(STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

// 탭 단위 저장(sessionStorage)을 먼저 보고, 없으면 브라우저 단위 저장(localStorage)을 본다.
export function loadApiKey(): StoredKey | null {
  const session = read("session");
  if (session) return { key: session, storage: "session" };
  const local = read("local");
  if (local) return { key: local, storage: "local" };
  return null;
}

export const getApiKey = (): string | null => loadApiKey()?.key ?? null;

// 서버(app/api.py)의 키 형식 검사와 같은 규칙: 공백 없는 출력 가능한 ASCII 20~256자
const KEY_FORMAT = /^[\x21-\x7e]{20,256}$/;

export function validateApiKey(raw: string): string | null {
  const key = raw.trim();
  if (!key) return "API 키를 입력해 주세요.";
  if (!KEY_FORMAT.test(key)) return "API 키 형식이 올바르지 않아요. 공백 없이 복사했는지 확인해 주세요.";
  return null;
}

export function saveApiKey(raw: string, storage: KeyStorage): boolean {
  const key = raw.trim();
  try {
    clearApiKey(); // 다른 저장소에 옛 키가 남지 않게 한다
    const target = area(storage);
    if (!target) return false;
    target.setItem(STORAGE_KEY, key);
    return true;
  } catch {
    return false;
  }
}

export function clearApiKey(): void {
  for (const kind of ["session", "local"] as const) {
    try {
      area(kind)?.removeItem(STORAGE_KEY);
    } catch {
      // 저장소를 쓸 수 없으면 지울 것도 없다
    }
  }
}

// 화면에는 키 전체를 보여 주지 않는다(앞 4자리와 뒤 4자리만).
export function maskApiKey(key: string): string {
  return key.length <= 8 ? "••••" : `${key.slice(0, 4)}••••${key.slice(-4)}`;
}
