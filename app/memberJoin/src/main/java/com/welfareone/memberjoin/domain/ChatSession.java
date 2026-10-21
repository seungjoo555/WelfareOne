package com.welfareone.memberjoin.domain;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChatSession {
    private String sessionId;
    private Long userId;
    private String title;
    private String regionLevel1;
    private String regionLevel2;
    private Integer age;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}

