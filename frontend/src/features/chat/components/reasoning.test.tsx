import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import type { TurnStreamEvent } from "@/types/chat";
import { initialTurnState, reduceTurn } from "../store";
import { ReasoningBlock } from "./ReasoningBlock";

function run(events: TurnStreamEvent[]) {
  return events.reduce(reduceTurn, { ...initialTurnState, status: "streaming" as const });
}

const start: TurnStreamEvent = { type: "speaker_start", message_id: "m1", speaker: "mai", seq: 2 };

describe("reasoning events", () => {
  it("appends deltas to the active speaker and keeps them out of the reply", () => {
    const s = run([
      start,
      { type: "reasoning", delta: "Mai đang ", attempt: 0 },
      { type: "reasoning", delta: "bận.", attempt: 0 },
      { type: "draft", delta: "Mai gật đầu." },
    ]);
    expect(s.speakerBuffers.m1?.reasoning).toBe("Mai đang bận.");
    expect(s.speakerBuffers.m1?.buffer).toBe("Mai gật đầu.");
  });

  it("a Director retry replaces the previous attempt's reasoning", () => {
    const s = run([
      start,
      { type: "reasoning", delta: "cũ", attempt: 0 },
      { type: "reset_content", message_id: "m1" },
      { type: "reasoning", delta: "mới", attempt: 1 },
    ]);
    expect(s.speakerBuffers.m1?.reasoning).toBe("mới");
    expect(s.speakerBuffers.m1?.reasoningAttempt).toBe(1);
  });
});

describe("ReasoningBlock", () => {
  it("is open while thinking and shows the text", () => {
    render(<ReasoningBlock text="suy nghĩ" thinking />);
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("suy nghĩ")).toBeInTheDocument();
  });

  it("saved reasoning is collapsed and opens on click", () => {
    render(<ReasoningBlock text="đã nghĩ" saved />);
    const toggle = screen.getByRole("button", { name: t("chat.reasoning.saved") });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("đã nghĩ")).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText("đã nghĩ")).toBeInTheDocument();
  });

  it("renders nothing without text", () => {
    const { container } = render(<ReasoningBlock text="  " />);
    expect(container).toBeEmptyDOMElement();
  });
});
