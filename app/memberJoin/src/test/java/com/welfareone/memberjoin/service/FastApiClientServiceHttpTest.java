package com.welfareone.memberjoin.service;

import com.sun.net.httpserver.HttpServer;
import com.welfareone.memberjoin.config.WebClientConfig;
import com.welfareone.memberjoin.exception.UpstreamApiException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 모의 서버(MockRestServiceServer)가 아니라 실제 HTTP로 FastAPI 흉내 서버를 호출한다.
 * 기본 HttpURLConnection은 POST가 401을 받으면 응답 본문을 읽지 못하는데(종단 시험에서 발견),
 * 모의 서버 테스트로는 이 문제가 드러나지 않으므로 별도로 검증한다.
 */
class FastApiClientServiceHttpTest {

    private HttpServer server;
    private final AtomicReference<String> receivedKeyHeader = new AtomicReference<>();
    private final AtomicReference<String> receivedUpgradeHeader = new AtomicReference<>();

    @BeforeEach
    void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();
    }

    @AfterEach
    void stop() {
        if (server != null) {
            server.stop(0);
        }
    }

    private FastApiClientService service(int connectMs, int readMs) {
        String base = "http://127.0.0.1:" + server.getAddress().getPort();
        return new FastApiClientService(WebClientConfig.build(base, connectMs, readMs));
    }

    private void respond(String path, int status, String body) {
        server.createContext(path, exchange -> {
            receivedKeyHeader.set(exchange.getRequestHeaders().getFirst("X-Gemini-Api-Key"));
            receivedUpgradeHeader.set(exchange.getRequestHeaders().getFirst("Upgrade"));
            exchange.getRequestBody().readAllBytes();
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
    }

    @SuppressWarnings("unchecked")
    private static String errorCode(UpstreamApiException e) {
        return (String) ((Map<String, Object>) e.getBody().get("error")).get("code");
    }

    @Test
    void status401KeepsTheFastApiErrorBodyOverRealHttp() {
        respond("/policies/search", 401,
                "{\"error\":{\"code\":\"INVALID_API_KEY\",\"message\":\"Gemini API 키가 올바르지 않습니다.\",\"details\":null}}");

        assertThatThrownBy(() -> service(1000, 5000).searchPolicies("월세", "서울특별시", "", null, "AIza-bad-key"))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> {
                    assertThat(e.getStatus()).isEqualTo(401);
                    assertThat(errorCode(e)).isEqualTo("INVALID_API_KEY");
                });
        assertThat(receivedKeyHeader.get()).isEqualTo("AIza-bad-key");
    }

    @Test
    void successBodyIsReturnedOverRealHttp() {
        respond("/policies/search", 200, "{\"local_policies\":[],\"national_policies\":[]}");

        Map<String, Object> result = service(1000, 5000).searchPolicies("월세", "서울특별시", "", null, null);

        assertThat(result).containsKeys("local_policies", "national_policies");
        assertThat(receivedKeyHeader.get()).isNull();
        // HTTP/2 업그레이드 요청(Upgrade: h2c)을 보내면 uvicorn(FastAPI)이 "Unsupported upgrade request"로 거절한다(종단 시험에서 발견)
        assertThat(receivedUpgradeHeader.get()).isNull();
    }

    @Test
    void slowServerBecomes504() {
        server.createContext("/policies/search", exchange -> {
            try {
                Thread.sleep(1500);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });

        assertThatThrownBy(() -> service(1000, 300).searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> assertThat(e.getStatus()).isEqualTo(504));
    }

    @Test
    void unreachableServerBecomes503() {
        int port = server.getAddress().getPort();
        server.stop(0);  // 이 포트에는 아무도 듣고 있지 않다
        FastApiClientService service = new FastApiClientService(WebClientConfig.build("http://127.0.0.1:" + port, 1000, 1000));

        assertThatThrownBy(() -> service.searchPolicies("월세", "서울특별시", "", null, null))
                .isInstanceOfSatisfying(UpstreamApiException.class, e -> assertThat(e.getStatus()).isEqualTo(503));
        server = null;
    }
}
