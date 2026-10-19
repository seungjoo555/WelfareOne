package com.welfareone.memberjoin.controller;

import com.welfareone.memberjoin.dto.ApiKeyRequest;
import com.welfareone.memberjoin.dto.ApiKeyStatusResponse;
import com.welfareone.memberjoin.service.ApiKeyService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/users/api-key")
@RequiredArgsConstructor
public class ApiKeyController {

    private final ApiKeyService apiKeyService;

    @PutMapping
    public ResponseEntity<ApiKeyStatusResponse> saveApiKey(
            @AuthenticationPrincipal Long userId,
            @Valid @RequestBody ApiKeyRequest request) {
        ApiKeyStatusResponse response = apiKeyService.saveApiKey(userId, request.getApiKey());
        return ResponseEntity.ok(response);
    }

    @GetMapping("/status")
    public ResponseEntity<ApiKeyStatusResponse> getApiKeyStatus(@AuthenticationPrincipal Long userId) {
        ApiKeyStatusResponse response = apiKeyService.getApiKeyStatus(userId);
        return ResponseEntity.ok(response);
    }

    @DeleteMapping
    public ResponseEntity<Map<String, String>> deleteApiKey(@AuthenticationPrincipal Long userId) {
        apiKeyService.deleteApiKey(userId);
        return ResponseEntity.ok(Map.of("message", "API 키가 삭제되었습니다."));
    }
}

