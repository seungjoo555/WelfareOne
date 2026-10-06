# WelfareOne

청년 복지정책 검색 및 안내 시스템의 터미널 프로토타입입니다.

## 실행

먼저 `.env.example`을 `.env`로 복사하고 Gemini API 키를 입력합니다.

```text
GEMINI_API_KEY=발급받은_API_키
GEMINI_MODEL=gemini-3.5-flash-lite
```

Anaconda Prompt에서 다음 명령을 실행합니다.

```powershell
conda activate welfareone
cd C:\ai_project01\WelfareOne
python -m app.main
```

현재 단계에서는 Gemini가 자연어 질문의 검색어와 복수 의도를 분석하고, 지역과 나이를
반영해 정책 후보를 검색합니다. 정책을 선택한 뒤에는 필요한 DB 원문 섹션만 사용하여
Gemini가 근거와 함께 자연어 답변을 생성합니다. 자격 예비 판정, LangGraph 및 FastAPI
연결은 다음 단계에서 추가합니다.
