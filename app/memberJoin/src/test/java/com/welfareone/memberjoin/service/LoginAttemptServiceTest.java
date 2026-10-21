package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.exception.ApiException;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LoginAttemptServiceTest {

    /** 시간을 직접 움직일 수 있는 시계. */
    static class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-10-21T00:00:00Z");

        void advance(Duration d) {
            now = now.plus(d);
        }

        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }

    @Test
    void blocksAfterFiveFailuresForTheSameEmailOnly() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES; i++) {
            service.checkAllowed("a@example.com");
            service.recordFailure("a@example.com");
        }

        assertThatThrownBy(() -> service.checkAllowed("A@Example.com "))
                .isInstanceOfSatisfying(ApiException.class, e -> {
                    assertThat(e.getCode()).isEqualTo("TOO_MANY_LOGIN_ATTEMPTS");
                    assertThat(e.getStatus().value()).isEqualTo(429);
                });
        service.checkAllowed("b@example.com");  // 다른 계정은 영향 없음
    }

    @Test
    void failuresExpireAfterTheWindow() {
        MutableClock clock = new MutableClock();
        LoginAttemptService service = new LoginAttemptService(clock);
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES; i++) service.recordFailure("a@example.com");
        assertThatThrownBy(() -> service.checkAllowed("a@example.com")).isInstanceOf(ApiException.class);

        clock.advance(LoginAttemptService.WINDOW.plusSeconds(1));

        service.checkAllowed("a@example.com");
    }

    @Test
    void successfulLoginClearsTheCounter() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES - 1; i++) service.recordFailure("a@example.com");

        service.reset("a@example.com");
        service.recordFailure("a@example.com");

        service.checkAllowed("a@example.com");
    }
}
