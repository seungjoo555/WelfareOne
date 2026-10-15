# WelfareOne 프로젝트 컨텍스트 (Context Guide)

본 문서는 WelfareOne 시스템의 핵심 계약, 데이터 규격, 인터페이스 연동 규칙을 한눈에 참조할 수 있도록 요약한 컨텍스트 문서입니다.

> **상세 계약서 원본**: [`docs/function_contracts.md`](file:///c:/work/WelfareOne/docs/function_contracts.md)  
> **신규 인증/히스토리 계획서**: [`docs/AUTH_AND_HISTORY_PLAN.md`](file:///c:/work/WelfareOne/docs/AUTH_AND_HISTORY_PLAN.md)  
> **기존 전체 코드 분석서**: [`docs/codebase_analysis.md`](file:///c:/work/WelfareOne/docs/codebase_analysis.md)

---

## 1. 기술 스택 및 포트 구성

| 구성 요소 | 기술 스택 | 포트 / 경로 | 역할 |
|---|---|---|---|
| **Frontend** | React 18, TypeScript, Vite | `http://localhost:5173` | 사용자 웹 UI, 챗봇, 히스토리 탭 |
| **Business Backend (신규)** | Java 17, Spring Boot 3.2.4, MyBatis 3.0.3 | `http://localhost:8080` | 회원인증(JWT), API키 암호화 관리, 히스토리 DB 저장, BFF 프록시 |
| **AI/RAG Server (기존)** | Python 3.11, FastAPI, Uvicorn | `http://localhost:8000` | 질문 분석, ChromaDB 벡터 검색, 원문 기반 답변 생성 |
| **Database (신규)** | Oracle Database | `1521` (XE/FREE) | 회원 정보, 암호화된 API 키, 상담 세션 및 메시지 영속화 |
| **Vector DB (기존)** | ChromaDB | `data/chroma` | 11,850개 복지 정책 원문 섹션 및 임베딩 벡터 저장 |

---

## 2. 공통 명명 규칙 및 고정 규격 (Contract Rules)

1. **명명 규칙**:
   - Python 및 REST API JSON 필드는 반드시 **`snake_case`** 사용 (임의 변경 금지).
   - Java 내부 필드는 `camelCase`를 쓰되, JSON 직렬화/역직렬화 시 `@JsonProperty`를 통해 snake_case와 매핑.
2. **핵심 필드 명세**:
   - `policy_id`: 정책 고유 식별자 (예: `local:WLF00006618`, `national:PL001`)
   - `route`: 질문 의도 라우팅 (`situation_search` | `specific_policy` | `current_policy_question`)
   - `intents`: 세부 의도 배열 (`policy_search`, `eligibility`, `benefit`, `application`, `documents`, `contact` 등)
   - `region`: `{"level1": "서울특별시", "level2": "관악구"}` (광역 정책은 `level2`가 빈 문자열 `""`)
   - `age`: 사용자 만 나이 (정수 또는 `null`)
3. **보안 규칙 (BYOK)**:
   - Gemini API 키는 클라이언트에 노출하지 않고 Spring Boot에서 AES-256 암호화 저장.
   - FastAPI 호출 시 `X-Gemini-Api-Key` 헤더로 주입.

