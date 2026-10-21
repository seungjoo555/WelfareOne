# WelfareOne 팀 개발 공통 계약서

이 문서는 WelfareOne의 백엔드 함수, FastAPI, React, LangGraph를 서로 연결하기 위한 공통 기준이다.
팀원과 AI 도구는 코드를 작성하기 전에 이 문서를 확인하고, 여기 정의된 이름과 자료형을 임의로 변경하지 않는다.

## 1. 현재 구현 범위

현재 구현된 기능:

- ChromaDB 연결
- 지역 목록 조회
- 지역과 나이를 반영한 정책 벡터 검색
- 지자체와 중앙부처 정책 후보 분리 반환
- 정책 후보 선택
- 선택한 정책의 섹션별 원문 조회
- Gemini 질문 분석 및 검색어 생성
- 선택 정책의 공식 원문 기반 Gemini 답변 생성
- 터미널 실행

현재 구현되지 않은 기능:

- 자격 조건 추출과 예비 판정
- 대화 상태 저장
- FastAPI
- React
- LangGraph

## 2. 기술 및 데이터베이스 고정값

| 항목 | 값 |
|---|---|
| Python | 3.11 |
| ChromaDB | 1.5.9 |
| sentence-transformers | 6.0.1 |
| 임베딩 모델 | `Qwen/Qwen3-Embedding-0.6B` |
| ChromaDB 경로 | `data/chroma` |
| 컬렉션명 | `welfare_policy_sections_qwen_v3` |
| 거리 방식 | cosine |
| 현재 레코드 수 | 11,850 |

ChromaDB를 만든 모델과 질문을 임베딩하는 모델은 반드시 동일해야 한다.

## 3. 공통 명명 규칙

Python 내부 필드와 API JSON에는 영문 snake_case를 사용한다.

| 이름 | 의미 | 예시 |
|---|---|---|
| `policy_id` | 정책 고유 ID | `local:WLF00006618` |
| `source_id` | 원천 API 정책 ID | `WLF00006618` |
| `title` | 정책명 | `성남시 청년 면접준비 지원사업` |
| `source` | 정책 출처 범위 | `local`, `national` |
| `region_level1` | 시·도 | `서울특별시` |
| `region_level2` | 시·군·구 | `관악구` |
| `region_text` | 표시용 전체 지역 | `서울특별시 관악구` |
| `age` | 사용자 만 나이 | `24` |
| `question` | 사용자 원문 질문 | `월세가 부담돼요` |
| `search_query` | LLM이 정리한 검색용 문장 | `청년 월세 주거비 지원` |
| `intent` | 질문 목적 | `benefit` |
| `intents` | 질문에 포함된 전체 목적(최대 3개) | `["benefit", "application"]` |
| `route` | 대화 처리 경로 | `situation_search` |
| `section` | 정책 문단 유형 | `target_criteria` |
| `current_policy_id` | 현재 선택된 정책 ID | `local:WLF...` |

정책 식별과 연결에는 정책명이 아니라 항상 `policy_id`를 사용한다.

## 4. DB 섹션 고정값

허용되는 섹션은 다음과 같다.

```text
candidate_summary
overview
target_criteria
benefit
application
documents
contact_source
administrative
```

| 섹션 | 내용 |
|---|---|
| `candidate_summary` | 후보 검색용 정책 요약 |
| `overview` | 정책 개요 |
| `target_criteria` | 지원 대상과 선정 기준 |
| `benefit` | 지원 내용과 금액 |
| `application` | 신청 방법과 절차 |
| `documents` | 필요·제출 서류 관련 원문 |
| `contact_source` | 문의처와 공식 출처 |
| `administrative` | 기간, 수정일, 법령 등 행정 정보 |

현재 실제 DB의 서류 섹션명은 `documents`이다. `attachments`, `required_documents` 등의 이름으로 바꾸지 않는다.

## 5. 공통 값 없음 규칙

- 단일 값이 없으면 Python에서는 `None`, JSON에서는 `null`을 사용한다.
- 목록이 없으면 `[]`를 사용한다.
- 객체가 없으면 `{}`를 사용한다.
- 데이터가 없다는 이유로 임의의 문자열 `없음`, `해당 없음`을 내부 값으로 넣지 않는다.
- 화면에 표시할 문구는 CLI 또는 프론트엔드에서 만든다.

