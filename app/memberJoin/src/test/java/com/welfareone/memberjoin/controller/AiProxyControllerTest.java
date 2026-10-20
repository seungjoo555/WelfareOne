package com.welfareone.memberjoin.controller;

import com.welfareone.memberjoin.dto.ChatMessageDto;
import com.welfareone.memberjoin.dto.SessionDetailDto;
import com.welfareone.memberjoin.exception.UpstreamApiException;
import com.welfareone.memberjoin.service.ApiKeyService;
import com.welfareone.memberjoin.service.FastApiClientService;
import com.welfareone.memberjoin.service.HistoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** AI 중계: 세션 소유자 검증이 먼저, 키 우선순위, 대문자 발신자 저장, 기록 실패가 응답을 막지 않음. */
class AiProxyControllerTest {

    private FastApiClientService fastApi;
    private ApiKeyService apiKeys;
    private HistoryService history;
    private AiProxyController controller;

    private final Map<String, Object> searchBody = Map.of(
            "question", "월세가 부담돼요",
            "region", Map.of("level1", "서울특별시", "level2", "관악구"),
            "age", 24);

    private final Map<String, Object> fastApiSearchResponse = Map.of(
            "analysis", Map.of("route", "situation_search", "intents", List.of("policy_search")),
            "local_policies", List.of(Map.of("policy_id", "local:1")),
            "national_policies", List.of());

    @BeforeEach
    void setUp() {
        fastApi = mock(FastApiClientService.class);
        apiKeys = mock(ApiKeyService.class);
        history = mock(HistoryService.class);
        controller = new AiProxyController(fastApi, apiKeys, history);
        when(history.getSessionDetail(anyString(), any())).thenReturn(
                SessionDetailDto.builder().messages(List.of(ChatMessageDto.builder().build(), ChatMessageDto.builder().build(), ChatMessageDto.builder().build())).build());
    }

    @Test
    void foreignSessionIsRejectedBeforeAnyAiCallOrWrite() {
        doThrow(new IllegalArgumentException("접근 권한이 없습니다.")).when(history).assertSessionOwner("s1", 7L);

        assertThatThrownBy(() -> controller.search("s1", 7L, null, searchBody)).isInstanceOf(IllegalArgumentException.class);

        verify(fastApi, never()).searchPolicies(any(), any(), any(), any(), any());
        verify(history, never()).saveMessage(any(), any(), any(), any(), any(), any(), any(), any(), any());
    }

    @Test
    void messagesAreSavedWithUpperCaseSenders() {
        when(fastApi.searchPolicies(any(), any(), any(), any(), any())).thenReturn(fastApiSearchResponse);

        ResponseEntity<Map<String, Object>> response = controller.search("s1", 7L, null, searchBody);

        assertThat(response.getBody()).isEqualTo(fastApiSearchResponse);
        verify(history).saveMessage(eq("s1"), eq("USER"), eq("월세가 부담돼요"), isNull(), isNull(), isNull(), isNull(), isNull(), isNull());
        verify(history).saveMessage(eq("s1"), eq("ASSISTANT"), anyString(), eq("situation_search"), anyString(), isNull(), anyString(), isNull(), isNull());
    }

    @Test
    void keyFromTheRequestWinsOverTheStoredKey() {
        when(apiKeys.getDecryptedApiKey(7L)).thenReturn("stored-key");
        when(fastApi.searchPolicies(any(), any(), any(), any(), any())).thenReturn(fastApiSearchResponse);

        controller.search("s1", 7L, " browser-key ", searchBody);

        verify(fastApi).searchPolicies("월세가 부담돼요", "서울특별시", "관악구", 24, "browser-key");
    }

    @Test
    void storedKeyIsUsedWhenTheRequestHasNone() {
        when(apiKeys.getDecryptedApiKey(7L)).thenReturn("stored-key");
        when(fastApi.searchPolicies(any(), any(), any(), any(), any())).thenReturn(fastApiSearchResponse);

        controller.search("s1", 7L, null, searchBody);

        verify(fastApi).searchPolicies("월세가 부담돼요", "서울특별시", "관악구", 24, "stored-key");
    }

    @Test
    void noKeyAtAllSendsNullSoFastApiCanUseTheServerModel() {
        when(apiKeys.getDecryptedApiKey(7L)).thenReturn(null);
        when(fastApi.searchPolicies(any(), any(), any(), any(), any())).thenReturn(fastApiSearchResponse);

        controller.search("s1", 7L, "  ", searchBody);

        verify(fastApi).searchPolicies("월세가 부담돼요", "서울특별시", "관악구", 24, null);
    }

    @Test
    void historyFailureDoesNotBlockTheAiResponse() {
        when(fastApi.searchPolicies(any(), any(), any(), any(), any())).thenReturn(fastApiSearchResponse);
        when(history.saveMessage(any(), any(), any(), any(), any(), any(), any(), any(), any())).thenThrow(new RuntimeException("ORA-02290"));

        ResponseEntity<Map<String, Object>> response = controller.search("s1", 7L, null, searchBody);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo(fastApiSearchResponse);
    }

    @Test
    void fastApiErrorIsNotSwallowedAndNothingIsSaved() {
        when(fastApi.searchPolicies(any(), any(), any(), any(), any()))
                .thenThrow(new UpstreamApiException(401, Map.of("error", Map.of("code", "API_KEY_REQUIRED"))));

        assertThatThrownBy(() -> controller.search("s1", 7L, null, searchBody)).isInstanceOf(UpstreamApiException.class);

        verify(history, never()).saveMessage(any(), any(), any(), any(), any(), any(), any(), any(), any());
    }

    @Test
    void askForwardsIntentAndPolicyAndSavesAnswerMetadata() {
        Map<String, Object> answer = Map.of(
                "route", "current_policy_question",
                "intents", List.of("eligibility"),
                "answer", Map.of("answer", "대상은 19~39세입니다.", "evidence", List.of("19~39세"), "resources", List.of()));
        when(fastApi.askPolicy(any(), any(), any(), any(), any())).thenReturn(answer);

        controller.askPolicy("s1", "local:WLF1", 7L, null, Map.of("question", "대상", "policy_title", "정책", "intent", "eligibility"));

        verify(fastApi).askPolicy("local:WLF1", "대상", "정책", "eligibility", null);
        verify(history).saveMessage(eq("s1"), eq("USER"), eq("대상"), isNull(), isNull(), eq("local:WLF1"), isNull(), isNull(), isNull());
        verify(history).saveMessage(eq("s1"), eq("ASSISTANT"), eq("대상은 19~39세입니다."), eq("current_policy_question"), anyString(), eq("local:WLF1"), isNull(), anyString(), anyString());
    }
}
