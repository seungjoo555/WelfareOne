package com.welfareone.memberjoin.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.welfareone.memberjoin.exception.UpstreamApiException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import java.net.SocketTimeoutException;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;

@Slf4j
@Service
@RequiredArgsConstructor
public class FastApiClientService {

    static final String API_KEY_HEADER = "X-Gemini-Api-Key";

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
        return execute(spec, apiKey, "정책 검색");
    }

    /** intent: 화면의 "자주 묻는 질문" 버튼 유형(없으면 null). FastAPI가 질문 분석을 건너뛰고 유형별 답변을 만든다. */
    public Map<String, Object> askPolicy(String policyId, String question, String policyTitle, String intent, String apiKey) {
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("question", question);
        requestBody.put("policy_title", policyTitle);
        if (intent != null && !intent.isBlank()) {
            requestBody.put("intent", intent);
        }

        RestClient.RequestHeadersSpec<?> spec = fastApiRestClient.post()
                .uri("/policies/{policyId}/ask", policyId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestBody);
        return execute(spec, apiKey, "정책 답변 생성");
    }

    private Map<String, Object> execute(RestClient.RequestHeadersSpec<?> spec, String apiKey, String what) {
        RestClient.RequestHeadersSpec<?> request = spec;
        if (apiKey != null && !apiKey.isBlank()) {
            request = request.header(API_KEY_HEADER, apiKey);
        }
        final RestClient.RequestHeadersSpec<?> finalRequest = request;
        return call(() -> finalRequest.retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {}), what);
    }

    /** FastAPI 오류는 상태 코드와 error 본문을 그대로 전달하고, 연결 실패·시간 초과는 계약서 오류 형식으로 바꾼다. */
    <T> T call(Supplier<T> action, String what) {
        try {
            return action.get();
        } catch (RestClientResponseException e) {
            log.warn("FastAPI {} 오류 응답: {}", what, e.getStatusCode().value());
            throw new UpstreamApiException(e.getStatusCode().value(), parseErrorBody(e));
        } catch (ResourceAccessException e) {
            boolean timeout = e.getCause() instanceof SocketTimeoutException;
            log.error("FastAPI {} 호출 실패({}): {}", what, timeout ? "시간 초과" : "연결 실패", e.getMessage());
            throw UpstreamApiException.unavailable(timeout ? 504 : 503,
                    timeout ? "AI 서버 응답 시간이 초과되었습니다." : "AI 서버에 연결하지 못했습니다.");
        }
    }

    private Map<String, Object> parseErrorBody(RestClientResponseException e) {
        try {
            Map<String, Object> body = objectMapper.readValue(e.getResponseBodyAsString(), new TypeReference<Map<String, Object>>() {});
            if (body.get("error") instanceof Map) {
                return body;
            }
        } catch (Exception ignored) {
            // 본문이 JSON이 아니면 아래 기본 형식을 쓴다
        }
        return Map.of("error", Map.of(
                "code", "INTERNAL_ERROR",
                "message", "AI 서버가 오류를 반환했습니다.",
                "details", Map.of()));
    }
}
