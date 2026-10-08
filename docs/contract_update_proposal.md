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

상황형 질문(`route == situation_search`)에서만 판정하며, 이때 후보를 범위별 8개까지 판정해 관련 판정을 앞쪽 **최대 8개**(화면이 3개씩 쪽으로 넘겨 봄) + 무관 판정을 뒤쪽 최대 3개로 돌려줍니다(그 외에는 이전처럼 범위별 최대 3개). 판정 실패는 오류가 아니라 `relevance_checked=false`입니다. 새 오류 코드는 없습니다.
