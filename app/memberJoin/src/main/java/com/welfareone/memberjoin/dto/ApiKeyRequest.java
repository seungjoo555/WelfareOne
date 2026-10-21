package com.welfareone.memberjoin.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ApiKeyRequest {
    @NotBlank(message = "Gemini API 키를 입력해주세요.")
    @Pattern(regexp = "^[\\x21-\\x7e]{20,256}$", message = "올바른 Gemini API 키 형식이 아닙니다.")
    @JsonProperty("api_key")
    private String apiKey;
}

