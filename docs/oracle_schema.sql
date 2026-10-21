-- ====================================================================
-- WelfareOne Oracle DB DDL Script (공통 인증, API 키, 상담 히스토리)
-- 대상 DB: Oracle 12c / 19c / 21c / 23c (XE/FREE 포함)
-- 문자셋: AL32UTF8 권장
-- ====================================================================

-- 기존 테이블 삭제 (초기화 필요 시 주석 해제 후 순서대로 실행)
/*
DROP TABLE CHAT_MESSAGES CASCADE CONSTRAINTS;
DROP TABLE CHAT_SESSIONS CASCADE CONSTRAINTS;
DROP TABLE USER_API_KEYS CASCADE CONSTRAINTS;
DROP TABLE USERS CASCADE CONSTRAINTS;
*/

-- --------------------------------------------------------------------
-- 1. 회원 테이블 (USERS)
-- 회원 기본 계정 정보 및 상담 기본 프로필(거주 지역, 나이) 저장
-- --------------------------------------------------------------------
CREATE TABLE USERS (
    user_id                 NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email                   VARCHAR2(100 CHAR) NOT NULL,
    password_hash           VARCHAR2(255)      NOT NULL,
    nickname                VARCHAR2(50 CHAR)  NOT NULL,
    role                    VARCHAR2(20)       DEFAULT 'ROLE_USER' NOT NULL,
    default_region_level1   VARCHAR2(50 CHAR),
    default_region_level2   VARCHAR2(50 CHAR),
    default_age             NUMBER(3),
    created_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_age CHECK (default_age IS NULL OR (default_age >= 0 AND default_age <= 120))
);

COMMENT ON TABLE  USERS IS '회원 기본 정보 테이블';
COMMENT ON COLUMN USERS.user_id IS '회원 고유 식별자 (PK, Identity)';
COMMENT ON COLUMN USERS.email IS '로그인용 이메일 계정 (Unique)';
COMMENT ON COLUMN USERS.password_hash IS 'BCrypt 단방향 암호화된 비밀번호';
COMMENT ON COLUMN USERS.nickname IS '사용자 표시용 닉네임';
COMMENT ON COLUMN USERS.role IS '권한 (ROLE_USER, ROLE_ADMIN)';
COMMENT ON COLUMN USERS.default_region_level1 IS '기본 거주지 시·도 (예: 서울특별시)';
COMMENT ON COLUMN USERS.default_region_level2 IS '기본 거주지 시·군·구 (예: 관악구)';
COMMENT ON COLUMN USERS.default_age IS '기본 만 나이 (예: 25)';


-- --------------------------------------------------------------------
-- 2. 사용자 Gemini API 키 테이블 (USER_API_KEYS)
-- 회원별 BYOK API 키를 AES-256-GCM으로 양방향 암호화하여 1인 1키 저장
-- --------------------------------------------------------------------
CREATE TABLE USER_API_KEYS (
    key_id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                 NUMBER             NOT NULL,
    encrypted_key           VARCHAR2(512)      NOT NULL,
    iv_salt                 VARCHAR2(64)       NOT NULL,
    is_active               CHAR(1)            DEFAULT 'Y' NOT NULL,
    created_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_keys_user UNIQUE (user_id),
    CONSTRAINT fk_keys_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE,
    CONSTRAINT ck_keys_active CHECK (is_active IN ('Y', 'N'))
);

COMMENT ON TABLE  USER_API_KEYS IS '회원별 Gemini API 키 보관 테이블 (AES-256 암호화)';
COMMENT ON COLUMN USER_API_KEYS.encrypted_key IS 'AES-256 알고리즘으로 암호화된 API 키';
COMMENT ON COLUMN USER_API_KEYS.iv_salt IS '암호화 복호화에 사용되는 초기화 벡터(IV) 및 솔트';
COMMENT ON COLUMN USER_API_KEYS.is_active IS '키 활성화 여부 (Y / N)';


-- --------------------------------------------------------------------
-- 3. 상담 세션 테이블 (CHAT_SESSIONS)
-- 독립된 히스토리 탭에서 목록으로 보여줄 상담 단위
-- ID는 분산 환경과 프론트엔드 연동이 용이한 UUID(36자) 사용
-- --------------------------------------------------------------------
CREATE TABLE CHAT_SESSIONS (
    session_id              VARCHAR2(36)       PRIMARY KEY,
    user_id                 NUMBER             NOT NULL,
    title                   VARCHAR2(200 CHAR) NOT NULL,
    region_level1           VARCHAR2(50 CHAR)  NOT NULL,
    region_level2           VARCHAR2(50 CHAR),
    age                     NUMBER(3),
    created_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
);

