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
public class UserApiKey {
    private Long keyId;
    private Long userId;
    private String encryptedKey;
    private String ivSalt;
    private String isActive;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}

