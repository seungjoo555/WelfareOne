package com.welfareone.memberjoin.controller;

import com.welfareone.memberjoin.dto.AuthResponse;
import com.welfareone.memberjoin.dto.LoginRequest;
import com.welfareone.memberjoin.dto.SignUpRequest;
import com.welfareone.memberjoin.dto.UserProfileDto;
import com.welfareone.memberjoin.service.AuthService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/signup")
    public ResponseEntity<AuthResponse> signUp(@Valid @RequestBody SignUpRequest request) {
        AuthResponse response = authService.signUp(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest request, HttpServletRequest http) {
        AuthResponse response = authService.login(request, http.getRemoteAddr());
        return ResponseEntity.ok(response);
    }

    @GetMapping("/me")
    public ResponseEntity<UserProfileDto> getMe(@AuthenticationPrincipal Long userId) {
        UserProfileDto profile = authService.getProfile(userId);
        return ResponseEntity.ok(profile);
    }

    @PostMapping("/logout")
    public ResponseEntity<Map<String, String>> logout() {
        // Stateless JWT이므로 클라이언트가 토큰을 삭제하면 완료
        return ResponseEntity.ok(Map.of("message", "로그아웃되었습니다."));
    }
}

