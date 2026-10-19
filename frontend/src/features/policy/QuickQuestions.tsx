import { QUICK_QUESTIONS } from "../../constants/quickQuestions";
import { QUICK_QUESTIONS_LABEL } from "../../constants/text";
import type { AskIntent } from "../../types/contract";

interface Props {
  disabled: boolean; // 응답을 기다리는 중에는 누를 수 없다
  onAsk: (question: string, intent: AskIntent) => void;
  compact?: boolean; // 현재 정책 바에 넣는 작은 버전
}

// 선택한 정책에 대해 자주 묻는 질문을 버튼으로 바로 보낸다. 직접 입력해도 된다.
export function QuickQuestions({ disabled, onAsk, compact = false }: Props) {
  return (
    <div className={`quick-questions${compact ? " compact" : ""}`} role="group" aria-label={QUICK_QUESTIONS_LABEL}>
      {QUICK_QUESTIONS.map((item) => (
        <button
          key={item.id}
          type="button"
          className="chip quick-chip"
          disabled={disabled}
          onClick={() => onAsk(item.question, item.intent)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
