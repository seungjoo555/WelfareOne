package com.welfareone.memberjoin.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserProfileDto {
    @JsonProperty("user_id")
    private Long userId;

    private String email;
    private String nickname;

    @JsonProperty("default_region_level1")
    private String defaultRegionLevel1;

    @JsonProperty("default_region_level2")
    private String defaultRegionLevel2;

    @JsonProperty("default_age")
    private Integer defaultAge;

    @JsonProperty("has_api_key")
    private boolean hasApiKey;
}