## 6. 현재 구현 모델

### RegionSelection

```python
@dataclass
class RegionSelection:
    level1: str
    level2: str = ""
```

예시:

```python
RegionSelection(level1="서울특별시", level2="관악구")
```

### PolicyCandidate

```python
@dataclass
class PolicyCandidate:
    policy_id: str
    title: str
    region_text: str
    score: float
    distance: float
    scope: str
    summary: str
    metadata: dict
    reasons: list[str]
```

### PolicySection

```python
@dataclass
class PolicySection:
    section: str
    chunk_index: int
    document: str
```

공통 모델은 `app/models.py`에 둔다. 다른 파일에서 같은 의미의 모델을 중복 정의하지 않는다.

## 7. 현재 구현 함수 계약

### 7.1 지역 목록 조회

```python
PolicyRepository.list_regions() -> dict[str, list[str]]
```

출력 예시:

```python
{
    "서울특별시": ["관악구", "용산구"],
    "경기도": ["성남시"]
}
```

### 7.2 정책 벡터 조회

```python
PolicyRepository.vector_query(
    query_vector: list[float],
    where: dict,
    limit: int,
) -> dict
```

이 함수는 ChromaDB의 원시 결과를 반환하며 서비스 외부에서 직접 사용하지 않는다.

### 7.3 정책 상세 섹션 조회

```python
PolicyRepository.get_policy_sections(
    policy_id: str,
) -> list[PolicySection]
```

정책을 찾지 못하면 빈 목록 `[]`를 반환한다.

### 7.4 기존 호환용 통합 정책 검색

```python
PolicySearchService.search(
    question: str,
    region: RegionSelection,
    age: int | None = None,
    top_k: int = 5,
    per_scope: int = 30,
) -> list[PolicyCandidate]
```

기존 평가 코드와 호출부의 호환성을 위해 유지한다. 신규 코드는 9장의 `search_policies()`를 사용한다.

나이 필터 규칙:

- 나이가 없으면 연령 필터를 적용하지 않는다.
- DB의 `age_status`가 `exact`인 경우만 최소·최대 나이를 적용한다.
- 복잡하거나 불명확한 연령 조건은 후보에서 제거하지 않는다.

## 8. 질문 분석 계약(구현됨)

### 함수

```python
analyze_question(
    question: str,
    current_policy_id: str | None = None,
) -> QuestionAnalysis
```

### route 허용값

```text
situation_search
specific_policy
current_policy_question
```

- `situation_search`: 사용자가 상황을 말하며 정책 추천을 요청
- `specific_policy`: 특정 정책을 직접 언급
- `current_policy_question`: 이미 선택한 정책에 관한 후속 질문

### intent 허용값

```text
policy_search
policy_overview
eligibility
benefit
application
required_documents
contact
administrative
```

### 출력 모델

```python
@dataclass
class QuestionAnalysis:
    route: str
    policy_name: str | None
    search_query: str
    intent: str
    intents: list[str]
    requested_sections: list[str]
    include_keywords: list[str]
    exclude_keywords: list[str]
    confidence: float
```

출력 예시:

```json
{
  "route": "situation_search",
  "policy_name": null,
  "search_query": "출산 후 산모의 산후조리 회복 비용 지원",
  "intent": "policy_search",
  "intents": ["policy_search"],
  "requested_sections": ["candidate_summary"],
  "include_keywords": ["산후조리", "산모 회복"],
  "exclude_keywords": ["출산 진료비", "분만 병원비"],
  "confidence": 0.96
}
```

분석 규칙:

1. DB 정책명 전체가 질문에 있으면 코드로 `specific_policy`를 우선 판정한다.
2. 정책명 일부만 언급되면 후보를 찾고, 하나로 확정할 수 없으면 사용자 선택을 요청한다.
3. 일반 상황 질문은 `situation_search`로 분류한다.
4. `current_policy_id`가 있고 현재 정책에 대한 후속 질문이면 `current_policy_question`으로 분류한다.
5. Gemini가 반환한 값은 허용값과 자료형을 코드로 검증한다.
6. `intent`는 대표 의도이며 `intents`의 첫 번째 값과 같아야 한다.
7. `intents`는 최대 3개이며, 같은 정책에 대한 복수 질문을 담는다.
8. `requested_sections`는 Gemini가 아니라 코드가 `intents`를 기준으로 생성한다.

