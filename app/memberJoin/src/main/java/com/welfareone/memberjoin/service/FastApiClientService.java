package com.welfareone.memberjoin.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class FastApiClientService {

    private final RestClient fastApiRestClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public Map<String, Object> searchPolicies(String question, String regionLevel1, String regionLevel2, Integer age, String apiKey) {
        Map<String, Object> regionBody = new HashMap<>();
        regionBody.put("level1", regionLevel1 != null ? regionLevel1 : "");
        regionBody.put("level2", regionLevel2 != null ? regionLevel2 : "");

        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("question", question);
        requestBody.put("region", regionBody);
        requestBody.put("age", age);

        RestClient.RequestHeadersSpec<?> spec = fastApiRestClient.post()
                .uri("/policies/search")
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestBody);

        if (apiKey != null && !apiKey.isBlank()) {
            spec.header("X-Gemini-Api-Key", apiKey);
        }

        try {
            return spec.retrieve().body(Map.class);
        } catch (Exception e) {
            log.error("FastAPI 정책 검색 실패: {}", e.getMessage());
            throw new RuntimeException("AI 정책 검색 엔진 호출 중 문제가 발생했습니다: " + e.getMessage(), e);
        }
    }

    public Map<String, Object> askPolicy(String policyId, String question, String policyTitle, String apiKey) {
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("question", question);
        requestBody.put("policy_title", policyTitle);

        RestClient.RequestHeadersSpec<?> spec = fastApiRestClient.post()
                .uri("/policies/{policyId}/ask", policyId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestBody);

        if (apiKey != null && !apiKey.isBlank()) {
            spec.header("X-Gemini-Api-Key", apiKey);
        }

        try {
            return spec.retrieve().body(Map.class);
        } catch (Exception e) {
            log.error("FastAPI 정책 답변 생성 실패: {}", e.getMessage());
            throw new RuntimeException("AI 정책 답변 생성 호출 중 문제가 발생했습니다: " + e.getMessage(), e);
        }
    }
}

