import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import { CharactersList, LorebooksList, PersonasList } from "./list/Lists";
import { characterOut, json, mockApi, renderAt } from "./testHelpers";

vi.mock("@/features/io", () => ({
  ImportButton: () => <button type="button">import-button</button>,
  ExportMenu: () => <button type="button">export-menu</button>,
}));

afterEach(() => vi.unstubAllGlobals());

const page = (items: unknown[]) => json(200, { items, next_cursor: null });

describe("characters list", () => {
  it("renders cards with the needs-age and visibility badges", async () => {
    mockApi((call) =>
      call.path.startsWith("/api/characters")
        ? page([
            characterOut({ id: "c1", name: "Mai", needs_age: true }),
            characterOut({ id: "c2", name: "Lan", visibility: "public", tags: ["nsfw"] }),
          ])
        : undefined,
    );
    renderAt(<CharactersList />, "/library/characters", "/library/characters");

    expect(await screen.findByRole("heading", { name: "Mai" })).toBeInTheDocument();
    expect(screen.getAllByText(t("library.badge.needsAge"))).toHaveLength(1);
    expect(screen.getByText(t("library.badge.public"))).toBeInTheDocument();
    expect(screen.getByText(t("library.badge.private"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Mai/ })).toHaveAttribute("href", "/characters/c1");
    // tag chips come from the loaded items
    expect(screen.getByRole("button", { name: "school" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows the empty state with a create link", async () => {
    mockApi((call) => (call.path.startsWith("/api/characters") ? page([]) : undefined));
    renderAt(<CharactersList />, "/library/characters", "/library/characters");

    expect(await screen.findByText(t("pages.library.characters.empty"))).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: t("library.actions.create") });
    expect(links[0]).toHaveAttribute("href", "/characters/new");
  });

  it("sends the search text and the selected tag to the API", async () => {
    const calls = mockApi((call) =>
      call.path.startsWith("/api/characters") ? page([characterOut()]) : undefined,
    );
    renderAt(<CharactersList />, "/library/characters", "/library/characters");
    await screen.findByRole("heading", { name: "Mai" });

    await userEvent.type(screen.getByLabelText(t("library.list.searchCharacters")), "mai");
    await waitFor(() => expect(calls.some((c) => c.path.includes("q=mai"))).toBe(true));

    await userEvent.click(screen.getByRole("button", { name: "school" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("tag=school"))).toBe(true));
  });

  it("shows a no-results message instead of the create CTA while filtering", async () => {
    mockApi((call) => {
      if (!call.path.startsWith("/api/characters")) return undefined;
      return call.path.includes("q=zzz") ? page([]) : page([characterOut()]);
    });
    renderAt(<CharactersList />, "/library/characters", "/library/characters");
    await screen.findByRole("heading", { name: "Mai" });

    await userEvent.type(screen.getByLabelText(t("library.list.searchCharacters")), "zzz");
    expect(await screen.findByText(t("library.list.noResults"))).toBeInTheDocument();
  });
});

describe("other lists", () => {
  it("lists lorebooks with their entry count", async () => {
    mockApi((call) =>
      call.path.startsWith("/api/lorebooks")
        ? page([
            {
              id: "l1",
              name: "Lore trường",
              entry_count: 3,
              visibility: "private",
              updated_at: "x",
            },
          ])
        : undefined,
    );
    renderAt(<LorebooksList />, "/library/lorebooks", "/library/lorebooks");
    expect(await screen.findByRole("heading", { name: "Lore trường" })).toBeInTheDocument();
    expect(screen.getByText(t("library.lorebooks.entryCount", { count: 3 }))).toBeInTheDocument();
  });

  it("filters personas by name on the client", async () => {
    mockApi((call) =>
      call.path === "/api/personas"
        ? json(200, {
            items: [
              {
                id: "p1",
                data: { name: "Hùng", age: 20 },
                avatar_url: null,
                created_at: "x",
                updated_at: "x",
              },
              {
                id: "p2",
                data: { name: "Linh" },
                avatar_url: null,
                created_at: "x",
                updated_at: "x",
              },
            ],
          })
        : undefined,
    );
    renderAt(<PersonasList />, "/library/personas", "/library/personas");
    expect(await screen.findByRole("heading", { name: "Hùng" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(t("library.list.searchPersonas")), "lin");
    expect(screen.queryByRole("heading", { name: "Hùng" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Linh" })).toBeInTheDocument();
  });
});
