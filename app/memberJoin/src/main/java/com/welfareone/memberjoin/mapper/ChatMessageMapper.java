package com.welfareone.memberjoin.mapper;

import com.welfareone.memberjoin.domain.ChatMessage;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ChatMessageMapper {
    int insertMessage(ChatMessage message);
    List<ChatMessage> findBySessionIdOrderByCreatedAtAsc(@Param("sessionId") String sessionId);
    int deleteBySessionId(@Param("sessionId") String sessionId);
}

