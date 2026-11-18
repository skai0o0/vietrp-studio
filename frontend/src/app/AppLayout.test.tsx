import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { AppLayout } from "./AppLayout";

function mockViewport(width: number): void {
  vi.stubGlobal("matchMedia", (query: string): MediaQueryList => {
    const match = /min-width:\s*(\d+)px/.exec(query);
    const matches = match ? width >= Number(match[1]) : false;
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

function renderLayout(): void {
  const router = createMemoryRouter(
    [{ element: <AppLayout />, children: [{ index: true, element: <p>nội dung</p> }] }],
    { initialEntries: ["/"] },
  );
  render(
    <TooltipProvider>
      <RouterProvider router={router} />
    </TooltipProvider>,
  );
}

describe("AppLayout", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the BottomNav on mobile widths", () => {
    mockViewport(375);
    renderLayout();
    expect(screen.getByRole("navigation", { name: t("nav.mobile") })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: t("nav.primary") })).not.toBeInTheDocument();
  });

  it("renders the IconRail on desktop widths", () => {
    mockViewport(1440);
    renderLayout();
    expect(screen.getByRole("navigation", { name: t("nav.primary") })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: t("nav.mobile") })).not.toBeInTheDocument();
  });

  it("renders the IconRail on tablet widths and a skip link", () => {
    mockViewport(900);
    renderLayout();
    expect(screen.getByRole("navigation", { name: t("nav.primary") })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t("app.skipToContent") })).toHaveAttribute(
      "href",
      "#main-content",
    );
  });
});
