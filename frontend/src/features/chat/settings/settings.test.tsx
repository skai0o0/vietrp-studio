import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import { PresetEditor } from "@/features/settings/presets/PresetEditor";
import { ChatSettingsPanel } from "./ChatSettingsPanel";

const mocks = vi.hoisted(() => ({ update: vi.fn(), save: vi.fn() }));

vi.mock("@/features/chat/hooks", () => ({
  useSavePreset: () => ({ mutate: mocks.save, isPending: false }),
  useDeletePreset: () => ({ mutate: vi.fn(), isPending: false }),
  useChat: () => ({
    data: {
      settings: { director: { enabled: true, stream_mode: "draft_then_replace" }, nsfw: false },
      default_lorebook_ids: ["lb-card"],
    },
  }),
  useUpdateChat: () => ({ mutate: mocks.update, isError: false }),
  useModels: () => ({
    isError: false,
    data: [{ id: "m/one", name: "Model One", context_length: 1000 }],
  }),
}));

vi.mock("@/features/library/form/LorebookPicker", () => ({
  LorebookPicker: ({
    selected,
    onChange,
  }: {
    selected: string[];
    onChange: (ids: string[]) => void;
  }) => (
    <button type="button" onClick={() => onChange([...selected, "lb-new"])}>
      picker:{selected.join(",")}
    </button>
  ),
}));

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  mocks.update.mockReset();
  mocks.save.mockReset();
});

describe("ChatSettingsPanel", () => {
  it("shows the under-18 note next to the NSFW toggle and patches merged settings", () => {
    wrap(<ChatSettingsPanel chatId="c1" />);
    expect(screen.getByTestId("nsfw-note").textContent).toBe(t("chatSettings.nsfw.note"));
    fireEvent.click(screen.getByRole("switch", { name: t("chatSettings.nsfw.label") }));
    expect(mocks.update).toHaveBeenCalledWith({
      settings: {
        director: { enabled: true, stream_mode: "draft_then_replace" },
        nsfw: true,
      },
    });
  });

  it("sets a per-agent model and clears it back to default (null)", () => {
    wrap(<ChatSettingsPanel chatId="c1" />);
    fireEvent.change(screen.getByLabelText(t("chatSettings.agents.writer")), {
      target: { value: "m/one" },
    });
    expect(mocks.update.mock.calls[0]?.[0].settings.models).toEqual({ writer: "m/one" });
  });
});

describe("ChatSettingsPanel lorebooks", () => {
  it("starts from the card's lorebooks and saves a chat-only list", () => {
    wrap(<ChatSettingsPanel chatId="c1" />);
    expect(screen.getByText(t("chatSettings.lorebook.booksDefault"))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "picker:lb-card" }));
    expect(mocks.update.mock.calls[0]?.[0].settings.lorebook).toEqual({
      book_ids: ["lb-card", "lb-new"],
    });
  });
});

describe("PresetEditor", () => {
  it("saves layers for the agent and resets a layer to blank", () => {
    wrap(<PresetEditor agent="writer" onNotify={() => undefined} />);
    fireEvent.change(screen.getByLabelText(t("presets.name")), { target: { value: "Của tôi" } });
    fireEvent.change(screen.getByLabelText(t("presets.layers.system")), {
      target: { value: "Bạn là {{char}}" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: t("presets.reset") })[1] as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: t("presets.save") }));
    expect(mocks.save.mock.calls[0]?.[0]).toEqual({
      id: undefined,
      body: { agent: "writer", name: "Của tôi", layers: { system: "Bạn là {{char}}", nsfw: "" } },
    });
  });
});
