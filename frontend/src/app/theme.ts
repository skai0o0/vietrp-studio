import { create } from "zustand";

export type ThemeId = "oled-neon" | "e-ink";

/** Keep in sync with the inline script in index.html. */
export const THEME_STORAGE_KEY = "vietrp.theme";
export const DEFAULT_THEME: ThemeId = "oled-neon";

function isThemeId(value: unknown): value is ThemeId {
  return value === "oled-neon" || value === "e-ink";
}

function readStoredTheme(): ThemeId {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemeId(stored)) return stored;
  } catch {
    /* storage blocked: fall back to the default */
  }
  return DEFAULT_THEME;
}

function applyTheme(theme: ThemeId): void {
  document.documentElement.setAttribute("data-theme", theme);
}

interface ThemeState {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readStoredTheme(),
  setTheme: (theme) => {
    applyTheme(theme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* storage blocked: the theme still applies for this session */
    }
    set({ theme });
  },
  toggleTheme: () => get().setTheme(get().theme === "oled-neon" ? "e-ink" : "oled-neon"),
}));

/** Applies the current theme to <html>; call once at startup (index.html already did it pre-paint). */
export function initTheme(): void {
  applyTheme(useThemeStore.getState().theme);
}
