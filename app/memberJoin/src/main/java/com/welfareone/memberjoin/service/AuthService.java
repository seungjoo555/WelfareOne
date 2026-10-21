package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.domain.User;
import com.welfareone.memberjoin.domain.UserApiKey;
import com.welfareone.memberjoin.dto.AuthResponse;
import com.welfareone.memberjoin.dto.LoginRequest;
import com.welfareone.memberjoin.dto.SignUpRequest;
import com.welfareone.memberjoin.dto.UserProfileDto;
import com.welfareone.memberjoin.exception.ApiException;
import com.welfareone.memberjoin.mapper.UserApiKeyMapper;
import com.welfareone.memberjoin.mapper.UserMapper;
import com.welfareone.memberjoin.util.JwtTokenProvider;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserMapper userMapper;
    private final UserApiKeyMapper userApiKeyMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;
    private final LoginAttemptService loginAttempts;

    @Transactional
    public AuthResponse signUp(SignUpRequest request) {
        if (userMapper.countByEmail(request.getEmail()) > 0) {
            throw ApiException.userAlreadyExists();
        }

        User user = User.builder()
                .email(request.getEmail())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .nickname(request.getNickname())
                .role("ROLE_USER")
                .defaultRegionLevel1(request.getDefaultRegionLevel1())
                .defaultRegionLevel2(request.getDefaultRegionLevel2())
                .defaultAge(request.getDefaultAge())
                .build();

        userMapper.insertUser(user);

        String token = jwtTokenProvider.createToken(user.getUserId(), user.getEmail(), user.getRole());

        UserProfileDto profile = UserProfileDto.builder()
                .userId(user.getUserId())
                .email(user.getEmail())
                .nickname(user.getNickname())
                .defaultRegionLevel1(user.getDefaultRegionLevel1())
                .defaultRegionLevel2(user.getDefaultRegionLevel2())
                .defaultAge(user.getDefaultAge())
                .hasApiKey(false)
                .build();

        return AuthResponse.builder()
                .accessToken(token)
                .tokenType("Bearer")
                .user(profile)
                .build();
    }

    @Transactional(readOnly = true)
    public AuthResponse login(LoginRequest request) {
        // 같은 이메일로 연속 실패하면 잠시 막는다(무차별 대입 방지)
        loginAttempts.checkAllowed(request.getEmail());
        User user = userMapper.findByEmail(request.getEmail());
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            loginAttempts.recordFailure(request.getEmail());
            throw ApiException.invalidCredentials();
        }
        loginAttempts.reset(request.getEmail());

        String token = jwtTokenProvider.createToken(user.getUserId(), user.getEmail(), user.getRole());
        UserApiKey key = userApiKeyMapper.findByUserId(user.getUserId());

        UserProfileDto profile = UserProfileDto.builder()
                .userId(user.getUserId())
                .email(user.getEmail())
                .nickname(user.getNickname())
                .defaultRegionLevel1(user.getDefaultRegionLevel1())
                .defaultRegionLevel2(user.getDefaultRegionLevel2())
                .defaultAge(user.getDefaultAge())
                .hasApiKey(key != null)
                .build();

        return AuthResponse.builder()
                .accessToken(token)
                .tokenType("Bearer")
                .user(profile)
                .build();
    }

    @Transactional(readOnly = true)
    public UserProfileDto getProfile(Long userId) {
        User user = userMapper.findById(userId);
        if (user == null) {
            throw ApiException.unauthorized();
        }
        UserApiKey key = userApiKeyMapper.findByUserId(userId);

        return UserProfileDto.builder()
                .userId(user.getUserId())
                .email(user.getEmail())
                .nickname(user.getNickname())
                .defaultRegionLevel1(user.getDefaultRegionLevel1())
                .defaultRegionLevel2(user.getDefaultRegionLevel2())
                .defaultAge(user.getDefaultAge())
                .hasApiKey(key != null)
                .build();
    }
}

