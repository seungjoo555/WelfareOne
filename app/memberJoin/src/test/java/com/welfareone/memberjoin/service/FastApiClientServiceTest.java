package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.exception.UpstreamApiException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.headerDoesNotExist;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/** FastAPI 중계: 키 헤더, intent 전달, 오류 코드 보존(계약서 17장), 연결 실패·시간 초과 처리. */
class FastApiClientServiceTest {

    private static final String BASE = "http://fastapi.test";

    private MockRestServiceServer server;
    private FastApiClientService service;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl(BASE);
        server = MockRestServiceServer.bindTo(builder).build();
        service = new FastApiClientService(builder.build());
    }

    @Test
    void searchSendsRegionAgeAndKeyHeaderAndReturnsBody() {
        server.expect(requestTo(BASE + "/policies/search"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Gemini-Api-Key", "AIza-user-key"))
                .andExpect(content().json("{\"question\":\"월세\",\"region\":{\"level1\":\"서울특별시\",\"level2\":\"관악구\"},\"age\":24}"))
                .andRespond(withSuccess("{\"local_policies\":[],\"national_policies\":[]}", MediaType.APPLICATION_JSON));

        Map<String, Object> result = service.searchPolicies("월세", "서울특별시", "관악구", 24, "AIza-user-key");

        assertThat(result).containsKeys("local_policies", "national_policies");
        server.verify();
    }

    @Test
    void noKeyMeansNoKeyHeader() {
        server.expect(requestTo(BASE + "/policies/search"))
                .andExpect(headerDoesNotExist("X-Gemini-Api-Key"))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        service.searchPolicies("월세", "서울특별시", "", null, null);

        server.verify();
    }

    @Test
    void askForwardsIntentWhenGiven() {
        server.expect(requestTo(BASE + "/policies/local%3AWLF1/ask"))
                .andExpect(content().json("{\"question\":\"대상\",\"policy_title\":\"정책\",\"intent\":\"eligibility\"}"))
                .andRespond(withSuccess("{\"route\":\"current_policy_question\"}", MediaType.APPLICATION_JSON));

        Map<String, Object> result = service.askPolicy("local:WLF1", "대상", "정책", "eligibility", null);

        assertThat(result).containsEntry("route", "current_policy_question");
        server.verify();
    }

    @Test
    void askOmitsIntentWhenBlank() {
        server.expect(requestTo(BASE + "/policies/local%3AWLF1/ask"))
                .andExpect(request -> assertThat(request.getBody().toString()).doesNotContain("intent"))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        service.askPolicy("local:WLF1", "대상", "정책", " ", null);

        server.verify();
    }

    @Test
    void fastApiErrorCodeAndStatusArePassedThrough() {
        String body = "{\"error\":{\"code\":\"API_KEY_REQUIRED\",\"message\":\"Gemini API 키가 필요합니다.\",\"details\":null}}";
        server.expect(requestTo(BASE + "/policies/search"))
                .andRespond(withStatus(org.springframework.http.HttpStatus.UNAUTHORIZED).contentType(MediaType.APPLICATION_JSON).body(body));

        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> {
                    assertThat(e.getStatus()).isEqualTo(401);
                    assertThat(errorCode(e)).isEqualTo("API_KEY_REQUIRED");
                });
    }

    @Test
    void rateLimitStaysRateLimit() {
        String body = "{\"error\":{\"code\":\"LLM_RATE_LIMITED\",\"message\":\"한도\",\"details\":null}}";
        server.expect(requestTo(BASE + "/policies/search"))
                .andRespond(withStatus(org.springframework.http.HttpStatus.TOO_MANY_REQUESTS).contentType(MediaType.APPLICATION_JSON).body(body));

        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> {
                    assertThat(e.getStatus()).isEqualTo(429);
                    assertThat(errorCode(e)).isEqualTo("LLM_RATE_LIMITED");
                });
    }

    @Test
    void nonJsonErrorBodyBecomesInternalError() {
        server.expect(requestTo(BASE + "/policies/search"))
                .andRespond(withStatus(org.springframework.http.HttpStatus.BAD_GATEWAY).body("<html>bad gateway</html>"));

        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> {
                    assertThat(e.getStatus()).isEqualTo(502);
                    assertThat(errorCode(e)).isEqualTo("INTERNAL_ERROR");
                });
    }

    @Test
    void timeoutIs504AndConnectionFailureIs503() {
        server.expect(requestTo(BASE + "/policies/search")).andRespond(withException(new SocketTimeoutException("read timed out")));
        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> assertThat(e.getStatus()).isEqualTo(504));

        server.reset();
        server.expect(requestTo(BASE + "/policies/search")).andRespond(withException(new java.net.ConnectException("refused")));
        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> assertThat(e.getStatus()).isEqualTo(503));
    }

    @SuppressWarnings("unchecked")
    private static String errorCode(UpstreamApiException e) {
        return (String) ((Map<String, Object>) e.getBody().get("error")).get("code");
    }
}
