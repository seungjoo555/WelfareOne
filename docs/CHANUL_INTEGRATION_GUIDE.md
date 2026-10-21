# 찬울님 회원·이력 서비스 통합 작업 가이드

대상: 찬울님 회원·이력 서비스를 병합한 `main`(PR #8, 2026-10-21 병합). 목적은 세 서버(Vite·Spring·FastAPI)와 Oracle이 함께 정상 동작하는지 확인하고, 남은 개선을 순서대로 진행하는 것이다.
실행 환경은 사용자 PC(Windows, PowerShell)를 기준으로 쓴다. 공용 Oracle(찬울님 PC)은 사설망이라 **클라우드 세션에서는 접속할 수 없고, 종단 시험은 같은 대역의 PC에서만 가능하다.**

## 0. 현재 상태 (2026-10-21, `main` `8233c1b` 기준)

| 항목 | 상태 |
|---|---|
| PR [#7](https://github.com/JMT-maker/WelfareOne/pull/7) 검색 DB 갱신 스크립트 | 초안 |
| PR [#8](https://github.com/JMT-maker/WelfareOne/pull/8) 찬울님 서비스 통합 | **병합 완료** (`8233c1b`, 일반 병합) |
| PR [#9](https://github.com/JMT-maker/WelfareOne/pull/9) 점검 보고서 | #8 안에 갱신본이 포함되어 있어 중복 — 닫아도 됨 |
| 완료된 개선(#8에 포함) | 오류 코드 계약서 17.4 정렬, 로그인 5회 실패 시 10분 제한(429), 기본 로그인 계정 비활성화, 서버 상담 대화 복원, JDK HTTP/1.1 클라이언트 |
| 검증 결과(작성자 PC) | Python 186개, 프론트 47개, Java 35개, 종단 시험 `scripts/e2e_member_flow.py` 36/36(실제 Oracle·FastAPI·Gemini) |
| 이 PR(#10)에서 추가로 고친 것 | 다크모드 로그인 창 입력 글자 안 보임, 로그인 중 대화가 브라우저에 남던 문제, 로그인 제한의 계정 잠금·메모리 증가 (10장 K·L·M) |
| 남은 일 | 13장 개선 방향 — 계약서 `function_contracts.md` 정리, 외부 공개 전 비밀값 교체 등 |

종단 시험은 `scripts/e2e_member_flow.py`가 자동으로 수행한다(시험 계정 생성 → 검증 → 정리, 시작·종료 건수 비교). 이 문서의 4~5장은 같은 흐름을 **손으로 확인**하고 싶을 때 쓰는 절차다. 상세한 변경 요약은 `docs/overview/integration_summary_2026-10-21.html`을 본다.

## 1. 준비

| 항목 | 요구 | 확인 명령 |
|---|---|---|
| JDK | 17 이상(21에서 검증) | `java -version` |
| Node | 18 이상 | `node -v` |
| Python | 3.11 이상 | `python --version` |
| 벡터 DB | `data/chroma` (저장소에 없음) | 폴더 존재 확인. 갱신본은 PR #7 설명 참고 |
| 임베딩 모델 | `Qwen/Qwen3-Embedding-0.6B` HF 캐시 | README 준비 3번 |
| Oracle | 172.31.57.141:1521, 서비스 `WELFAREONE_ORACLE_DB`, 계정 `WELFAREONE` | 2장 |

Gradle은 따로 설치하지 않는다. `app/memberJoin`에서 `.\gradlew.bat`을 쓰면 8.10.2를 자동으로 받는다.

### 환경변수 (Spring)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` | `jdbc:oracle:thin:@172.31.57.141:1521/WELFAREONE_ORACLE_DB` | 다른 DB를 쓸 때만 |
| `DB_USERNAME` | `WELFAREONE` | |
| `DB_PASSWORD` | 없음(필수) | 팀에서 공유받은 값을 **현재 PowerShell 창에서만** 지정 |
| `JWT_SECRET` | 파일의 기존 값 | 교체는 나중에(12장) |
| `AES_MASTER_KEY` | 파일의 기존 값 | 32바이트 이상 |
| `FASTAPI_BASE_URL` | `http://localhost:8000` | |
| `FASTAPI_CONNECT_TIMEOUT_MS` / `FASTAPI_READ_TIMEOUT_MS` | 3000 / 60000 | |
| `FORWARD_HEADERS_STRATEGY` | `none` | 역방향 프록시(Nginx 등) 뒤에서 실제 클라이언트 IP를 쓰려면 `native`. 로그인 시도 제한이 IP를 쓴다. 프록시 없이 직접 노출할 때는 `none`(헤더로 IP를 속이지 못함) |

비밀번호는 문서·명령 기록·커밋에 남기지 않는다. 입력은 이렇게 한다.

```powershell
$env:DB_PASSWORD = Read-Host "Oracle 비밀번호"   # 화면에 보이지만 이 창을 닫으면 사라짐
```

## 2. 읽기 전용 점검 (DB에 쓰지 않음)

```powershell
cd app\memberJoin
.\gradlew.bat test                 # 단위 테스트 24개 (DB 불필요)
.\gradlew.bat bootRun              # 새 창에서. "Started MemberJoinApplication" 확인
```

다른 창에서:

PowerShell에서 상태 코드와 본문을 함께 보는 도우미(오류 응답도 출력, PowerShell 5·7 공통):

```powershell
function Probe($method, $path, $json = $null) {
  $p = @{ Method=$method; Uri="http://localhost:8080$path"; UseBasicParsing=$true; ContentType="application/json; charset=utf-8" }
  if ($json) { $p.Body = [Text.Encoding]::UTF8.GetBytes($json) }
  try { $r = Invoke-WebRequest @p; "$([int]$r.StatusCode) $($r.Content)" }
  catch { $e = $_.Exception.Response; "$([int]$e.StatusCode) " + (New-Object IO.StreamReader($e.GetResponseStream())).ReadToEnd() }
}

# 보호된 API는 인증 없이 거부되어야 한다 → 401 UNAUTHORIZED
Probe GET /api/history/sessions
# 가입 입력 검증은 DB를 쓰지 않는다 → 422
Probe POST /api/auth/signup '{"email":"x","password":"1","nickname":""}'
# 없는 계정 로그인 → USERS 조회(SELECT)만 발생 → 401 INVALID_CREDENTIALS
Probe POST /api/auth/login '{"email":"nobody@example.invalid","password":"wrong-password-1"}'
```

로그 첫 줄들에서 `HikariPool-1 - Added connection oracle.jdbc.driver.T4CConnection`이 보이면 JDBC 연결 성공이다.
`/api/health`는 인증 면제로 열려 있지만 처리하는 컨트롤러가 없어 404가 난다. 살아 있는지는 위 로그인 호출로 확인한다.

## 3. 세 서버 기동

```powershell
# 터미널 1 — FastAPI (루트에서). 모델 로딩에 시간이 걸린다
uvicorn app.api:app --port 8000
# 터미널 2 — Spring (환경변수 지정 후)
cd app\memberJoin; .\gradlew.bat bootRun
# 터미널 3 — 프론트. frontend\.env.local 에 VITE_USE_MOCK=false 가 있어야 실제 서버에 붙는다
cd frontend; npm install; npm run dev      # http://localhost:5173
```

AI 호출에는 둘 중 하나가 필요하다.
- 브라우저의 "API 키" 창에 본인 Gemini 키를 넣는다(요청 헤더 `X-Gemini-Api-Key`로 Spring→FastAPI에 전달됨).
- 또는 `.env`에 `LLM_PROVIDER=qwen`, `QWEN_BASE_URL` 등을 설정한 서버 기본 AI(LM Studio 등).

## 4. 종단 시험 (공용 DB에 **쓰기** 발생)

원칙: 시험 계정 1개와 그 계정의 세션·메시지만 만든다. 기존 7개 계정(USERS 7행)은 읽지도 건드리지도 않는다. 이메일은 `integration-test+YYYYMMDD@example.invalid` 형식, 시험이 끝나면 5장으로 반드시 정리한다.

PowerShell 도우미(한글이 깨지지 않게 UTF-8 바이트로 보낸다):

```powershell
$base = "http://localhost:8080"
function Call($method, $path, $body = $null, $token = $null, $extra = @{}) {
  $h = @{} + $extra; if ($token) { $h["Authorization"] = "Bearer $token" }
  $p = @{ Method=$method; Uri="$base$path"; Headers=$h; ContentType="application/json; charset=utf-8" }
  if ($body) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6)) }
  Invoke-RestMethod @p
}
$email = "integration-test+$(Get-Date -Format yyyyMMdd)@example.invalid"
$pw    = "Test-" + [guid]::NewGuid().ToString("N").Substring(0,12)   # 일회용, 저장하지 않음
```

| # | 동작 | 호출 | 기대 결과 |
|---|---|---|---|
| 1 | 가입 | `$r = Call POST /api/auth/signup @{email=$email;password=$pw;nickname="통합시험";default_region_level1="서울특별시";default_region_level2="관악구";default_age=24}` | `access_token`, `user.has_api_key=false`. 중복 가입은 409 `USER_ALREADY_EXISTS` |
| 2 | 로그인 | `$r = Call POST /api/auth/login @{email=$email;password=$pw}; $t = $r.access_token` | 토큰 발급 |
| 3 | 내 정보 | `Call GET /api/auth/me $null $t` | 가입 때 값과 동일 |
| 4 | 세션 생성 | `$s = Call POST /api/history/sessions @{region_level1="서울특별시";region_level2="관악구";age=24;title="통합시험"} $t; $sid = $s.session_id` | `session_id`(UUID) |
| 5 | 남의 세션 차단 | 존재하지 않는 UUID로 호출(오류 응답이 예외로 던져지므로 `try { Call … } catch { $_.Exception.Response.StatusCode }`). `Call POST /api/ai/sessions/00000000-0000-0000-0000-000000000000/search @{question="x";region=@{level1="서울특별시";level2=""};age=24} $t` | 404 `SESSION_NOT_FOUND`(다른 사용자의 세션이면 403 `FORBIDDEN`). **AI가 호출되지 않아야 함**(FastAPI 로그에 요청 없음) |
| 6 | 검색 | `Call POST /api/ai/sessions/$sid/search @{question="월세가 부담돼요";region=@{level1="서울특별시";level2="관악구"};age=24} $t @{"X-Gemini-Api-Key"="<본인 키>"}` — 서버 기본 AI를 쓰면 마지막 인자 생략 | `local_policies`/`national_policies` 후보. 키도 서버 AI도 없으면 401 `API_KEY_REQUIRED`가 **그대로** 전달되어야 함 |
| 7 | 정책 질문 | 6의 `policy_id`를 `[uri]::EscapeDataString`으로 인코딩해 `POST /api/ai/sessions/$sid/policies/{id}/ask` `@{question="지원 대상이 어떻게 돼요?";policy_title="…";intent="eligibility"} $t` | `route=current_policy_question`, `answer` |
| 8 | 기록 조회 | `Call GET /api/history/sessions/$sid $null $t` | `messages` 4개, `sender_type`은 **소문자** `user`/`assistant`, 후보·근거 JSON 문자열 포함 |
| 9 | 제목 | 6 이후 목록의 `title`이 첫 질문(30자)으로 바뀌었는지 `GET /api/history/sessions` | 자동 제목 반영 |
| 10 | 삭제 | `Call DELETE /api/history/sessions/$sid $null $t` 후 8을 다시 호출 | 삭제 후 404 `SESSION_NOT_FOUND` |

DB에서 직접 확인할 것(읽기): 6~7 직후 `CHAT_MESSAGES`에서 해당 `session_id` 행의 `sender_type`이 `USER`/`ASSISTANT` 대문자인지.

실패 시 먼저 볼 곳: Spring 콘솔의 `상담 기록 저장 실패`/`FastAPI … 오류` 로그, FastAPI 콘솔.

## 5. 시험 데이터 정리

세션·메시지는 4장 10번으로 지워진다(FK `ON DELETE CASCADE`). 시험 **계정 행**은 API가 없으므로 한 건만 지운다. 외래키 연쇄로 그 계정의 세션·키도 함께 지워진다.

아래 내용을 저장소 밖(예: `D:\tmp\cleanup_test_user.py`)에 파일로 저장해 `python D:\tmp\cleanup_test_user.py`로 실행한다. 비밀번호는 실행 때 입력받으며 파일에 쓰지 않는다. 시험 계정이 아니면 중단한다.

```python
import getpass
import oracledb

email = input("지울 시험 계정 이메일(integration-test+…@example.invalid): ").strip()
assert email.startswith("integration-test+") and email.endswith("@example.invalid"), "시험 계정이 아닙니다"
conn = oracledb.connect(
    user="WELFAREONE",
    password=getpass.getpass("Oracle 비밀번호: "),
    dsn=oracledb.makedsn("172.31.57.141", 1521, service_name="WELFAREONE_ORACLE_DB"),
)
cur = conn.cursor()
cur.execute("select count(*) from USERS where email = :e", e=email)
print("대상 행:", cur.fetchone()[0])  # 1이어야 함
if input("삭제하려면 yes 입력: ") == "yes":
    cur.execute("delete from USERS where email = :e", e=email)
    conn.commit()
    print("삭제 완료")
conn.close()
```

확인: 시험 전후 `USERS` 7행, `USER_API_KEYS` 2행, `CHAT_SESSIONS` 3행, `CHAT_MESSAGES` 6행이 그대로여야 한다(2026-10-19 기준 건수).

## 6. 브라우저 시험 체크리스트

1. 게스트로 접속: 사이드바는 `WelfareOne`, 상담 기록은 브라우저 저장(기존 동작), 검색·질문·버튼 질문이 정상.
2. 가입 → 자동 로그인: 사이드바에 `👤 닉네임 님`과 "저장된 대화 기록 (Oracle DB)".
3. 로그인 상태로 검색: 개발자 도구 Network에서 호출이 `/api/ai/sessions/{id}/search`(8080 경유)인지, 응답 후 서버 기록 목록이 갱신되는지.
4. 정책 선택 → "자주 묻는 질문" 버튼: `/api/ai/sessions/{id}/policies/.../ask` 요청 본문에 `intent`가 있는지.
5. 키가 없는 상태에서 검색: "API 키" 입력 창이 떠야 한다(`API_KEY_REQUIRED` 전달 확인). 잘못된 키: `INVALID_API_KEY` 안내.
6. Spring을 끄고 검색: 화면이 FastAPI 직접 경로로 **대체 동작**하는지(세션 생성 실패 → null → 직접 호출).
7. 토큰 삭제(`localStorage`의 `welfareone_access_token`) 후 새로고침: 게스트 화면으로 복귀.
8. 모바일 폭(≤ 600px)에서 사이드바 열기·닫기.

## 7. 알려진 한계 (시험 때 오류로 오해하지 말 것)

- 서버 저장 Gemini 키는 **화면에서 등록할 방법이 없다**. `saveServerApiKey`(`frontend/src/api/auth.ts`)가 정의만 되어 있고 어디서도 호출되지 않는다. 지금은 브라우저에 입력한 키가 우선 사용된다. 서버 저장 키를 쓰려면 `PUT /api/users/api-key`를 직접 호출하거나 화면을 추가해야 한다.
- 키 우선순위: 요청 헤더 키 > 서버 저장 키 > 없음(FastAPI가 서버 기본 AI 또는 401 `API_KEY_REQUIRED`).
- 로그인 중의 대화는 브라우저(localStorage)에 복사하지 않는다(서버가 기준 저장소). 로그아웃하면 화면을 비우고, 서버에서 불러와 복사됐던 `server-…` 상담도 지운다. **이전 버전에서 로그인 중에 만들어 이미 저장된 일반 대화는 구분할 수 없어 자동으로 지우지 않는다** — 공용 PC에서는 사이드바에서 직접 삭제한다.
- 로그인 실패 제한은 서버 메모리 기반이라 재시작하면 초기화되고, 서버를 여러 대로 늘리면 공유되지 않는다. 한도: 같은 이메일+같은 IP 5회, 같은 이메일 전체 30회, 같은 IP 전체 20회(각 10분). Vite 개발 프록시를 거치면 모든 요청이 `127.0.0.1`로 보여 IP 한도(20회)가 개발자 전체에 공유된다.
- 프론트 mock 모드(`npm run dev` 기본)에서는 로그인·가입이 동작하지 않는다. 로그인 시험은 `VITE_USE_MOCK=false`와 Spring이 필요하다.

## 8. 문제 해결

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| Spring 기동 시 `ORA-01017` | 비밀번호/계정 오류 | `DB_PASSWORD` 확인, 계정명 `WELFAREONE` 대문자 |
| `IO Error: The Network Adapter could not establish the connection` | 찬울님 PC 꺼짐·방화벽·IP 변경 | `Test-NetConnection 172.31.57.141 -Port 1521` |
| `ORA-12514` | 서비스 이름 오류 | `WELFAREONE_ORACLE_DB` 확인 |
| 기동 중 `master-key는 32바이트 이상` | `AES_MASTER_KEY`가 짧음 | 32바이트 이상으로 지정 |
| 검색은 되는데 Oracle에 기록이 안 쌓임 | 로그인 안 됨 → FastAPI 직행 | 6장 3번으로 경로 확인 |
| 검색 시 503/504 | FastAPI 미기동/응답 지연 | 3장 터미널 1 확인, `FASTAPI_READ_TIMEOUT_MS` |
| 한글이 `???`로 저장 | PowerShell 5 인코딩 | 4장 도우미(UTF-8 바이트 전송) 사용 |
| 프론트에서 mock 데이터만 나옴 | `VITE_USE_MOCK` | `frontend/.env.local`에 `VITE_USE_MOCK=false` |
| `gradlew` 다운로드 실패(429) | 저장소 프록시 요청 과다 | 잠시 후 재시도 |

## 9. 확인된 설계 요약 (코드 기준)

```
브라우저(5173) ─ Vite 프록시 ─┬─ /api/auth·users·history·ai → Spring(8080) ─┬→ Oracle
                              └─ 그 외 /api/* (prefix 제거) → FastAPI(8000)  └→ FastAPI (중계)
```

- Spring 컨트롤러: `AuthController`(`/api/auth/signup|login|me`), `ApiKeyController`(`/api/users/api-key[/status]`), `HistoryController`(`/api/history/sessions[/{id}[/title]]`), `AiProxyController`(`/api/ai/sessions/{id}/search`, `/policies/{pid}/ask`).
- 보안: JWT(24시간, stateless), 가입·로그인만 인증 면제, CORS는 `localhost:5173`/`127.0.0.1:5173`만.
- 오류 형식: `{"error":{"code","message","details"}}` — FastAPI 오류는 상태·본문 그대로 전달.
- 브라우저 기록: `useConversationHistory`는 로그인 토큰이 있으면 대화를 localStorage에 저장하지 않는다. 로그아웃(`ChatPage.tsx`의 `handleLogout`)은 토큰·서버 목록·화면 대화를 비우고 `purgeServerCopies()`로 서버에서 온 복사본을 지운다.
- 로그인 창 스타일: `styles.css`의 `.portal-*` 클래스와 앱 테마 변수(`--surface/--text/--border/--bg/--muted/--accent/--danger/--warn-*`)만 쓴다. 정의되지 않은 변수나 하드코딩 색을 쓰면 `tests/cssVars.test.ts`가 실패한다.

## 10. 개선 작업 현황

| 상태 | 작업 | 비고 |
|---|---|---|
| 완료 | A. 오류 코드를 계약서 17.4에 맞춤 | 401 `UNAUTHORIZED`/`INVALID_CREDENTIALS`, 403 `FORBIDDEN`, 404 `SESSION_NOT_FOUND`, 409 `USER_ALREADY_EXISTS` |
| 완료 | B. 프론트 인증 오류 처리 | `UNAUTHORIZED`만 로그아웃, `SESSION_NOT_FOUND`/`FORBIDDEN`은 세션 연결만 끊고 직접 경로로 재시도 |
| 완료 | C. 서버 상담 대화 복원 | `frontend/src/utils/serverHistory.ts` |
| 완료 | D. 기본 보안 계정 비활성화 | `application.yml`의 autoconfigure exclude |
| 완료 | E. 로그인 실패 횟수 제한 | `LoginAttemptService` (같은 이메일 5회/10분, 메모리 기반) |
| 완료 | K. 로그아웃·로그인 중 브라우저 기록 처리 | 로그인 중에는 브라우저에 저장하지 않고, 로그아웃 때 화면과 서버 복사본을 비움 |
| 완료 | L. 로그인 제한의 부작용 | 이메일+IP 기준 5회, 이메일 30회, IP 20회로 나누고(남의 IP가 내 계정을 잠그지 못함), 조회만으로 항목을 만들지 않으며, 항목이 1,000개를 넘으면 만료분 정리 |
| 완료 | M. 다크모드 로그인 창 | 입력 글자 대비 1.31:1 → 정상. 모달·사이드바 인라인 스타일을 테마 변수 기반 클래스로 교체, 오버레이 위치(fixed)·모바일 1단 정리 |
| 열림 | F. 서버 키 등록 UI 또는 방침 확정 | `ApiKeyDialog.tsx`, `contract_update_proposal.md` 8-1과 충돌 |
| 열림 | G. 상담 기록 기준 결정 | 로그인 시 사이드바는 Oracle 목록만 보임. 게스트 기록 이전 없음 |
| 열림 | H. 지역·정책 상세·설정 경로 | Spring 한 곳으로 모으면 로그인 때문에 막힘. 운영 프록시(Nginx 등)에서 경로 분기 유지 권장 |
| 열림 | I. 계약서 반영 | `/sessions` 계열 주소(실제는 `/api/history/sessions`, `/api/ai/sessions/{id}/…`)와 가입 응답(토큰 포함) 정리. 미구현 항목(`/sessions/{id}/messages`, `/eligibility`) 표시 |
| 열림 | J. 토큰 보관·갱신 | localStorage 저장, 24시간 유효. HttpOnly 쿠키 또는 만료 단축+갱신 |

## 11. 오류 코드 (구현 기준)

| 상황 | 응답 |
|---|---|
| 토큰 없음/무효 | 401 `UNAUTHORIZED` |
| 로그인 실패 | 401 `INVALID_CREDENTIALS` |
| 같은 이메일 5회 연속 실패 | 429 `TOO_MANY_LOGIN_ATTEMPTS` (10분) |
| 가입 중복 | 409 `USER_ALREADY_EXISTS` |
| 없는 세션 / 남의 세션 | 404 `SESSION_NOT_FOUND` / 403 `FORBIDDEN` |
| AI 서버 오류 | FastAPI의 상태·`error` 본문을 그대로 전달(`API_KEY_REQUIRED`, `INVALID_API_KEY`, `LLM_RATE_LIMITED` 등) |
| AI 서버 연결 실패 / 응답 시간 초과 | 503 / 504 `INTERNAL_ERROR` |

## 12. 비밀값 (나중에 교체하기로 한 항목)

현재 합의: 팀 내부에서만 공유하므로 당분간 유지. 다음 시점에는 **반드시** 교체한다 — 저장소를 팀 밖으로 공개/공유할 때, 팀원이 바뀔 때.
교체 대상은 DB 비밀번호, `JWT_SECRET`, `AES_MASTER_KEY`이다. 순서: 새 값 생성 → 환경변수 적용 → Spring 재시작 → AES 키를 바꿨다면 `USER_API_KEYS`의 저장 키(2건)를 재등록 → 옛 값 폐기. 이미 Git 이력에 올라간 값은 교체로 무효화된다.

## 13. 개선 방향

우선순위 순서. 앞의 것이 뒤의 것의 전제가 되는 경우가 많다.

| 시점 | 방향 | 이유 / 완료 기준 |
|---|---|---|
| 병합 직후 | **`docs/function_contracts.md`를 구현에 맞게 정리** (별도 PR) | `/sessions` 계열 주소(실제는 `/api/history/sessions`, `/api/ai/sessions/{id}/…`)·가입 응답(토큰 포함)이 실제와 다르고, 구현되지 않은 `/sessions/{id}/messages`, `/eligibility`가 적혀 있다. 팀 합의 문서이므로 팀 확인 후 반영 |
| 외부 공개 전 (필수) | **JWT 키·AES 마스터 키·DB 비밀번호 교체** (12장 순서) | 지금은 기본값이 저장소와 Git 이력에 있다. 팀 안에서만 쓰는 동안만 유예 |
| 단기 | **서버 저장 Gemini 키 방침 확정** | 서버 암호화 저장은 `contract_update_proposal.md` 8-1("서버는 키를 저장하지 않는다")과 충돌한다. (a) 저장을 허용하고 등록 화면을 만들거나(`saveServerApiKey`를 연결), (b) 브라우저 키만 쓰고 서버 저장 기능을 제거한다 |
| 단기 | **로그인 중 상담 기록의 기준 확정** | 로그인하면 사이드바가 Oracle 목록만 보인다. 게스트 때 만든 기록을 계정으로 옮길지, 로그인 중에도 보여 줄지 정한다. 서버 상담에는 제목 수정·삭제 UI가 없다 |
| 중기 | **공용 DB를 개인 PC에서 서버로 이전** | 찬울님 PC가 꺼지면 로그인·기록 전체가 멈춘다. 이전 시 `DB_URL`만 바꾸면 된다 |
| 중기 | **운영 경로 설계** | 지금은 Vite 개발 프록시가 `/api/auth·users·history·ai`를 Spring, 나머지를 FastAPI로 나눈다. 운영에서는 Nginx 등에서 같은 분기를 만들고 `FORWARD_HEADERS_STRATEGY=native`를 켠다. CORS 허용 주소(`localhost:5173`)를 설정값으로 뺀다 |
| 중기 | **토큰·로그인 제한 강화** | JWT는 localStorage에 24시간. HttpOnly 쿠키 또는 짧은 만료+갱신, 로그아웃 시 서버 쪽 무효화. 서버를 여러 대로 늘리면 로그인 제한을 DB/Redis로 옮긴다 |
| 계속 | **브라우저 자동 시험을 저장소에 도입** | 이번 회귀 확인(게스트 흐름·로그인 흐름·다크모드 대비·로그아웃 후 잔존)은 임시 Playwright 스크립트로 했다. `frontend/`에 정식 포함하면 테마·로그인 회귀를 CI에서 잡는다 |
| 계속 | **화면 스타일은 테마 변수만** | `tests/cssVars.test.ts`가 정의되지 않은 변수와 `features/` 안의 하드코딩 색 인라인 스타일을 막는다. 새 화면도 `styles.css`의 변수를 쓴다 |
