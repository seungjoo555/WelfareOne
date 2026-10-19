# 계약서(function_contracts.md) 수정 제안 — 팀 검토용

상태: **제안**. 아래는 실제 구현과 계약서가 어긋난 부분이다. 계약서는 팀 합의 없이 바꾸지 않는 문서이므로 이 파일로 먼저 검토하고, 합의되면 `function_contracts.md`에 반영한다.
기준 코드: `app/api.py`, `app/search_service.py`, `app/repository.py`, `app/question_analyzer.py`, `app/answer_service.py` (2026-10-06).

## 1. 17장 FastAPI — 실제는 stateless 방식 (수정 필요)

계약서 표는 `/sessions` 계열이지만 현재 구현은 세션 없이 프론트가 `region`, `age`, 선택 정책을 들고 요청마다 보낸다. 제안: 현재 구현을 표에 추가하고 `/sessions` 계열은 "구현 예정"으로 표시한다.

| Method | URL | 역할 | 상태 |
|---|---|---|---|
| GET | `/health` | 서버 준비 확인 → `{"status": "ok"}` | 구현됨 |
| GET | `/regions` | 지역 목록 조회 | 구현됨 |
| POST | `/policies/search` | `{question, region:{level1, level2}, age}` → `{analysis, local_policies, national_policies}` | 구현됨 |
| GET | `/policies/{policy_id}` | → `{policy_id, title, region_text, sections}` | 구현됨 |
| POST | `/policies/{policy_id}/ask` | `{question, policy_title}` → `{route, intents, answer}` | 구현됨 |
| POST | `/sessions` 외 2개 | 세션·자격 확인 | 구현 예정 |

- `region.level2`가 없으면 `""`(null 아님). 5장 "값 없음은 null" 규칙의 예외이므로 5장에 한 줄 추가 제안.
- `/ask`는 `route != current_policy_question`이면 `answer: null`.
- 검색 결과가 없는 것은 오류가 아니라 200 + 빈 목록(`NO_SEARCH_RESULTS` 코드는 현재 쓰지 않음).

## 2. 17장 오류 코드 추가 (BYOK)

사용자 본인 Gemini 키를 헤더 `X-Gemini-Api-Key`로 받는 방식을 도입하면서 추가된 코드(HTTP 401):

```text
API_KEY_REQUIRED   사용자 키가 없고 서버 키 폴백도 꺼진 경우
INVALID_API_KEY    키 형식이 틀렸거나 Gemini가 거부한 경우(401/403, 또는 400 + "API key" 메시지)
```

- 서버 키 폴백은 환경변수 `WELFAREONE_ALLOW_SERVER_KEY=true`일 때만 동작(기본 꺼짐). 서버는 사용자 키를 저장·로깅하지 않는다.
- 오류 코드 목록(`INVALID_REQUEST` … `INTERNAL_ERROR`)에 위 두 개를 추가하고, 프론트 `ApiErrorCode`(`src/types/contract.ts`)와 맞춘다(이미 반영됨).

## 3. 8장 질문 분석 — 시그니처

계약서: `analyze_question(question, current_policy_id=None)`
실제: `analyze_question(question, current_policy_id=None, current_policy_title=None)`
제안: `current_policy_title` 인자를 계약서에 추가(선택 정책명을 분석 문맥에 넣어 후속 질문 판정을 돕는다).

## 4. 9장 정책 검색 — 거리 하한 (규칙 5 이행)

실제: `search_policies(question, region, age=None, local_top_k=3, national_top_k=3, per_scope=30, max_distance=0.60)`

- 규칙 5("관련 정책이 없으면 빈 목록, 억지로 개수를 채우지 않는다")를 이행하기 위해 `distance > max_distance`인 후보를 제외한다. `max_distance=None`이면 끈다(평가·튜닝용).
- 정책명 단어가 모두 질문에 들어 있으면(규칙 6) 거리와 무관하게 남긴다.
- 값 근거(평가 질문 280개 실측): top3 정답 266건 중 264건 보존(99.2%), 무의미 질문 7개는 모두 빈 결과. 임베딩 모델·DB가 바뀌면 `scripts/measure_search_distance.py`로 다시 측정한다.
- 제안: 9장 검색 규칙에 "9. 거리가 `max_distance`보다 먼 후보는 제외한다(기본 0.60)" 추가, 상수 위치(`search_service.py` vs `config.py`)는 담당자 협의.

