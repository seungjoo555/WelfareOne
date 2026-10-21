package com.welfareone.memberjoin.mapper;

import com.welfareone.memberjoin.domain.ChatSession;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ChatSessionMapper {
    int insertSession(ChatSession session);
    List<ChatSession> findByUserIdOrderByUpdatedAtDesc(@Param("userId") Long userId);
    ChatSession findById(@Param("sessionId") String sessionId);
    int updateSessionTitle(@Param("sessionId") String sessionId, @Param("title") String title);
    int updateSessionUpdatedAt(@Param("sessionId") String sessionId);
    int deleteById(@Param("sessionId") String sessionId);
}

