package com.welfareone.memberjoin.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

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
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(connectTimeoutMs));
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));
        return RestClient.builder()
                .baseUrl(fastApiBaseUrl)
                .requestFactory(factory)
                .build();
    }
}
