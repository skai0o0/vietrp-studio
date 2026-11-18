import { beforeEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY, initTheme, useThemeStore } from "./theme";

describe("theme store", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({ theme: "oled-neon" });
    document.documentElement.setAttribute("data-theme", "oled-neon");
  });

  it("applies data-theme and persists on setTheme", () => {
    useThemeStore.getState().setTheme("e-ink");
    expect(document.documentElement.getAttribute("data-theme")).toBe("e-ink");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("e-ink");
  });

  it("toggles between the two themes", () => {
    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("e-ink");
    useThemeStore.getState().toggleTheme();
    expect(document.documentElement.getAttribute("data-theme")).toBe("oled-neon");
  });

  it("initTheme applies the current store value", () => {
    useThemeStore.setState({ theme: "e-ink" });
    initTheme();
    expect(document.documentElement.getAttribute("data-theme")).toBe("e-ink");
  });
});
