import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import type { CastMemberSummary, ChatSummary, MessageOut } from "@/types/chat";
import { RecentChats } from "../newChat/RecentChats";
import { initialTurnState, type TurnState } from "../store";
import { ChatHeader } from "./ChatHeader";
import { ChatInput } from "./ChatInput";
import { ChatView } from "./ChatView";
import { MessageBubble } from "./MessageBubble";
import { MessageList } from "./MessageList";
import { NoticeList } from "./NoticeList";
import { StreamingBubble } from "./StreamingBubble";
import {
  CMD_HISTORY_KEY,
  SLASH_COMMANDS,
  commandQuery,
  filterCommands,
  loadCommandHistory,
  saveCommandHistory,
} from "./commands";
import { groupMessages } from "./grouping";
import { splitRp } from "./RpText";
import { TokenBar } from "./TokenBar";
import { tokenBarState } from "./tokenMath";

const singleChat = {
  id: "c1",
  mode: "single",
  character_name: "Linh",
  avatar_url: null,
  settings: { director: { stream_mode: "draft_then_replace" } },
};

const variant = (content: string, idx = 0) => ({ idx, content, created_at: "t" });
function msg(id: string, speaker: string, content: string, seq = 1): MessageOut {
  return {
    id,
    seq,
    speaker,
    meta: {},
    active_variant: 0,
    created_at: "t",
    variants: [variant(content)],
  } as MessageOut;
}

const defaultMessages = [
  msg("1", "user", "Chào"),
  msg("2", "linh", '*mỉm cười* "Chào bạn"'),
  msg("3", "linh", "Ừ"),
];

const mocks = vi.hoisted(() => ({
  turn: undefined as unknown,
  send: vi.fn(),
  continueTurn: vi.fn(),
  regenerate: vi.fn(),
  stop: vi.fn(),
  chat: undefined as unknown,
  messages: undefined as unknown,
  chats: [] as ChatSummary[],
  setActiveVariant: vi.fn(),
  editMessage: vi.fn(),
  deleteMessage: vi.fn(),
  undoChat: vi.fn(),
  forkChat: vi.fn(),
  previewCalls: [] as Array<{ chatId: string; text: string; speaker?: string }>,
}));

vi.mock("../useTurnStream", () => ({
  useTurnStream: () => ({
    turn: mocks.turn,
    isStreaming: (mocks.turn as { status: string }).status === "streaming",
    send: mocks.send,
    continueTurn: mocks.continueTurn,
    regenerate: mocks.regenerate,
    stop: mocks.stop,
    reset: vi.fn(),
  }),
}));

vi.mock("../hooks", () => ({
  useChat: () => ({ data: mocks.chat, isError: false }),
  useChats: () => ({ data: mocks.chats, isSuccess: true, isError: false }),
  useChatMessages: () => ({
    data: mocks.messages,
    isError: false,
  }),
  useSetActiveVariant: () => ({ mutateAsync: mocks.setActiveVariant, isPending: false }),
  useEditMessage: () => ({ mutateAsync: mocks.editMessage, isPending: false }),
  useDeleteMessage: () => ({ mutateAsync: mocks.deleteMessage, isPending: false }),
  useUndoChat: () => ({ mutateAsync: mocks.undoChat, isPending: false }),
  useForkChat: () => ({ mutateAsync: mocks.forkChat, isPending: false }),
}));
vi.mock("./usePromptPreview", () => ({
  usePromptPreview: (chatId: string, text: string, speaker?: string) => {
    mocks.previewCalls.push({ chatId, text, speaker });
    return {
      data: {
        budget: 1000,
        total_tokens: 700,
        layers: [
          { name: "system", text: "hello", tokens: 10 },
          { name: "minor_rule", text: "no minors", tokens: 5 },
        ],
      },
      isLoading: false,
      isError: false,
    };
  },
}));

function wrap(node: ReactNode, initialEntry = "/chat/c1") {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[initialEntry]}>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

function turn(partial: Partial<TurnState>): TurnState {
  return { ...initialTurnState, ...partial };
}

