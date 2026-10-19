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
public class ChatMessage {
    private String messageId;
    private String sessionId;
    private String senderType; // USER or ASSISTANT
    private String content;
    private String route;
    private String intentsJson;
    private String selectedPolicyId;
    private String candidatesJson;
    private String evidenceJson;
    private String resourcesJson;
    private LocalDateTime createdAt;
}

