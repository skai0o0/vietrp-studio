import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePageChromeStore } from "@/app/pageChrome";
import { worldOut } from "@/features/library/testHelpers";
import { t } from "@/i18n";
import type { ChatOut, ChatSummary, WorldState } from "@/types/chat";
import { ApiError } from "@/lib/apiClient";
import { RecentChats } from "../newChat/RecentChats";
import { ChatChrome } from "../settings/ChatChrome";
import { ChatSettingsPanel } from "../settings/ChatSettingsPanel";
import { initialTurnState, useChatStreamStore } from "../store";
import { LiveStateEditor } from "./LiveStateEditor";
import { MAX_MEMORABLE_EVENTS, MemorySection } from "./MemorySection";

const mocks = vi.hoisted(() => ({
  patchState: vi.fn(),
  updateChat: vi.fn(),
  summarize: vi.fn(),
  chat: undefined as ChatOut | undefined,
  chats: [] as ChatSummary[],
  world: undefined as ReturnType<typeof worldOut> | undefined,
  isPending: false,
  isError: false,
  summarizePending: false,
  summarizeError: false,
  summarizeErrorObj: null as unknown,
}));

vi.mock("../hooks", () => ({
  useChat: () => ({ data: mocks.chat, isError: false }),
  useChats: () => ({ data: mocks.chats, isSuccess: true, isError: false }),
  usePatchState: () => ({
    mutate: mocks.patchState,
    isPending: mocks.isPending,
    isError: mocks.isError,
  }),
  useSummarizeChat: () => ({
    mutate: mocks.summarize,
    isPending: mocks.summarizePending,
    isError: mocks.summarizeError,
    error: mocks.summarizeErrorObj,
  }),
  useUpdateChat: () => ({ mutate: mocks.updateChat, isError: false }),
  useModels: () => ({ data: [], isError: false }),
}));

vi.mock("@/features/library/hooks", () => ({
  useWorld: () => ({ data: mocks.world }),
}));

function makeWorldChat(stateOverrides: Partial<WorldState> = {}): ChatOut {
  return {
    id: "cw1",
    mode: "world",
    title: "Sài Gòn Mưa",
    persona_id: "p1",
    world_id: "w1",
    world_name: "Sài Gòn Mưa",
    opening_id: "op1",
    cast: [
      { id: "vy", character_id: "c1", name: "Vy", tagline: "Chủ quán", avatar_url: null },
      { id: "han", character_id: "c2", name: "Hân", tagline: "Bạn thân", avatar_url: null },
    ],
    messages_count: 3,
    settings: {
      director: { enabled: true, stream_mode: "draft_then_replace" },
      group: { write_mode: "per_character", chain_max: 3 },
      nsfw: false,
    },
    state: {
      location_id: "cafe",
      time: "19:30 Thứ Sáu",
      tension: 1,
      present_ids: ["vy"],
      awaiting_reply: ["vy"],
      silence: { vy: 0, han: 2 },
      scene: {
        env: { weather: "mưa nhỏ" },
        chars: {
          vy: { mood: "vui", outfit: "áo sơ mi", pose: "đứng", holding: "ly trà", condition: "" },
          han: { mood: "buồn ngủ", outfit: "áo khoác", pose: "", holding: "", condition: "" },
        },
        items: ["cuốn sổ"],
      },
      bonds: {
        "vy:user": {
          pair_id: "vy:user",
          label: "Vy ↔ Nam",
          fields: {
            addressing: "tôi - cậu",
            nickname: "Nam",
            relationship: "Bạn cùng lớp",
            stance: "thân thiện",
            closeness: 2,
            history: "Quen từ năm nhất",
          },
          pinned: ["addressing"],
          manual: ["nickname"],
          changes: [{ seq: 2, field: "stance", old: "xa cách", new: "thân thiện" }],
        },
      },
      manual: ["time"],
      ...stateOverrides,
    },
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
  };
}

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.patchState.mockReset();
  mocks.updateChat.mockReset();
  mocks.summarize.mockReset();
  mocks.isPending = false;
  mocks.isError = false;
  mocks.summarizePending = false;
  mocks.summarizeError = false;
  mocks.summarizeErrorObj = null;
  useChatStreamStore.setState({ turns: {} });
  usePageChromeStore.setState({ left: null, right: null, railFooter: null });
  mocks.world = worldOut({
    id: "w1",
    name: "Sài Gòn Mưa",
    data: {
      format: "vietrp-world",
      spec_version: "1.0",
      name: "Sài Gòn Mưa",
      locations: [
        { id: "vn", parent_id: null, level: "country", name: "Việt Nam", description: "" },
        { id: "hcm", parent_id: "vn", level: "province", name: "TP.HCM", description: "" },
        { id: "cafe", parent_id: "hcm", level: "place", name: "Quán cà phê", description: "" },
      ],
      openings: [],
    },
  });
  mocks.chat = makeWorldChat();
});

