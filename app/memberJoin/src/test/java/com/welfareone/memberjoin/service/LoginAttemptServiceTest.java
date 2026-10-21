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

    private static final String IP = "10.0.0.1";

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

    private static void fail(LoginAttemptService service, String email, String ip, int times) {
        for (int i = 0; i < times; i++) {
            service.checkAllowed(email, ip);
            service.recordFailure(email, ip);
        }
    }

    @Test
    void blocksAfterFiveFailuresForTheSameEmailAndIpOnly() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        fail(service, "a@example.com", IP, LoginAttemptService.MAX_FAILURES);

        assertThatThrownBy(() -> service.checkAllowed("A@Example.com ", IP))
                .isInstanceOfSatisfying(ApiException.class, e -> {
                    assertThat(e.getCode()).isEqualTo("TOO_MANY_LOGIN_ATTEMPTS");
                    assertThat(e.getStatus().value()).isEqualTo(429);
                });
        service.checkAllowed("b@example.com", IP);  // 다른 계정은 영향 없음
    }

    @Test
    void anotherIpCannotLockOutTheOwnerOfAnEmail() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        fail(service, "victim@example.com", "203.0.113.9", LoginAttemptService.MAX_FAILURES);  // 공격자

        service.checkAllowed("victim@example.com", IP);  // 본인은 다른 IP에서 계속 로그인할 수 있다
    }

    @Test
    void spreadingAttemptsOverManyIpsIsStillStoppedPerEmail() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES_PER_EMAIL; i++) {
            service.recordFailure("target@example.com", "198.51.100." + i);
        }

        assertThatThrownBy(() -> service.checkAllowed("target@example.com", "198.51.100.250"))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getCode()).isEqualTo("TOO_MANY_LOGIN_ATTEMPTS"));
    }

    @Test
    void oneIpTryingManyEmailsIsStopped() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES_PER_IP; i++) {
            service.recordFailure("user" + i + "@example.com", IP);
        }

        assertThatThrownBy(() -> service.checkAllowed("brand-new@example.com", IP)).isInstanceOf(ApiException.class);
        service.checkAllowed("brand-new@example.com", "192.0.2.77");  // 다른 IP는 영향 없음
    }

    @Test
    void failuresExpireAfterTheWindow() {
        MutableClock clock = new MutableClock();
        LoginAttemptService service = new LoginAttemptService(clock);
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES; i++) service.recordFailure("a@example.com", IP);
        assertThatThrownBy(() -> service.checkAllowed("a@example.com", IP)).isInstanceOf(ApiException.class);

        clock.advance(LoginAttemptService.WINDOW.plusSeconds(1));

        service.checkAllowed("a@example.com", IP);
    }

    @Test
    void successfulLoginClearsTheCounter() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES - 1; i++) service.recordFailure("a@example.com", IP);

        service.reset("a@example.com", IP);
        service.recordFailure("a@example.com", IP);

        service.checkAllowed("a@example.com", IP);
    }

    @Test
    void checkingDoesNotCreateEntriesSoRandomProbesDoNotGrowMemory() {
        LoginAttemptService service = new LoginAttemptService(new MutableClock());
        for (int i = 0; i < 500; i++) service.checkAllowed("probe" + i + "@example.com", "10.1." + (i / 250) + "." + (i % 250));

        assertThat(service.trackedKeys()).isZero();
    }

    @Test
    void expiredEntriesAreCleanedUpOnceTheMapGrows() {
        MutableClock clock = new MutableClock();
        LoginAttemptService service = new LoginAttemptService(clock);
        for (int i = 0; i < LoginAttemptService.CLEANUP_THRESHOLD; i++) {
            service.recordFailure("old" + i + "@example.com", "10.2." + (i / 250) + "." + (i % 250));
        }
        assertThat(service.trackedKeys()).isGreaterThan(LoginAttemptService.CLEANUP_THRESHOLD);

        clock.advance(LoginAttemptService.WINDOW.plusSeconds(1));
        service.recordFailure("fresh@example.com", IP);  // 정리가 일어나는 시점

        assertThat(service.trackedKeys()).isEqualTo(3);  // fresh 하나(이메일+IP, 이메일, IP)만 남는다
    }
}
