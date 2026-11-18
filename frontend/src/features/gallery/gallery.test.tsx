import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { errorMessage, t } from "@/i18n";
import type { GalleryItem } from "@/types/library";
import { GalleryView } from "./GalleryView";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function item(over: Partial<GalleryItem> = {}): GalleryItem {
  return {
    type: "character",
    id: "c1",
    name: "Mai",
    tagline: "Cô bán hoa",
    tags: ["slice-of-life"],
    image_url: null,
    author: "Lan",
    is_owner: false,
    is_favorite: false,
    favorite_count: 2,
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

let favoritesBody: GalleryItem[] = [];
let duplicateFails = false;
let favoriteRequest: Promise<Response> | null = null;

function route(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  if (url.startsWith("/api/gallery")) {
    const type = new URL(url, "http://x").searchParams.get("type");
    const items =
      type === "world" ? [item({ type: "world", id: "w1", name: "Thành phố mưa" })] : [item()];
    return Promise.resolve(json({ items, next_cursor: null }));
  }
  if (url === "/api/favorites") return Promise.resolve(json({ items: favoritesBody }));
  if (url.startsWith("/api/favorites/") && method !== "GET") {
    return favoriteRequest ?? Promise.resolve(new Response(null, { status: 204 }));
  }
  if (url.endsWith("/duplicate")) {
    return Promise.resolve(
      duplicateFails
        ? json({ error: { code: "not_found", message: "gone" } }, 404)
        : json({ character: { id: "c2" } }, 201),
    );
  }
  return Promise.resolve(json({}, 404));
}

function renderGallery() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GalleryView />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  favoritesBody = [];
  favoriteRequest = null;
  duplicateFails = false;
  vi.mocked(toast.error).mockClear();
  fetchMock.mockReset();
  fetchMock.mockImplementation(route);
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("GalleryView", () => {
  it("renders cards with a detail link, author and tag chips", async () => {
    renderGallery();
    const link = await screen.findByRole("link", { name: t("gallery.open", { name: "Mai" }) });
    expect(link).toHaveAttribute("href", "/characters/c1");
    expect(screen.getByText(t("gallery.byAuthor", { author: "Lan" }))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "slice-of-life" })).toBeInTheDocument();
  });

  it("switches to the world tab and queries type=world", async () => {
    const user = userEvent.setup();
    renderGallery();
    await screen.findByText("Mai");
    await user.click(screen.getByRole("tab", { name: t("gallery.tabs.world") }));
    expect(await screen.findByText("Thành phố mưa")).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.startsWith("/api/gallery") && u.includes("type=world"))).toBe(true);
  });

  it("toggles favorite optimistically before the server answers", async () => {
    const user = userEvent.setup();
    let release: (r: Response) => void = () => {};
    favoriteRequest = new Promise<Response>((resolve) => {
      release = resolve;
    });
    renderGallery();
    const button = await screen.findByRole("button", {
      name: t("gallery.favorite", { name: "Mai" }),
    });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await user.click(button);

    // The card also appears in the "Yêu thích của tôi" strip, so expect at least one.
    const pressed = (
      await screen.findAllByRole("button", { name: t("gallery.unfavorite", { name: "Mai" }) })
    )[0] as HTMLElement;
    expect(pressed).toHaveAttribute("aria-pressed", "true");
    expect(pressed).toHaveTextContent("3");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/favorites/character/c1",
      expect.objectContaining({ method: "PUT" }),
    );
    release(new Response(null, { status: 204 }));
  });

  it("rolls back the optimistic favorite when the request fails", async () => {
    const user = userEvent.setup();
    favoriteRequest = Promise.resolve(json({ error: { code: "not_found", message: "x" } }, 404));
    renderGallery();
    await user.click(
      await screen.findByRole("button", { name: t("gallery.favorite", { name: "Mai" }) }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: t("gallery.favorite", { name: "Mai" }) }),
      ).toHaveAttribute("aria-pressed", "false"),
    );
  });

  it("shows the Vietnamese not_found message when duplicating fails", async () => {
    const user = userEvent.setup();
    duplicateFails = true;
    renderGallery();
    await user.click(await screen.findByRole("button", { name: t("gallery.addToLibrary") }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(errorMessage("not_found")));
    expect(errorMessage("not_found")).not.toBe(errorMessage("unknown"));
  });

  it("shows the favorites section only when it is not empty", async () => {
    favoritesBody = [item({ is_favorite: true })];
    renderGallery();
    expect(await screen.findByText(t("gallery.favoritesSection"))).toBeInTheDocument();
  });

  it("hides the favorites section when empty", async () => {
    renderGallery();
    await screen.findByText("Mai");
    expect(screen.queryByText(t("gallery.favoritesSection"))).not.toBeInTheDocument();
  });

  it("adds a public card to the library", async () => {
    const user = userEvent.setup();
    renderGallery();
    await user.click(await screen.findByRole("button", { name: t("gallery.addToLibrary") }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/characters/c1/duplicate",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
