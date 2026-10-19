package com.welfareone.memberjoin.service;

import com.welfareone.memberjoin.domain.UserApiKey;
import com.welfareone.memberjoin.dto.ApiKeyStatusResponse;
import com.welfareone.memberjoin.mapper.UserApiKeyMapper;
import com.welfareone.memberjoin.util.AESCryptoUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ApiKeyService {

    private final UserApiKeyMapper apiKeyMapper;
    private final AESCryptoUtil cryptoUtil;

    @Transactional
    public ApiKeyStatusResponse saveApiKey(Long userId, String plainApiKey) {
        AESCryptoUtil.EncryptedResult encrypted = cryptoUtil.encrypt(plainApiKey);

        UserApiKey entity = UserApiKey.builder()
                .userId(userId)
                .encryptedKey(encrypted.cipherText())
                .ivSalt(encrypted.iv())
                .isActive("Y")
                .build();

        apiKeyMapper.upsertApiKey(entity);

        UserApiKey saved = apiKeyMapper.findByUserId(userId);
        return ApiKeyStatusResponse.builder()
                .hasApiKey(true)
                .updatedAt(saved != null ? saved.getUpdatedAt() : null)
                .build();
    }

    @Transactional(readOnly = true)
    public ApiKeyStatusResponse getApiKeyStatus(Long userId) {
        UserApiKey key = apiKeyMapper.findByUserId(userId);
        return ApiKeyStatusResponse.builder()
                .hasApiKey(key != null)
                .updatedAt(key != null ? key.getUpdatedAt() : null)
                .build();
    }

    @Transactional(readOnly = true)
    public String getDecryptedApiKey(Long userId) {
        UserApiKey key = apiKeyMapper.findByUserId(userId);
        if (key == null) {
            return null;
        }
        return cryptoUtil.decrypt(key.getEncryptedKey(), key.getIvSalt());
    }

    @Transactional
    public void deleteApiKey(Long userId) {
        apiKeyMapper.deleteByUserId(userId);
    }
}