## 9. 정책 검색 계약(구현됨)

### 함수

```python
search_policies(
    question: str,
    region: RegionSelection,
    age: int | None = None,
    local_top_k: int = 3,
    national_top_k: int = 3,
    per_scope: int = 30,
) -> PolicySearchResult
```

Gemini 질문 분석을 연결한 뒤에는 `QuestionAnalysis.search_query`를 `question` 인자로 전달한다. `include_keywords`와 `exclude_keywords`를 이용한 재정렬은 후속 구현 항목이다.

### 출력 모델

```python
@dataclass
class PolicySearchResult:
    local_policies: list[PolicyCandidate]
    national_policies: list[PolicyCandidate]
```

JSON 예시:

```json
{
  "local_policies": [
    {
      "policy_id": "local:WLF00006618",
      "title": "성남시 청년 면접준비 지원사업",
      "region_text": "경기도 성남시",
      "score": 1.25,
      "summary": "면접 준비 비용을 지원하는 정책"
    }
  ],
  "national_policies": []
}
```

검색 규칙:

1. 지자체와 중앙부처 정책을 하나의 순위로 섞지 않는다.
2. 지자체 결과는 선택한 시군구, 시도 광역 정책을 포함한다.
3. 중앙부처 결과는 전국 단위 정책만 포함한다.
4. 각 목록은 관련도 순으로 정렬한다.
5. 관련 정책이 없으면 빈 목록을 반환하며 억지로 개수를 채우지 않는다.
6. 정책명 전체 일치는 강하게 우대한다.
7. 상황 질문의 일반 단어 일부 일치는 과도하게 우대하지 않는다.
8. 제외 의도는 후보 감점 또는 재정렬에 사용한다.

## 10. 정책 상세 조회 계약(개선 예정)

```python
get_policy_details(
    policy_id: str,
    sections: list[str] | None = None,
) -> PolicyDetail | None
```

출력 예시:

```json
{
  "policy_id": "local:WLF00006618",
  "title": "성남시 청년 면접준비 지원사업",
  "region_text": "경기도 성남시",
  "sections": {
    "overview": ["정책 원문"],
    "target_criteria": ["정책 원문"],
    "benefit": ["정책 원문"],
    "application": ["정책 원문"],
    "documents": [],
    "contact_source": ["정책 원문"]
  }
}
```

정책 ID가 없으면 `None`을 반환한다. API 계층에서 이를 404로 변환한다.

## 11. 자연어 답변 계약(구현됨)

```python
generate_answer(
    question: str,
    policy_id: str,
    contexts: list[PolicySection],
) -> AnswerResult
```

출력 모델:

```python
@dataclass
class AnswerResult:
    answer: str
    policy_id: str
    used_sections: list[str]
    evidence: list[str]
    resources: list[PolicyResource]
    grounded: bool
```

`resources`는 LLM이 생성하지 않고 선택 정책의 전체 원문에서 코드로 추출한다. 답변
생성에는 질문 의도에 해당하는 섹션만 사용하지만 자료 링크 조회에는 전체 섹션을 사용한다. 각 항목은
`label`, `resource_type`, `url`을 가지며 `resource_type`은 `attachment`,
`website`, `legal_reference` 중 하나이다. 프론트엔드는 첨부파일에는 다운로드,
나머지 URL에는 바로가기 버튼을 표시한다.

복수 의도 질문에서는 `requested_sections`에 포함된 원문을 함께 전달하며,
`evidence`는 실제 전달된 원문에 존재하는 구절만 최종 결과에 유지한다.

출력 예시:

```json
{
  "answer": "이 정책은 성남시에 거주하는 19~39세 취업 준비 청년을 대상으로 합니다.",
  "policy_id": "local:WLF00006618",
  "used_sections": ["target_criteria"],
  "evidence": ["성남시 거주 19~39세 취업준비 청년"],
  "grounded": true
}
```

답변 규칙:

