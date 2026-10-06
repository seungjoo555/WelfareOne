# 자격 판정(3단계) 설계 초안

상태: **초안, 팀 합의 전**. 계약서 12~13장을 구현 가능한 수준으로 구체화한 제안이다. 합의된 항목만 계약서에 반영한 뒤 구현한다.
관련: `docs/function_contracts.md` 12~14장, `docs/HANDOFF.md` 9절 3~4번.

## 1. 데이터 현실 (설계 전제)

- `target_criteria` 섹션은 문단 1,837개, 정책 1,418개 전부에 있다.
- 원문은 **정형 값이 아니라 자유 서술**이다. 한 문단에 정책명, "생애주기: 청소년, 청년", "대상 유형: 저소득", "지원 대상:", "선정 기준:"이 섞여 있고 번호·기호 목록(`1)`, `①`, `*`)으로 조건이 이어진다.
- 조건 유형이 다양하다: 연령("만 19세 이상 49세 이하"), 거주 기간("6개월 이상 관내 주민등록"), 소득("기준중위소득 150% 이하"), 장애 등급·점수("기능제한 360점 이상"), 수급자 여부, 혼인·출산 상태, 직업(농어민) 등.
- 따라서 정규식만으로 추출하면 놓치는 조건이 많고, LLM만 쓰면 판정이 흔들린다. **추출은 LLM, 비교는 코드**로 나눈다(계약서 16장 원칙과 동일).

## 2. 전체 구조

```text
target_criteria 문단 ──(Gemini, 구조화 출력)──▶ list[EligibilityCondition]
                                                       │ (policy_id 단위로 캐시)
사용자 프로필 dict ──────────────────────────────▶ evaluate_eligibility() [순수 Python]
                                                       ▼
                                  EligibilityResult (overall_status, results, missing_fields)
```

- `extract_conditions`: LLM 1회 호출. 같은 `policy_id`는 결과를 캐시해 반복 호출을 피한다(메모리 dict로 시작, 필요하면 파일 캐시).
- `evaluate_eligibility`: LLM을 쓰지 않는다. 같은 입력이면 항상 같은 결과(테스트 가능).
- API 후보: `POST /policies/{id}/eligibility` — 요청 `{profile}` → 응답 `EligibilityResult`. `GET`으로 `missing_fields`만 먼저 조회하는 방식도 가능(7절 결정 사항).

## 3. 파일과 모델

| 파일 | 내용 |
|---|---|
| `app/eligibility_service.py` | `extract_conditions`, `evaluate_eligibility` (+ Gemini 호출·재시도는 `question_analyzer.py`의 패턴 재사용: `temperature=0`, JSON 스키마 출력, 429/5xx 재시도) |
| `app/models.py` | `EligibilityCondition`, `ConditionResult`, `EligibilityResult` 추가. **통합 담당자와 협의 후 수정**(HANDOFF 규칙 4) |
| `tests/test_eligibility_service.py` | 비교 로직 단위 테스트(가짜 조건으로) + 추출은 Gemini를 가짜로 대체한 테스트 |

`EligibilityCondition`은 계약서 12장 그대로(`field, operator, value, minimum, maximum, required, source_text`).

## 4. 합의가 필요한 값 형식 (병목)

### field 목록
계약서의 12개를 그대로 쓰되, 프로필에서 **어떻게 값을 받는지**를 먼저 정한다.

| field | 프로필 값 형식(제안) | operator(제안) | 비고 |
|---|---|---|---|
| `age` | int | `between`(minimum/maximum), `gte`, `lte` | 이미 입력받음 |
| `region` | `{level1, level2}` | `in_region` | 이미 입력받음. 정책 지역은 DB 메타데이터(`region_level1/2`)로 비교 가능 → **LLM 추출 불필요** |
| `employment_status` | `"employed" \| "unemployed" \| "student" \| "self_employed" \| "other"` | `equals`, `in` | 계약서 예시는 한글 "미취업"이므로 **코드값과 한글 라벨 중 택일** 필요. 제안: 코드값 저장 + 표시용 라벨 별도 |
| `income` | 기준중위소득 대비 비율(int, %) 또는 구간 선택 | `lte`, `gte` | 아래 "소득" 참고 |
| `household_size` | int | `equals`, `gte`, `lte` | |
| `household_type` | `"single" \| "couple" \| "single_parent" \| ...` | `equals`, `in` | |
| `marital_status` | `"single" \| "married" \| ...` | `equals` | |
| `housing_status` | `"homeless" \| "jeonse" \| "monthly_rent" \| "owner"` | `equals`, `in` | |
| `disability_status` | `"none" \| "registered"` (등급은 `other`) | `equals` | 민감 정보 |
| `student_status` | `"enrolled" \| "not_enrolled"` | `equals` | |
| `residency_period` | 개월 수(int) | `gte` | 정책 지역 거주 기간 |
| `other` | — | `unsupported` | **자동 판정하지 않음**(계약서 12장). 항상 `unknown` + 원문 그대로 안내 |

**소득**은 원문 기준이 제각각(기준중위소득 %, 연소득 금액, 월 건강보험료, 부부합산)이라 한 값으로 맞추기 어렵다. 제안: 1차 구현은 `income`을 **"기준중위소득 %"로 표기된 조건만** 자동 판정하고, 금액 기준·합산 소득은 `other`로 분류한다.

### operator 허용값 (제안)
`equals`, `in`, `gte`, `lte`, `between`, `in_region`, `unsupported`. 목록 밖 값은 추출 단계에서 `other`/`unsupported`로 강제한다.

