"""회원·상담 기록 서버(Spring) 종단 시험: 가입 → 로그인 → 상담 세션 → AI 검색·질문(Spring → FastAPI) → 기록 저장 → 오류 코드 → 정리.

    # 1) FastAPI(:8000)와 Spring(:8080)을 띄운다. FastAPI는 서버 기본 AI가 필요하다(WELFAREONE_ALLOW_SERVER_KEY=true 또는 LLM_PROVIDER=qwen).
    # 2) 접속 정보는 환경변수로만 넘긴다(저장소·로그에 남기지 않는다).
    $env:ORA_HOST="<Oracle 주소>"; $env:ORA_PORT="1521"; $env:ORA_DB="WELFAREONE_ORACLE_DB"; $env:ORA_USER="WELFAREONE"; $env:ORA_PW="<비밀번호>"
    python scripts/e2e_member_flow.py

주의
- 공용 Oracle에 시험 계정(integration-test-<시각>-*@example.invalid)을 만들고, 끝나면 그 계정만 지운다(FK 연쇄로 세션·메시지·키도 삭제).
  기존 사용자 데이터는 읽지도 건드리지도 않는다. 시작 전·후 테이블 건수가 같은지도 검사한다.
- Gemini에 가짜 키를 보내는 시험이 있어 외부 호출이 몇 번 발생한다.
"""

import json, os, secrets, sys, time, urllib.request, urllib.error
import oracledb

SPRING = os.environ.get("SPRING", "http://localhost:8080")
STAMP = time.strftime("%Y%m%d%H%M%S")
PREFIX = "integration-test-"
EMAIL_A = f"{PREFIX}{STAMP}-a@example.invalid"
EMAIL_B = f"{PREFIX}{STAMP}-b@example.invalid"
EMAIL_LOCK = f"{PREFIX}{STAMP}-lock@example.invalid"
PW_A, PW_B = secrets.token_urlsafe(14), secrets.token_urlsafe(14)
results = []


def db():
    dsn = oracledb.makedsn(os.environ["ORA_HOST"], int(os.environ["ORA_PORT"]), service_name=os.environ["ORA_DB"])
    return oracledb.connect(user=os.environ["ORA_USER"], password=os.environ["ORA_PW"], dsn=dsn, tcp_connect_timeout=8)


def call(method, path, body=None, token=None, headers=None, base=SPRING, timeout=90):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None), time.time() - t
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else None, time.time() - t
        except Exception:
            return e.code, raw, time.time() - t


def code_of(body):
    return (body or {}).get("error", {}).get("code") if isinstance(body, dict) else None


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    return ok


def counts(cur):
    out = {}
    for t in ("USERS", "USER_API_KEYS", "CHAT_SESSIONS", "CHAT_MESSAGES"):
        cur.execute(f"select count(*) from {t}")
        out[t] = cur.fetchone()[0]
    return out


