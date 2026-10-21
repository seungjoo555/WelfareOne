package com.welfareone.memberjoin.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.welfareone.memberjoin.dto.SessionDetailDto;
import com.welfareone.memberjoin.service.ApiKeyService;
import com.welfareone.memberjoin.service.FastApiClientService;
import com.welfareone.memberjoin.service.HistoryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/ai/sessions/{sessionId}")
@RequiredArgsConstructor
public class AiProxyController {

    // DB 제약(CK_MESSAGES_SENDER)이 허용하는 값은 대문자 USER / ASSISTANT 뿐이다.
    static final String SENDER_USER = "USER";
    static final String SENDER_ASSISTANT = "ASSISTANT";
    static final String API_KEY_HEADER = "X-Gemini-Api-Key";

    private final FastApiClientService fastApiClientService;
    private final ApiKeyService apiKeyService;
    private final HistoryService historyService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @PostMapping("/search")
    @SuppressWarnings("unchecked")
    public ResponseEntity<Map<String, Object>> search(
            @PathVariable String sessionId,
            @AuthenticationPrincipal Long userId,
            @RequestHeader(value = API_KEY_HEADER, required = false) String browserApiKey,
            @RequestBody Map<String, Object> body) {

        // 0. 내 세션인지 먼저 확인한다(남의 세션 ID로 AI를 부르거나 기록을 쓰지 못하게)
        historyService.assertSessionOwner(sessionId, userId);

        String question = (String) body.get("question");
        Map<String, Object> region = (Map<String, Object>) body.get("region");
        String level1 = region != null ? (String) region.get("level1") : "";
        String level2 = region != null ? (String) region.get("level2") : "";
        Integer age = body.get("age") != null ? ((Number) body.get("age")).intValue() : null;

        // 1. 사용할 Gemini 키: 이 요청에 직접 실린 키 > 서버에 저장된 키 > 없음(FastAPI가 서버 기본 AI 또는 오류로 처리)
        String apiKey = resolveApiKey(userId, browserApiKey);

        // 2. FastAPI 호출. 오류는 코드·상태를 그대로 프론트에 전달한다(UpstreamApiException).
        Map<String, Object> fastApiResponse = fastApiClientService.searchPolicies(question, level1, level2, age, apiKey);

        // 3. 기록 저장은 부가 기능이므로 실패해도 AI 응답은 돌려준다.
        saveQuietly(sessionId, SENDER_USER, question, null, null, null, null, null, null);
        try {
            Map<String, Object> analysis = (Map<String, Object>) fastApiResponse.get("analysis");
            String route = analysis != null ? (String) analysis.get("route") : "situation_search";
            String intentsJson = analysis != null ? objectMapper.writeValueAsString(analysis.get("intents")) : "[]";
            List<?> localPolicies = (List<?>) fastApiResponse.get("local_policies");
            List<?> nationalPolicies = (List<?>) fastApiResponse.get("national_policies");

            String candidatesJson = objectMapper.writeValueAsString(Map.of(
                    "local_policies", localPolicies != null ? localPolicies : List.of(),
                    "national_policies", nationalPolicies != null ? nationalPolicies : List.of()
            ));
            String content = "조건에 부합하는 복지정책 후보 "
                    + ((localPolicies != null ? localPolicies.size() : 0) + (nationalPolicies != null ? nationalPolicies.size() : 0))
                    + "건을 찾았습니다.";
            saveQuietly(sessionId, SENDER_ASSISTANT, content, route, intentsJson, null, candidatesJson, null, null);

            // 첫 질문이면 세션 제목을 질문 내용으로 자동 업데이트
            SessionDetailDto detail = historyService.getSessionDetail(sessionId, userId);
            if (detail.getMessages().size() <= 2) {
                String autoTitle = question.length() > 30 ? question.substring(0, 30) + "..." : question;
                historyService.updateSessionTitle(sessionId, userId, autoTitle);
            }
        } catch (Exception e) {
            log.error("AI 응답 기록 저장 실패: {}", e.getMessage());
        }

        return ResponseEntity.ok(fastApiResponse);
    }

    @PostMapping("/policies/{policyId}/ask")
    @SuppressWarnings("unchecked")
    public ResponseEntity<Map<String, Object>> askPolicy(
            @PathVariable String sessionId,
            @PathVariable String policyId,
            @AuthenticationPrincipal Long userId,
            @RequestHeader(value = API_KEY_HEADER, required = false) String browserApiKey,
            @RequestBody Map<String, Object> body) {

        historyService.assertSessionOwner(sessionId, userId);

        String question = (String) body.get("question");
        String policyTitle = (String) body.get("policy_title");
        String intent = (String) body.get("intent");  // "자주 묻는 질문" 버튼 유형(없으면 null)

        String apiKey = resolveApiKey(userId, browserApiKey);

        Map<String, Object> fastApiResponse = fastApiClientService.askPolicy(policyId, question, policyTitle, intent, apiKey);

        saveQuietly(sessionId, SENDER_USER, question, null, null, policyId, null, null, null);
        try {
            Map<String, Object> answerObj = (Map<String, Object>) fastApiResponse.get("answer");
            String content = answerObj != null ? (String) answerObj.get("answer") : "답변을 생성하지 못했습니다.";
            String route = (String) fastApiResponse.get("route");
            String intentsJson = objectMapper.writeValueAsString(fastApiResponse.get("intents"));
            String evidenceJson = answerObj != null ? objectMapper.writeValueAsString(answerObj.get("evidence")) : null;
            String resourcesJson = answerObj != null ? objectMapper.writeValueAsString(answerObj.get("resources")) : null;
            saveQuietly(sessionId, SENDER_ASSISTANT, content, route, intentsJson, policyId, null, evidenceJson, resourcesJson);
        } catch (Exception e) {
            log.error("정책 답변 기록 저장 실패: {}", e.getMessage());
        }

        return ResponseEntity.ok(fastApiResponse);
    }

    /** 이 요청에 직접 실린 키가 있으면 그것을, 없으면 저장된 키를 쓴다. 둘 다 없으면 null. */
    private String resolveApiKey(Long userId, String browserApiKey) {
        if (browserApiKey != null && !browserApiKey.isBlank()) {
            return browserApiKey.trim();
        }
        return apiKeyService.getDecryptedApiKey(userId);
    }

    private void saveQuietly(String sessionId, String senderType, String content, String route, String intentsJson,
                             String policyId, String candidatesJson, String evidenceJson, String resourcesJson) {
        try {
            historyService.saveMessage(sessionId, senderType, content, route, intentsJson, policyId, candidatesJson, evidenceJson, resourcesJson);
        } catch (Exception e) {
            log.error("상담 기록 저장 실패({}): {}", senderType, e.getMessage());
        }
    }
}
