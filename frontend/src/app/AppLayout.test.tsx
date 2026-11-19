import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import ChatsHubPage from "@/pages/ChatsHubPage";
import { AppLayout } from "./AppLayout";
import { NAV_ITEMS, isNavActive } from "./navItems";
import { usePageChrome } from "./pageChrome";

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

function renderLayout(initialEntry = "/"): void {
  const router = createMemoryRouter(
    [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <p>nội dung</p> },
          { path: "/chats", element: <ChatsHubPage /> },
        ],
      },
    ],
    { initialEntries: [initialEntry] },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function DrawerPage() {
  usePageChrome({
    left: (
      <div>
        <Link to="/other">Chuyển trang</Link>
      </div>
    ),
    leftTitle: "Đoạn chat",
  });
  return <p>Trang có thanh bên</p>;
}

describe("AppLayout & Wave 2 IA", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders 5 nav items including Chat on mobile and desktop", () => {
    mockViewport(375);
    renderLayout();
    const mobileNav = screen.getByRole("navigation", { name: t("nav.mobile") });
    expect(mobileNav).toBeInTheDocument();
    expect(mobileNav.querySelectorAll("a")).toHaveLength(5);
    expect(mobileNav.querySelector('a[href="/chats"]')).toHaveTextContent(t("nav.chats"));
    expect(screen.queryByRole("navigation", { name: t("nav.primary") })).not.toBeInTheDocument();
  });

  it("renders the IconRail on desktop widths", () => {
    mockViewport(1440);
    renderLayout();
    const rail = screen.getByRole("navigation", { name: t("nav.primary") });
    expect(rail).toBeInTheDocument();
    expect(rail.querySelector('a[href="/chats"]')).toBeInTheDocument();
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

  it("matches active nav items across chat, library detail, and creator routes", () => {
    const chatsItem = NAV_ITEMS.find((i) => i.id === "chats")!;
    const libItem = NAV_ITEMS.find((i) => i.id === "library")!;
    const createItem = NAV_ITEMS.find((i) => i.id === "create")!;

    expect(isNavActive(chatsItem, "/chats")).toBe(true);
    expect(isNavActive(chatsItem, "/chat/c1")).toBe(true);
    expect(isNavActive(chatsItem, "/create/chat")).toBe(true);
    expect(isNavActive(libItem, "/characters/abc")).toBe(true);
    expect(isNavActive(libItem, "/worlds/w1")).toBe(true);
    expect(isNavActive(createItem, "/create")).toBe(true);
    expect(isNavActive(createItem, "/create/chat")).toBe(false);
  });

  it("auto-closes mobile/tablet Sheet drawer when navigating to another route", () => {
    mockViewport(900);
    const router = createMemoryRouter(
      [
        {
          element: <AppLayout />,
          children: [
            { path: "/", element: <DrawerPage /> },
            { path: "/other", element: <p>Trang khác</p> },
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

    fireEvent.click(screen.getByRole("button", { name: t("layout.openLeftSidebar") }));
    expect(screen.getByRole("link", { name: "Chuyển trang" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Chuyển trang" }));
    expect(screen.getByText("Trang khác")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Chuyển trang" })).not.toBeInTheDocument();
  });

  it("renders ChatsHubPage quick-start cards at /chats", () => {
    mockViewport(1440);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 })),
    );
    renderLayout("/chats");
    expect(screen.getByRole("heading", { name: t("pages.chatsHub.title") })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Chat đơn/ })).toHaveAttribute("href", "/chats/new");
    expect(screen.getByRole("link", { name: /Chat Thực tại/ })).toHaveAttribute(
      "href",
      "/chats/new?mode=world",
    );
  });
});
