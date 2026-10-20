package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.domain.ChatMessage;
import com.welfareone.memberjoin.domain.ChatSession;
import com.welfareone.memberjoin.dto.SessionDetailDto;
import com.welfareone.memberjoin.mapper.ChatMessageMapper;
import com.welfareone.memberjoin.mapper.ChatSessionMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** DB 제약(CK_MESSAGES_SENDER: USER/ASSISTANT 대문자)과 세션 소유자 검증. */
class HistoryServiceTest {

    private ChatSessionMapper sessionMapper;
    private ChatMessageMapper messageMapper;
    private HistoryService service;

    @BeforeEach
    void setUp() {
        sessionMapper = mock(ChatSessionMapper.class);
        messageMapper = mock(ChatMessageMapper.class);
        service = new HistoryService(sessionMapper, messageMapper);
    }

    @Test
    void senderIsStoredInUpperCaseToSatisfyTheDbConstraint() {
        service.saveMessage("s1", "user", "질문", null, null, null, null, null, null);
        service.saveMessage("s1", "assistant", "답변", "situation_search", "[]", null, null, null, null);

        ArgumentCaptor<ChatMessage> captor = ArgumentCaptor.forClass(ChatMessage.class);
        verify(messageMapper, org.mockito.Mockito.times(2)).insertMessage(captor.capture());
        assertThat(captor.getAllValues()).extracting(ChatMessage::getSenderType).containsExactly("USER", "ASSISTANT");
    }

    @Test
    void responseKeepsTheLowerCaseContractWithTheFrontend() {
        ChatSession session = ChatSession.builder().sessionId("s1").userId(7L).title("t").regionLevel1("서울특별시").build();
        ChatMessage stored = ChatMessage.builder().messageId("m1").sessionId("s1").senderType("ASSISTANT").content("답변").build();
        when(sessionMapper.findById("s1")).thenReturn(session);
        when(messageMapper.findBySessionIdOrderByCreatedAtAsc("s1")).thenReturn(List.of(stored));

        SessionDetailDto detail = service.getSessionDetail("s1", 7L);

        assertThat(detail.getMessages()).extracting("senderType").containsExactly("assistant");
    }

    @Test
    void assertSessionOwnerAcceptsOwner() {
        when(sessionMapper.findById("s1")).thenReturn(ChatSession.builder().sessionId("s1").userId(7L).build());

        service.assertSessionOwner("s1", 7L);
    }

    @Test
    void assertSessionOwnerRejectsOtherUsersAndUnknownSessions() {
        when(sessionMapper.findById("s1")).thenReturn(ChatSession.builder().sessionId("s1").userId(7L).build());

        assertThatThrownBy(() -> service.assertSessionOwner("s1", 8L)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.assertSessionOwner("nope", 7L)).isInstanceOf(IllegalArgumentException.class);
        verify(messageMapper, never()).insertMessage(any());
    }
}
