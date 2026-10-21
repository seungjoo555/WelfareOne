package com.welfareone.memberjoin.util;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** 사용자 Gemini 키 암호화(AES-256-GCM). 마스터 키 길이와 왕복·변조 검증. */
class AESCryptoUtilTest {

    private static final String MASTER = "0123456789abcdef0123456789abcdef-extra";  // 32바이트 이상

    @Test
    void roundTripReturnsTheOriginalKey() {
        AESCryptoUtil util = new AESCryptoUtil(MASTER);

        AESCryptoUtil.EncryptedResult encrypted = util.encrypt("AIzaSyExampleKey-0123456789");

        assertThat(encrypted.cipherText()).doesNotContain("AIza");
        assertThat(util.decrypt(encrypted.cipherText(), encrypted.iv())).isEqualTo("AIzaSyExampleKey-0123456789");
    }

    @Test
    void everyEncryptionUsesANewIv() {
        AESCryptoUtil util = new AESCryptoUtil(MASTER);

        assertThat(util.encrypt("same").iv()).isNotEqualTo(util.encrypt("same").iv());
    }

    @Test
    void tamperedCipherTextOrWrongMasterKeyFailsToDecrypt() {
        AESCryptoUtil util = new AESCryptoUtil(MASTER);
        AESCryptoUtil.EncryptedResult encrypted = util.encrypt("secret");
        AESCryptoUtil other = new AESCryptoUtil("ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ");

        assertThatThrownBy(() -> other.decrypt(encrypted.cipherText(), encrypted.iv())).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> util.decrypt(encrypted.cipherText().substring(2) + "AA", encrypted.iv())).isInstanceOf(RuntimeException.class);
    }

    @Test
    void masterKeyShorterThan32BytesStopsTheServer() {
        assertThatThrownBy(() -> new AESCryptoUtil("too-short")).isInstanceOf(IllegalStateException.class);
    }
}