### 4-1. 9장 — 키워드 재정렬 (규칙 8 이행)

실제: `search_policies(..., include_keywords=None, exclude_keywords=None)` 인자 추가. 질문 분석기의 `include_keywords`/`exclude_keywords`를 받아 **점수만 조정하고 후보는 걸러내지 않는다.**

- 키워드가 정책명에 있으면 +0.10, 요약 본문에만 있으면 +0.05(키워드당, 최대 3개까지). `exclude_keywords`는 같은 크기로 감점. 구("복지 지원 사업")는 단어로 쪼개고 "지원·사업·청년·비용" 같은 일반어와 1글자는 무시한다.
- 근거(평가 질문 75개, Gemini가 만든 키워드 사용): 불일치 후보를 제거하는 하드 필터는 정답 5/69(7.2%)를 잃어 채택하지 않았다. 가산점은 정답 손실 없이 top3 진입 69→71, 1위 60→63. 가산점을 더 키워도(0.20/0.10) 이득이 늘지 않았다(70/63).
- 한계: `exclude_keywords` 감점은 분석기가 실제로 내놓은 값이 0건이라 검증하지 못했다. 표본이 작아(75개) 값은 추후 재측정 대상이다.
- API(`POST /policies/search`)와 CLI가 분석 결과의 키워드를 그대로 넘긴다.

## 5. 10장 정책 상세 조회 — 부분 구현

계약서의 `get_policy_details(policy_id, sections)`는 아직 없다. 대신 API 구현을 위해 다음이 생겼다.

- `PolicyRepository.get_policy_meta(policy_id) -> dict | None` — `{"title", "region_text"}`(candidate_summary 메타데이터에서 읽음, 없으면 `None`)
- `GET /policies/{id}`가 `get_policy_sections`(문단)와 `get_policy_meta`(정책명·지역)를 합쳐 응답한다.

제안: 10장에 `get_policy_meta`를 7장 함수 계약(7.5)으로 추가하고, `get_policy_details`는 "API 계층에서 두 함수를 합쳐 구현"으로 정리한다. `repository.py` 담당자 확인 필요.

## 6. 11장 자연어 답변 — 시그니처

계약서: `generate_answer(question, policy_id, contexts)`
실제: `generate_answer(question, policy_id, contexts, requested_sections=None, policy_title=None)`
제안: 두 선택 인자를 계약서에 추가(복수 의도 질문에서 사용할 섹션 지정, 정책명 표시).

## 7. 반영 순서 제안

1. 위 2·4번은 동작이 바뀐 항목이라 먼저 합의한다(오류 코드, 검색 규칙).
2. 1·3·5·6번은 문서를 코드에 맞추는 작업이라 합의 즉시 반영해도 된다.
3. 반영 후 `docs/HANDOFF.md`의 4절(API)·8절(알려진 이슈)도 함께 갱신한다(8절의 `title`/`region_text` null 이슈와 `requirements.txt` 항목은 이미 해결됨).

### 4-2. 9장 — 검색 응답의 관련도 재판정 필드 (제안)

`POST /policies/search` 응답에 필드 2개를 추가했습니다(기존 필드는 그대로, 추가만).

- `relevance_checked: bool` — 상황형 질문의 후보를 LLM으로 다시 판정했으면 true, 판정을 안 했거나 실패했으면 false
- `low_relevance_ids: list[str]` — 판정에서 "관련도 낮음"으로 본 `policy_id`. 목록의 후보는 응답에 그대로 포함되며 화면에서 접힌다.

상황형 질문(`route == situation_search`)에서만 판정하며, 이때 후보를 범위별 12개까지 판정해 **풀 전체**를 관련 판정 → 무관 판정(`low_relevance_ids`) 순으로 돌려줍니다(화면이 3개씩 쪽으로 넘겨 봄. 그 외 경로는 이전처럼 범위별 최대 3개). 판정 실패는 오류가 아니라 거리순 후보 전체와 `relevance_checked=false`입니다. 새 오류 코드는 없습니다.

