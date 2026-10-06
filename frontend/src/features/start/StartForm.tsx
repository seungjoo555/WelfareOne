import { useEffect, useMemo, useState } from "react";
import { getRegions } from "../../api/regions";
import { ERROR_MESSAGES, SERVICE_NAME, DISCLAIMER } from "../../constants/text";
import { toErrorCode } from "../../api/client";
import type { AppErrorCode, RegionSelection, Regions } from "../../types/contract";
import { loadApiKey } from "../../utils/apiKey";
import { ApiKeyDialog } from "../settings/ApiKeyDialog";
import { ThemeToggle } from "../settings/ThemeToggle";
import { RegionSelect } from "./RegionSelect";

interface Props {
  initialRegion: RegionSelection | null;
  initialAge: number | null;
  onSubmit: (region: RegionSelection, age: number | null) => void;
  onCancel?: () => void;
}

type Loaded =
  | { status: "loading" }
  | { status: "error"; code: AppErrorCode }
  | { status: "ready"; regions: Regions };

// app/cli.py의 read_age와 같은 규칙: 비우면 null, 입력하면 0~120 정수
function parseAge(raw: string): { ok: true; value: number | null } | { ok: false; message: string } {
  const text = raw.trim();
  if (!text) return { ok: true, value: null };
  if (!/^\d+$/.test(text) || Number(text) > 120) {
    return { ok: false, message: "0부터 120 사이의 숫자를 입력해 주세요." };
  }
  return { ok: true, value: Number(text) };
}

export function StartForm({ initialRegion, initialAge, onSubmit, onCancel }: Props) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [level1, setLevel1] = useState(initialRegion?.level1 ?? "");
  const [level2, setLevel2] = useState(initialRegion?.level2 ?? "");
  const [ageText, setAgeText] = useState(initialAge === null ? "" : String(initialAge));
  const [ageError, setAgeError] = useState<string | null>(null);
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [keyVersion, setKeyVersion] = useState(0);
  // 저장소 값은 keyVersion이 바뀔 때(저장·삭제 후)만 다시 읽는다
  const hasKey = useMemo(() => loadApiKey() !== null, [keyVersion]);

  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    getRegions()
      .then((regions) => !cancelled && setLoaded({ status: "ready", regions }))
      .catch((error) => !cancelled && setLoaded({ status: "error", code: toErrorCode(error) }));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const age = parseAge(ageText);
    if (!age.ok) {
      setAgeError(age.message);
      return;
    }
    if (!level1) return;
    onSubmit({ level1, level2 }, age.value);
  };

  return (
    <main className="start">
      <div className="theme-corner">
        <ThemeToggle />
      </div>
      <form className="start-card" onSubmit={submit}>
        <h1>{SERVICE_NAME}</h1>
        <p className="lead">지역과 나이를 알려 주시면 내게 맞는 청년 복지정책을 찾아 드려요.</p>

        {loaded.status === "loading" && <p className="muted">지역 목록을 불러오는 중…</p>}
        {loaded.status === "error" && (
          <div className="error-box" role="alert">
            <p>{ERROR_MESSAGES[loaded.code]}</p>
            <button type="button" className="btn" onClick={() => setReloadKey((k) => k + 1)}>
              다시 불러오기
            </button>
          </div>
        )}
        {loaded.status === "ready" && (
          <RegionSelect
            regions={loaded.regions}
            level1={level1}
            level2={level2}
            onChange={(a, b) => {
              setLevel1(a);
              setLevel2(b);
            }}
          />
        )}

        <label className="field">
          <span>만 나이 (선택)</span>
          <input
            inputMode="numeric"
            placeholder="예: 24"
            value={ageText}
            onChange={(e) => {
              setAgeText(e.target.value);
              setAgeError(null);
            }}
            aria-invalid={ageError !== null}
            aria-describedby="age-help"
          />
          <small id="age-help" className={ageError ? "field-error" : "muted"}>
            {ageError ?? "입력하면 연령 기준이 명확한 정책 중 대상이 아닌 정책을 걸러내요."}
          </small>
        </label>

        <div className="actions">
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              취소
            </button>
          )}
          <button type="submit" className="btn primary" disabled={!level1 || loaded.status !== "ready"}>
            시작하기
          </button>
        </div>
        <p className="notice">
          {hasKey ? "Gemini API 키가 등록돼 있어요. " : "AI 답변에는 본인의 Gemini API 키가 필요해요. "}
          <button type="button" className="link-btn" onClick={() => setKeyDialogOpen(true)}>
            {hasKey ? "키 관리" : "키 입력"}
          </button>
        </p>
        <p className="notice">{DISCLAIMER}</p>
      </form>
      <ApiKeyDialog
        open={keyDialogOpen}
        onClose={() => setKeyDialogOpen(false)}
        onChange={() => setKeyVersion((v) => v + 1)}
      />
    </main>
  );
}