1. 제공된 공식 원문만 사용한다.
2. 금액, 나이, 기간, 지역, 비율은 원문 그대로 사용한다.
3. 원문에 없는 내용을 추측하지 않는다.
4. 근거가 없으면 `grounded=false`로 반환한다.
5. 자격 충족을 임의로 확정하지 않는다.
6. 답변과 함께 사용한 섹션 및 근거를 반환한다.

## 12. 자격 조건 추출 계약(구현 예정)

```python
extract_conditions(
    policy_id: str,
    target_criteria: list[str],
) -> list[EligibilityCondition]
```

조건 모델:

```python
@dataclass
class EligibilityCondition:
    field: str
    operator: str
    value: object | None
    minimum: float | None
    maximum: float | None
    required: bool
    source_text: str
```

예시:

```json
{
  "field": "employment_status",
  "operator": "equals",
  "value": "미취업",
  "minimum": null,
  "maximum": null,
  "required": true,
  "source_text": "성남시 거주 19~39세 미취업 청년"
}
```

초기 공통 field 후보:

```text
age
region
employment_status
income
household_size
household_type
marital_status
housing_status
disability_status
student_status
residency_period
other
```

복잡하거나 코드로 안전하게 비교할 수 없는 조건은 `field=other`로 두고 자동 충족 판정을 하지 않는다.

## 13. 자격 비교 계약(구현 예정)

```python
evaluate_eligibility(
    conditions: list[EligibilityCondition],
    user_profile: dict,
) -> EligibilityResult
```

조건 상태 허용값:

```text
met
not_met
unknown
```

전체 상태 허용값:

```text
likely_eligible
not_eligible
needs_information
cannot_determine
```

출력 예시:

```json
{
  "overall_status": "needs_information",
  "results": [
    {
      "field": "age",
      "status": "met",
      "reason": "사용자 만 24세, 정책 기준 19~39세",
      "source_text": "19~39세 청년"
    },
    {
      "field": "employment_status",
      "status": "unknown",
      "reason": "취업 상태가 입력되지 않았습니다.",
      "source_text": "미취업 청년"
    }
  ],
  "missing_fields": ["employment_status"]
}
```

자격 확인은 최종 수급 자격 판정이 아니라 공개 정책 원문에 근거한 예비 안내이다.

## 14. 공통 대화 상태 계약(구현 예정)

터미널, FastAPI 세션 및 LangGraph에서 같은 의미의 상태 구조를 사용한다.

```python
@dataclass
class ConversationState:
    session_id: str
    region: RegionSelection
    age: int | None
    latest_question: str
    route: str | None
    intent: str | None
    local_candidates: list[PolicyCandidate]
    national_candidates: list[PolicyCandidate]
    current_policy_id: str | None
    user_profile: dict
    missing_fields: list[str]
```

초기 상태 예시:

```json
{
  "session_id": "uuid",
  "region": {
    "level1": "서울특별시",
    "level2": "관악구"
  },
  "age": 24,
  "latest_question": "월세가 부담돼요",
  "route": null,
  "intent": null,
  "local_candidates": [],
  "national_candidates": [],
  "current_policy_id": null,
  "user_profile": {
    "age": 24,
    "region_level1": "서울특별시",
    "region_level2": "관악구"
  },
  "missing_fields": []
}
```

## 15. 대화 흐름 계약

핵심 흐름:

```text
지역·기본정보 입력
→ 사용자 질문 분석
→ 상황 검색 / 특정 정책 조회 / 현재 정책 후속 질문
→ 지자체·중앙부처 후보 제시
→ 사용자 정책 선택
→ 상세 설명 또는 자격 확인
→ 부족한 정보 추가 질문
→ 조건별 예비 판정
→ 신청 방법·서류·문의처 안내
→ 추가 질문 / 다른 정책 / 새 상황 / 종료
```

후속 행동 허용값:

```text
ask_current_policy
choose_other_policy
start_new_situation
end_conversation
```

## 16. LangGraph 연결 원칙

LangGraph 노드는 기존 서비스 함수를 호출해야 하며 검색·판정 로직을 노드 안에 중복 작성하지 않는다.

