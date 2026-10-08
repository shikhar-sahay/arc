export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "arc-theme";

export function getInitialTheme(): Theme {
  const applied = document.documentElement.dataset.theme;
  if (applied === "dark" || applied === "light") return applied;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}
