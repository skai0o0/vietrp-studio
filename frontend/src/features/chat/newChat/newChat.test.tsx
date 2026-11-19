import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { characterOut } from "@/features/library/testHelpers";
import { t } from "@/i18n";
import type { CharacterOut } from "@/types/library";
import NewChatPage from "./NewChatPage";

const mocks = vi.hoisted(() => ({
  character: undefined as unknown,
  mutate: vi.fn(),
}));

vi.mock("@/features/library/hooks", () => ({
  useCharacter: () => ({ data: mocks.character }),
  useCharacters: () => ({ isPending: false, isSuccess: true, data: { pages: [{ items: [] }] } }),
  usePersonas: () => ({ isSuccess: true, data: [] }),
}));
vi.mock("../hooks", () => ({
  useCreateChat: () => ({ mutate: mocks.mutate, isPending: false }),
  useChats: () => ({ isSuccess: true, isError: false, data: [] }),
}));

function renderPage(card: CharacterOut) {
  mocks.character = card;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/create/chat?character=${card.id}`]}>
        <Routes>
          <Route path="/create/chat" element={<NewChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function withGreetings(greetings: string[]): CharacterOut {
  const base = characterOut();
  return { ...base, data: { ...base.data, greetings } };
}

describe("NewChatPage", () => {
  beforeEach(() => mocks.mutate.mockReset());

  it("replaces {{user}} in the greeting preview with the fallback name", () => {
    renderPage(withGreetings(["Chào {{user}}, tôi là {{char}}."]));
    expect(screen.getByText(/Chào người chơi, tôi là/)).toBeTruthy();
  });

  it("links directly to persona creation from PersonaPicker", () => {
    renderPage(withGreetings(["Xin chào"]));
    expect(
      screen.getByRole("link", { name: t("newChat.createPersona") }).getAttribute("href"),
    ).toBe("/library/personas/new");
  });

  it("blocks cards that need an age and links to the editor", () => {
    renderPage(characterOut({ id: "c9", needs_age: true }));
    expect(screen.getByTestId("needs-age-block")).toBeTruthy();
    expect(screen.getByRole("link", { name: t("newChat.fixInEditor") }).getAttribute("href")).toBe(
      "/characters/c9",
    );
    expect(
      (screen.getByRole("button", { name: t("newChat.create") }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("swipes greetings and creates the chat with the chosen index", () => {
    renderPage(withGreetings(["Xin chào", "Chào buổi sáng"]));
    expect(screen.getByTestId("greeting-counter").textContent).toBe("1/2");
    fireEvent.click(screen.getByRole("button", { name: t("newChat.nextGreeting") }));
    expect(screen.getByTestId("greeting-counter").textContent).toBe("2/2");
    fireEvent.click(screen.getByRole("button", { name: t("newChat.create") }));
    expect(mocks.mutate.mock.calls[0]?.[0]).toEqual({
      character_id: "c1",
      persona_id: null,
      greeting_index: 1,
    });
  });
});