```python
def search_policy_node(state):
    result = search_service.search_policies(
        search_query=state.search_query,
        region=state.region,
        age=state.age,
        include_keywords=state.include_keywords,
        exclude_keywords=state.exclude_keywords,
    )
    return {
        "local_candidates": result.local_policies,
        "national_candidates": result.national_policies,
    }
```

판단 역할:

- 자연어 의미 판단: Gemini 또는 질문 분석 함수
- 명확한 값 검사: 일반 Python 코드
- 판단 결과에 따른 다음 단계 이동: LangGraph

## 17. FastAPI 계약 초안

FastAPI(및 Spring Boot BFF)에서 사용하는 공통 REST API 계약이다. 모든 엔드포인트는 구조화된 JSON을 반환하며, 필드명은 `snake_case`를 준수한다.

### 17.1. 엔드포인트 목록

| 도메인 | Method | URL | 역할 | 인증 헤더 |
|---|---|---|---|---|
| **시스템/지역** | GET | `/health` | 서버 및 AI 모델 준비 상태 확인 | 선택 |
| | GET | `/regions` | 지원 가능 지역 목록 조회 | 없음 |
| **정책/RAG** | POST | `/policies/search` | 정책 후보 검색 (지자체/중앙부처 분리) | `X-Gemini-Api-Key` 또는 Bearer |
| | GET | `/policies/{policy_id}` | 정책 상세 섹션 원문 조회 | 없음 |
| | POST | `/policies/{policy_id}/ask` | 선택 정책 원문 기반 질문 답변 | `X-Gemini-Api-Key` 또는 Bearer |
| **회원/인증** | POST | `/auth/signup` | 신규 회원가입 | 없음 |
| | POST | `/auth/login` | 로그인 및 JWT 토큰 발급 | 없음 |
| | GET | `/auth/me` | 내 프로필 정보 및 기본 지역/나이 조회 | `Authorization: Bearer` |
| | POST | `/auth/logout` | 로그아웃 (세션 정리) | `Authorization: Bearer` |
| **Gemini 키** | PUT | `/users/api-key` | 사용자 Gemini API 키 등록/수정 (암호화 저장) | `Authorization: Bearer` |
| | GET | `/users/api-key/status`| API 키 등록 여부 및 갱신일시 확인 | `Authorization: Bearer` |
| | DELETE | `/users/api-key` | 등록된 Gemini API 키 삭제 | `Authorization: Bearer` |
| **대화/로그** | GET | `/sessions` | 회원의 이전 상담 세션 목록 조회 (히스토리 탭) | `Authorization: Bearer` |
| | POST | `/sessions` | 신규 상담 세션 생성 (지역/나이 설정) | 선택 (비회원은 Local) |
| | GET | `/sessions/{session_id}` | 특정 세션 상세 및 전체 대화 로그 조회 | `Authorization: Bearer` |
| | DELETE| `/sessions/{session_id}` | 특정 상담 세션 및 대화 로그 삭제 | `Authorization: Bearer` |
| | PATCH | `/sessions/{session_id}/title` | 상담 세션 제목 수정 | `Authorization: Bearer` |
| | POST | `/sessions/{session_id}/messages` | 세션 내 대화 메시지 처리 및 로그 영속화 | `Authorization: Bearer` |
| | POST | `/sessions/{session_id}/eligibility` | 자격 확인 진행 (단계 1) | `Authorization: Bearer` |

---

### 17.2. 인증 및 헤더 규칙

1. **사용자 JWT 인증 (`Authorization`)**:
   - `Authorization: Bearer <jwt_access_token>`
   - 회원 전용 API(프로필, API 키 관리, 클라우드 히스토리 동기화) 호출 시 필수.
2. **BYOK (Bring Your Own Key) 전달 (`X-Gemini-Api-Key`)**:
   - `X-Gemini-Api-Key: <gemini_api_key>`
   - 비회원 또는 클라이언트가 직접 AI 키를 전달할 때 사용. 서버는 키를 로그에 기록하지 않음.
   - 로그인 회원의 경우 백엔드(Spring Boot/DB)에 암호화 저장된 키가 자동 주입되므로 클라이언트가 직접 보낼 필요 없음.

---

### 17.3. 주요 요청 및 응답 본문 규격

