package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.exception.ApiException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 같은 이메일로 로그인에 연속 실패하면 잠시 막는다(비밀번호 무차별 대입 방지).
 * 서버 한 대 기준의 메모리 방식이라 재시작하면 초기화된다. 서버를 여러 대로 늘리면 DB나 Redis로 옮겨야 한다.
 */
@Service
public class LoginAttemptService {

    static final int MAX_FAILURES = 5;
    static final Duration WINDOW = Duration.ofMinutes(10);

    private final Clock clock;
    private final Map<String, Deque<Instant>> failures = new ConcurrentHashMap<>();

    @Autowired
    public LoginAttemptService() {
        this(Clock.systemUTC());
    }

    LoginAttemptService(Clock clock) {
        this.clock = clock;
    }

    /** 최근 WINDOW 안에 실패가 MAX_FAILURES회 이상이면 429(TOO_MANY_LOGIN_ATTEMPTS). */
    public void checkAllowed(String email) {
        Deque<Instant> recent = recent(email);
        synchronized (recent) {
            if (recent.size() >= MAX_FAILURES) {
                throw ApiException.tooManyLoginAttempts();
            }
        }
    }

    public void recordFailure(String email) {
        Deque<Instant> recent = recent(email);
        synchronized (recent) {
            recent.addLast(clock.instant());
        }
    }

    public void reset(String email) {
        failures.remove(key(email));
    }

    private Deque<Instant> recent(String email) {
        Deque<Instant> deque = failures.computeIfAbsent(key(email), k -> new ArrayDeque<>());
        Instant cutoff = clock.instant().minus(WINDOW);
        synchronized (deque) {
            while (!deque.isEmpty() && deque.peekFirst().isBefore(cutoff)) {
                deque.pollFirst();
            }
        }
        return deque;
    }

    private static String key(String email) {
        return email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    }
}
