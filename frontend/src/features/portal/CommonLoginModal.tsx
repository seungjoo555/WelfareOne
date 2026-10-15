import { useState, useEffect } from "react";
import { getRegions } from "../../api/regions";
import { RegionSelect } from "../start/RegionSelect";
import { login, signUp, UserProfile } from "../../api/auth";
import type { RegionSelection, Regions } from "../../types/contract";

interface Props {
  open: boolean;
  onClose: () => void;
  onLoginSuccess: (user: UserProfile) => void;
  onGuestStart: (region: RegionSelection, age: number | null) => void;
}

export function CommonLoginModal({ open, onClose, onLoginSuccess, onGuestStart }: Props) {
  const [tab, setTab] = useState<"login" | "signup">("login");

  // 로그인 폼 상태
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);

  // 회원가입 폼 상태
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupPasswordConfirm, setSignupPasswordConfirm] = useState("");
  const [signupNickname, setSignupNickname] = useState("");
  const [signupLevel1, setSignupLevel1] = useState("");
  const [signupLevel2, setSignupLevel2] = useState("");
  const [signupAgeText, setSignupAgeText] = useState("");
  const [signupError, setSignupError] = useState<string | null>(null);
  const [signupLoading, setSignupLoading] = useState(false);

  // 우측 비회원 폼 상태
  const [guestLevel1, setGuestLevel1] = useState("");
  const [guestLevel2, setGuestLevel2] = useState("");
  const [guestAgeText, setGuestAgeText] = useState("");
  const [guestAgeError, setGuestAgeError] = useState<string | null>(null);

  // 지역 목록
  const [regions, setRegions] = useState<Regions>({});

  useEffect(() => {
    if (open) {
      getRegions().then(setRegions).catch(() => {});
    }
  }, [open]);

  if (!open) return null;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    setLoginLoading(true);
    try {
      const res = await login({ email: loginEmail, password: loginPassword });
      onLoginSuccess(res.user);
      onClose();
    } catch (err: any) {
      setLoginError(err.message || "로그인에 실패했습니다. 이메일과 비밀번호를 확인해주세요.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setSignupError(null);

    if (signupPassword !== signupPasswordConfirm) {
      setSignupError("비밀번호가 일치하지 않습니다.");
      return;
    }
    if (signupPassword.length < 8) {
      setSignupError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }

    setSignupLoading(true);
    try {
      const parsedAge = signupAgeText.trim() ? parseInt(signupAgeText.trim(), 10) : undefined;
      const res = await signUp({
        email: signupEmail,
        password: signupPassword,
        nickname: signupNickname,
        default_region_level1: signupLevel1 || undefined,
        default_region_level2: signupLevel2 || undefined,
        default_age: parsedAge,
      });
      onLoginSuccess(res.user);
      onClose();
    } catch (err: any) {
      setSignupError(err.message || "회원가입에 실패했습니다.");
    } finally {
      setSignupLoading(false);
    }
  };

  const handleGuestSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!guestLevel1) {
      alert("시·도를 선택해주세요.");
      return;
    }
    let age: number | null = null;
    if (guestAgeText.trim()) {
      const n = parseInt(guestAgeText.trim(), 10);
      if (isNaN(n) || n < 0 || n > 120) {
        setGuestAgeError("만 나이는 0부터 120 사이여야 합니다.");
        return;
      }
      age = n;
    }
    onGuestStart({ level1: guestLevel1, level2: guestLevel2 }, age);
    onClose();
  };

  return (
    <div className="dialog-overlay" onClick={onClose} style={{ zIndex: 1000 }}>
      <div
        className="portal-modal-container"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-card, #ffffff)",
          color: "var(--text-color, #1f2937)",
          borderRadius: "16px",
          width: "900px",
          maxWidth: "95vw",
          maxHeight: "90vh",
          overflowY: "auto",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
          padding: "24px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid var(--border-color, #e5e7eb)", paddingBottom: "12px" }}>
          <div>
            <span style={{ fontSize: "12px", color: "var(--text-muted, #6b7280)", fontWeight: "bold" }}>공통 로그인 & 시작 포털</span>
            <h2 style={{ margin: "4px 0 0 0", fontSize: "20px", fontWeight: "bold" }}>WelfareOne 청년 복지정책 맞춤 안내</h2>
          </div>
          <button type="button" onClick={onClose} style={{ background: "none", border: "none", fontSize: "20px", cursor: "pointer", color: "var(--text-muted, #9ca3af)" }}>✕</button>
        </div>

        {/* 2단 분할 그리드 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
          {/* 좌측: 회원 서비스 (로그인 / 회원가입) */}
          <div style={{ padding: "16px", background: "var(--bg-subtle, #f9fafb)", borderRadius: "12px", border: "1px solid var(--border-color, #e5e7eb)" }}>
            <div style={{ display: "flex", borderBottom: "2px solid #e5e7eb", marginBottom: "16px" }}>
              <button
                type="button"
                onClick={() => setTab("login")}
                style={{
                  flex: 1,
                  padding: "10px",
                  background: "none",
                  border: "none",
                  borderBottom: tab === "login" ? "2px solid #059669" : "none",
                  fontWeight: tab === "login" ? "bold" : "normal",
                  color: tab === "login" ? "#059669" : "#6b7280",
                  cursor: "pointer",
                }}
              >
                회원 로그인
              </button>
              <button
                type="button"
                onClick={() => setTab("signup")}
                style={{
                  flex: 1,
                  padding: "10px",
                  background: "none",
                  border: "none",
                  borderBottom: tab === "signup" ? "2px solid #059669" : "none",
                  fontWeight: tab === "signup" ? "bold" : "normal",
                  color: tab === "signup" ? "#059669" : "#6b7280",
                  cursor: "pointer",
                }}
              >
                회원가입
              </button>
            </div>

            {tab === "login" ? (
              <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {loginError && <div style={{ color: "#ef4444", fontSize: "13px" }}>{loginError}</div>}
                <div>
                  <label style={{ fontSize: "13px", fontWeight: "bold" }}>이메일</label>
                  <input
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="이메일을 입력하세요"
                    style={{ width: "100%", padding: "10px", marginTop: "4px", borderRadius: "8px", border: "1px solid #d1d5db" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "13px", fontWeight: "bold" }}>비밀번호</label>
                  <input
                    type="password"
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="비밀번호를 입력하세요"
                    style={{ width: "100%", padding: "10px", marginTop: "4px", borderRadius: "8px", border: "1px solid #d1d5db" }}
                  />
                </div>
                <button
                  type="submit"
                  disabled={loginLoading}
                  style={{
                    padding: "12px",
                    background: "#059669",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    fontWeight: "bold",
                    cursor: "pointer",
                    marginTop: "8px",
                  }}
                >
                  {loginLoading ? "로그인 중..." : "로그인"}
                </button>
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "8px", lineHeight: "1.5" }}>
                  💡 회원 혜택: Gemini API 키 안전 보관, 모든 기기에서 상담 히스토리 영구 보관
                </div>
              </form>
            ) : (
              <form onSubmit={handleSignup} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {signupError && <div style={{ color: "#ef4444", fontSize: "13px" }}>{signupError}</div>}
                <div>
                  <label style={{ fontSize: "12px", fontWeight: "bold" }}>이메일 *</label>
                  <input
                    type="email"
                    required
                    value={signupEmail}
                    onChange={(e) => setSignupEmail(e.target.value)}
                    placeholder="user@example.com"
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #d1d5db" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "12px", fontWeight: "bold" }}>닉네임 *</label>
                  <input
                    type="text"
                    required
                    value={signupNickname}
                    onChange={(e) => setSignupNickname(e.target.value)}
                    placeholder="표시될 닉네임"
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #d1d5db" }}
                  />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                  <div>
                    <label style={{ fontSize: "12px", fontWeight: "bold" }}>비밀번호 *</label>
                    <input
                      type="password"
                      required
                      value={signupPassword}
                      onChange={(e) => setSignupPassword(e.target.value)}
                      placeholder="8자 이상"
                      style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #d1d5db" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "12px", fontWeight: "bold" }}>비밀번호 확인 *</label>
                    <input
                      type="password"
                      required
                      value={signupPasswordConfirm}
                      onChange={(e) => setSignupPasswordConfirm(e.target.value)}
                      placeholder="비밀번호 확인"
                      style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #d1d5db" }}
                    />
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: "12px", fontWeight: "bold" }}>기본 거주지 (선택)</label>
                  <RegionSelect
                    regions={regions}
                    level1={signupLevel1}
                    level2={signupLevel2}
                    onChange={(l1, l2) => {
                      setSignupLevel1(l1);
                      setSignupLevel2(l2);
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "12px", fontWeight: "bold" }}>만 나이 (선택)</label>
                  <input
                    type="number"
                    value={signupAgeText}
                    onChange={(e) => setSignupAgeText(e.target.value)}
                    placeholder="만 나이 (예: 25)"
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #d1d5db" }}
                  />
                </div>
                <button
                  type="submit"
                  disabled={signupLoading}
                  style={{
                    padding: "10px",
                    background: "#059669",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    fontWeight: "bold",
                    cursor: "pointer",
                    marginTop: "6px",
                  }}
                >
                  {signupLoading ? "가입 처리 중..." : "회원가입 완료"}
                </button>
              </form>
            )}
          </div>

          {/* 우측: 기존 비회원 바로 시작하기 */}
          <div style={{ padding: "16px", background: "var(--bg-subtle, #f9fafb)", borderRadius: "12px", border: "1px solid var(--border-color, #e5e7eb)", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "12px" }}>
                <span style={{ fontSize: "18px" }}>🚀</span>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "bold" }}>비회원으로 바로 상담 시작</h3>
              </div>
              <p style={{ fontSize: "13px", color: "var(--text-muted, #6b7280)", margin: "0 0 16px 0", lineHeight: "1.5" }}>
                회원가입 없이 거주 지역과 나이를 입력하여 즉시 청년 맞춤형 복지정책 검색과 AI 상담을 시작할 수 있습니다.
              </p>

              <form onSubmit={handleGuestSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div>
                  <label style={{ fontSize: "13px", fontWeight: "bold" }}>거주 지역 선택 *</label>
                  <RegionSelect
                    regions={regions}
                    level1={guestLevel1}
                    level2={guestLevel2}
                    onChange={(l1, l2) => {
                      setGuestLevel1(l1);
                      setGuestLevel2(l2);
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "13px", fontWeight: "bold" }}>만 나이 입력 (선택)</label>
                  <input
                    type="number"
                    value={guestAgeText}
                    onChange={(e) => {
                      setGuestAgeText(e.target.value);
                      setGuestAgeError(null);
                    }}
                    placeholder="만 나이 (건너뛰려면 빈칸)"
                    style={{ width: "100%", padding: "10px", marginTop: "4px", borderRadius: "8px", border: "1px solid #d1d5db" }}
                  />
                  {guestAgeError && <p style={{ color: "#ef4444", fontSize: "12px", margin: "4px 0 0 0" }}>{guestAgeError}</p>}
                </div>
                <button
                  type="submit"
                  style={{
                    padding: "12px",
                    background: "#2563eb",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    fontWeight: "bold",
                    cursor: "pointer",
                    marginTop: "16px",
                  }}
                >
                  비회원 상담 시작하기 →
                </button>
              </form>
            </div>

            <div style={{ marginTop: "16px", padding: "10px", background: "rgba(245, 158, 11, 0.1)", borderRadius: "8px", border: "1px solid rgba(245, 158, 11, 0.3)", fontSize: "12px", color: "#b45309", lineHeight: "1.4" }}>
              ※ 비회원 이용 시 대화 내역은 현재 브라우저(LocalStorage)에만 임시 저장되며, 브라우저 캐시 삭제 시 초기화됩니다.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
