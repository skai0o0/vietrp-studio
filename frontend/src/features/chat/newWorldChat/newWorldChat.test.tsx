import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { json, mockApi, worldOut } from "@/features/library/testHelpers";
import { WorldEditor } from "@/features/library/world/WorldEditor";
import { t } from "@/i18n";
import type { CharacterSummary, PersonaOut, WorldOut, WorldSummary } from "@/types/library";
import NewChatPage from "../newChat/NewChatPage";

vi.mock("@/features/io", () => ({
  ImportButton: () => <button type="button">import-button</button>,
  ExportMenu: () => <button type="button">export-menu</button>,
}));

afterEach(() => vi.unstubAllGlobals());

const WORLD_SUMMARY: WorldSummary = {
  id: "w1",
  name: "Sài Gòn Mưa",
  tagline: "Đêm mưa phố đi bộ",
  tags: ["slice-of-life"],
  visibility: "private",
  cover_url: null,
  needs_age: false,
  updated_at: "2026-11-18T00:00:00Z",
};

const WORLD_DETAIL: WorldOut = worldOut({
  id: "w1",
  name: "Sài Gòn Mưa",
  data: {
    format: "vietrp-world",
    spec_version: "1.0",
    name: "Sài Gòn Mưa",
    rules: "Đời thường.",
    locations: [
      { id: "vn", parent_id: null, level: "country", name: "Việt Nam", description: "" },
      { id: "hcm", parent_id: "vn", level: "province", name: "TP.HCM", description: "" },
      { id: "cafe", parent_id: "hcm", level: "place", name: "Quán cà phê", description: "" },
    ],
    openings: [
      {
        id: "op1",
        title: "Chiều mưa",
        message: "Trời đổ mưa, {{user}} vừa bước vào quán.",
        time: "17:30 Thứ Sáu",
        location_id: "cafe",
        present_ids: ["c1"],
        tension: 1,
        player_role: "Khách quen mới tới",
      },
      {
        id: "op2",
        title: "Đêm muộn",
        message: "Quán sắp đóng cửa khi {{user}} quay lại.",
        time: "22:00 Thứ Bảy",
        location_id: "hcm",
        present_ids: ["c1"],
        tension: 3,
        player_role: "Bạn học cũ",
      },
    ],
  },
});

const CHARACTERS: CharacterSummary[] = [
  {
    id: "c1",
    name: "Vy",
    tagline: "Chủ quán cà phê",
    tags: [],
    visibility: "private",
    avatar_url: null,
    needs_age: false,
    updated_at: "2026-11-18T00:00:00Z",
  },
  {
    id: "c2",
    name: "Hân",
    tagline: "Bạn thân của Vy",
    tags: [],
    visibility: "private",
    avatar_url: null,
    needs_age: false,
    updated_at: "2026-11-18T00:00:00Z",
  },
  {
    id: "c_no_age",
    name: "Minh",
    tagline: "Thiếu tuổi",
    tags: [],
    visibility: "private",
    avatar_url: null,
    needs_age: true,
    updated_at: "2026-11-18T00:00:00Z",
  },
];

const PERSONAS: PersonaOut[] = [
  {
    id: "p1",
    avatar_url: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
    data: { format: "vietrp-persona", spec_version: "1.0", name: "Nam", aliases: [] },
  },
];