conn = db()
cur = conn.cursor()
before = counts(cur)
print("시작 전 건수:", before, flush=True)
try:
    # 1. 가입
    st, body, _ = call("POST", "/api/auth/signup", {"email": EMAIL_A, "password": PW_A, "nickname": "통합시험A", "default_region_level1": "서울특별시", "default_region_level2": "관악구", "default_age": 24})
    tok_a = (body or {}).get("access_token")
    check("가입 201 + 토큰 발급", st == 201 and bool(tok_a), f"status={st}")
    cur.execute("select password_hash, role from users where email=:e", e=EMAIL_A)
    row = cur.fetchone()
    check("DB에 BCrypt 해시로 저장(평문 아님)", bool(row) and row[0].startswith("$2") and PW_A not in row[0], f"hash 접두={row[0][:4] if row else None}")
    st, body, _ = call("POST", "/api/auth/signup", {"email": EMAIL_A, "password": PW_A, "nickname": "중복"})
    check("중복 가입 409 USER_ALREADY_EXISTS", st == 409 and code_of(body) == "USER_ALREADY_EXISTS", f"status={st} code={code_of(body)}")

    # 2. 로그인·인증
    st, body, _ = call("POST", "/api/auth/login", {"email": EMAIL_A, "password": PW_A})
    check("로그인 200", st == 200 and "access_token" in (body or {}), f"status={st}")
    tok_a = body["access_token"]
    st, body, _ = call("POST", "/api/auth/login", {"email": EMAIL_A, "password": "wrong-password-1"})
    check("잘못된 비밀번호 401 INVALID_CREDENTIALS", st == 401 and code_of(body) == "INVALID_CREDENTIALS", f"status={st} code={code_of(body)}")
    st, body, _ = call("GET", "/api/auth/me")
    check("토큰 없이 /me → 401 UNAUTHORIZED(JSON)", st == 401 and code_of(body) == "UNAUTHORIZED", f"status={st} code={code_of(body)}")
    st, body, _ = call("GET", "/api/auth/me", token="not-a-token")
    check("잘못된 토큰 → 401 UNAUTHORIZED", st == 401 and code_of(body) == "UNAUTHORIZED", f"status={st}")
    st, body, _ = call("GET", "/api/auth/me", token=tok_a)
    check("/me 프로필 조회", st == 200 and body.get("email") == EMAIL_A and body.get("has_api_key") is False, f"status={st}")
    # 로그인 시도 제한(별도 가짜 계정)
    codes = []
    for _ in range(6):
        st, body, _ = call("POST", "/api/auth/login", {"email": EMAIL_LOCK, "password": "wrong-password-1"})
        codes.append((st, code_of(body)))
    check("로그인 5회 실패 후 6번째 429 TOO_MANY_LOGIN_ATTEMPTS", codes[:5] == [(401, "INVALID_CREDENTIALS")] * 5 and codes[5] == (429, "TOO_MANY_LOGIN_ATTEMPTS"), str(codes[4:]))

    # 3. 상담 세션
    st, body, _ = call("POST", "/api/history/sessions", {"region_level1": "서울특별시", "region_level2": "관악구", "age": 24, "title": "통합시험 상담"}, token=tok_a)
    sid = (body or {}).get("session_id")
    check("상담 세션 생성", st in (200, 201) and bool(sid), f"status={st}")

    # 4. AI 검색(Spring → FastAPI)
    st, body, sec = call("POST", f"/api/ai/sessions/{sid}/search", {"question": "월세가 부담돼요", "region": {"level1": "서울특별시", "level2": "관악구"}, "age": 24}, token=tok_a)
    local = (body or {}).get("local_policies") or []
    national = (body or {}).get("national_policies") or []
    check("Spring 경유 정책 검색 200 + 후보", st == 200 and (len(local) + len(national)) > 0, f"status={st} {sec:.1f}s local={len(local)} national={len(national)}")
    cur.execute("select sender_type, route from chat_messages where session_id=:s order by created_at", s=sid)
    rows = cur.fetchall()
    check("기록 저장: USER/ASSISTANT 대문자 2건", [r[0] for r in rows] == ["USER", "ASSISTANT"], f"{rows}")
    st, detail, _ = call("GET", f"/api/history/sessions/{sid}", token=tok_a)
    msgs = (detail or {}).get("messages") or []
    check("상세 조회: 소문자 sender_type + 후보 JSON 보존", [m["sender_type"] for m in msgs] == ["user", "assistant"] and "local_policies" in (msgs[-1].get("candidates_json") or ""), f"status={st}")
    check("첫 질문으로 세션 제목 자동 변경", (detail or {}).get("session", {}).get("title") == "월세가 부담돼요", f"title={(detail or {}).get('session', {}).get('title')}")

    # 5. 정책 질문(intent 전달)
    pol = (local or national)[0]
    st, body, sec = call("POST", f"/api/ai/sessions/{sid}/policies/{urllib.request.quote(pol['policy_id'], safe='')}/ask", {"question": "지원 대상이 어떻게 돼요?", "policy_title": pol["title"], "intent": "eligibility"}, token=tok_a)
    ans = (body or {}).get("answer") or {}
    check("정책 질문 200 + 답변·근거", st == 200 and bool(ans.get("answer")) and (body or {}).get("route") == "current_policy_question", f"status={st} {sec:.1f}s grounded={ans.get('grounded')}")
    cur.execute("select count(*), listagg(sender_type, ',') within group (order by created_at) from chat_messages where session_id=:s", s=sid)
    n, senders = cur.fetchone()
    check("질문·답변 기록 누적(총 4건)", n == 4 and senders == "USER,ASSISTANT,USER,ASSISTANT", f"{n} {senders}")

    # 6. 남의 세션·없는 세션
    st, body, _ = call("POST", "/api/auth/signup", {"email": EMAIL_B, "password": PW_B, "nickname": "통합시험B"})
    tok_b = (body or {}).get("access_token")
    check("두 번째 계정 가입", st == 201 and bool(tok_b), f"status={st}")
    st, body, _ = call("POST", f"/api/ai/sessions/{sid}/search", {"question": "침입 시도", "region": {"level1": "서울특별시", "level2": ""}, "age": 24}, token=tok_b)
    check("남의 세션으로 AI 호출 → 403 FORBIDDEN", st == 403 and code_of(body) == "FORBIDDEN", f"status={st} code={code_of(body)}")
    st, body, _ = call("GET", f"/api/history/sessions/{sid}", token=tok_b)
    check("남의 세션 상세 조회 → 403", st == 403 and code_of(body) == "FORBIDDEN", f"status={st}")
    st, body, _ = call("DELETE", f"/api/history/sessions/{sid}", token=tok_b)
    check("남의 세션 삭제 → 403", st == 403, f"status={st}")
    st, body, _ = call("POST", "/api/ai/sessions/00000000-0000-0000-0000-000000000000/search", {"question": "q", "region": {"level1": "서울특별시", "level2": ""}, "age": 24}, token=tok_b)
    check("없는 세션 → 404 SESSION_NOT_FOUND", st == 404 and code_of(body) == "SESSION_NOT_FOUND", f"status={st} code={code_of(body)}")
    cur.execute("select count(*) from chat_messages where session_id=:s", s=sid)
    check("침입 시도로 A의 기록이 늘지 않음", cur.fetchone()[0] == 4)

    # 7. Gemini 키 저장·주입·오류 전달
    fake_key = "AIza" + secrets.token_urlsafe(30)
    st, body, _ = call("PUT", "/api/users/api-key", {"api_key": fake_key}, token=tok_a)
    check("키 등록", st == 200 and (body or {}).get("has_api_key") is True, f"status={st}")
    cur.execute("select encrypted_key, iv_salt from user_api_keys k join users u on u.user_id=k.user_id where u.email=:e", e=EMAIL_A)
    enc = cur.fetchone()
    check("DB에 암호문으로 저장(평문 없음)", bool(enc) and fake_key not in enc[0] and len(enc[1]) >= 12, f"cipher 길이={len(enc[0]) if enc else None}")
    st, body, _ = call("GET", "/api/users/api-key/status", token=tok_a)
    check("키 상태 조회(키 값 미노출)", st == 200 and body.get("has_api_key") is True and fake_key not in json.dumps(body), f"{body}")
    st, body, sec = call("POST", f"/api/ai/sessions/{sid}/search", {"question": "자격증 비용", "region": {"level1": "서울특별시", "level2": "관악구"}, "age": 24}, token=tok_a)
    check("저장된(가짜) 키가 FastAPI→Gemini에 전달 → 401 INVALID_API_KEY 그대로 전달", st == 401 and code_of(body) == "INVALID_API_KEY", f"status={st} code={code_of(body)} {sec:.1f}s")
    cur.execute("select count(*) from chat_messages where session_id=:s", s=sid)
    check("AI 오류 시 기록을 남기지 않음", cur.fetchone()[0] == 4)
    st, body, _ = call("DELETE", "/api/users/api-key", token=tok_a)
    check("키 삭제", st in (200, 204), f"status={st}")
    st, body, sec = call("POST", f"/api/ai/sessions/{sid}/search", {"question": "자격증 비용", "region": {"level1": "서울특별시", "level2": "관악구"}, "age": 24}, token=tok_a)
    check("키 삭제 후 서버 기본 AI로 정상 응답", st == 200, f"status={st} {sec:.1f}s")
    st, body, _ = call("POST", f"/api/ai/sessions/{sid}/search", {"question": "자격증 비용", "region": {"level1": "서울특별시", "level2": "관악구"}, "age": 24}, token=tok_a, headers={"X-Gemini-Api-Key": "AIza" + secrets.token_urlsafe(30)})
    check("요청 헤더 키가 우선 적용(가짜 키 → 401 INVALID_API_KEY)", st == 401 and code_of(body) == "INVALID_API_KEY", f"status={st} code={code_of(body)}")

    # 8. Vite 프록시 경유(실제 브라우저와 같은 경로)
    st, body, _ = call("POST", "/api/auth/login", {"email": EMAIL_A, "password": PW_A}, base="http://localhost:5173")
    check("Vite 프록시 경유 로그인(/api/auth → Spring)", st == 200 and "access_token" in (body or {}), f"status={st}")
    st, body, _ = call("GET", "/api/regions", base="http://localhost:5173")
    check("Vite 프록시 경유 지역 목록(/api/regions → FastAPI)", st == 200 and "서울특별시" in (body or {}), f"status={st}")

    # 9. 삭제
    st, body, _ = call("DELETE", f"/api/history/sessions/{sid}", token=tok_a)
    check("세션 삭제", st in (200, 204), f"status={st}")
    st, body, _ = call("GET", f"/api/history/sessions/{sid}", token=tok_a)
    check("삭제 후 조회 → 404 SESSION_NOT_FOUND", st == 404 and code_of(body) == "SESSION_NOT_FOUND", f"status={st}")
    cur.execute("select count(*) from chat_messages where session_id=:s", s=sid)
    check("연쇄 삭제로 메시지도 제거", cur.fetchone()[0] == 0)
finally:
    # 시험용 계정만 삭제(FK 연쇄로 세션·메시지·키도 삭제)
    cur.execute("delete from users where email like :p", p=f"{PREFIX}{STAMP}-%@example.invalid")
    removed = cur.rowcount
    conn.commit()
    after = counts(cur)
    print(f"시험 계정 {removed}개 삭제. 정리 후 건수: {after}", flush=True)
    check("정리 후 DB 건수가 시작 전과 동일", after == before, f"before={before} after={after}")
    conn.close()

failed = [r for r in results if not r[1]]
print(f"\n합계: {len(results) - len(failed)}/{len(results)} 통과")
sys.exit(1 if failed else 0)
