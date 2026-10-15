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

    private final FastApiClientService fastApiClientService;
    private final ApiKeyService apiKeyService;
    private final HistoryService historyService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @PostMapping("/search")
    public ResponseEntity<Map<String, Object>> search(
            @PathVariable String sessionId,
            @AuthenticationPrincipal Long userId,
            @RequestBody Map<String, Object> body) {

        String question = (String) body.get("question");
        Map<String, Object> region = (Map<String, Object>) body.get("region");
        String level1 = region != null ? (String) region.get("level1") : "";
        String level2 = region != null ? (String) region.get("level2") : "";
        Integer age = body.get("age") != null ? ((Number) body.get("age")).intValue() : null;

        // 1. 사용자 복호화 API 키 확인
        String apiKey = apiKeyService.getDecryptedApiKey(userId);

        // 2. FastAPI 호출 (8000번)
        Map<String, Object> fastApiResponse = fastApiClientService.searchPolicies(question, level1, level2, age, apiKey);

        // 3. 사용자 질문 로그 저장
        historyService.saveMessage(sessionId, "user", question, null, null, null, null, null, null);

        // 4. AI 검색 결과 로그 저장
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

            historyService.saveMessage(sessionId, "assistant", content, route, intentsJson, null, candidatesJson, null, null);

            // 첫 질문이면 세션 제목을 질문 내용으로 자동 업데이트
            SessionDetailDto detail = historyService.getSessionDetail(sessionId, userId);
            if (detail.getMessages().size() <= 2) {
                String autoTitle = question.length() > 30 ? question.substring(0, 30) + "..." : question;
                historyService.updateSessionTitle(sessionId, userId, autoTitle);
            }
        } catch (Exception e) {
            log.error("AI 응답 로그 저장 실패: {}", e.getMessage());
        }

        return ResponseEntity.ok(fastApiResponse);
    }

    @PostMapping("/policies/{policyId}/ask")
    public ResponseEntity<Map<String, Object>> askPolicy(
            @PathVariable String sessionId,
            @PathVariable String policyId,
            @AuthenticationPrincipal Long userId,
            @RequestBody Map<String, Object> body) {

        String question = (String) body.get("question");
        String policyTitle = (String) body.get("policy_title");

        // 1. 사용자 복호화 API 키 확인
        String apiKey = apiKeyService.getDecryptedApiKey(userId);

        // 2. FastAPI 호출 (8000번)
        Map<String, Object> fastApiResponse = fastApiClientService.askPolicy(policyId, question, policyTitle, apiKey);

        // 3. 사용자 질문 로그 저장
        historyService.saveMessage(sessionId, "user", question, null, null, policyId, null, null, null);

        // 4. AI 답변 로그 저장
        try {
            Map<String, Object> answerObj = (Map<String, Object>) fastApiResponse.get("answer");
            String content = answerObj != null ? (String) answerObj.get("answer") : "답변을 생성하지 못했습니다.";
            String route = (String) fastApiResponse.get("route");
            String intentsJson = objectMapper.writeValueAsString(fastApiResponse.get("intents"));
            String evidenceJson = answerObj != null ? objectMapper.writeValueAsString(answerObj.get("evidence")) : null;
            String resourcesJson = answerObj != null ? objectMapper.writeValueAsString(answerObj.get("resources")) : null;

            historyService.saveMessage(sessionId, "assistant", content, route, intentsJson, policyId, null, evidenceJson, resourcesJson);
        } catch (Exception e) {
            log.error("정책 세부 답변 로그 저장 실패: {}", e.getMessage());
        }

        return ResponseEntity.ok(fastApiResponse);
    }
}

