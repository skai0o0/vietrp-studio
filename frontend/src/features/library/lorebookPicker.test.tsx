import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ImportResult } from "@/types/library";
import { LorebookPicker } from "./form/LorebookPicker";
import { json, mockApi, renderAt } from "./testHelpers";

const imported = (id: string) => ({
  kind: "lorebook",
  lorebook: { id },
  warnings: [],
  needs_age: false,
});

vi.mock("@/features/io", () => ({
  ImportButton: ({ onImported }: { onImported?: (r: ImportResult) => void }) => (
    <button
      type="button"
      onClick={() => {
        // Two files from one batch, before the parent re-renders.
        onImported?.(imported("lb-new") as unknown as ImportResult);
        onImported?.(imported("lb-new2") as unknown as ImportResult);
      }}
    >
      import-button
    </button>
  ),
}));

afterEach(() => vi.unstubAllGlobals());

describe("LorebookPicker", () => {
  it("offers World Info import and links the imported lorebook", async () => {
    mockApi(() =>
      json(200, { items: [{ id: "lb-1", name: "Có sẵn", entry_count: 5 }], next_cursor: null }),
    );
    const onChange = vi.fn();
    renderAt(<LorebookPicker selected={["lb-1"]} onChange={onChange} />, "/", "/");
    fireEvent.click(await screen.findByRole("button", { name: "import-button" }));
    expect(onChange).toHaveBeenLastCalledWith(["lb-1", "lb-new", "lb-new2"]);
  });

  it("still offers import when the vault has no lorebook", async () => {
    mockApi(() => json(200, { items: [], next_cursor: null }));
    renderAt(<LorebookPicker selected={[]} onChange={vi.fn()} />, "/", "/");
    expect(await screen.findByRole("button", { name: "import-button" })).toBeInTheDocument();
  });
});
