import ReactMarkdown from "react-markdown";
import type { AnswerResult } from "../../types/contract";
import { EvidenceToggle } from "./EvidenceToggle";
import { ResourceButtons } from "./ResourceButtons";

// react-markdown은 기본 설정에서 원문 HTML을 렌더링하지 않는다(LLM 출력 보호).
// rehype-raw 같은 플러그인을 추가하지 말 것.
export function AnswerBubble({ answer }: { answer: AnswerResult }) {
  return (
    <div className="answer">
      <div className="markdown">
        <ReactMarkdown>{answer.answer}</ReactMarkdown>
      </div>
      {!answer.grounded && (
        <p className="warning" role="note">
          제공된 공식 원문만으로 충분히 확인되지 않은 답변입니다.
        </p>
      )}
      <EvidenceToggle evidence={answer.evidence} />
      <ResourceButtons resources={answer.resources} />
    </div>
  );
}
