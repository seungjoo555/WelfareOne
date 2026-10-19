package com.welfareone.memberjoin.mapper;

import com.welfareone.memberjoin.domain.UserApiKey;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface UserApiKeyMapper {
    int upsertApiKey(UserApiKey apiKey);
    UserApiKey findByUserId(@Param("userId") Long userId);
    int deleteByUserId(@Param("userId") Long userId);
}

