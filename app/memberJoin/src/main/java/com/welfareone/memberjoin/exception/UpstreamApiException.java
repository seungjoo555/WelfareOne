package com.welfareone.memberjoin.exception;

import java.util.Map;

/**
 * FastAPI(AI 서버)가 돌려준 오류를 그대로 프론트에 전달하기 위한 예외.
 * 계약서 17장 오류 코드(API_KEY_REQUIRED, INVALID_API_KEY, LLM_RATE_LIMITED 등)가 사라지지 않게 상태 코드와 본문을 보존한다.
 */
public class UpstreamApiException extends RuntimeException {

    private final int status;
    private final Map<String, Object> body;

    public UpstreamApiException(int status, Map<String, Object> body) {
        super("AI 서버 오류 " + status);
        this.status = status;
        this.body = body;
    }

    public int getStatus() {
        return status;
    }

    public Map<String, Object> getBody() {
        return body;
    }

    /** 연결 실패·시간 초과처럼 FastAPI가 응답 본문을 주지 못한 경우를 계약서 오류 형식으로 만든다. */
    public static UpstreamApiException unavailable(int status, String message) {
        return new UpstreamApiException(status, Map.of("error", Map.of(
                "code", "INTERNAL_ERROR",
                "message", message,
                "details", Map.of())));
    }
}
