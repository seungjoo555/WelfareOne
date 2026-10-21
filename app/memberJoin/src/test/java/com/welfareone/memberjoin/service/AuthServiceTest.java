package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.domain.User;
import com.welfareone.memberjoin.dto.LoginRequest;
import com.welfareone.memberjoin.dto.SignUpRequest;
import com.welfareone.memberjoin.exception.ApiException;
import com.welfareone.memberjoin.mapper.UserApiKeyMapper;
import com.welfareone.memberjoin.mapper.UserMapper;
import com.welfareone.memberjoin.util.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** 계약서 17.4 오류 코드와 로그인 시도 제한. */
class AuthServiceTest {

    private UserMapper userMapper;
    private JwtTokenProvider jwt;
    private LoginAttemptService attempts;
    private AuthService service;
    private final PasswordEncoder encoder = new BCryptPasswordEncoder();

    @BeforeEach
    void setUp() {
        userMapper = mock(UserMapper.class);
        jwt = mock(JwtTokenProvider.class);
        attempts = new LoginAttemptService();
        service = new AuthService(userMapper, mock(UserApiKeyMapper.class), encoder, jwt, attempts);
    }

    private static final String IP = "10.0.0.1";

    private static LoginRequest login(String email, String password) {
        LoginRequest request = new LoginRequest();
        request.setEmail(email);
        request.setPassword(password);
        return request;
    }

    @Test
    void duplicateEmailIs409UserAlreadyExists() {
        when(userMapper.countByEmail("a@example.com")).thenReturn(1);
        SignUpRequest request = SignUpRequest.builder().email("a@example.com").password("password123").nickname("a").build();

        assertThatThrownBy(() -> service.signUp(request)).isInstanceOfSatisfying(ApiException.class, e -> {
            assertThat(e.getCode()).isEqualTo("USER_ALREADY_EXISTS");
            assertThat(e.getStatus().value()).isEqualTo(409);
        });
        verify(userMapper, never()).insertUser(any());
    }

    @Test
    void wrongPasswordAndUnknownEmailLookTheSame401InvalidCredentials() {
        User user = User.builder().userId(1L).email("a@example.com").passwordHash(encoder.encode("right-password")).role("ROLE_USER").build();
        when(userMapper.findByEmail("a@example.com")).thenReturn(user);

        for (LoginRequest request : new LoginRequest[]{login("a@example.com", "wrong-password"), login("nobody@example.com", "whatever12")}) {
            assertThatThrownBy(() -> service.login(request, IP)).isInstanceOfSatisfying(ApiException.class, e -> {
                assertThat(e.getCode()).isEqualTo("INVALID_CREDENTIALS");
                assertThat(e.getStatus().value()).isEqualTo(401);
            });
        }
    }

    @Test
    void sixthWrongPasswordIsBlocked() {
        when(userMapper.findByEmail("a@example.com")).thenReturn(null);
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES; i++) {
            assertThatThrownBy(() -> service.login(login("a@example.com", "wrong-password"), IP)).isInstanceOf(ApiException.class);
        }

        assertThatThrownBy(() -> service.login(login("a@example.com", "wrong-password"), IP))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getCode()).isEqualTo("TOO_MANY_LOGIN_ATTEMPTS"));
    }

    @Test
    void successfulLoginResetsTheFailureCounter() {
        User user = User.builder().userId(1L).email("a@example.com").passwordHash(encoder.encode("right-password")).role("ROLE_USER").build();
        when(userMapper.findByEmail("a@example.com")).thenReturn(user);
        when(jwt.createToken(1L, "a@example.com", "ROLE_USER")).thenReturn("token");
        for (int i = 0; i < LoginAttemptService.MAX_FAILURES - 1; i++) {
            assertThatThrownBy(() -> service.login(login("a@example.com", "wrong-password"), IP)).isInstanceOf(ApiException.class);
        }

        assertThat(service.login(login("a@example.com", "right-password"), IP).getAccessToken()).isEqualTo("token");
        attempts.checkAllowed("a@example.com", IP);  // 카운터가 초기화돼 막히지 않음
    }
}