beforeEach(() => {
  window.localStorage.clear();
  mocks.turn = initialTurnState;
  mocks.chat = singleChat;
  mocks.messages = defaultMessages;
  mocks.chats = [];
  mocks.previewCalls = [];
  mocks.send.mockReset();
  mocks.continueTurn.mockReset();
  mocks.regenerate.mockReset();
  mocks.stop.mockReset();
  mocks.setActiveVariant.mockReset();
  mocks.editMessage.mockReset();
  mocks.deleteMessage.mockReset();
  mocks.undoChat.mockReset();
  mocks.forkChat.mockReset();
});

describe("tokenBarState", () => {
  it("steps at 60 / 80 / 100 percent and clamps the fill", () => {
    expect(tokenBarState(59, 100).level).toBe("ok");
    expect(tokenBarState(60, 100).level).toBe("notice");
    expect(tokenBarState(80, 100).level).toBe("warn");
    expect(tokenBarState(100, 100).level).toBe("full");
    expect(tokenBarState(150, 100)).toMatchObject({ ratio: 1, percent: 150, level: "full" });
  });
  it("is safe with a missing budget", () => {
    expect(tokenBarState(10, 0)).toEqual({ ratio: 0, percent: 0, level: "ok" });
  });
});

describe("commands", () => {
  it("opens only for a lone /word and filters by prefix with all P5 commands enabled", () => {
    expect(commandQuery("/fo")).toBe("fo");
    expect(commandQuery("/force x")).toBeNull();
    expect(commandQuery("hi")).toBeNull();
    expect(SLASH_COMMANDS.every((c) => c.supported)).toBe(true);
    expect(filterCommands("").map((c) => c.name)).toEqual([
      "cmd",
      "force",
      "time",
      "move",
      "addnpc",
      "removenpc",
      "listnpc",
      "clearnpc",
    ]);
    expect(filterCommands("c").map((c) => c.name)).toEqual(["cmd", "clearnpc"]);
  });

  it("persists up to 20 slash commands under vietrp_cmd_history safely", () => {
    for (let i = 1; i <= 25; i += 1) {
      saveCommandHistory(`/time ${i}:00`);
    }
    const stored = loadCommandHistory();
    expect(stored).toHaveLength(20);
    expect(stored[0]).toBe("/time 25:00");
    window.localStorage.setItem(CMD_HISTORY_KEY, "{broken json");
    expect(loadCommandHistory()).toEqual([]);
  });
});

describe("grouping and RP text", () => {
  it("groups consecutive messages of one speaker", () => {
    const groups = groupMessages([msg("1", "a", ""), msg("2", "b", ""), msg("3", "b", "")]);
    expect(groups.map((g) => g.messages.length)).toEqual([1, 2]);
  });
  it("splits actions and dialogue", () => {
    expect(splitRp('*cười* "Chào" xong').map((p) => p.kind)).toEqual([
      "action",
      "text",
      "dialogue",
      "text",
    ]);
  });
});

