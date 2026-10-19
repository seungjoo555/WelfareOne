package com.welfareone.memberjoin.controller;

import com.welfareone.memberjoin.dto.CreateSessionRequest;
import com.welfareone.memberjoin.dto.SessionDetailDto;
import com.welfareone.memberjoin.dto.SessionSummaryDto;
import com.welfareone.memberjoin.service.HistoryService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/history/sessions")
@RequiredArgsConstructor
public class HistoryController {

    private final HistoryService historyService;

    @GetMapping
    public ResponseEntity<List<SessionSummaryDto>> getSessions(@AuthenticationPrincipal Long userId) {
        List<SessionSummaryDto> list = historyService.getSessions(userId);
        return ResponseEntity.ok(list);
    }

    @PostMapping
    public ResponseEntity<SessionSummaryDto> createSession(
            @AuthenticationPrincipal Long userId,
            @RequestBody(required = false) CreateSessionRequest request) {
        CreateSessionRequest req = request != null ? request : new CreateSessionRequest();
        SessionSummaryDto session = historyService.createSession(userId, req);
        return ResponseEntity.status(HttpStatus.CREATED).body(session);
    }

    @GetMapping("/{sessionId}")
    public ResponseEntity<SessionDetailDto> getSessionDetail(
            @PathVariable String sessionId,
            @AuthenticationPrincipal Long userId) {
        SessionDetailDto detail = historyService.getSessionDetail(sessionId, userId);
        return ResponseEntity.ok(detail);
    }

    @DeleteMapping("/{sessionId}")
    public ResponseEntity<Map<String, String>> deleteSession(
            @PathVariable String sessionId,
            @AuthenticationPrincipal Long userId) {
        historyService.deleteSession(sessionId, userId);
        return ResponseEntity.ok(Map.of("message", "세션이 삭제되었습니다."));
    }

    @PatchMapping("/{sessionId}/title")
    public ResponseEntity<Map<String, String>> updateTitle(
            @PathVariable String sessionId,
            @AuthenticationPrincipal Long userId,
            @RequestBody Map<String, String> body) {
        String newTitle = body.get("title");
        historyService.updateSessionTitle(sessionId, userId, newTitle);
        return ResponseEntity.ok(Map.of("message", "제목이 수정되었습니다."));
    }
}

