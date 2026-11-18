import fs from "node:fs";
import path from "node:path";
import { act, render, renderHook, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppLayout } from "@/app/AppLayout";
import { useThemeStore } from "@/app/theme";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatInput } from "@/features/chat/components/ChatInput";
import { ReasoningBlock } from "@/features/chat/components/ReasoningBlock";
import { t } from "@/i18n";
import { useMotionKit } from "@/lib/motion";
import { useReducedMotion } from "@/lib/useReducedMotion";

function stubViewport(width: number, reducedMotion = false): void {
  vi.stubGlobal("matchMedia", (query: string): MediaQueryList => {
    let matches = false;
    const widthMatch = /min-width:\s*(\d+)px/.exec(query);
    if (widthMatch) matches = width >= Number(widthMatch[1]);
    if (query.includes("prefers-reduced-motion")) matches = reducedMotion;
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    } as MediaQueryList;
  });
}

describe("P7 E-ink, OLED Neon & mobile 375px verification", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({ theme: "oled-neon" });
    document.documentElement.setAttribute("data-theme", "oled-neon");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("defines required CSS tokens for OLED Neon and E-ink (no glow/motion, serif chat)", () => {
    const themesDir = path.resolve(process.cwd(), "src/styles/themes");
    const oledCss = fs.readFileSync(path.join(themesDir, "oled-neon.css"), "utf-8");
    const einkCss = fs.readFileSync(path.join(themesDir, "e-ink.css"), "utf-8");

    expect(oledCss).toContain("--bg: 0 0 0;");
    expect(oledCss).toContain("--motion: 1;");

    expect(einkCss).toContain("--glow: none;");
    expect(einkCss).toContain("--motion: 0;");
    expect(einkCss).toContain("serif");
    expect(einkCss).toContain("box-shadow: none !important;");
    expect(einkCss).toContain("animation: none !important;");
    expect(einkCss).toContain('.token-bar-fill[data-level="notice"]');
  });

  it("forces reduced motion on E-ink and restores motion on OLED Neon", () => {
    stubViewport(1440, false);
    const { result } = renderHook(() => ({
      reduced: useReducedMotion(),
      kit: useMotionKit(),
    }));

    expect(result.current.reduced).toBe(false);
    expect(result.current.kit.hoverTap).not.toEqual({});

    act(() => {
      useThemeStore.getState().setTheme("e-ink");
    });

    expect(document.documentElement.getAttribute("data-theme")).toBe("e-ink");
    expect(result.current.reduced).toBe(true);
    expect(result.current.kit.reduced).toBe(true);
    expect(result.current.kit.transition).toEqual({ duration: 0 });
    expect(result.current.kit.hoverTap).toEqual({});
  });

  it("renders mobile 375px layout, token bar chat input, and reasoning block under E-ink", () => {
    stubViewport(375, false);
    act(() => {
      useThemeStore.getState().setTheme("e-ink");
    });

    const router = createMemoryRouter(
      [
        {
          element: <AppLayout />,
          children: [
            {
              index: true,
              element: (
                <div>
                  <ReasoningBlock text="Suy nghĩ ngắn gọn." saved />
                  <ChatInput
                    isStreaming={false}
                    usedTokens={650}
                    budget={1000}
                    onSend={vi.fn()}
                    onStop={vi.fn()}
                    onOpenInspector={vi.fn()}
                    onTextChange={vi.fn()}
                  />
                </div>
              ),
            },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );

    render(
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>,
    );

    expect(document.documentElement.getAttribute("data-theme")).toBe("e-ink");
    expect(screen.getByRole("navigation", { name: t("nav.mobile") })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: t("nav.primary") })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(t("chat.input.placeholderShort"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t("chat.reasoning.saved") })).toBeInTheDocument();
    expect(screen.getByTitle(/650 \/ 1\.?000/)).toHaveAttribute("data-level", "notice");
  });
});
