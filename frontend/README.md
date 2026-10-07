# WelfareOne Frontend

청년 복지정책 안내 서비스의 React 프론트엔드입니다. 기본값은 mock 응답이고, 환경변수만 바꾸면 실제 FastAPI 백엔드에 연결됩니다.
기능: 지역·나이 입력, 채팅형 정책 검색, 후보 카드(관련도 낮은 후보 접기), 정책별 후속 질문, 라이트/다크 테마,
상담 기록(브라우저 localStorage), 사용자 본인 Gemini 키 입력(BYOK, 브라우저에만 저장).

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
| `npm test` | 단위 테스트(node:test, 상담 기록·관련도 접기) |
| `npm run typecheck` | TypeScript 타입 검사 |
| `npm run build` | 타입 검사 + 배포용 빌드(`dist/`) |

## mock ↔ 실제 백엔드 전환

- `npm run dev`의 기본값은 mock입니다(`src/config.ts`). 백엔드, Gemini 키, ChromaDB 없이도 화면 개발이 가능합니다.
- 실제 FastAPI를 쓰려면 `frontend/.env.local`을 만들고 `VITE_USE_MOCK=false`를 적습니다(`.env.example` 참고).
  `/api/*` 요청은 `vite.config.ts` 프록시가 `http://localhost:8000/*`로 전달합니다(CORS 설정 불필요).
- 백엔드 실행: 프로젝트 루트에서 `uvicorn app.api:app --port 8000`. 사용자 키가 없으면 401 `API_KEY_REQUIRED`가 오고 화면이 키 입력창을 엽니다.

### mock에서 상황 바꿔 보기

질문에 아래 키워드를 넣으면 응답이 달라집니다.

| 키워드 | 동작 |
|---|---|
| `없음` | 검색 결과 0건 |
| `에러` | 429 `LLM_RATE_LIMITED` |
| `날씨` | (정책 선택 후) 현재 정책 질문이 아님 → "다른 정책 찾기" |
| `근거없음` | (정책 선택 후) `grounded=false` 경고 |
| `관련낮음` | 거리 0.50 초과 후보가 "더 보기"로 접히는지 확인 |
| `재판정` | 서버 LLM 재판정 결과(`relevance_checked`)대로 접히는지 확인 |
| `키없음` / `키오류` | 401 `API_KEY_REQUIRED` / `INVALID_API_KEY` (키 입력창 확인) |

시·도 목록에 "세종특별자치시"(하위 지역 없음)가 있어 시·군·구 비활성 케이스를 확인할 수 있습니다.

## 구조

```
src/
├─ api/          client.ts(타임아웃·오류 변환), regions.ts, policies.ts
├─ mocks/        handlers.ts(MSW 가짜 응답), browser.ts
├─ types/        contract.ts(계약서 타입), chat.ts(메시지 종류)
├─ constants/    sections.ts(섹션 라벨·순서), text.ts(오류·안내 문구)
├─ state/        conversation.ts(useReducer, 계약서 ConversationState 형태), useConversationHistory.ts
├─ storage/      history.ts(상담 기록 localStorage 저장)
├─ utils/        apiKey.ts, theme.ts, relevance.ts(관련도 낮은 후보 분리), summary.ts
└─ features/
   ├─ start/     StartForm, RegionSelect
   ├─ chat/      ChatPage, MessageList, MessageItem, ChatInput, ExampleChips, CurrentPolicyBar, ConversationList
   ├─ policy/    CandidateGroup, CandidateCard, AnswerBubble, EvidenceToggle, ResourceButtons, RawSectionsTab
   └─ settings/  ApiKeyDialog, ThemeToggle
tests/           history.test.ts, relevance.test.ts
```

## 백엔드와 합의된 API (`src/types/contract.ts`)

- `POST /policies/search`: 요청 `{question, region, age}` → 응답 `{analysis, local_policies, national_policies, relevance_checked?, low_relevance_ids?}` (뒤 두 필드는 계약서 반영 전 제안, `docs/contract_update_proposal.md` 4-2)
- `GET /policies/{policy_id}`: 응답에 `title`, `sections` 포함 (없으면 404 `POLICY_NOT_FOUND`)
- `POST /policies/{policy_id}/ask`: 요청 `{question, policy_title}` → 응답 `{route, intents, answer}`.
  `route`가 `current_policy_question`이 아니면 `answer`는 `null`
- `region.level2`가 없으면 `null`이 아니라 `""`(DB가 광역 정책을 `region_level2 == ""`로 저장)
- 오류 응답은 계약서 17장 형식 `{error: {code, message, details}}`

## 아직 구현하지 않은 것

- 자격 판정 동적 폼(`missing_fields` 기반): 백엔드 `extract_conditions`/`evaluate_eligibility` 구현 후 추가
- 서버 세션 저장(`/sessions`): 현재는 상담 기록을 브라우저에만 저장하고 서버는 상태가 없습니다(stateless).
- 예시 질문(`constants/text.ts`)은 임시값입니다. 검색이 잘 되는 질문으로 교체하세요.
