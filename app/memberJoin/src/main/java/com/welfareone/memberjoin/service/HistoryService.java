package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.domain.ChatMessage;
import com.welfareone.memberjoin.domain.ChatSession;
import com.welfareone.memberjoin.exception.ApiException;
import com.welfareone.memberjoin.dto.ChatMessageDto;
import com.welfareone.memberjoin.dto.CreateSessionRequest;
import com.welfareone.memberjoin.dto.SessionDetailDto;
import com.welfareone.memberjoin.dto.SessionSummaryDto;
import com.welfareone.memberjoin.mapper.ChatMessageMapper;
import com.welfareone.memberjoin.mapper.ChatSessionMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class HistoryService {

    private final ChatSessionMapper sessionMapper;
    private final ChatMessageMapper messageMapper;

    @Transactional
    public SessionSummaryDto createSession(Long userId, CreateSessionRequest request) {
        String sessionId = UUID.randomUUID().toString();
        String title = (request.getTitle() != null && !request.getTitle().isBlank())
                ? request.getTitle()
                : "새로운 복지 상담";

        ChatSession session = ChatSession.builder()
                .sessionId(sessionId)
                .userId(userId)
                .title(title)
                .regionLevel1(request.getRegionLevel1() != null ? request.getRegionLevel1() : "")
                .regionLevel2(request.getRegionLevel2() != null ? request.getRegionLevel2() : "")
                .age(request.getAge())
                .build();

        sessionMapper.insertSession(session);

        return toSummaryDto(session);
    }

    @Transactional(readOnly = true)
    public List<SessionSummaryDto> getSessions(Long userId) {
        return sessionMapper.findByUserIdOrderByUpdatedAtDesc(userId).stream()
                .map(this::toSummaryDto)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public SessionDetailDto getSessionDetail(String sessionId, Long userId) {
        ChatSession session = requireOwnedSession(sessionId, userId);

        List<ChatMessageDto> messages = messageMapper.findBySessionIdOrderByCreatedAtAsc(sessionId).stream()
                .map(this::toMessageDto)
                .collect(Collectors.toList());

        return SessionDetailDto.builder()
                .session(toSummaryDto(session))
                .messages(messages)
                .build();
    }

    @Transactional
    public void deleteSession(String sessionId, Long userId) {
        requireOwnedSession(sessionId, userId);
        sessionMapper.deleteById(sessionId);
    }

    @Transactional
    public void updateSessionTitle(String sessionId, Long userId, String newTitle) {
        requireOwnedSession(sessionId, userId);
        sessionMapper.updateSessionTitle(sessionId, newTitle);
    }

    /** 세션이 로그인 사용자의 것인지 확인한다. 없으면 404(SESSION_NOT_FOUND), 남의 세션이면 403(FORBIDDEN). AI 호출 전에 호출해 남의 세션에 기록이 쓰이지 않게 한다. */
    @Transactional(readOnly = true)
    public void assertSessionOwner(String sessionId, Long userId) {
        requireOwnedSession(sessionId, userId);
    }

    private ChatSession requireOwnedSession(String sessionId, Long userId) {
        ChatSession session = sessionMapper.findById(sessionId);
        if (session == null) {
            throw ApiException.sessionNotFound();
        }
        if (!session.getUserId().equals(userId)) {
            throw ApiException.forbidden();
        }
        return session;
    }

    @Transactional
    public ChatMessageDto saveMessage(
            String sessionId,
            String senderType,
            String content,
            String route,
            String intentsJson,
            String selectedPolicyId,
            String candidatesJson,
            String evidenceJson,
            String resourcesJson) {

        String messageId = UUID.randomUUID().toString();
        senderType = senderType == null ? null : senderType.toUpperCase();  // DB 제약: USER 또는 ASSISTANT
        ChatMessage message = ChatMessage.builder()
                .messageId(messageId)
                .sessionId(sessionId)
                .senderType(senderType)
                .content(content)
                .route(route)
                .intentsJson(intentsJson)
                .selectedPolicyId(selectedPolicyId)
                .candidatesJson(candidatesJson)
                .evidenceJson(evidenceJson)
                .resourcesJson(resourcesJson)
                .build();

        messageMapper.insertMessage(message);
        sessionMapper.updateSessionUpdatedAt(sessionId);

        return toMessageDto(message);
    }

    private SessionSummaryDto toSummaryDto(ChatSession session) {
        return SessionSummaryDto.builder()
                .sessionId(session.getSessionId())
                .title(session.getTitle())
                .regionLevel1(session.getRegionLevel1())
                .regionLevel2(session.getRegionLevel2())
                .age(session.getAge())
                .createdAt(session.getCreatedAt())
                .updatedAt(session.getUpdatedAt())
                .build();
    }

    private ChatMessageDto toMessageDto(ChatMessage message) {
        return ChatMessageDto.builder()
                .messageId(message.getMessageId())
                .sessionId(message.getSessionId())
                .senderType(message.getSenderType() == null ? null : message.getSenderType().toLowerCase())  // DB는 대문자(USER/ASSISTANT), 화면 계약은 소문자
                .content(message.getContent())
                .route(message.getRoute())
                .intentsJson(message.getIntentsJson())
                .selectedPolicyId(message.getSelectedPolicyId())
                .candidatesJson(message.getCandidatesJson())
                .evidenceJson(message.getEvidenceJson())
                .resourcesJson(message.getResourcesJson())
                .createdAt(message.getCreatedAt())
                .build();
    }
}

