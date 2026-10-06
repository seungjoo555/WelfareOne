import { EXAMPLE_QUESTIONS } from "../../constants/text";

interface Props {
  disabled: boolean;
  onPick: (question: string) => void;
}

export function ExampleChips({ disabled, onPick }: Props) {
  return (
    <div className="chips" aria-label="예시 질문">
      {EXAMPLE_QUESTIONS.map((question) => (
        <button key={question} type="button" className="chip" disabled={disabled} onClick={() => onPick(question)}>
          {question}
        </button>
      ))}
    </div>
  );
}