### 4-3. 17장·11장 — 자주 묻는 질문 버튼(`/ask`의 `intent`)과 질문 유형별 답변 구성 (제안)

화면에서 정책을 선택하면 "지원 대상 / 지원 내용·금액 / 신청 방법 / 신청 기간 / 필요 서류 / 문의처" 버튼이 나옵니다. 기존 계약은 그대로 두고 **선택 필드만 추가**합니다.

- `POST /policies/{policy_id}/ask` 요청에 선택 필드 `intent` 추가. 허용값은 계약서 8장 intent 중 `eligibility`, `benefit`, `application`, `administrative`, `required_documents`, `contact`. 값이 있으면 질문 분석(Gemini)을 **건너뛰고** `route=current_policy_question`, `intents=[intent]`로 처리하며 `requested_sections`는 기존 규칙(`INTENT_SECTIONS`)으로 만든다. 값이 없으면 기존과 동일. 허용값 밖이면 422 `INVALID_REQUEST`.
- `generate_answer(question, policy_id, contexts, requested_sections=None, policy_title=None, intents=None)`: 선택 인자 `intents` 추가. 질문 유형별로 사람들이 보통 알고 싶어 하는 항목 순서(예: 지원 대상 = 누가 대상인가 → 제외·우선 대상 → 신청 전 확인할 점)를 프롬프트에 안내해 답변을 소제목+불릿으로 구성한다. 직접 입력한 질문도 분석기가 정한 `intents`로 같은 구성을 쓴다. 원문에 없는 항목은 지어내지 않고 한 줄로 묶어 "확인되지 않습니다"로 안내한다.
- 효과(실측, 1개 정책): 버튼 질문 응답 약 1.3~2.6초, 직접 입력(분석 약 1.4초 + 답변 약 1.8초 = 약 3.2초)보다 빠르다.

## 8. LLM 공급자와 사용자 키 우선순위 (제안, 2026-10-19)

상태: **제안**. 서버가 기본 LLM(예: 자체 호스팅 Qwen)을 제공하되, 지금처럼 사용자가 본인 Gemini 키를 넣어 쓰는 방식(BYOK)은 그대로 유지하기 위한 규칙이다. 기존 계약은 바꾸지 않고 **공급자 선택 규칙과 조회용 엔드포인트만 추가**한다.

### 8-1. 공급자 선택 우선순위 (질문 분석·관련도 판정·답변 공통)

| 순서 | 조건 | 사용하는 LLM |
|---|---|---|
| 1 | 요청에 `X-Gemini-Api-Key` 헤더가 있음 | **항상** 그 키의 Gemini (서버 설정과 무관) |
| 2 | 헤더 없음 + 서버 기본 공급자(`LLM_PROVIDER`)가 설정되어 있음 | 서버 기본 공급자 (예: Qwen) |
| 3 | 헤더 없음 + 기본 공급자 없음 + `WELFAREONE_ALLOW_SERVER_KEY=true` | 서버 `GEMINI_API_KEY`의 Gemini (기존 폴백) |
| 4 | 위에 모두 해당 없음 | 401 `API_KEY_REQUIRED` |

- 1번이 가장 높다. 사용자가 키를 보냈는데 서버 Qwen으로 처리하거나, 반대로 사용자 키가 Qwen으로 전달되는 일은 없어야 한다(테스트로 고정).
- 형식이 틀린 키는 2~3번으로 넘어가지 않고 401 `INVALID_API_KEY`다(기존 동작 유지).
- 한 요청 안에서 공급자를 섞지 않는다. 질문 분석, 관련도 판정, 답변은 같은 공급자를 쓴다.
- 서버는 사용자 키를 저장·로깅하지 않고 요청 처리 중에만 사용한다(기존 규칙 유지).

### 8-2. 오류 코드

새 코드는 없다. 의미만 정리한다.

```text
API_KEY_REQUIRED    8-1의 4번: 사용자 키도, 서버 기본 공급자도, 서버 키 폴백도 없음
INVALID_API_KEY     사용자 키 형식 오류 또는 Gemini가 거부(기존과 동일)
LLM_RATE_LIMITED    공급자 무관하게 429(요청 한도 초과)
LLM_RESPONSE_INVALID 공급자 무관하게 응답이 스키마·허용값 검증을 통과하지 못함
```

