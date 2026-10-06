import { useState } from "react";
import { THEME_LABELS, getTheme, setTheme } from "../../utils/theme";
import type { Theme } from "../../utils/theme";

const OPTIONS: Theme[] = ["system", "light", "dark"];

// Chrome 설정처럼 시스템 / 라이트 / 다크 중 하나를 고르는 3버튼.
export function ThemeToggle() {
  const [theme, setCurrent] = useState<Theme>(getTheme);

  return (
    <div className="theme-toggle" role="group" aria-label="화면 테마">
      {OPTIONS.map((option) => (
        <button
          key={option}
          type="button"
          className={`theme-option${theme === option ? " active" : ""}`}
          aria-pressed={theme === option}
          onClick={() => {
            setTheme(option);
            setCurrent(option);
          }}
        >
          {THEME_LABELS[option]}
        </button>
      ))}
    </div>
  );
}
