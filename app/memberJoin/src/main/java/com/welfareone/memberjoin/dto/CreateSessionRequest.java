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
public class CreateSessionRequest {
    @JsonProperty("region_level1")
    private String regionLevel1;

    @JsonProperty("region_level2")
    private String regionLevel2;

    private Integer age;

    private String title;
}