#### ① 회원가입 (`POST /auth/signup`)
```json
// Request
{
  "email": "user@example.com",
  "password": "Password123!",
  "nickname": "청년희망",
  "default_region_level1": "서울특별시",
  "default_region_level2": "관악구",
  "default_age": 25
}
// Response (201 Created)
{
  "user_id": 1,
  "email": "user@example.com",
  "nickname": "청년희망",
  "created_at": "2026-10-15T12:00:00Z"
}
```

#### ② 로그인 (`POST /auth/login`)
```json
// Request
{
  "email": "user@example.com",
  "password": "Password123!"
}
// Response (200 OK)
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "user": {
    "user_id": 1,
    "email": "user@example.com",
    "nickname": "청년희망",
    "default_region_level1": "서울특별시",
    "default_region_level2": "관악구",
    "default_age": 25,
    "has_api_key": true
  }
}
```

#### ③ Gemini API 키 관리 (`PUT /users/api-key`, `GET /users/api-key/status`)
```json
// PUT /users/api-key Request
{
  "api_key": "AIzaSyD-example-key-value"
}
// Response
{
  "status": "ok",
  "has_api_key": true,
  "updated_at": "2026-10-15T12:05:00Z"
}

// GET /users/api-key/status Response (보안상 실제 키 문자열은 반환하지 않음)
{
  "has_api_key": true,
  "updated_at": "2026-10-15T12:05:00Z"
}
```

#### ④ 대화 세션 및 로그 조회 (`GET /sessions`, `GET /sessions/{session_id}`)
```json
// GET /sessions Response (목록)
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "관악구 청년 월세 지원 상담",
    "region_level1": "서울특별시",
    "region_level2": "관악구",
    "age": 25,
    "created_at": "2026-10-15T10:00:00Z",
    "updated_at": "2026-10-15T10:30:00Z"
  }
]

// GET /sessions/{session_id} Response (상세 및 대화 로그 전체 복원)
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "관악구 청년 월세 지원 상담",
  "region_level1": "서울특별시",
  "region_level2": "관악구",
  "age": 25,
  "messages": [
    {
      "message_id": "msg-001",
      "sender_type": "user",
      "content": "월세가 부담스러운데 지원받을 수 있을까요?",
      "created_at": "2026-10-15T10:00:00Z"
    },
    {
      "message_id": "msg-002",
      "sender_type": "assistant",
      "content": "관악구 및 중앙부처에서 지원하는 월세 지원 정책 3건을 찾았습니다.",
      "route": "situation_search",
      "intents": ["benefit"],
      "candidates": [
        {
          "policy_id": "local:WLF00006618",
          "title": "청년 월세 한시 특별지원",
          "scope": "시군구",
          "summary": "..."
        }
      ],
      "evidence": [],
      "resources": [],
      "created_at": "2026-10-15T10:00:05Z"
    }
  ]
}
```

---

### 17.4. 오류 응답 규격

API 실패 시 항상 통일된 오류 구조를 반환한다.

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "details": null
  }
}
```

#### 공통 오류 코드 목록:

```text
-- 클라이언트 요청 오류
INVALID_REQUEST           -- 파라미터 유효성 검증 실패 (422/400)
INVALID_REGION            -- 지원하지 않는 지역명
POLICY_NOT_FOUND          -- 정책 ID 미존재 (404)
SESSION_NOT_FOUND         -- 상담 세션 ID 미존재 (404)
NO_SEARCH_RESULTS         -- 검색 결과 없음

-- 인증 및 보안 오류
UNAUTHORIZED              -- 로그인 필요 또는 유효하지 않은 JWT 토큰 (401)
FORBIDDEN                 -- 타인의 상담 세션 접근 등 권한 없음 (403)
INVALID_CREDENTIALS       -- 로그인 아이디/비밀번호 불일치 (401)
USER_ALREADY_EXISTS       -- 이미 가입된 이메일 계정 (409)
TOO_MANY_LOGIN_ATTEMPTS   -- 같은 이메일로 로그인 연속 실패(5회/10분) 시 잠시 제한 (429)
INVALID_API_KEY           -- 잘못된 Gemini API 키 (401)
API_KEY_REQUIRED          -- AI 질의에 필요한 API 키 누락 (401)