describe("LiveStateEditor", () => {
  it("renders location tree path, hides absent chars from scene, and shows manual badges", () => {
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    // Location tree option uses full hierarchy path.
    const locationSelect = screen.getByLabelText(t("stateEditor.structured.location"));
    expect(
      within(locationSelect).getByRole("option", { name: "Việt Nam › TP.HCM › Quán cà phê" }),
    ).toBeInTheDocument();

    // Time field has a manual badge because state.manual includes "time".
    expect(screen.getAllByText(t("stateEditor.manualBadge")).length).toBeGreaterThanOrEqual(2);

    // Structured state wins: Vy is present (rendered), Hân is absent (hidden).
    expect(screen.getByTestId("scene-char-vy")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-char-han")).toBeNull();
  });

  it("edits structured fields and submits minimal diff via usePatchState", async () => {
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    fireEvent.change(screen.getByLabelText(t("stateEditor.structured.location")), {
      target: { value: "hcm" },
    });
    fireEvent.change(screen.getByLabelText(t("stateEditor.structured.tension")), {
      target: { value: "3" },
    });
    const presentGroup = screen.getByRole("group", {
      name: t("stateEditor.structured.present"),
    });
    await userEvent.click(within(presentGroup).getByRole("button", { name: /Hân/ }));

    const structuredSection = screen.getByRole("region", {
      name: t("stateEditor.structured.title"),
    });
    await userEvent.click(
      within(structuredSection).getByRole("button", { name: t("stateEditor.save") }),
    );

    expect(mocks.patchState).toHaveBeenCalledWith(
      {
        location_id: "hcm",
        tension: 3,
        present_ids: ["vy", "han"],
      },
      expect.any(Object),
    );
  });

  it("edits scene env, char fields, and items via usePatchState", async () => {
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    await userEvent.type(
      screen.getByLabelText(t("stateEditor.scene.envKeyPlaceholder")),
      "ánh sáng",
    );
    await userEvent.type(
      screen.getByLabelText(t("stateEditor.scene.envValuePlaceholder")),
      "đèn vàng",
    );
    await userEvent.click(screen.getByRole("button", { name: t("stateEditor.scene.addEnv") }));

    await userEvent.type(screen.getByLabelText(t("stateEditor.scene.itemPlaceholder")), "chiếc ô");
    await userEvent.click(screen.getByRole("button", { name: t("stateEditor.scene.addItem") }));

    const moodInput = screen.getByLabelText(t("stateEditor.scene.mood"));
    fireEvent.change(moodInput, { target: { value: "hào hứng" } });

    const sceneSection = screen.getByRole("region", { name: t("stateEditor.scene.title") });
    await userEvent.click(
      within(sceneSection).getByRole("button", { name: t("stateEditor.save") }),
    );

    expect(mocks.patchState).toHaveBeenCalledWith(
      {
        scene: {
          env: { weather: "mưa nhỏ", "ánh sáng": "đèn vàng" },
          chars: {
            vy: {
              mood: "hào hứng",
              outfit: "áo sơ mi",
              pose: "đứng",
              holding: "ly trà",
              condition: "",
            },
            han: { mood: "buồn ngủ", outfit: "áo khoác", pose: "", holding: "", condition: "" },
          },
          items: ["cuốn sổ", "chiếc ô"],
        },
      },
      expect.any(Object),
    );
  });

  it("renders pinned and manual badges on bonds and saves edited fields", async () => {
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    const pairCard = screen.getByTestId("bond-pair-vy:user");
    expect(within(pairCard).getByText(t("stateEditor.bonds.pinnedBadge"))).toBeInTheDocument();
    expect(within(pairCard).getByText(t("stateEditor.manualBadge"))).toBeInTheDocument();

    // Pinned addressing field is disabled/readOnly.
    const addressingInput = within(pairCard).getByLabelText(
      t("stateEditor.bonds.fields.addressing"),
    );
    expect(addressingInput).toBeDisabled();

    // Edit non-pinned stance and closeness.
    const stanceInput = within(pairCard).getByLabelText(t("stateEditor.bonds.fields.stance"));
    fireEvent.change(stanceInput, { target: { value: "tin tưởng" } });
    fireEvent.change(within(pairCard).getByLabelText(t("stateEditor.bonds.fields.closeness")), {
      target: { value: "4" },
    });

    await userEvent.click(
      within(pairCard).getByRole("button", { name: t("stateEditor.bonds.savePair") }),
    );

    expect(mocks.patchState).toHaveBeenCalledWith(
      {
        bonds: {
          "vy:user": {
            pair_id: "vy:user",
            label: "Vy ↔ Nam",
            fields: {
              addressing: "tôi - cậu",
              nickname: "Nam",
              relationship: "Bạn cùng lớp",
              stance: "tin tưởng",
              closeness: 4,
              history: "Quen từ năm nhất",
            },
            pinned: ["addressing"],
            manual: ["nickname", "stance", "closeness"],
            changes: [{ seq: 2, field: "stance", old: "xa cách", new: "thân thiện" }],
          },
        },
      },
      expect.any(Object),
    );
  });

  it("overlays live streaming state and scene updates from useChatStreamStore", () => {
    useChatStreamStore.setState({
      turns: {
        cw1: {
          ...initialTurnState,
          status: "streaming",
          liveState: {
            location_id: "hcm",
            time: "21:00 Thứ Sáu",
            tension: 4,
            present_ids: ["vy", "han"],
          },
          liveScene: {
            env: { weather: "gió lớn" },
            chars: {
              vy: { mood: "lo lắng" },
              han: { mood: "bình tĩnh" },
            },
            items: [],
          },
        },
      },
    });
    wrap(<LiveStateEditor chat={mocks.chat!} />);
    expect(screen.getByLabelText(t("stateEditor.structured.time"))).toHaveValue("21:00 Thứ Sáu");
    expect(screen.getByTestId("scene-char-vy")).toBeInTheDocument();
    expect(screen.getByTestId("scene-char-han")).toBeInTheDocument();
  });

  it("renders MemorySection in LiveStateEditor with summary, compressed pill, events, and liveSummary overlay", () => {
    mocks.chat = makeWorldChat({
      summary: "Tóm tắt cũ",
      summary_upto: 6,
      events: [{ id: "sk_hen_gap", title: "Hẹn gặp", content: "Vy và Nam hẹn tại quán." }],
    });
    useChatStreamStore.setState({
      turns: {
        cw1: {
          ...initialTurnState,
          status: "done",
          liveSummary: "Tóm tắt live từ Archivist",
          archivistEventsAdded: 1,
        },
      },
    });
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    expect(screen.getByText(t("stateEditor.memory.title"))).toBeInTheDocument();
    expect(
      screen.getByText(t("stateEditor.memory.compressedUpto", { seq: 6 })),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(t("stateEditor.memory.summaryLabel"))).toHaveValue(
      "Tóm tắt live từ Archivist",
    );
    expect(screen.getByTestId("memory-event-sk_hen_gap")).toBeInTheDocument();
  });

  it("edits summary and memorable events (add, edit, remove) and saves via usePatchState", async () => {
    mocks.chat = makeWorldChat({
      summary: "Tóm tắt ban đầu",
      summary_upto: 4,
      events: [
        { id: "sk_one", title: "Sự kiện một", content: "Nội dung một" },
        { id: "sk_two", title: "Sự kiện hai", content: "Nội dung hai" },
      ],
    });
    wrap(<LiveStateEditor chat={mocks.chat!} />);

    const summaryBox = screen.getByLabelText(t("stateEditor.memory.summaryLabel"));
    fireEvent.change(summaryBox, { target: { value: "Tóm tắt đã sửa" } });
    await userEvent.click(
      screen.getByRole("button", { name: t("stateEditor.memory.saveSummary") }),
    );
    expect(mocks.patchState).toHaveBeenCalledWith(
      { summary: "Tóm tắt đã sửa" },
      expect.any(Object),
    );

    // Edit first event, remove second event, add a third event.
    fireEvent.change(screen.getByLabelText(t("stateEditor.memory.eventContentItem", { n: 1 })), {
      target: { value: "Nội dung một đã sửa" },
    });
    await userEvent.click(
      screen.getByRole("button", {
        name: t("stateEditor.memory.removeEvent", { title: "Sự kiện hai" }),
      }),
    );
    await userEvent.type(
      screen.getByLabelText(t("stateEditor.memory.eventTitlePlaceholder")),
      "Mưa chiều",
    );
    await userEvent.type(
      screen.getByLabelText(t("stateEditor.memory.eventContentPlaceholder")),
      "Trời bắt đầu mưa rào.",
    );
    await userEvent.click(screen.getByRole("button", { name: t("stateEditor.memory.addEvent") }));
    await userEvent.click(screen.getByRole("button", { name: t("stateEditor.memory.saveEvents") }));

    expect(mocks.patchState).toHaveBeenLastCalledWith(
      {
        events: [
          { id: "sk_one", title: "Sự kiện một", content: "Nội dung một đã sửa" },
          { id: "sk_mua_chieu", title: "Mưa chiều", content: "Trời bắt đầu mưa rào." },
        ],
      },
      expect.any(Object),
    );
  });
});

describe("MemorySection states", () => {
  it("disables summarize while streaming/pending, shows saving label, and maps error codes", async () => {
    useChatStreamStore.setState({
      turns: { c1: { ...initialTurnState, status: "streaming" } },
    });
    const { rerender } = wrap(
      <MemorySection
        chatId="c1"
        summary=""
        summaryUpto={0}
        events={[]}
        isStreaming={true}
        onSaveSummary={vi.fn()}
        onSaveEvents={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: t("stateEditor.memory.summarizeNow") }),
    ).toBeDisabled();

    mocks.summarizePending = true;
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemorySection
          chatId="c1"
          summary=""
          summaryUpto={0}
          events={[]}
          isStreaming={false}
          onSaveSummary={vi.fn()}
          onSaveEvents={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole("button", { name: t("stateEditor.memory.summarizing") }),
    ).toBeDisabled();

    mocks.summarizePending = false;
    for (const code of [
      "nothing_to_summarize",
      "archivist_failed",
      "openrouter_key_missing",
    ] as const) {
      mocks.summarizeError = true;
      mocks.summarizeErrorObj = new ApiError(422, code, "err");
      rerender(
        <QueryClientProvider client={new QueryClient()}>
          <MemorySection
            chatId="c1"
            summary=""
            summaryUpto={0}
            events={[]}
            onSaveSummary={vi.fn()}
            onSaveEvents={vi.fn()}
          />
        </QueryClientProvider>,
      );
      expect(screen.getByRole("alert")).toHaveTextContent(t(`chat.errors.${code}`));
    }

    mocks.summarizeError = false;
    mocks.summarizeErrorObj = null;
    const maxEvents = Array.from({ length: MAX_MEMORABLE_EVENTS }, (_, i) => ({
      id: `sk_${i}`,
      title: `Sự kiện ${i}`,
      content: `Nội dung ${i}`,
    }));
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemorySection
          chatId="c1"
          summary=""
          summaryUpto={0}
          events={maxEvents}
          onSaveSummary={vi.fn()}
          onSaveEvents={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(
      screen.getByText(t("stateEditor.memory.maxEventsReached", { max: MAX_MEMORABLE_EVENTS })),
    ).toBeInTheDocument();
  });
});

describe("ChatChrome, ChatSettingsPanel (world), and RecentChats", () => {
  it("renders right sidebar tabs for world chat and group settings", async () => {
    wrap(<ChatChrome chatId="cw1" />);
    const rightSlot = usePageChromeStore.getState().right;
    expect(rightSlot).not.toBeNull();

    const { rerender } = wrap(<>{rightSlot}</>);
    expect(screen.getByRole("tab", { name: t("chatSettings.tabs.state") })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText(t("stateEditor.title"))).toBeInTheDocument();

    // Switch to Settings tab and verify group write_mode + chain_max.
    await userEvent.click(screen.getByRole("tab", { name: t("chatSettings.tabs.settings") }));
    await waitFor(() =>
      expect(screen.getByLabelText(t("chatSettings.group.writeMode"))).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText(t("chatSettings.group.writeMode")), {
      target: { value: "single_call" },
    });
    expect(mocks.updateChat).toHaveBeenCalledWith({
      settings: expect.objectContaining({
        group: { write_mode: "single_call", chain_max: 3 },
      }),
    });

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ChatSettingsPanel chatId="cw1" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText(t("chatSettings.group.chainMax")), {
      target: { value: "5" },
    });
    expect(mocks.updateChat).toHaveBeenLastCalledWith({
      settings: expect.objectContaining({
        group: { write_mode: "per_character", chain_max: 5 },
      }),
    });
  });

  it("renders world chat title and subtitle in RecentChats", () => {
    mocks.chats = [
      {
        id: "cw1",
        mode: "world",
        title: "Cuộc hẹn cuối tuần",
        world_id: "w1",
        world_name: "Sài Gòn Mưa",
        persona_id: null,
        messages_count: 7,
        created_at: "2026-11-18T00:00:00Z",
        updated_at: "2026-11-18T00:00:00Z",
      },
    ];
    wrap(<RecentChats />);
    expect(screen.getByText("Cuộc hẹn cuối tuần")).toBeInTheDocument();
    expect(screen.getByText(/Sài Gòn Mưa · 7 tin nhắn/)).toBeInTheDocument();
  });
});

