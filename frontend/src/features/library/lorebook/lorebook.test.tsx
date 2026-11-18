import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import { json, lorebookOut, mockApi, renderAt } from "../testHelpers";
import { LorebookEditor } from "./LorebookEditor";

vi.mock("@/features/io", () => ({
  ImportButton: () => <button type="button">import-button</button>,
  ExportMenu: () => <button type="button">export-menu</button>,
}));

afterEach(() => vi.unstubAllGlobals());

describe("lorebook editor", () => {
  it("edits an entry inline and saves the whole book", async () => {
    const calls = mockApi((call) => {
      if (call.method === "PUT") return json(200, { lorebook: lorebookOut() });
      return json(200, { lorebook: lorebookOut() });
    });
    renderAt(<LorebookEditor id="l1" />, "/library/lorebooks/:id", "/library/lorebooks/l1");

    await userEvent.click(
      await screen.findByRole("button", {
        name: t("library.lorebook.expand", { name: "Cổng trường" }),
      }),
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: t("library.lorebook.keys") }),
      "sân{Enter}",
    );
    await userEvent.type(screen.getByLabelText(t("library.lorebook.content")), " Có bảo vệ.");
    await userEvent.click(screen.getByLabelText(t("library.lorebook.constant")));
    await userEvent.selectOptions(screen.getByLabelText(t("library.lorebook.selectMode")), "both");
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const body = calls.find((c) => c.method === "PUT")?.body as {
      data: { entries: Record<string, unknown>[] };
    };
    expect(body.data.entries[0]).toMatchObject({
      keys: ["cổng", "sân"],
      content: "Cổng chính màu xanh. Có bảo vệ.",
      constant: true,
      select_mode: "both",
    });
  });

  it("shows secondary keys only for selective entries and can disable an entry", async () => {
    mockApi(() => json(200, { lorebook: lorebookOut() }));
    renderAt(<LorebookEditor id="l1" />, "/library/lorebooks/:id", "/library/lorebooks/l1");
    await userEvent.click(
      await screen.findByRole("button", {
        name: t("library.lorebook.expand", { name: "Cổng trường" }),
      }),
    );

    expect(screen.queryByRole("textbox", { name: t("library.lorebook.secondaryKeys") })).toBeNull();
    await userEvent.click(screen.getByLabelText(t("library.lorebook.selective")));
    expect(
      screen.getByRole("textbox", { name: t("library.lorebook.secondaryKeys") }),
    ).toBeInTheDocument();

    const enabled = screen.getByRole("switch", {
      name: t("library.lorebook.enabledAria", { name: "Cổng trường" }),
    });
    expect(enabled).toBeChecked();
    await userEvent.click(enabled);
    expect(enabled).not.toBeChecked();
  });

  it("adds, reorders and removes entries", async () => {
    mockApi(() => json(200, { lorebook: lorebookOut() }));
    renderAt(<LorebookEditor id="l1" />, "/library/lorebooks/:id", "/library/lorebooks/l1");
    await screen.findByRole("button", {
      name: t("library.lorebook.expand", { name: "Cổng trường" }),
    });

    await userEvent.click(screen.getByRole("button", { name: t("library.lorebook.addEntry") }));
    const second = t("library.lorebook.entryItem", { n: 2 });
    expect(
      screen.getByRole("button", { name: t("library.lorebook.expand", { name: second }) }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: t("library.list.moveUp", { name: second }) }),
    );
    expect(
      screen.getByRole("button", { name: t("library.list.moveUp", { name: "Cổng trường" }) }),
    ).toBeEnabled();

    await userEvent.click(
      screen.getByRole("button", { name: t("library.list.remove", { name: "Cổng trường" }) }),
    );
    expect(
      screen.queryByRole("button", { name: t("library.lorebook.expand", { name: "Cổng trường" }) }),
    ).toBeNull();
  });

  it("is read-only for a public book of another owner", async () => {
    mockApi(() => json(200, { lorebook: lorebookOut({ is_owner: false, visibility: "public" }) }));
    renderAt(<LorebookEditor id="l1" />, "/library/lorebooks/:id", "/library/lorebooks/l1");

    expect(await screen.findByLabelText(t("library.lorebook.name"))).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: t("library.lorebook.addEntry") })).toBeNull();
    expect(
      screen.getByRole("button", { name: t("library.actions.addToLibrary") }),
    ).toBeInTheDocument();
  });
});