function renderNewChat(initialRoute = "/create/chat") {
  const calls = mockApi((call) => {
    if (call.path.startsWith("/api/worlds?")) {
      return json(200, { items: [WORLD_SUMMARY], next_cursor: null });
    }
    if (call.path === "/api/worlds/w1") {
      return json(200, { world: WORLD_DETAIL });
    }
    if (call.path.startsWith("/api/characters?")) {
      return json(200, { items: CHARACTERS, next_cursor: null });
    }
    if (call.path === "/api/personas") {
      return json(200, { items: PERSONAS });
    }
    if (call.path.startsWith("/api/chats") && call.method === "GET") {
      return json(200, []);
    }
    if (call.path === "/api/chats" && call.method === "POST") {
      return json(201, {
        id: "chat_w1",
        mode: "world",
        title: "Sài Gòn Mưa",
        persona_id: "p1",
        world_id: "w1",
        world_name: "Sài Gòn Mưa",
        opening_id: "op2",
        cast: [],
        messages_count: 1,
        settings: {},
        state: {},
        created_at: "2026-11-18T00:00:00Z",
        updated_at: "2026-11-18T00:00:00Z",
      });
    }
    return undefined;
  });

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/create/chat" element={<NewChatPage />} />
          <Route path="/chat/:chatId" element={<p data-testid="chat-route">opened chat</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

describe("NewWorldChat flow", () => {
  it("switches to world mode, swipes openings, blocks needs_age cast, and creates a world chat", async () => {
    const calls = renderNewChat("/create/chat");

    // Defaults to single mode, then switches via tab.
    expect(screen.getByRole("tab", { name: t("worldChat.modeSingle") })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.click(screen.getByRole("tab", { name: t("worldChat.modeWorld") }));

    // Step 1: Pick a world.
    const worldBtn = await screen.findByRole("button", { name: /Sài Gòn Mưa/ });
    await userEvent.click(worldBtn);

    // Step 2: Opening 1 preview with location path, time, tension, player_role, and {{user}} replacement.
    expect(await screen.findByTestId("opening-counter")).toHaveTextContent("1/2");
    expect(screen.getByText("Việt Nam › TP.HCM › Quán cà phê")).toBeInTheDocument();
    expect(screen.getByText(/17:30 Thứ Sáu/)).toBeInTheDocument();
    expect(screen.getByTestId("opening-tension")).toHaveTextContent(t("library.world.tension.t1"));
    expect(screen.getByText(/Khách quen mới tới/)).toBeInTheDocument();
    expect(screen.getByText(/Trời đổ mưa, người chơi vừa bước vào quán\./)).toBeInTheDocument();

    // Swipe to Opening 2 via accessible button.
    await userEvent.click(screen.getByRole("button", { name: t("worldChat.nextOpening") }));
    expect(screen.getByTestId("opening-counter")).toHaveTextContent("2/2");
    expect(screen.getByTestId("opening-tension")).toHaveTextContent(t("library.world.tension.t3"));

    // Step 3: Needs-age card is blocked with alert + editor link and disabled checkbox.
    const blockedBlock = screen.getByTestId("needs-age-block-c_no_age");
    expect(blockedBlock).toBeInTheDocument();
    expect(blockedBlock.querySelector('a[href="/characters/c_no_age"]')?.textContent).toBe(
      t("newChat.fixInEditor"),
    );
    const minhCheckbox = screen.getByRole("checkbox", { name: /Minh/ });
    expect(minhCheckbox).toBeDisabled();

    // Select Vy and Hân.
    await userEvent.click(screen.getByRole("checkbox", { name: /^Vy/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^Hân/ }));

    // Step 4: Pick persona Nam -> updates {{user}} in opening preview too.
    await userEvent.click(screen.getByRole("radio", { name: "Nam" }));
    expect(screen.getByText(/Quán sắp đóng cửa khi Nam quay lại\./)).toBeInTheDocument();

    // Create chat and navigate to /chat/chat_w1.
    await userEvent.click(screen.getByRole("button", { name: t("worldChat.create") }));
    await waitFor(() => expect(screen.getByTestId("chat-route")).toBeInTheDocument());

    const post = calls.find((c) => c.path === "/api/chats" && c.method === "POST");
    expect(post?.body).toEqual({
      mode: "world",
      world_id: "w1",
      opening_id: "op2",
      cast_ids: ["c1", "c2"],
      persona_id: "p1",
    });
  });

  it("opens directly in world mode when ?mode=world&world=w1 is in the URL", async () => {
    renderNewChat("/create/chat?mode=world&world=w1");
    expect(screen.getByRole("tab", { name: t("worldChat.modeWorld") })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await screen.findByTestId("opening-counter")).toHaveTextContent("1/2");
  });

  it("renders a Chat link on WorldEditor when editing an existing world", async () => {
    mockApi((call) => {
      if (call.path === "/api/worlds/w1") return json(200, { world: WORLD_DETAIL });
      if (call.path.startsWith("/api/lorebooks"))
        return json(200, { items: [], next_cursor: null });
      return undefined;
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/worlds/w1"]}>
          <Routes>
            <Route path="/worlds/:id" element={<WorldEditor id="w1" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const chatLink = await screen.findByRole("link", { name: t("newChat.startChat") });
    expect(chatLink).toHaveAttribute("href", "/create/chat?mode=world&world=w1");
  });
});
