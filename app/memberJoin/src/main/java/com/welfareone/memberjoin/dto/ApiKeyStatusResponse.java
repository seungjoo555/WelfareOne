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
public class ApiKeyStatusResponse {
    @JsonProperty("has_api_key")
    private boolean hasApiKey;

    @JsonProperty("updated_at")
    private LocalDateTime updatedAt;
}