공급자별 예외는 서버 내부에서 공통 예외로 바꾼 뒤 위 코드로 변환한다. API 응답에는 공급자 이름이나 원본 오류 메시지를 싣지 않는다.

### 8-3. 17장 FastAPI — `GET /config` 추가

프론트가 "키 입력을 필수로 받을지, 선택으로 둘지" 정하기 위한 조회용 엔드포인트다. 인증·상태 없음, 민감 정보 없음.

| Method | URL | 역할 | 응답 |
|---|---|---|---|
| GET | `/config` | 서버 LLM 사용 가능 여부 | 아래 참고 |

```json
{
  "server_llm": true,
  "server_llm_provider": "qwen",
  "user_key_provider": "gemini"
}
```

- `server_llm`: 헤더 없이도 요청을 처리할 수 있으면 `true`(8-1의 2번 또는 3번). 4번 상태면 `false`.
- `server_llm_provider`: `"qwen"`, `"gemini"`, 없으면 `null`.
- `user_key_provider`: 사용자가 헤더로 보낼 수 있는 키의 종류. 현재는 항상 `"gemini"`.
- 프론트: `server_llm=true`이면 키 입력을 "선택 사항(본인 Gemini 키로 사용)"으로 안내하고, `false`이면 기존처럼 필수 입력이다. 이 요청이 실패하면 기존과 같이 필수 입력으로 동작한다.

### 8-4. 18장 파일 역할 추가

| 파일 | 역할 |
|---|---|
| `app/llm_client.py` | LLM 호출 공통 인터페이스(`generate_json`), Gemini·Qwen 구현, 공급자 공통 예외 |

- `question_analyzer.py`, `answer_service.py`, `relevance_judge.py`는 `genai.Client`를 직접 만들지 않고 `LLMClient`를 주입받는다. 프롬프트와 출력 검증은 공급자와 무관하게 공통이다.
- 기존 함수 시그니처(`analyze_question`, `generate_answer` 등)와 `QuestionAnalyzer(api_key=...)`, `AnswerService(api_key=...)` 호출 방식은 유지한다(호환).

### 8-5. 환경변수 (`.env.example`에 추가)

```text
LLM_PROVIDER=qwen          # 서버 기본 공급자. 비우면 8-1의 3~4번 동작(현재와 동일)
QWEN_BASE_URL=http://...   # OpenAI 호환 엔드포인트 (vLLM, Ollama 등)
QWEN_MODEL=...
```

API 키·주소는 코드에 쓰지 않는다. `LLM_PROVIDER`를 설정하지 않으면 현재 동작이 그대로다.

### 8-6. 합의가 필요한 항목과 대안

**1. Qwen 실행 방식·위치** — 이 PC(RTX A4000 16GB, 리랭커·임베딩이 약 3GB 사용)에는 LM Studio가 있고, 설치된 `Qwen3-Embedding-8B`는 임베딩 전용이라 텍스트 생성에 쓸 수 없다. 생성용 Qwen3 instruct 계열(4B/8B, Q4_K_M)을 추가로 받아야 한다.

| 안 | 방식 | 장점 | 단점 |
|---|---|---|---|
| A (추천 시작점) | 이 PC의 LM Studio/Ollama (OpenAI 호환 서버) | 설치가 쉽고 JSON 스키마 출력 지원 | 동시 요청 처리량이 낮고 PC가 켜져 있어야 함 |
| B | vLLM (WSL2/Docker) | 구조화 출력·처리량 최고 | Windows 네이티브 불가, 설정 번거로움 |
| C | 팀 공용/클라우드 GPU 서버의 vLLM | 모두 같은 엔드포인트 | 비용·운영·접근 제어 |
| D | 호스티드 Qwen API | 서버 불필요 | 질문이 외부로 전송됨, 키·비용 관리 |
| E | 서버 프로세스 안에서 `transformers` 직접 로드 | 구성요소 하나 | 동시 요청·메모리·속도 문제 (비추천) |

모두 OpenAI 호환 주소(`QWEN_BASE_URL`)로 붙으므로 A로 시작하고 B/C로 옮겨도 코드는 바뀌지 않는다.

