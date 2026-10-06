# WelfareOne Frontend

청년 복지정책 안내 서비스의 React 프론트엔드입니다. 현재는 **mock 응답으로 동작하는 골격**(Phase 0~1 + 일부 Phase 2)이며,
FastAPI 백엔드가 준비되면 환경변수만 바꿔 실제 API로 전환합니다.

## 실행

Node.js LTS(18 이상)가 필요합니다. conda 환경(`welfareone`)과는 별개로 설치해야 합니다.

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
```

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버 (기본값: mock 모드) |
| `npm run typecheck` | TypeScript 타입 검사 |
| `npm run build` | 타입 검사 + 배포용 빌드(`dist/`) |

## mock ↔ 실제 백엔드 전환

- `npm run dev`의 기본값은 mock입니다(`src/config.ts`). 백엔드, Gemini 키, ChromaDB 없이도 화면 개발이 가능합니다.
- 실제 FastAPI를 쓰려면 `frontend/.env.local`을 만들고 `VITE_USE_MOCK=false`를 적습니다(`.env.example` 참고).
  `/api/*` 요청은 `vite.config.ts` 프록시가 `http://localhost:8000/*`로 전달합니다(CORS 설정 불필요).
- 백엔드 실행 예시(FastAPI 구현 후): `uvicorn app.api:app --port 8000`

### mock에서 상황 바꿔 보기

질문에 아래 키워드를 넣으면 응답이 달라집니다.

| 키워드 | 동작 |
|---|---|
| `없음` | 검색 결과 0건 |
| `에러` | 429 `LLM_RATE_LIMITED` |
| `날씨` | (정책 선택 후) 현재 정책 질문이 아님 → "다른 정책 찾기" |
| `근거없음` | (정책 선택 후) `grounded=false` 경고 |

시·도 목록에 "세종특별자치시"(하위 지역 없음)가 있어 시·군·구 비활성 케이스를 확인할 수 있습니다.

## 구조

```
src/
├─ api/          client.ts(타임아웃·오류 변환), regions.ts, policies.ts
├─ mocks/        handlers.ts(MSW 가짜 응답), browser.ts
├─ types/        contract.ts(계약서 타입), chat.ts(메시지 종류)
├─ constants/    sections.ts(섹션 라벨·순서), text.ts(오류·안내 문구)
├─ state/        conversation.ts(useReducer, 계약서 ConversationState 형태)
└─ features/
   ├─ start/     StartForm, RegionSelect
   ├─ chat/      ChatPage, MessageList, MessageItem, ChatInput, ExampleChips, CurrentPolicyBar
   └─ policy/    CandidateGroup, CandidateCard, AnswerBubble, EvidenceToggle, ResourceButtons, RawSectionsTab
```

## 백엔드와 합의가 필요한 부분 (`src/types/contract.ts`의 `[초안]`)

- `POST /policies/search`: 요청 `{question, region, age}` → 응답 `{analysis, local_policies, national_policies}`
- `GET /policies/{policy_id}`: 응답에 `title`, `sections` 포함 (없으면 404 `POLICY_NOT_FOUND`)
- `POST /policies/{policy_id}/ask`: 요청 `{question, policy_title}` → 응답 `{route, intents, answer}`.
  `route`가 `current_policy_question`이 아니면 `answer`는 `null`
- `region.level2`가 없으면 `null`이 아니라 `""`(DB가 광역 정책을 `region_level2 == ""`로 저장)
- 오류 응답은 계약서 17장 형식 `{error: {code, message, details}}`

## 아직 구현하지 않은 것

- 자격 판정 동적 폼(`missing_fields` 기반): 백엔드 `extract_conditions`/`evaluate_eligibility` 구현 후 추가
- 사이드바 대화 목록, 세션 저장(`/sessions`): 1차 범위 제외
- 예시 질문(`constants/text.ts`)은 임시값입니다. 검색이 잘 되는 질문으로 교체하세요.
