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
public class SessionSummaryDto {
    @JsonProperty("session_id")
    private String sessionId;

    private String title;

    @JsonProperty("region_level1")
    private String regionLevel1;

    @JsonProperty("region_level2")
    private String regionLevel2;

    private Integer age;

    @JsonProperty("created_at")
    private LocalDateTime createdAt;

    @JsonProperty("updated_at")
    private LocalDateTime updatedAt;
}

