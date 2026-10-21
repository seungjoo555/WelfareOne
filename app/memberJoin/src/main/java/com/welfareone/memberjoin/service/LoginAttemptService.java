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
 * 로그인 연속 실패를 잠시 막는다(비밀번호 무차별 대입 방지). 세 가지를 따로 센다.
 * <ul>
 *   <li>같은 이메일 + 같은 IP: {@link #MAX_FAILURES}회. 남이 내 이메일로 실패시켜도 내 IP에서는 막히지 않는다.</li>
 *   <li>같은 이메일(IP 무관): {@link #MAX_FAILURES_PER_EMAIL}회. 여러 IP로 나눠 대입하는 시도를 막는다.</li>
 *   <li>같은 IP(이메일 무관): {@link #MAX_FAILURES_PER_IP}회. 한 곳에서 여러 계정을 번갈아 시도하는 것을 막는다.</li>
 * </ul>
 * 서버 한 대 기준의 메모리 방식이라 재시작하면 초기화된다. 서버를 여러 대로 늘리면 DB나 Redis로 옮겨야 한다.
 * 실패 기록은 {@link #WINDOW}가 지나면 사라지고, 항목이 많아지면 만료된 것을 정리한다.
 * IP는 요청의 원격 주소다. 역방향 프록시 뒤에서는 프록시 주소로 보이므로 {@code server.forward-headers-strategy} 설정이 필요하다.
 */
@Service
public class LoginAttemptService {

    static final int MAX_FAILURES = 5;
    static final int MAX_FAILURES_PER_EMAIL = 30;
    static final int MAX_FAILURES_PER_IP = 20;
    static final Duration WINDOW = Duration.ofMinutes(10);
    /** 추적 중인 항목이 이 수를 넘으면 만료된 항목을 정리한다. */
    static final int CLEANUP_THRESHOLD = 1_000;

    private final Clock clock;
    private final Map<String, Deque<Instant>> failures = new ConcurrentHashMap<>();

    @Autowired
    public LoginAttemptService() {
        this(Clock.systemUTC());
    }

    LoginAttemptService(Clock clock) {
        this.clock = clock;
    }

    /** 최근 WINDOW 안의 실패가 한도 이상이면 429(TOO_MANY_LOGIN_ATTEMPTS). 조회만 하고 항목을 만들지 않는다. */
    public void checkAllowed(String email, String ip) {
        if (count(pairKey(email, ip)) >= MAX_FAILURES
                || count(emailKey(email)) >= MAX_FAILURES_PER_EMAIL
                || count(ipKey(ip)) >= MAX_FAILURES_PER_IP) {
            throw ApiException.tooManyLoginAttempts();
        }
    }

    public void recordFailure(String email, String ip) {
        Instant now = clock.instant();
        add(pairKey(email, ip), now);
        add(emailKey(email), now);
        add(ipKey(ip), now);
        if (failures.size() > CLEANUP_THRESHOLD) {
            purgeExpired(now);
        }
    }

    /** 로그인에 성공하면 그 이메일(+IP)의 실패 기록을 지운다. IP 전체 기록은 다른 시도를 막기 위해 남긴다. */
    public void reset(String email, String ip) {
        failures.remove(pairKey(email, ip));
        failures.remove(emailKey(email));
    }

    /** 시험용: 추적 중인 항목 수. */
    int trackedKeys() {
        return failures.size();
    }

    private int count(String key) {
        Instant now = clock.instant();
        int[] size = {0};
        failures.computeIfPresent(key, (k, recent) -> {
            prune(recent, now);
            size[0] = recent.size();
            return recent.isEmpty() ? null : recent;
        });
        return size[0];
    }

    private void add(String key, Instant now) {
        failures.compute(key, (k, recent) -> {
            Deque<Instant> deque = recent == null ? new ArrayDeque<>() : recent;
            prune(deque, now);
            deque.addLast(now);
            return deque;
        });
    }

    private void purgeExpired(Instant now) {
        for (String key : failures.keySet()) {
            failures.computeIfPresent(key, (k, recent) -> {
                prune(recent, now);
                return recent.isEmpty() ? null : recent;
            });
        }
    }

    private static void prune(Deque<Instant> recent, Instant now) {
        Instant cutoff = now.minus(WINDOW);
        while (!recent.isEmpty() && recent.peekFirst().isBefore(cutoff)) {
            recent.pollFirst();
        }
    }

    private static String pairKey(String email, String ip) {
        return "p|" + normalize(email) + "|" + normalizeIp(ip);
    }

    private static String emailKey(String email) {
        return "e|" + normalize(email);
    }

    private static String ipKey(String ip) {
        return "i|" + normalizeIp(ip);
    }

    private static String normalize(String email) {
        return email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    }

    private static String normalizeIp(String ip) {
        return ip == null || ip.isBlank() ? "unknown" : ip.trim();
    }
}