describe("ChatSettingsPanel memory settings and single-chat MemorySection", () => {
  it("saves memory.context_length presets, custom token value, and memory.summarize_at", async () => {
    mocks.chat = makeWorldChat();
    wrap(<ChatSettingsPanel chatId="cw1" />);

    // World chat ChatSettingsPanel does NOT duplicate MemorySection (it lives in LiveStateEditor).
    expect(screen.queryByText(t("stateEditor.memory.title"))).toBeNull();
    expect(screen.getByText(t("chatSettings.memory.title"))).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t("chatSettings.memory.contextLength")), {
      target: { value: "32768" },
    });
    expect(mocks.updateChat).toHaveBeenCalledWith({
      settings: expect.objectContaining({
        memory: { context_length: 32768 },
      }),
    });

    fireEvent.change(screen.getByLabelText(t("chatSettings.memory.summarizeAt")), {
      target: { value: "0.7" },
    });
    expect(mocks.updateChat).toHaveBeenLastCalledWith({
      settings: expect.objectContaining({
        memory: { summarize_at: 0.7 },
      }),
    });

    // Switch to custom context length and submit a positive integer.
    fireEvent.change(screen.getByLabelText(t("chatSettings.memory.contextLength")), {
      target: { value: "custom" },
    });
    const customInput = screen.getByLabelText(t("chatSettings.memory.customContextLength"));
    await userEvent.type(customInput, "24000");
    await userEvent.click(
      screen.getByRole("button", { name: t("chatSettings.memory.applyCustomContext") }),
    );
    expect(mocks.updateChat).toHaveBeenLastCalledWith({
      settings: expect.objectContaining({
        memory: { context_length: 24000 },
      }),
    });

    // Reset back to model default (null).
    fireEvent.change(screen.getByLabelText(t("chatSettings.memory.contextLength")), {
      target: { value: "" },
    });
    expect(mocks.updateChat).toHaveBeenLastCalledWith({
      settings: expect.objectContaining({
        memory: { context_length: null },
      }),
    });
  });

  it("renders MemorySection in single-chat ChatSettingsPanel and submits summarize & state patches", async () => {
    mocks.chat = {
      id: "cs1",
      mode: "single",
      title: "Trò chuyện đơn",
      character_id: "c1",
      character_name: "Vy",
      persona_id: "p1",
      messages_count: 10,
      settings: {
        director: { enabled: true, stream_mode: "draft_then_replace" },
        memory: { context_length: 16384, summarize_at: 0.8 },
        nsfw: false,
      },
      state: {
        bonds: {},
        summary: "Vy đang ở thư viện.",
        summary_upto: 8,
        events: [{ id: "sk_doc_sach", title: "Đọc sách", content: "Vy mượn cuốn sách cũ." }],
      },
      created_at: "2026-11-18T00:00:00Z",
      updated_at: "2026-11-18T00:00:00Z",
    };
    wrap(<ChatSettingsPanel chatId="cs1" />);

    expect(screen.getByText(t("stateEditor.memory.title"))).toBeInTheDocument();
    expect(
      screen.getByText(t("stateEditor.memory.compressedUpto", { seq: 8 })),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(t("stateEditor.memory.summaryLabel"))).toHaveValue(
      "Vy đang ở thư viện.",
    );
    expect(screen.getByTestId("memory-event-sk_doc_sach")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: t("stateEditor.memory.summarizeNow") }),
    );
    expect(mocks.summarize).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText(t("stateEditor.memory.summaryLabel")), {
      target: { value: "Vy đã về nhà." },
    });
    await userEvent.click(
      screen.getByRole("button", { name: t("stateEditor.memory.saveSummary") }),
    );
    expect(mocks.patchState).toHaveBeenCalledWith({ summary: "Vy đã về nhà." }, expect.any(Object));
  });
});