**2. 구조화 출력·재시도** — 결정: **서버 제약 디코딩**(JSON 스키마를 요청에 실어 보냄: LM Studio/Ollama `response_format`·`format`, vLLM `guided_json`)을 기본으로 한다. 대안(JSON 모드 + 검증 재시도, 프롬프트만으로 요청, 함수 호출)은 호환성 확인용 보조로만 둔다. 의미 검증(route·intents 허용값 등)은 지금처럼 코드가 공급자와 무관하게 수행한다.

- 네트워크·서버 오류(429, 5xx): 기존과 같이 최대 3회(1초, 2초 대기)
- 검증 실패(스키마·허용값 위반): 오류 내용을 알려 주고 `temperature`를 낮춰 **1회** 재시도, 그래도 실패하면 `LLM_RESPONSE_INVALID`
- 단계별 실패 정책: 질문 분석 실패 → 오류, 관련도 판정 실패 → 거리·리랭커 순 폴백(오류 아님), 답변 실패 → 오류

**3. 기본 공급자를 Qwen으로 올리는 조건** — 평가셋(`welfareone_rag_eval_280.csv`)에서 질문 분석 정확도(route·intents), 관련도 판정 일치율, 답변 근거 포함률이 Gemini 대비 어느 수준이면 기본으로 쓸지. 기준에 못 미치면 선택 옵션으로만 둔다.

**4. `GET /config` 응답 필드명** (`server_llm`, `server_llm_provider`, `user_key_provider`) 확정.

### 8-7. 반영 순서

1. 8-1·8-3·8-6을 팀이 먼저 합의한다(동작이 바뀌는 항목).
2. 합의 후 `function_contracts.md` 17장 표(`GET /config`)와 18장 표(`app/llm_client.py`)에 반영하고, 17장 오류 코드 설명에 8-2를 반영한다.
3. 코드는 (a) 동작 변경 없는 `LLMClient` 도입(**완료**, 2026-10-19) → (b) Qwen 구현 → (c) 선택 로직과 `/config` → (d) 프론트 순서로 나눠 진행한다. (a)는 기존 테스트가 그대로 통과해야 한다.

### 8-8. 실측 메모 (2026-10-19, RTX A4000 16GB, LM Studio, 질문 5개·판정 1건 수준의 소규모 확인)

| 모델 | 크기 | 호출당 시간 | 확인된 문제 |
|---|---|---|---|
| gemma-4-12b-qat (추론 모델) | 7GB | 4~19초 (`reasoning_effort: none` 필요) | GPU 포화로 느림, 대역 확인용으로만 사용 |
| **qwen3-4b-2507** | 2.5GB | 1.6~3.5초 | 의도(`intents`)를 과다 지정, 제외 키워드를 엉뚱하게 채움(예: "월세가 부담돼요" → 제외 `주택`·`전세`), `route` 오분류 |
| **qwen3-8b** | 5GB (컨텍스트 8192) | 1.0~4.2초 | 검색어·제외 키워드는 정확. `route` 오분류 일부, 답변에 지침 문구가 섞임 |

- 4B는 제외 키워드 오류가 검색 점수 감점으로 이어질 수 있어 **기본 후보에서 제외**하고, 8B를 기준으로 평가셋 비교를 진행하는 것을 제안한다.
- 코드에서 공급자와 무관하게 보정하도록 추가: `specific_policy`인데 `policy_name`이 없으면 `situation_search`로 바꾸고, "알려줘·정책·추천" 같은 요청어는 키워드에서 제거한다.
- 모델을 계속 메모리에 올려 두어야 한다. 처음 요청에 모델 로딩이 걸리면 100초를 넘길 수 있다(`lms load <모델> --gpu max -c 8192 --parallel 2`, TTL 없음).
- 전체 요청 시간(질문 분석 + 검색 + 리랭커 + 판정): Gemini 약 3~6초, Qwen3-8B 약 5~11초. 관련도 판정은 가끔 실패해 거리·리랭커 순 폴백으로 처리된다(판정 제한시간 10초).
- 평가셋 280개 기준의 정량 비교(route·intents 정확도, 판정 일치율, 근거 포함률)는 아직 하지 않았다.
