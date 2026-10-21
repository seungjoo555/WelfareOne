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
    <div className="modal-backdrop portal-backdrop" onClick={onClose}>
      <div className="portal-modal" role="dialog" aria-modal="true" aria-labelledby="portal-title" onClick={(e) => e.stopPropagation()}>
        <div className="portal-head">
          <div>
            <span className="portal-eyebrow">공통 로그인 &amp; 시작 포털</span>
            <h2 id="portal-title" className="portal-title">WelfareOne 청년 복지정책 맞춤 안내</h2>
          </div>
          <button type="button" className="portal-close" aria-label="닫기" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* 2단 분할 그리드(좁은 화면에서는 1단) */}
        <div className="portal-grid">
          {/* 좌측: 회원 서비스 (로그인 / 회원가입) */}
          <section className="portal-panel">
            <div className="portal-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "login"}
                className={`portal-tab${tab === "login" ? " active" : ""}`}
                onClick={() => setTab("login")}
              >
                회원 로그인
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "signup"}
                className={`portal-tab${tab === "signup" ? " active" : ""}`}
                onClick={() => setTab("signup")}
              >
                회원가입
              </button>
            </div>

            {tab === "login" ? (
              <form onSubmit={handleLogin} className="portal-form">
                {loginError && <div className="portal-error" role="alert">{loginError}</div>}
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-login-email">이메일</label>
                  <input
                    id="portal-login-email"
                    className="portal-input"
                    type="email"
                    required
                    autoComplete="username"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="이메일을 입력하세요"
                  />
                </div>
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-login-password">비밀번호</label>
                  <input
                    id="portal-login-password"
                    className="portal-input"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="비밀번호를 입력하세요"
                  />
                </div>
                <button type="submit" className="btn primary portal-submit" disabled={loginLoading}>
                  {loginLoading ? "로그인 중..." : "로그인"}
                </button>
                <div className="portal-hint">
                  💡 회원 혜택: Gemini API 키 안전 보관, 모든 기기에서 상담 히스토리 영구 보관
                </div>
              </form>
            ) : (
              <form onSubmit={handleSignup} className="portal-form portal-form-tight">
                {signupError && <div className="portal-error" role="alert">{signupError}</div>}
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-signup-email">이메일 *</label>
                  <input
                    id="portal-signup-email"
                    className="portal-input"
                    type="email"
                    required
                    autoComplete="username"
                    value={signupEmail}
                    onChange={(e) => setSignupEmail(e.target.value)}
                    placeholder="user@example.com"
                  />
                </div>
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-signup-nickname">닉네임 *</label>
                  <input
                    id="portal-signup-nickname"
                    className="portal-input"
                    type="text"
                    required
                    value={signupNickname}
                    onChange={(e) => setSignupNickname(e.target.value)}
                    placeholder="표시될 닉네임"
                  />
                </div>
                <div className="portal-row2">
                  <div className="portal-field">
                    <label className="portal-label" htmlFor="portal-signup-password">비밀번호 *</label>
                    <input
                      id="portal-signup-password"
                      className="portal-input"
                      type="password"
                      required
                      autoComplete="new-password"
                      value={signupPassword}
                      onChange={(e) => setSignupPassword(e.target.value)}
                      placeholder="8자 이상"
                    />
                  </div>
                  <div className="portal-field">
                    <label className="portal-label" htmlFor="portal-signup-password2">비밀번호 확인 *</label>
                    <input
                      id="portal-signup-password2"
                      className="portal-input"
                      type="password"
                      required
                      autoComplete="new-password"
                      value={signupPasswordConfirm}
                      onChange={(e) => setSignupPasswordConfirm(e.target.value)}
                      placeholder="비밀번호 확인"
                    />
                  </div>
                </div>
                <div className="portal-field">
                  <span className="portal-label">기본 거주지 (선택)</span>
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
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-signup-age">만 나이 (선택)</label>
                  <input
                    id="portal-signup-age"
                    className="portal-input"
                    type="number"
                    value={signupAgeText}
                    onChange={(e) => setSignupAgeText(e.target.value)}
                    placeholder="만 나이 (예: 25)"
                  />
                </div>
                <button type="submit" className="btn primary portal-submit" disabled={signupLoading}>
                  {signupLoading ? "가입 처리 중..." : "회원가입 완료"}
                </button>
              </form>
            )}
          </section>

          {/* 우측: 기존 비회원 바로 시작하기 */}
          <section className="portal-panel portal-guest">
            <div>
              <div className="portal-guest-head">
                <span aria-hidden="true">🚀</span>
                <h3>비회원으로 바로 상담 시작</h3>
              </div>
              <p className="portal-hint portal-guest-lead">
                회원가입 없이 거주 지역과 나이를 입력하여 즉시 청년 맞춤형 복지정책 검색과 AI 상담을 시작할 수 있습니다.
              </p>

              <form onSubmit={handleGuestSubmit} className="portal-form">
                <div className="portal-field">
                  <span className="portal-label">거주 지역 선택 *</span>
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
                <div className="portal-field">
                  <label className="portal-label" htmlFor="portal-guest-age">만 나이 입력 (선택)</label>
                  <input
                    id="portal-guest-age"
                    className="portal-input"
                    type="number"
                    value={guestAgeText}
                    onChange={(e) => {
                      setGuestAgeText(e.target.value);
                      setGuestAgeError(null);
                    }}
                    placeholder="만 나이 (건너뛰려면 빈칸)"
                  />
                  {guestAgeError && <p className="portal-error" role="alert">{guestAgeError}</p>}
                </div>
                <button type="submit" className="btn primary portal-submit">
                  비회원 상담 시작하기 →
                </button>
              </form>
            </div>

            <div className="portal-note">
              ※ 비회원 이용 시 대화 내역은 현재 브라우저(LocalStorage)에만 임시 저장되며, 브라우저 캐시 삭제 시 초기화됩니다.
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
