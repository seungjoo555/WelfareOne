// 화면 테마: "system"(OS 설정을 따름, 기본) / "light" / "dark".
// 선택값은 localStorage에만 저장한다. index.html의 인라인 스크립트가 같은 키로 첫 화면 전에 적용한다.

export type Theme = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "welfareone.theme";

export const THEME_LABELS: Record<Theme, string> = {
  system: "시스템",
  light: "라이트",
  dark: "다크",
};

export function getTheme(): Theme {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

// "system"이면 속성을 지워 CSS의 color-scheme: light dark가 OS 설정을 따르게 한다.
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

export function setTheme(theme: Theme): void {
  try {
    if (theme === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // 저장소를 쓸 수 없어도 이번 접속 동안은 적용된다
  }
  applyTheme(theme);
}
