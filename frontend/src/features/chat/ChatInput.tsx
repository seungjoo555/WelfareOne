import { useEffect, useRef, useState } from "react";
import { MAX_QUESTION_LENGTH } from "../../constants/text";

interface Props {
  disabled: boolean;
  placeholder: string;
  onSend: (text: string) => void;
}

export function ChatInput({ disabled, placeholder, onSend }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // 입력 줄 수에 맞춰 높이를 자동으로 늘린다(최대 160px).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText("");
  };

  return (
    <div className="input-row">
      <textarea
        ref={ref}
        rows={1}
        value={text}
        maxLength={MAX_QUESTION_LENGTH}
        placeholder={placeholder}
        aria-label="질문 입력"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          // 한글 조합 중에는 Enter가 두 번 발생하므로 isComposing을 확인한다.
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button type="button" className="btn primary" disabled={disabled || !text.trim()} onClick={submit}>
        전송
      </button>
    </div>
  );
}
