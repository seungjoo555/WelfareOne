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
public class User {
    private Long userId;
    private String email;
    private String passwordHash;
    private String nickname;
    private String role;
    private String defaultRegionLevel1;
    private String defaultRegionLevel2;
    private Integer defaultAge;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}