-- 서버 및 AI 모델 오류
LLM_RESPONSE_INVALID      -- AI 응답 파싱 실패 (502)
LLM_RATE_LIMITED          -- Gemini API 호출 한도 초과 (429)
DATABASE_ERROR            -- DB(ChromaDB 또는 Oracle) 조회 실패 (500)
INTERNAL_ERROR            -- 서버 내부 예기치 않은 오류 (500)
```


## 18. 파일 역할과 담당 범위

| 파일 | 역할 |
|---|---|
| `app/config.py` | 경로, 모델명, 컬렉션명 등 설정 |
| `app/models.py` | 모든 공통 입출력 모델 |
| `app/repository.py` | ChromaDB 접근만 담당 |
| `app/search_service.py` | 정책 검색과 정렬 |
| `app/question_analyzer.py` | Gemini 질문 분석 |
| `app/answer_service.py` | 원문 기반 자연어 답변 |
| `app/eligibility_service.py` | 조건 추출과 예비 판정 |
| `app/state.py` | 공통 대화 상태 |
| `app/graph.py` | LangGraph 노드와 흐름 연결 |
| `app/api.py` 또는 `app/routers/` | FastAPI 엔드포인트 |
| `app/cli.py` | 터미널 테스트 입출력 |
| `tests/` | 단위·통합 테스트 |

같은 의미의 코드를 여러 파일에 중복 작성하지 않는다.

## 19. 팀 작업 규칙

1. 한 파일의 주 담당자는 한 명으로 정한다.
2. `models.py`, `config.py`, `main.py`는 통합 담당자와 협의 없이 수정하지 않는다.
3. 함수 시그니처나 공통 필드를 바꾸려면 이 문서를 먼저 수정하고 팀에 알린다.
4. 담당자는 실행 예시와 예상 출력을 함께 전달한다.
5. API 키를 코드에 직접 작성하지 않는다.
6. `.env`는 공유하지 않고 `.env.example`만 공유한다.
7. DB 원본과 컬렉션명은 임의로 변경하거나 재적재하지 않는다.
8. AI가 작성한 코드는 담당자가 실행하고 입출력을 검증한 후 통합한다.
9. 현재 작동하는 터미널 프로토타입을 유지하면서 기능을 추가한다.
10. 사용하지 않는 대규모 리팩터링은 통합 전에 하지 않는다.

## 20. 완료 기준

각 기능은 다음 조건을 만족해야 완료로 본다.

- 문서에 정의된 입력을 받는다.
- 문서에 정의된 출력 형식을 반환한다.
- 값이 없는 경우 공통 규칙을 따른다.
- 예시 입력을 실행한 결과를 공유한다.
- API 키나 개인 경로가 코드에 포함되지 않는다.
- 다른 담당 파일을 수정하지 않는다.
- 오류가 발생해도 프로그램 전체가 비정상 종료되지 않는다.

## 21. AI 도구에 함께 전달할 지시문

팀원이 ChatGPT, Gemini, Codex 등으로 코드를 작성할 때 다음 문장을 요청과 함께 전달한다.

```text
WelfareOne 프로젝트의 docs/function_contracts.md를 먼저 읽고 작업하세요.
문서에 정의된 필드명, route, intent, section, 함수 입출력 형식을 변경하지 마세요.
공통 모델은 app/models.py에서 가져오고 같은 모델을 다시 정의하지 마세요.
DB 접근은 app/repository.py, 정책 검색은 app/search_service.py를 재사용하세요.
담당 파일 외의 코드는 필요한 경우에도 먼저 변경 이유를 설명하세요.
구현 후 실행 방법, 예시 입력, 실제 출력, 남은 제한 사항을 알려주세요.
```

## 22. 현재 다음 작업 순서

```text
1. 이 계약서를 팀 전체가 검토하고 확정
2. 정책 검색 결과를 지자체·중앙부처로 분리
3. Gemini 질문 분석 구현
4. 선택 정책의 원문 기반 답변 구현
5. 공통 대화 상태 구현
6. 자격 조건 추출과 예비 판정 구현
7. FastAPI 검색 API 연결
8. React 최소 화면 연결
9. LangGraph로 대화 흐름 통합
```