COMMENT ON TABLE  CHAT_SESSIONS IS '상담 세션 마스터 테이블';
COMMENT ON COLUMN CHAT_SESSIONS.session_id IS '상담 세션 UUID (36자리 문자열)';
COMMENT ON COLUMN CHAT_SESSIONS.user_id IS '회원 ID (FK)';
COMMENT ON COLUMN CHAT_SESSIONS.title IS '상담 제목 (첫 질문 요약 또는 자동 생성)';
COMMENT ON COLUMN CHAT_SESSIONS.region_level1 IS '상담 시점의 시·도';
COMMENT ON COLUMN CHAT_SESSIONS.region_level2 IS '상담 시점의 시·군·구';


-- --------------------------------------------------------------------
-- 4. 대화 메시지 테이블 (CHAT_MESSAGES)
-- 세션 내에서 오간 질문, AI 답변, 추천 정책 카드, 근거 구절 영속화
-- --------------------------------------------------------------------
CREATE TABLE CHAT_MESSAGES (
    message_id              VARCHAR2(36)       PRIMARY KEY,
    session_id              VARCHAR2(36)       NOT NULL,
    sender_type             VARCHAR2(20)       NOT NULL,
    content                 CLOB               NOT NULL,
    route                   VARCHAR2(50),
    intents_json            VARCHAR2(200),
    selected_policy_id      VARCHAR2(50),
    candidates_json         CLOB,
    evidence_json           CLOB,
    resources_json          CLOB,
    created_at              TIMESTAMP          DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES CHAT_SESSIONS(session_id) ON DELETE CASCADE,
    CONSTRAINT ck_messages_sender CHECK (sender_type IN ('USER', 'ASSISTANT'))
);

COMMENT ON TABLE  CHAT_MESSAGES IS '상담 세부 대화 및 AI 응답 데이터';
COMMENT ON COLUMN CHAT_MESSAGES.message_id IS '메시지 UUID (36자리 문자열)';
COMMENT ON COLUMN CHAT_MESSAGES.session_id IS '소속 상담 세션 ID (FK)';
COMMENT ON COLUMN CHAT_MESSAGES.sender_type IS '발화자 구분 (USER / ASSISTANT)';
COMMENT ON COLUMN CHAT_MESSAGES.content IS '사용자 질문 또는 AI 답변 텍스트 본문';
COMMENT ON COLUMN CHAT_MESSAGES.route IS '질문 라우팅 (situation_search, specific_policy 등)';
COMMENT ON COLUMN CHAT_MESSAGES.intents_json IS '질문 의도 목록 JSON (예: ["benefit", "application"])';
COMMENT ON COLUMN CHAT_MESSAGES.selected_policy_id IS '선택된 정책 ID (예: local:WLF00006618)';
COMMENT ON COLUMN CHAT_MESSAGES.candidates_json IS '추천된 정책 카드 배열 JSON (CLOB)';
COMMENT ON COLUMN CHAT_MESSAGES.evidence_json IS 'AI 답변의 근거 원문 구절 배열 JSON (CLOB)';
COMMENT ON COLUMN CHAT_MESSAGES.resources_json IS '공식 링크 및 첨부파일 다운로드 URL JSON (CLOB)';


-- --------------------------------------------------------------------
-- 5. 성능 최적화 인덱스 (INDEXES)
-- --------------------------------------------------------------------

-- 사용자의 세션 목록을 최신순(내림차순)으로 빠르게 조회
CREATE INDEX idx_sessions_user_updated ON CHAT_SESSIONS(user_id, updated_at DESC);

-- 세션의 전체 대화 내용을 시간순(오름차순)으로 빠르게 로드
CREATE INDEX idx_messages_session_created ON CHAT_MESSAGES(session_id, created_at ASC);


-- --------------------------------------------------------------------
-- 6. 시험용 더미 데이터 (DDL 실행 후 1회 실행)
-- 실제 로그인/암호화 연동에 사용할 수 없는 테스트 전용 값입니다.
-- --------------------------------------------------------------------
INSERT INTO USERS (
    email, password_hash, nickname, role,
    default_region_level1, default_region_level2, default_age
) VALUES (
    'tester@example.com', '$2a$10$dummy.password.hash.for.testing.only', '복지테스터',
    'ROLE_USER', '서울특별시', '관악구', 29
);

INSERT INTO USERS (
    email, password_hash, nickname, role,
    default_region_level1, default_region_level2, default_age
) VALUES (
    'admin@example.com', '$2a$10$dummy.admin.hash.for.testing.only', '관리자테스트',
    'ROLE_ADMIN', '경기도', '수원시', 35
);

INSERT INTO USER_API_KEYS (
    user_id, encrypted_key, iv_salt, is_active
)
SELECT user_id, 'DUMMY_ENCRYPTED_API_KEY_DO_NOT_USE', 'DUMMY_IV_SALT', 'Y'
FROM USERS
WHERE email = 'tester@example.com';

