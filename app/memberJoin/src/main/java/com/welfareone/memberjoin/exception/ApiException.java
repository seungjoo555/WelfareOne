package com.welfareone.memberjoin.exception;

import org.springframework.http.HttpStatus;

/**
 * 계약서 17.4의 오류 코드와 HTTP 상태를 함께 담는 예외.
 * GlobalExceptionHandler가 {"error": {"code", "message", "details"}} 형식으로 응답한다.
 */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public static ApiException unauthorized() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "로그인이 필요하거나 유효하지 않은 토큰입니다.");
    }

    public static ApiException forbidden() {
        return new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", "접근 권한이 없습니다.");
    }

    public static ApiException invalidCredentials() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.");
    }

    public static ApiException userAlreadyExists() {
        return new ApiException(HttpStatus.CONFLICT, "USER_ALREADY_EXISTS", "이미 가입된 이메일 계정입니다.");
    }

    public static ApiException sessionNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "SESSION_NOT_FOUND", "상담 세션을 찾을 수 없습니다.");
    }

    public static ApiException tooManyLoginAttempts() {
        return new ApiException(HttpStatus.TOO_MANY_REQUESTS, "TOO_MANY_LOGIN_ATTEMPTS", "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.");
    }
}
