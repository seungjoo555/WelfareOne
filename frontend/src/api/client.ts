import type { ApiErrorBody, AppErrorCode } from "../types/contract";
import { API_KEY_HEADER, getApiKey } from "../utils/apiKey";

const BASE_URL = "/api"; // vite.config.ts 프록시가 FastAPI로 전달
const TIMEOUT_MS = 30_000; // Gemini 재시도(최대 3회)를 고려해 넉넉하게

export class ApiClientError extends Error {
  constructor(
    public code: AppErrorCode,
    message: string,
    public status?: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

// options.apiKey: Gemini를 호출하는 요청(검색·질문)에만 사용자 키를 헤더로 붙인다.
export async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { apiKey?: boolean } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const apiKey = options.apiKey ? getApiKey() : null;
  try {
    const response = await fetch(BASE_URL + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { [API_KEY_HEADER]: apiKey } : {}),
        ...init.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      let body: Partial<ApiErrorBody> | null = null;
      try {
        body = (await response.json()) as Partial<ApiErrorBody>;
      } catch {
        // 오류 본문이 JSON이 아니면 기본값 사용
      }
      throw new ApiClientError(
        body?.error?.code ?? "INTERNAL_ERROR",
        body?.error?.message ?? response.statusText,
        response.status,
        body?.error?.details,
      );
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiClientError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError("TIMEOUT", "요청 시간이 초과되었습니다.");
    }
    throw new ApiClientError("NETWORK_ERROR", "서버에 연결하지 못했습니다.");
  } finally {
    clearTimeout(timer);
  }
}

export function toErrorCode(error: unknown): AppErrorCode {
  return error instanceof ApiClientError ? error.code : "INTERNAL_ERROR";
}