### required 의미
- `required=true`: 충족해야 하는 필수 조건(AND)
- `required=false`: 우대·가산 조건 → 판정에는 반영하지 않고 안내만
- "~ 중 하나에 속하는 사람" 같은 **OR 조건**은 현재 모델(평면 목록)로 표현되지 않는다. 제안: 1차에서는 OR 묶음을 `other`로 두고 자동 판정에서 제외. 필요해지면 `group_id` 필드를 추가한다(계약서 변경 필요).

## 5. 판정 규칙 (`evaluate_eligibility`)

조건별 상태:
- 프로필에 해당 field 값이 없거나 `unknown` → `unknown` (+ `missing_fields`에 추가)
- 값이 있고 조건 만족 → `met`, 불만족 → `not_met`
- `field=other` / `operator=unsupported` → `unknown` (missing_fields에는 넣지 않음. 사용자가 답할 수 없는 조건이므로)

전체 상태(우선순위 순):
1. `required` 조건 중 `not_met`가 하나라도 있음 → `not_eligible`
2. 조건이 하나도 추출되지 않았거나 판정 가능한 조건이 없음 → `cannot_determine`
3. `required` 조건 중 `unknown`이 있음 → `needs_information` (`missing_fields` 채움)
4. 그 외(판정 가능한 required 조건이 모두 `met`) → `likely_eligible`

주의:
- `likely_eligible`이라도 `other` 조건이 있으면 "원문의 나머지 조건은 직접 확인" 문구를 함께 내려준다. 자격 충족을 확정하지 않는다(HANDOFF 규칙 7).
- `reason`은 값과 기준을 함께 적는다(예: "사용자 만 24세, 정책 기준 19~39세"). 사용자에게 보일 최종 문구는 프론트가 만든다(계약서 5장).
- 응답에 `disclaimer`는 넣지 않고 프론트의 `DISCLAIMER`를 쓴다.

## 6. 추출 단계(LLM) 지침

- 입력: 한 정책의 `target_criteria` 문단 전부(보통 1~2개). 출력: `EligibilityCondition` 목록, `source_text`에는 **원문에서 그대로 잘라 온 문장**을 넣는다(환각 방지·근거 표시용).
- 프롬프트 규칙: 원문에 없는 조건을 만들지 말 것 / 확신이 없으면 `other` / 숫자는 원문 단위 그대로(만 나이, 개월, %) / OR 조건은 `other`.
- 후처리(코드): field·operator가 허용값 밖이면 `other`로 교체, `minimum > maximum` 같은 모순은 `other`로 교체, `source_text`가 원문에 실제로 포함되는지 검사해 아니면 조건 폐기.
- `region`, `age`처럼 이미 DB 메타데이터로 확인되는 값은 LLM 결과보다 메타데이터를 우선한다(`age_known`, `age_status`, `region_level1/2` 활용).
- 호출 실패(429/5xx)는 `question_analyzer`와 같이 최대 3회 재시도 후 `QuestionAnalysisError`와 같은 계열의 서비스 오류로 올린다. API 오류 코드는 기존 `_llm_error` 매핑을 재사용.

## 7. 합의·결정이 필요한 사항 (체크리스트)

1. `employment_status` 등 코드값 확정(코드값 vs 한글 라벨) — **가장 먼저**
2. 소득 표현: "기준중위소득 %"로 1차 한정할지
3. OR 조건/우대 조건 표현: 1차는 `other` 처리로 시작할지, `group_id`를 계약서에 추가할지
4. 민감 항목(소득·장애·수급 여부)을 **어느 시점에, 어떤 안내 문구로** 묻고 저장하지 않을지(세션 메모리에만 보관 권장)
5. API 형태: `POST /policies/{id}/eligibility` 단일 호출 vs `missing_fields` 조회 + 평가 2단계
6. 추출 결과 캐시 위치(메모리 / 파일) 및 정책 DB 갱신 시 무효화 방법
7. 정확도 검증 방법: `welfareone_rag_eval_280.csv`는 답변 평가용이라 자격 판정 정답이 없다. 정책 20~30개를 사람이 라벨링한 골든셋을 만들지 여부

## 8. 구현 순서 (제안)

1. 위 7절 1~3번 합의 → 계약서 12~13장 갱신 → `models.py`에 모델 추가
2. `evaluate_eligibility` 먼저 구현 + 단위 테스트(LLM 없이 가능, 합의된 값만 있으면 바로 시작)
3. `extract_conditions` 구현: 실제 정책 20~30개로 결과를 눈으로 검토하며 프롬프트·후처리 조정
4. API 엔드포인트 추가(`api.py`) + `tests/test_api.py` 확장
5. 프론트: `missing_fields` → 동적 폼(모든 질문에 "모름"=`unknown`, 민감 항목은 이유 안내), 결과 화면(조건별 met/not_met/unknown 배지 + `source_text`)
6. 이후 `ConversationState.user_profile`/`missing_fields`와 연결(14~16장, LangGraph)

## 9. 리스크

- LLM 추출 오류가 `not_eligible`로 이어지면 사용자가 신청 기회를 잃는다 → **확신이 낮거나 모순이면 `other`/`unknown`으로 두고, `not_eligible`은 명확한 수치 불일치(나이·거주지 등)에서만** 내린다.
- 정책 원문이 바뀌면 캐시가 낡는다 → 7절 6번.
- 민감정보 입력 → 서버에 저장·로그하지 않는다(요청 로그에 프로필 값 남기지 않기).
