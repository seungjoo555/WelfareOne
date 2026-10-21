package com.welfareone.memberjoin.controller;

import com.welfareone.memberjoin.exception.ApiException;
import com.welfareone.memberjoin.exception.UpstreamApiException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.HashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    // 계약서 17.4 오류 코드(UNAUTHORIZED, INVALID_CREDENTIALS, USER_ALREADY_EXISTS, SESSION_NOT_FOUND, FORBIDDEN 등)
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> handleApi(ApiException e) {
        Map<String, Object> error = new HashMap<>();
        error.put("code", e.getCode());
        error.put("message", e.getMessage());
        error.put("details", null);
        return ResponseEntity.status(e.getStatus()).body(Map.of("error", error));
    }

    // FastAPI 오류(API_KEY_REQUIRED, INVALID_API_KEY, LLM_RATE_LIMITED 등)는 상태 코드와 본문을 그대로 전달한다.
    @ExceptionHandler(UpstreamApiException.class)
    public ResponseEntity<Map<String, Object>> handleUpstream(UpstreamApiException e) {
        return ResponseEntity.status(e.getStatus()).body(e.getBody());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, Object>> handleIllegalArgument(IllegalArgumentException e) {
        Map<String, Object> error = new HashMap<>();
        error.put("code", "INVALID_REQUEST");
        error.put("message", e.getMessage());
        error.put("details", null);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", error));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidationExceptions(MethodArgumentNotValidException ex) {
        Map<String, String> details = new HashMap<>();
        for (FieldError fieldError : ex.getBindingResult().getFieldErrors()) {
            details.put(fieldError.getField(), fieldError.getDefaultMessage());
        }

        Map<String, Object> error = new HashMap<>();
        error.put("code", "INVALID_REQUEST");
        error.put("message", "요청 데이터 유효성 검증에 실패했습니다.");
        error.put("details", details);

        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY).body(Map.of("error", error));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleGeneralException(Exception e) {
        Map<String, Object> error = new HashMap<>();
        error.put("code", "INTERNAL_ERROR");
        error.put("message", e.getMessage() != null ? e.getMessage() : "서버 내부 오류가 발생했습니다.");
        error.put("details", null);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", error));
    }
}

