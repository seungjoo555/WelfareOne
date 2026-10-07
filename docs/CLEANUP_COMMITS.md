# 폴더 구조 정리 커밋 설명 (팀 리뷰용)

기능을 빠르게 붙이는 동안 쌓인 **문서 불일치와 중복 코드**를 정리한 브랜치입니다. 커밋 5개로 나눴고, **검색·답변 동작은 바뀌지 않습니다**(API 응답 형식도 그대로). 커밋 순서대로 보면 각각 독립적으로 이해되고, 어느 커밋에서나 테스트가 통과합니다.

| # | 커밋 | 한 줄 요약 | 동작 변화 |
|---|---|---|---|
| 1 | `refactor:` 중복 코드 정리 | 같은 코드 3곳을 공용 모듈로 모음 | 없음 |
| 2 | `test:` 검색 흐름·재시도 테스트 | 1번에서 만든 모듈의 테스트 추가 | 없음(테스트만) |
| 3 | `feat:` 사람 라벨링 도구 | 평가용 후보 시트 생성 스크립트와 팀원 가이드 | 없음(새 파일만) |
| 4 | `docs:` README·설정 정리 | 낡은 README 갱신, 폴더별 안내 추가 | 없음 |
| 5 | `docs:` 이 문서 | 커밋별 설명 | 없음 |

---

## 1. `refactor:` 중복 코드를 공용 모듈로 정리

**바뀐 파일**
- 새 파일: `app/env.py`, `app/gemini_retry.py`, `app/search_pipeline.py`
- 수정: `app/question_analyzer.py`, `app/answer_service.py`, `app/api.py`, `app/cli.py`

**무엇이 바뀌나**

| 이전 | 이후 |
|---|---|
| `.env`를 읽는 함수가 `question_analyzer.py`와 `answer_service.py`에 똑같이 복사돼 있고, `api.py`는 다른 모듈의 비공개 함수(`_load_env_file`)를 가져다 씀 | `app/env.py`의 `load_env_file()` 한 곳 |
| Gemini 호출 재시도 루프(429·5xx일 때 1초, 2초 쉬고 재시도)가 분석기·답변 서비스에 거의 같은 모양으로 두 번 있음 | `app/gemini_retry.py`의 `call_with_retry()` 한 곳. 재시도 규칙과 오류 메시지는 그대로 |
| "검색 → LLM 관련도 재판정 → 실패 시 거리 기반 결과로 대신" 흐름이 `api.py` 엔드포인트 안에 60줄로 들어 있음 | `app/search_pipeline.py`의 `run_search()`. `api.py`는 이를 호출만 함 |

**기대효과**
- 수정할 곳이 한 곳이 됩니다. 예: 재시도 횟수·대기 시간을 바꿀 때 두 파일을 따로 고치다 어긋날 위험이 없습니다.
- `api.py` 엔드포인트가 짧아져 읽기 쉬워지고, 검색 흐름을 API 없이도 테스트할 수 있습니다.
- 이후 자격 판정·LangGraph를 붙일 때 같은 검색 흐름(`run_search`)을 그대로 재사용할 수 있습니다(계약서 16장 "노드 안에 로직 중복 금지"에 맞음).

**리뷰 포인트**
- `cli.py`(터미널)는 `run_search(..., judge=None)`로 호출하므로 **이전과 같은 결과**(재판정 없음)입니다.
- 로거 이름 `welfareone.api`를 유지했습니다(기존 테스트·로그 필터 호환).
- `models.py`, `config.py`, `main.py`, 계약서는 건드리지 않았습니다.

**확인**: `python -m unittest discover -s tests` (기존 89개 그대로 통과)

---

## 2. `test:` 검색 흐름·재시도 테스트 추가

**바뀐 파일**: `tests/test_search_pipeline.py` (새 파일, 10개 테스트)

**무엇을 확인하나**
- `run_search`: 재판정 없음 / 재판정 켬(후보 풀을 넓히고 관련 없는 후보를 접음) / 재판정 실패 시 거리 기반 3+3으로 대체 / 상황형이 아닌 질문은 재판정 건너뜀
- `call_with_retry`: 재시도 가능한 오류(503)는 1초·2초 쉬고 재시도, 400 같은 오류는 즉시 중단, 최대 횟수 후 포기, API 오류가 아닌 예외는 재시도 안 함
- `load_env_file`: 이미 있는 환경변수는 덮어쓰지 않음, 파일이 없어도 오류 없음

**기대효과**: 1번 커밋의 "동작이 바뀌지 않았다"를 테스트로 증명하고, 이후 실수로 재시도·대체 규칙을 깨면 바로 잡힙니다.

