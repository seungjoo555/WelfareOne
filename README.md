# WelfareOne

청년 복지정책 맞춤 추천·안내 AI 에이전트. 사용자가 지역·나이와 자연어 질문을 입력하면 정책 후보를 찾아 주고,
선택한 정책의 공식 원문에 근거해 답변합니다. 자격 판정은 "예비 안내"이며 최종 확인은 해당 기관에서 합니다.

| 영역 | 기술 |
|---|---|
| 백엔드 | Python, FastAPI, ChromaDB 1.5.9, sentence-transformers(`Qwen/Qwen3-Embedding-0.6B`), Gemini(`google-genai`) |
| 프론트엔드 | React 18 + TypeScript + Vite 5, MSW(mock) |
| 데이터 | 복지로 공개 API → `data/processed` → ChromaDB (`data/chroma`, 저장소에 없음) |

## 폴더 구조

| 폴더 | 내용 |
|---|---|
| `app/` | 백엔드. `api.py`(FastAPI), `cli.py`(터미널), 검색·질문 분석·답변·관련도 판정 서비스 |
| `frontend/` | React 프론트엔드 (자세한 내용은 `frontend/README.md`) |
| `docs/` | 계약서와 설계·인수인계 문서 (목록은 `docs/README.md`) |
| `tests/` | 백엔드 단위 테스트와 평가 노트북 |
| `scripts/` | 데이터 수집·적재와 측정 스크립트 (목록은 `scripts/README.md`) |
| `data/` | `raw`(원본 XML), `processed`(가공 JSONL), `evaluation`(평가 데이터), `chroma`(벡터 DB, Git 제외) |

## 준비

1. Python 환경을 만들고 패키지를 설치합니다. (이 저장소는 Python 3.11 이상에서 동작하며, 개발 PC에서는 3.14로 검증했습니다.)

   ```powershell
   pip install -r requirements.txt
   ```

2. 벡터 DB(`data/chroma`)를 받아 이 폴더에 둡니다. DB는 용량이 커서 Git에 없습니다.
3. 임베딩 모델(`Qwen/Qwen3-Embedding-0.6B`)이 Hugging Face 캐시에 있어야 합니다(`local_files_only`로 읽습니다).
4. Gemini API 키는 **웹 화면의 "API 키" 입력창**에 본인 키를 넣어 씁니다(BYOK). 키는 브라우저에만 저장되고 요청마다 헤더(`X-Gemini-Api-Key`)로 전달됩니다.

## 실행

```powershell
# 백엔드 (프로젝트 루트에서)
uvicorn app.api:app --port 8000      # 시작 때 모델 로딩으로 시간이 걸립니다

# 프론트엔드
cd frontend
npm install
npm run dev                          # 실제 연결은 frontend/.env.local 에 VITE_USE_MOCK=false

# 터미널 프로토타입 (서버 키가 필요하므로 .env의 GEMINI_API_KEY 사용)
python -m app.main
```

## 환경 변수 (`.env`, 공유·커밋 금지. 예시는 `.env.example`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | 없음 | 터미널 프로토타입과 서버 키 폴백에서만 사용 |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | 사용할 Gemini 모델 |
| `WELFAREONE_ALLOW_SERVER_KEY` | 꺼짐 | `true`면 사용자 키가 없을 때 서버 키로 처리 (공개 배포에서는 끄세요) |
| `WELFAREONE_LLM_RERANK` | 켜짐 | `0`이면 상황형 질문의 LLM 관련도 재판정을 끕니다 |

## 테스트

```powershell
python -m unittest discover -s tests                                   # 백엔드
$env:WELFAREONE_REAL_TESTS="1"; python -m unittest tests.test_real_smoke -v   # 실제 DB·모델 스모크(선택)
cd frontend; npm test; npm run build                                   # 프론트 테스트·타입 검사·빌드
```

## 팀 작업 규칙

- 필드명·함수 입출력·API는 `docs/function_contracts.md`(공통 계약서)를 따르고, 임의로 바꾸지 않습니다.
- `app/models.py`, `app/config.py`, `app/main.py`는 팀 협의 없이 수정하지 않습니다.
- `.env`, API 키, `data/chroma`는 커밋하지 않습니다.
