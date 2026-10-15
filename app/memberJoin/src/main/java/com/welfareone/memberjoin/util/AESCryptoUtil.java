package com.welfareone.memberjoin.util;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;

@Component
public class AESCryptoUtil {

    private static final String ALGORITHM = "AES/GCM/NoPadding";
    private static final int TAG_LENGTH_BIT = 128;
    private static final int IV_LENGTH_BYTE = 12;

    private final SecretKey masterKeySpec;

    public AESCryptoUtil(@Value("${security.aes.master-key}") String masterKey) {
        // 32바이트(256비트) 키 보장
        byte[] keyBytes = masterKey.getBytes(StandardCharsets.UTF_8);
        byte[] normalized = new byte[32];
        System.arraycopy(keyBytes, 0, normalized, 0, Math.min(keyBytes.length, 32));
        this.masterKeySpec = new SecretKeySpec(normalized, "AES");
    }

    public record EncryptedResult(String cipherText, String iv) {}

    public EncryptedResult encrypt(String plainText) {
        try {
            byte[] iv = new byte[IV_LENGTH_BYTE];
            new SecureRandom().nextBytes(iv);

            Cipher cipher = Cipher.getInstance(ALGORITHM);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(TAG_LENGTH_BIT, iv);
            cipher.init(Cipher.ENCRYPT_MODE, masterKeySpec, parameterSpec);

            byte[] cipherText = cipher.doFinal(plainText.getBytes(StandardCharsets.UTF_8));

            String encodedCipher = Base64.getEncoder().encodeToString(cipherText);
            String encodedIv = Base64.getEncoder().encodeToString(iv);

            return new EncryptedResult(encodedCipher, encodedIv);
        } catch (Exception e) {
            throw new RuntimeException("API 키 암호화 중 오류가 발생했습니다.", e);
        }
    }

    public String decrypt(String cipherText, String iv) {
        try {
            byte[] decodedCipher = Base64.getDecoder().decode(cipherText);
            byte[] decodedIv = Base64.getDecoder().decode(iv);

            Cipher cipher = Cipher.getInstance(ALGORITHM);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(TAG_LENGTH_BIT, decodedIv);
            cipher.init(Cipher.DECRYPT_MODE, masterKeySpec, parameterSpec);

            byte[] decrypted = cipher.doFinal(decodedCipher);
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("API 키 복호화 중 오류가 발생했습니다.", e);
        }
    }
}