**확인**: `python -m unittest tests.test_search_pipeline -v`

---

## 3. `feat:` 사람 라벨링 도구

**바뀐 파일**: `scripts/make_labeling_sheet.py`, `tests/test_labeling_sheet.py`, `data/evaluation/situational_questions_template.csv`, `docs/labeling/labeling_guide.pdf`, `docs/labeling/labeling_guide.html`

**무엇이 바뀌나**
- 팀원이 쓴 상황형·구어체 질문(양식 CSV)을 넣으면 질문마다 후보 정책 12개를 뽑아 **라벨러별 시트**(점수·거리 숨김, 순서 섞음)와 **정답 키**를 만드는 스크립트
- 팀원에게 전달할 5쪽 가이드(PDF): 질문 쓰는 법, 0/1/2점 판정 기준, 역할 분담

**왜 필요한가**: 지금 정확도 수치는 모두 Gemini가 매긴 점수라 실제보다 좋게 나옵니다(AI 판정 일치율 81%). 사람이 만든 정답이 있어야 거리 기준값(0.55/0.50)과 후보 개수를 믿고 정할 수 있고, 이후 개선의 효과를 숫자로 비교할 수 있습니다.

**기대효과**
- 처음으로 상황형 질문의 정밀도·재현율을 사람 기준으로 잴 수 있습니다.
- 작성자와 라벨러를 분리하고 점수를 숨기는 규칙이 스크립트에 들어 있어 라벨 편향을 막습니다.

**리뷰 포인트**
- 기존 앱 코드를 수정하지 않는 **새 파일만** 추가합니다.
- 정답 키(`labeling_key_PRIVATE.csv`)는 `.gitignore`에 들어 있어(4번 커밋) 실수로 올라가지 않습니다. 라벨러에게도 공유하지 않습니다.
- 스크립트는 Gemini를 호출하므로 실행할 때 본인 `.env` 키가 필요합니다. 테스트는 Gemini를 호출하지 않습니다.

**확인**: `python -m unittest tests.test_labeling_sheet -v`

---

## 4. `docs:` README·설정 정리

**바뀐 파일**
- 수정: `README.md`, `frontend/README.md`, `.gitignore`
- 새 파일: `docs/README.md`, `data/evaluation/README.md`, `scripts/README.md`

**무엇이 바뀌나**

| 파일 | 이전 문제 | 이후 |
|---|---|---|
| `README.md` | 경로 `C:\ai_project01`, "터미널 프로토타입", "FastAPI는 다음 단계" | 현재 구조, 실행·테스트 명령, 환경 변수, BYOK 안내 |
| `frontend/README.md` | "mock 골격" | 현재 기능, `npm test`, mock 키워드, 폴더 구조 갱신 |
| `.gitignore` | `data/investigation/` 중복, 정답 키 보호 없음 | 중복 제거, 정답 키 파일 제외 추가 |
| `docs/README.md` (신규) | 문서 9개가 있는데 용도·공유 여부 안내 없음 | 문서별 용도·상태·공유 여부 표, 읽는 순서 |
| `data/evaluation/README.md` (신규) | 평가 파일 16개에 설명 없음 | 파일별 설명, 수정 금지 표시 |
| `scripts/README.md` (신규) | 현행과 구버전 스크립트가 섞여 있음 | 현행/구버전 구분(파일 이동 없음) |

**기대효과**
- 새로 합류한 팀원이 README만 보고 서버·프론트·테스트를 실행할 수 있습니다.
- 어떤 문서가 기준이고 어떤 것이 초안·개인 메모인지 헷갈리지 않습니다.
- 어떤 스크립트가 지금 쓰는 것인지 알 수 있어 구버전 적재기를 실수로 돌리는 일을 줄입니다.

**리뷰 포인트**: 코드 변경 없음. 파일 이동·삭제도 없습니다(재배치는 팀 합의 후 별도 진행).

---

## 5. `docs:` 이 문서

`docs/CLEANUP_COMMITS.md` 추가. 위 설명을 팀이 참고할 수 있게 남깁니다.

---

## 이번에 일부러 하지 않은 것

- `scripts/`·`tests/` 파일 이동(`legacy/`, `notebooks/`): 팀원 경로와 문서 속 명령이 바뀌므로 합의 후
- `app/models.py`, `app/config.py`, `app/main.py`, `docs/function_contracts.md` 수정
- 계약서 반영(`docs/contract_update_proposal.md`의 내용): 별도 합의 필요
- 개인 메모(`HANDOFF*.md`)와 이를 참조하는 `CHANGELOG_2026-10-06.md`, `HANDOFF_BRANCH.md`: 저장소에 올리지 않음