describe("ChatInput", () => {
  const props = {
    isStreaming: false,
    usedTokens: 10,
    budget: 100,
    onStop: vi.fn(),
    onOpenInspector: vi.fn(),
    onTextChange: vi.fn(),
  };

  it("shows all P5 commands enabled in the popup on /", async () => {
    render(<ChatInput {...props} onSend={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "/");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    for (const cmd of [
      "/cmd",
      "/force",
      "/time",
      "/move",
      "/addnpc",
      "/removenpc",
      "/listnpc",
      "/clearnpc",
    ]) {
      expect(screen.getByRole("button", { name: new RegExp(cmd) })).toBeEnabled();
    }
    await userEvent.click(screen.getByRole("button", { name: /\/force/ }));
    expect(screen.getByRole("textbox", { name: "Tin nhắn" })).toHaveValue("/force ");
  });

  it("persists slash commands in localStorage for popup history and Up/Down recall across reloads", async () => {
    const first = render(<ChatInput {...props} onSend={vi.fn().mockResolvedValue(true)} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "/time 21:00{Enter}");
    expect(JSON.parse(window.localStorage.getItem(CMD_HISTORY_KEY) ?? "[]")).toEqual([
      "/time 21:00",
    ]);
    first.unmount();

    render(<ChatInput {...props} onSend={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "Tin nhắn" });
    await userEvent.type(input, "/");
    expect(screen.getByRole("button", { name: "/time 21:00" })).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input).toHaveValue("/time 21:00");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input).toHaveValue("");
  });

  it("shows Continue when empty and Undo when canUndo, disabling both while pending", async () => {
    const onContinue = vi.fn();
    const onUndo = vi.fn();
    const { rerender } = render(
      <ChatInput
        {...props}
        onSend={vi.fn()}
        onContinue={onContinue}
        onUndo={onUndo}
        canContinue
        canUndo
      />,
    );

    const continueBtn = screen.getByRole("button", { name: t("chat.input.continue") });
    const undoBtn = screen.getByRole("button", { name: t("chat.input.undo") });
    await userEvent.click(continueBtn);
    await userEvent.click(undoBtn);
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onUndo).toHaveBeenCalledTimes(1);

    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "Xin chào");
    expect(screen.queryByRole("button", { name: t("chat.input.continue") })).toBeNull();

    rerender(
      <ChatInput
        {...props}
        onSend={vi.fn()}
        onContinue={onContinue}
        onUndo={onUndo}
        canContinue
        canUndo
        isActionPending
      />,
    );
    expect(screen.getByRole("button", { name: t("chat.input.undo") })).toBeDisabled();
  });

  it("sends text with the prefill", async () => {
    const onSend = vi.fn();
    render(<ChatInput {...props} onSend={onSend} />);
    await userEvent.click(screen.getByRole("button", { name: /Bật prefill/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Prefill" }), "Ừm");
    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "Chào{Enter}");
    expect(onSend).toHaveBeenCalledWith("Chào", "Ừm");
  });

  it("restores text and prefill when sending fails before streaming", async () => {
    const onSend = vi.fn().mockResolvedValue(false);
    render(<ChatInput {...props} onSend={onSend} />);
    await userEvent.click(screen.getByRole("button", { name: /Bật prefill/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Prefill" }), "Ừm");
    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "Chào{Enter}");
    expect(screen.getByRole("textbox", { name: "Tin nhắn" })).toHaveValue("Chào");
    expect(screen.getByRole("textbox", { name: "Prefill" })).toHaveValue("Ừm");
  });

  it("clears the input after a successful send", async () => {
    render(<ChatInput {...props} onSend={vi.fn().mockResolvedValue(true)} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Tin nhắn" }), "Chào{Enter}");
    expect(screen.getByRole("textbox", { name: "Tin nhắn" })).toHaveValue("");
  });

  it("exposes the token step as a data attribute", () => {
    render(<TokenBar used={85} budget={100} onOpen={vi.fn()} />);
    expect(screen.getByRole("button").getAttribute("data-level")).toBe("warn");
    expect(document.querySelector(".token-bar-fill")?.getAttribute("data-level")).toBe("warn");
  });

  it("shows stop while streaming and opens the inspector from the token bar", async () => {
    const onOpenInspector = vi.fn();
    render(<ChatInput {...props} isStreaming onSend={vi.fn()} onOpenInspector={onOpenInspector} />);
    expect(screen.getByRole("button", { name: "Dừng" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Mở Prompt Inspector/ }));
    expect(onOpenInspector).toHaveBeenCalled();
  });
});

describe("StreamingBubble", () => {
  it("mutes draft text while the Director is pending", () => {
    render(
      <StreamingBubble
        holdUntilApproved={false}
        turn={turn({
          status: "streaming",
          speaker: "linh",
          buffer: "Nháp",
          isDraft: true,
          directorPending: true,
        })}
      />,
    );
    expect(screen.getByText("Nháp").closest("[data-draft]")).not.toBeNull();
  });

  it("hides text and shows progress for hold_until_approved", () => {
    render(
      <StreamingBubble
        holdUntilApproved
        turn={turn({ status: "streaming", speaker: "linh", buffer: "Nháp", directorPending: true })}
      />,
    );
    expect(screen.queryByText("Nháp")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Director đang duyệt");
  });
});

describe("ChatView", () => {
  it("renders grouped history, a live turn, a notice, and the safety layer in the inspector", async () => {
    mocks.turn = turn({
      status: "streaming",
      speaker: "linh",
      buffer: "Đang viết",
      notices: [{ code: "director_failed" } as never],
    });
    render(wrap(<ChatView chatId="c1" />));
    expect(screen.getByRole("heading", { name: "Linh" })).toBeInTheDocument();
    expect(screen.getAllByText("Linh")).toHaveLength(2);
    expect(screen.getByText("Đang viết")).toBeInTheDocument();
    expect(screen.getByText(/Director lỗi/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Mở Prompt Inspector/ }));
    expect(await screen.findByText("Quy tắc an toàn")).toBeInTheDocument();
  });

  it("lets world chats switch preview speaker inside Prompt Inspector", async () => {
    mocks.chat = {
      id: "cw1",
      mode: "world",
      world_name: "Sài Gòn Mưa",
      cast: [
        { id: "vy", character_id: "c1", name: "Vy", tagline: "", avatar_url: null },
        { id: "han", character_id: "c2", name: "Hân", tagline: "", avatar_url: null },
      ],
      settings: { director: { stream_mode: "draft_then_replace" } },
    };
    mocks.messages = [msg("1", "narrator", "Trời đổ mưa.")];
    render(wrap(<ChatView chatId="cw1" />));
    fireEvent.click(screen.getByRole("button", { name: /Mở Prompt Inspector/ }));
    const select = await screen.findByLabelText(t("worldChat.previewSpeaker"));
    fireEvent.change(select, { target: { value: "vy" } });
    expect(mocks.previewCalls.at(-1)?.speaker).toBe("vy");
  });
});

describe("Multi-speaker MessageList and StreamingBubble", () => {
  const cast: CastMemberSummary[] = [
    { id: "vy", character_id: "uuid-vy", name: "Vy", avatar_url: "/vy.png" },
    { id: "han", character_id: "uuid-han", name: "Hân", avatar_url: null },
  ];

  it("resolves cast speaker names/avatars and keeps user/narrator distinct", () => {
    render(
      <MessageList
        messages={[
          msg("1", "narrator", "Ánh đèn bật sáng."),
          msg("2", "vy", "Chào mọi người!"),
          msg("3", "uuid-han", "Ừm, chào cậu."),
          msg("4", "user", "Mọi người đến đủ rồi à?"),
        ]}
        characterName=""
        avatarUrl={null}
        cast={cast}
        worldName="Sài Gòn Mưa"
        scrollKey={4}
      />,
    );
    expect(screen.getByText("Sài Gòn Mưa")).toBeInTheDocument();
    expect(screen.getByText("Người dẫn truyện")).toBeInTheDocument();
    expect(screen.getByText("Vy")).toBeInTheDocument();
    expect(screen.getByText("Hân")).toBeInTheDocument();
    expect(screen.getByText("Bạn")).toBeInTheDocument();
    expect(document.querySelector('img[src="/vy.png"]')).not.toBeNull();
  });

  it("renders multiple streaming speakers in speakerOrder with narrator and cast names", () => {
    render(
      <StreamingBubble
        holdUntilApproved={false}
        cast={cast}
        turn={turn({
          status: "streaming",
          speaker: "vy",
          speakerOrder: ["m1", "m2"],
          speakerBuffers: {
            m1: {
              messageId: "m1",
              speaker: "narrator",
              seq: 1,
              buffer: "Cửa mở ra.",
              isDraft: false,
              director: null,
              directorPending: false,
              attempt: 0,
              reasoning: "",
              reasoningAttempt: 0,
              stopped: false,
              done: true,
            },
            m2: {
              messageId: "m2",
              speaker: "vy",
              seq: 2,
              buffer: "Cậu tới rồi!",
              isDraft: true,
              director: null,
              directorPending: true,
              attempt: 1,
              reasoning: "",
              reasoningAttempt: 0,
              stopped: false,
              done: false,
            },
          },
        })}
      />,
    );
    const bubble = screen.getByTestId("streaming-bubble");
    const items = bubble.querySelectorAll("[data-speaker]");
    expect(items[0]?.getAttribute("data-speaker")).toBe("narrator");
    expect(items[1]?.getAttribute("data-speaker")).toBe("vy");
    expect(screen.getByText("Người dẫn truyện")).toBeInTheDocument();
    expect(screen.getByText("Vy")).toBeInTheDocument();
    expect(screen.getByText(t("chat.stream.done"))).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Đang viết lại (lần 1)");
  });
});

describe("MessageBubble P5 actions", () => {
  it("swipes variants, calls onSelectVariant with target idx, and resets picked on prop update", async () => {
    const onSelectVariant = vi.fn();
    const multiMsg: MessageOut = {
      id: "m1",
      seq: 1,
      speaker: "linh",
      meta: {},
      active_variant: 0,
      created_at: "t",
      variants: [variant("Phương án 1", 0), variant("Phương án 2", 1)],
    };
    const { rerender } = render(
      <MessageBubble
        message={multiMsg}
        isFirstInGroup
        isLastInGroup
        onSelectVariant={onSelectVariant}
      />,
    );

    expect(screen.getByText("1/2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: t("chat.message.swipeNext") }));
    expect(onSelectVariant).toHaveBeenCalledWith(1);
    expect(screen.getByText("2/2")).toBeInTheDocument();
    expect(screen.getByText("Phương án 2")).toBeInTheDocument();

    // Server updates active_variant back or adds a new variant -> optimistic picked resets.
    rerender(
      <MessageBubble
        message={{
          ...multiMsg,
          active_variant: 0,
          variants: [...multiMsg.variants, variant("Phương án 3", 2)],
        }}
        isFirstInGroup
        isLastInGroup
        onSelectVariant={onSelectVariant}
      />,
    );
    expect(screen.getByText("1/3")).toBeInTheDocument();
  });

  it("supports inline edit, regenerate, delete confirmation, greeting lock, and fork", async () => {
    const onEdit = vi.fn();
    const onRegenerate = vi.fn();
    const onDelete = vi.fn();
    const onFork = vi.fn();

    const greeting = msg("m0", "linh", "Lời mở đầu", 0);
    const { rerender } = render(
      <MessageBubble
        message={greeting}
        isFirstInGroup
        isLastInGroup
        onEdit={onEdit}
        onRegenerate={onRegenerate}
        onDelete={onDelete}
        onFork={onFork}
      />,
    );
    expect(screen.getByRole("button", { name: t("chat.message.delete") })).toBeDisabled();
    expect(screen.getByRole("button", { name: t("chat.message.delete") })).toHaveAttribute(
      "title",
      t("chat.message.cannotDeleteGreeting"),
    );

    const normal = msg("m1", "linh", "Bản đầu", 2);
    rerender(
      <MessageBubble
        message={normal}
        isFirstInGroup
        isLastInGroup
        onEdit={onEdit}
        onRegenerate={onRegenerate}
        onDelete={onDelete}
        onFork={onFork}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.regenerate") }));
    expect(onRegenerate).toHaveBeenCalledWith("m1");

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.fork") }));
    expect(onFork).toHaveBeenCalledWith("m1", 2);

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.edit") }));
    const editor = screen.getByRole("textbox", { name: t("chat.message.edit") });
    await userEvent.clear(editor);
    await userEvent.type(editor, "Bản đã sửa");
    await userEvent.click(screen.getByRole("button", { name: t("chat.message.saveEdit") }));
    expect(onEdit).toHaveBeenCalledWith("m1", "Bản đã sửa");

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.delete") }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: t("chat.message.confirmDeleteButton") }),
    );
    expect(onDelete).toHaveBeenCalledWith("m1");
  });
});

describe("NoticeList details", () => {
  it("renders notice details for npc_listed, location_moved, move_target_unknown, and writer_repeated", () => {
    render(
      <NoticeList
        errorCode={null}
        notices={[
          { type: "notice", code: "npc_listed", detail: "Lan (20) - bán trà; Minh" },
          { type: "notice", code: "location_moved", detail: "Quán trà" },
          { type: "notice", code: "move_target_unknown", detail: "Cung trăng" },
          { type: "notice", code: "writer_repeated" },
        ]}
      />,
    );
    expect(screen.getByText(/Lan \(20\) - bán trà; Minh/)).toBeInTheDocument();
    expect(screen.getByText(/Quán trà/)).toBeInTheDocument();
    expect(screen.getByText(/Cung trăng/)).toBeInTheDocument();
    expect(screen.getByText(t("chat.notices.writer_repeated"))).toBeInTheDocument();
  });
});

describe("ChatView fork navigation and RecentChats tree", () => {
  function ForkDest() {
    const { chatId } = useParams<{ chatId: string }>();
    return <div data-testid="forked-dest">{chatId}</div>;
  }

  it("forks from a message in ChatView and navigates to /chat/{forked.id}", async () => {
    mocks.forkChat.mockResolvedValue({ ...singleChat, id: "c_fork", parent_chat_id: "c1" });
    render(
      wrap(
        <Routes>
          <Route path="/chat/c1" element={<ChatView chatId="c1" />} />
          <Route path="/chat/:chatId" element={<ForkDest />} />
        </Routes>,
        "/chat/c1",
      ),
    );
    const forkButtons = screen.getAllByRole("button", { name: t("chat.message.fork") });
    await userEvent.click(forkButtons[0]!);
    await waitFor(() => expect(screen.getByTestId("forked-dest")).toHaveTextContent("c_fork"));
    expect(mocks.forkChat).toHaveBeenCalledWith({ message_id: "1", upto_seq: 1 });
  });

  it("wires ChatView Continue, Undo, Regenerate, Swipe, Edit, and Delete plus parent fork banner", async () => {
    mocks.chat = { ...singleChat, parent_chat_id: "c_parent", forked_at_seq: 4 };
    mocks.messages = [
      {
        id: "m1",
        seq: 1,
        speaker: "linh",
        meta: {},
        active_variant: 0,
        created_at: "t",
        variants: [variant("A", 0), variant("B", 1)],
      } as MessageOut,
    ];
    mocks.setActiveVariant.mockResolvedValue({});
    mocks.editMessage.mockResolvedValue({});
    mocks.deleteMessage.mockResolvedValue({ removed_count: 1, chat: mocks.chat });
    mocks.undoChat.mockResolvedValue({ removed_count: 1, chat: mocks.chat });

    render(wrap(<ChatView chatId="c1" />));

    expect(screen.getByRole("link", { name: t("chat.message.forkParentLink") })).toHaveAttribute(
      "href",
      "/chat/c_parent",
    );
    expect(screen.getByText(t("chat.message.forkedAt", { seq: 4 }))).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: t("chat.input.continue") }));
    expect(mocks.continueTurn).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: t("chat.input.undo") }));
    expect(mocks.undoChat).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.regenerate") }));
    expect(mocks.regenerate).toHaveBeenCalledWith("m1");

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.swipeNext") }));
    expect(mocks.setActiveVariant).toHaveBeenCalledWith({ messageId: "m1", variantIdx: 1 });

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.edit") }));
    const editBox = screen.getByRole("textbox", { name: t("chat.message.edit") });
    await userEvent.clear(editBox);
    await userEvent.type(editBox, "Bản mới");
    await userEvent.click(screen.getByRole("button", { name: t("chat.message.saveEdit") }));
    expect(mocks.editMessage).toHaveBeenCalledWith({ messageId: "m1", content: "Bản mới" });

    await userEvent.click(screen.getByRole("button", { name: t("chat.message.delete") }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: t("chat.message.confirmDeleteButton") }),
    );
    expect(mocks.deleteMessage).toHaveBeenCalledWith("m1");
  });

  it("filters RecentChats by search, groups by card/world, and renders fork tree + badges", async () => {
    mocks.chats = [
      {
        id: "c_root",
        mode: "single",
        title: "Chuyến đi Đà Lạt",
        character_id: "char_linh",
        character_name: "Linh",
        persona_id: null,
        messages_count: 10,
        created_at: "t",
        updated_at: "t",
      },
      {
        id: "c_branch",
        mode: "single",
        title: "Rẽ hướng quán cà phê",
        character_id: "char_linh",
        character_name: "Linh",
        persona_id: null,
        parent_chat_id: "c_root",
        forked_at_seq: 6,
        messages_count: 8,
        created_at: "t",
        updated_at: "t",
      },
      {
        id: "c_world",
        mode: "world",
        title: "Đêm Hà Nội",
        world_id: "w1",
        world_name: "Hà Nội Cổ",
        persona_id: null,
        parent_chat_id: "c_missing_parent",
        forked_at_seq: 3,
        messages_count: 5,
        created_at: "t",
        updated_at: "t",
      },
    ];
    render(wrap(<RecentChats />));

    expect(screen.getByText(t("newChat.forkBadge", { seq: 6 }))).toBeInTheDocument();
    expect(screen.getByText(t("newChat.forkBadge", { seq: 3 }))).toBeInTheDocument();
    // Nested child sits inside an indented child list under its parent item.
    const branchLink = screen.getByRole("link", { name: /Rẽ hướng quán cà phê/ });
    expect(branchLink.closest("li")?.parentElement?.closest("li")).toContainElement(
      screen.getByRole("link", { name: /Chuyến đi Đà Lạt/ }),
    );

    await userEvent.click(screen.getByRole("button", { name: t("newChat.groupChats") }));
    expect(screen.getByRole("button", { name: t("newChat.groupChats") })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    const searchInput = screen.getByRole("searchbox", { name: t("newChat.searchChats") });
    await userEvent.type(searchInput, "Hà Nội");
    expect(screen.getByText("Đêm Hà Nội")).toBeInTheDocument();
    expect(screen.queryByText("Chuyến đi Đà Lạt")).toBeNull();
  });

  it("filters world-only slash commands in single chat mode", async () => {
    render(
      <ChatInput
        mode="single"
        isStreaming={false}
        usedTokens={100}
        budget={1000}
        onSend={vi.fn()}
        onStop={vi.fn()}
        onOpenInspector={vi.fn()}
        onTextChange={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByRole("textbox", { name: t("chat.input.label") }), "/");
    const list = screen.getByRole("listbox", { name: t("chat.input.commandsLabel") });
    expect(within(list).getByText("/cmd")).toBeInTheDocument();
    expect(within(list).getByText("/addnpc")).toBeInTheDocument();
    expect(within(list).queryByText("/move")).toBeNull();
    expect(within(list).queryByText("/time")).toBeNull();
    expect(within(list).queryByText("/force")).toBeNull();
  });

  it("renders pre-speaker skeleton while streaming before first speaker starts", () => {
    render(
      <StreamingBubble
        holdUntilApproved={false}
        turn={turn({ status: "streaming" })}
      />,
    );
    const bubble = screen.getByTestId("streaming-bubble");
    expect(bubble).toHaveAttribute("data-preparing", "true");
    expect(screen.getByRole("status")).toHaveTextContent(t("chat.stream.preparing"));
  });

  it("re-opens dismissed NoticeList error when errorNonce increments", async () => {
    const { rerender } = render(
      <NoticeList notices={[]} errorCode="llm_failed" errorNonce={1} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(t("chat.errors.llm_failed"));
    await userEvent.click(screen.getByRole("button", { name: t("chat.stream.dismiss") }));
    expect(screen.queryByRole("alert")).toBeNull();

    rerender(<NoticeList notices={[]} errorCode="llm_failed" errorNonce={2} />);
    expect(screen.getByRole("alert")).toHaveTextContent(t("chat.errors.llm_failed"));
  });

  it("renders ChatHeader with title, persona pill, world scene summary, and inspector trigger", async () => {
    const onOpenInspector = vi.fn();
    render(
      wrap(
        <ChatHeader
          chat={{
            id: "cw1",
            mode: "world",
            title: "Phố Mưa",
            world_name: "Hà Nội",
            persona_id: "p1",
            cast: [],
            messages_count: 2,
            settings: {},
            state: { location_id: "quan_ca_phe", time: "20:00", tension: 2 },
            created_at: "t",
            updated_at: "t",
          }}
          personaName="Minh"
          onOpenInspector={onOpenInspector}
        />,
      ),
    );
    expect(screen.getByRole("heading", { name: "Phố Mưa" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t("chat.header.personaLabel", { name: "Minh" }) })).toBeInTheDocument();
    expect(screen.getByText(/quan_ca_phe · 20:00/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: t("chat.header.moreActions") }));
    await userEvent.click(await screen.findByRole("menuitem", { name: t("chat.header.openInspector") }));
    expect(onOpenInspector).toHaveBeenCalledTimes(1);
  });
});
