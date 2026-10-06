import { USE_MOCK } from "../config";
import { createHistoryStore } from "./history";

function getLocalStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // 사생활 보호 모드 등에서는 접근 자체가 예외를 던진다
  }
}

// mock 데이터가 실제 상담 기록과 섞이지 않도록 이름 공간을 나눈다.
export const HISTORY_NAMESPACE = USE_MOCK ? "welfareone.mock.v1" : "welfareone.v1";

export const historyStore = createHistoryStore(getLocalStorage(), HISTORY_NAMESPACE);
