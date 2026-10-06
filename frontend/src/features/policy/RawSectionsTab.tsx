import { useEffect, useState } from "react";
import { getPolicy } from "../../api/policies";
import { toErrorCode } from "../../api/client";
import { SECTION_LABELS, SECTION_ORDER } from "../../constants/sections";
import { CRITERIA_NOTICE, ERROR_MESSAGES } from "../../constants/text";
import type { AppErrorCode, PolicyDetail } from "../../types/contract";

type State =
  | { status: "loading" }
  | { status: "error"; code: AppErrorCode }
  | { status: "ready"; detail: PolicyDetail };

// 원문에는 "key: value" 줄이 섞여 있어서 마크다운 변환 없이 줄바꿈 그대로 보여준다.
export function RawSectionsTab({ policyId }: { policyId: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    getPolicy(policyId)
      .then((detail) => !cancelled && setState({ status: "ready", detail }))
      .catch((error) => !cancelled && setState({ status: "error", code: toErrorCode(error) }));
    return () => {
      cancelled = true;
    };
  }, [policyId]);

  if (state.status === "loading") return <p className="muted raw">원문을 불러오는 중…</p>;
  if (state.status === "error") {
    return (
      <p className="error-box raw" role="alert">
        {ERROR_MESSAGES[state.code]}
      </p>
    );
  }

  return (
    <div className="raw">
      {SECTION_ORDER.map((key) => {
        const documents = state.detail.sections[key];
        if (!documents || documents.length === 0) return null;
        return (
          <section key={key}>
            <h4>{SECTION_LABELS[key]}</h4>
            {documents.map((text, index) => (
              <p key={index} className="raw-text">
                {text}
              </p>
            ))}
            {key === "target_criteria" && <p className="muted">{CRITERIA_NOTICE}</p>}
          </section>
        );
      })}
    </div>
  );
}
