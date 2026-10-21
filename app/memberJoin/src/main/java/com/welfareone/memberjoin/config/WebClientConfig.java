package com.welfareone.memberjoin.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.net.http.HttpClient;
import java.time.Duration;

@Configuration
public class WebClientConfig {

    @Value("${fastapi.base-url}")
    private String fastApiBaseUrl;

    // FastAPI가 응답하지 않을 때 Spring 스레드가 무한 대기하지 않도록 제한한다(프론트 요청 제한 30초보다 길게).
    @Value("${fastapi.connect-timeout-ms:3000}")
    private int connectTimeoutMs;

    @Value("${fastapi.read-timeout-ms:60000}")
    private int readTimeoutMs;

    @Bean
    public RestClient fastApiRestClient() {
        return build(fastApiBaseUrl, connectTimeoutMs, readTimeoutMs);
    }

    /**
     * JDK HttpClient 기반으로 만든다. 기본값인 HttpURLConnection은 POST 요청이 401 응답을 받으면
     * 응답 본문을 읽지 못해 FastAPI의 오류 코드(API_KEY_REQUIRED, INVALID_API_KEY)가 사라지는 문제가 있다.
     * 단 JDK HttpClient는 HTTP/1.1로 고정해야 한다(아래 주석).
     */
    public static RestClient build(String baseUrl, int connectTimeoutMs, int readTimeoutMs) {
        HttpClient httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)  // 기본값은 HTTP/2 업그레이드(Upgrade: h2c)를 시도해 uvicorn이 요청을 거절한다(실측)
                .connectTimeout(Duration.ofMillis(connectTimeoutMs))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));
        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
