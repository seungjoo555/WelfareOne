package com.welfareone.memberjoin.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChatMessageDto {
    @JsonProperty("message_id")
    private String messageId;

    @JsonProperty("session_id")
    private String sessionId;

    @JsonProperty("sender_type")
    private String senderType;

    private String content;

    private String route;

    @JsonProperty("intents_json")
    private String intentsJson;

    @JsonProperty("selected_policy_id")
    private String selectedPolicyId;

    @JsonProperty("candidates_json")
    private String candidatesJson;

    @JsonProperty("evidence_json")
    private String evidenceJson;

    @JsonProperty("resources_json")
    private String resourcesJson;

    @JsonProperty("created_at")
    private LocalDateTime createdAt;
}