INSERT INTO CHAT_SESSIONS (
    session_id, user_id, title, region_level1, region_level2, age,
    created_at, updated_at
)
SELECT
    '11111111-1111-4111-8111-111111111111', user_id,
    '청년 월세 지원을 받을 수 있을까요?', '서울특별시', '관악구', 29,
    TIMESTAMP '2026-01-15 09:00:00', TIMESTAMP '2026-01-15 09:02:00'
FROM USERS
WHERE email = 'tester@example.com';

INSERT INTO CHAT_SESSIONS (
    session_id, user_id, title, region_level1, region_level2, age,
    created_at, updated_at
)
SELECT
    '22222222-2222-4222-8222-222222222222', user_id,
    '긴급복지 지원 상담', '서울특별시', '관악구', 29,
    TIMESTAMP '2026-01-16 14:30:00', TIMESTAMP '2026-01-16 14:32:00'
FROM USERS
WHERE email = 'tester@example.com';

INSERT INTO CHAT_SESSIONS (
    session_id, user_id, title, region_level1, region_level2, age,
    created_at, updated_at
)
SELECT
    '33333333-3333-4333-8333-333333333333', user_id,
    '기초생활보장 제도 문의', '경기도', '수원시', 35,
    TIMESTAMP '2026-01-17 11:00:00', TIMESTAMP '2026-01-17 11:02:00'
FROM USERS
WHERE email = 'admin@example.com';

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
    '11111111-1111-4111-8111-111111111111',
    'USER', '서울 관악구에 사는 29세인데 청년 월세 지원을 받을 수 있을까요?',
    'situation_search', '["benefit","application"]', NULL, NULL, NULL, NULL,
    TIMESTAMP '2026-01-15 09:00:00'
);

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2',
    '11111111-1111-4111-8111-111111111111',
    'ASSISTANT',
    '거주 지역과 연령 기준으로 청년 월세 지원 사업을 확인해 볼 수 있습니다. 소득 및 임대차 계약 조건에 따라 자격이 달라질 수 있으니 관할 기관의 최신 공고를 확인해 주세요.',
    'situation_search', '["benefit","application"]', 'local:WLF00006618',
    '[{"policyId":"local:WLF00006618","name":"청년 월세 지원","region":"서울특별시"}]',
    '[{"text":"지원 대상 및 소득 기준은 사업 공고에 따라 다를 수 있습니다."}]',
    '[{"label":"복지로","url":"https://www.bokjiro.go.kr/"}]',
    TIMESTAMP '2026-01-15 09:02:00'
);

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
    '22222222-2222-4222-8222-222222222222',
    'USER', '갑작스럽게 실직해서 생활이 어려운데 긴급복지 지원을 신청할 수 있나요?',
    'specific_policy', '["crisis","application"]', 'local:WLF00000001',
    NULL, NULL, NULL, TIMESTAMP '2026-01-16 14:30:00'
);

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
    '22222222-2222-4222-8222-222222222222',
    'ASSISTANT',
    '긴급복지 지원은 위기 상황과 소득·재산 기준 등을 확인해 지원 여부를 결정합니다. 빠른 상담이 필요하면 보건복지상담센터 129 또는 관할 행정복지센터에 문의해 주세요.',
    'specific_policy', '["crisis","application"]', 'local:WLF00000001',
    '[{"policyId":"local:WLF00000001","name":"긴급복지 지원"}]',
    '[{"text":"위기 사유 및 가구의 소득·재산 기준을 확인합니다."}]',
    '[{"label":"보건복지상담센터","url":"https://www.129.go.kr/"}]',
    TIMESTAMP '2026-01-16 14:32:00'
);

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'cccccccc-cccc-4ccc-8ccc-ccccccccccc1',
    '33333333-3333-4333-8333-333333333333',
    'USER', '기초생활보장 제도의 신청 절차가 궁금합니다.',
    'specific_policy', '["benefit","application"]', NULL, NULL, NULL, NULL,
    TIMESTAMP '2026-01-17 11:00:00'
);

INSERT INTO CHAT_MESSAGES (
    message_id, session_id, sender_type, content, route, intents_json,
    selected_policy_id, candidates_json, evidence_json, resources_json, created_at
) VALUES (
    'cccccccc-cccc-4ccc-8ccc-ccccccccccc2',
    '33333333-3333-4333-8333-333333333333',
    'ASSISTANT',
    '주소지 관할 읍·면·동 행정복지센터에서 상담 및 신청할 수 있습니다. 가구의 소득·재산과 급여 종류에 따라 선정 기준이 다르므로 방문 전 필요한 서류를 문의해 주세요.',
    'specific_policy', '["benefit","application"]', 'local:WLF00000002',
    '[{"policyId":"local:WLF00000002","name":"국민기초생활보장"}]',
    '[{"text":"급여별 선정 기준에 따라 수급 여부를 결정합니다."}]',
    '[{"label":"복지로","url":"https://www.bokjiro.go.kr/"}]',
    TIMESTAMP '2026-01-17 11:02:00'
);

COMMIT;


