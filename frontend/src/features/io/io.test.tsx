import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { errorMessage, t } from "@/i18n";
import { ExportMenu, ImportButton } from ".";
import { resolveOptions } from "./exportOptions";

const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

async function pickFile(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: t("io.import.button") }));
  const input = screen.getByTestId("import-input");
  await user.upload(input, new File(["{}"], "mai.json", { type: "application/json" }));
}

describe("ImportButton", () => {
  it("imports several files one by one and reports each result", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    fetchMock
      .mockResolvedValueOnce(
        json(
          {
            kind: "lorebook",
            lorebook: { id: "l1", name: "Sách A" },
            warnings: [],
            needs_age: false,
          },
          201,
        ),
      )
      .mockResolvedValueOnce(json({ error: { code: "invalid_json", message: "x" } }, 422))
      .mockResolvedValueOnce(
        json(
          {
            kind: "lorebook",
            lorebook: { id: "l2", name: "Sách B" },
            warnings: [],
            needs_age: false,
          },
          201,
        ),
      );
    wrap(<ImportButton onImported={onImported} />);
    await user.click(screen.getByRole("button", { name: t("io.import.button") }));
    await user.upload(screen.getByTestId("import-input"), [
      new File(["{}"], "a.json", { type: "application/json" }),
      new File(["x"], "broken.json", { type: "application/json" }),
      new File(["{}"], "b.json", { type: "application/json" }),
    ]);

    expect(
      await screen.findByText(t("io.import.batch.summary", { done: 2, failed: 1 })),
    ).toBeInTheDocument();
    const rows = screen.getAllByTestId("import-batch-row");
    expect(rows).toHaveLength(3);
    expect(within(rows[0] as HTMLElement).getByText("Sách A")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByRole("alert")).toHaveTextContent(
      errorMessage("invalid_json"),
    );
    expect(within(rows[2] as HTMLElement).getByText("Sách B")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(onImported).toHaveBeenCalledTimes(2);
  });

  it("shows kind, warnings and the needs-age call-out linking to the editor", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    fetchMock.mockResolvedValue(
      json(
        {
          kind: "character",
          character: { id: "c9", name: "Mai", needs_age: true },
          warnings: [{ path: "age", code: "age_missing", message: "x" }],
          needs_age: true,
        },
        201,
      ),
    );
    wrap(<ImportButton onImported={onImported} />);
    await pickFile(user);

    expect(await screen.findByText(t("io.import.needsAgeTitle"))).toBeInTheDocument();
    const link = screen.getByRole("link", { name: t("io.import.needsAgeLink") });
    expect(link).toHaveAttribute("href", "/characters/c9");
    expect(screen.getByText(t("io.import.warningCodes.age_missing"))).toBeInTheDocument();
    expect(screen.getByText(t("io.import.kind.character"))).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/import");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("omits the call-out when the age is known", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      json(
        { kind: "world", world: { id: "w1", name: "Mưa" }, warnings: [], needs_age: false },
        201,
      ),
    );
    wrap(<ImportButton />);
    await pickFile(user);
    expect(await screen.findByRole("link", { name: t("io.import.openItem") })).toHaveAttribute(
      "href",
      "/worlds/w1",
    );
    expect(screen.queryByText(t("io.import.needsAgeTitle"))).not.toBeInTheDocument();
  });

  it("opens an imported lorebook at its detail route", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      json({ kind: "lorebook", lorebook: { id: "l1", name: "Sổ" }, warnings: [] }, 201),
    );
    wrap(<ImportButton />);
    await pickFile(user);
    expect(await screen.findByRole("link", { name: t("io.import.openItem") })).toHaveAttribute(
      "href",
      "/library/lorebooks/l1",
    );
  });

  it("maps a granular error code to Vietnamese", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(json({ error: { code: "png_crc_mismatch", message: "bad" } }, 422));
    wrap(<ImportButton />);
    await pickFile(user);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(errorMessage("png_crc_mismatch"));
    expect(errorMessage("png_crc_mismatch")).not.toBe(errorMessage("unknown"));
  });
});

describe("ExportMenu", () => {
  it("lists five formats for a character", async () => {
    const user = userEvent.setup();
    wrap(<ExportMenu kind="character" id="c1" />);
    await user.click(screen.getByRole("button", { name: t("io.export.menuLabel") }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(5);
  });

  it("lists only vietrp json for a world and calls the export endpoint", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(new Response("{}"));
    URL.createObjectURL = () => "blob:x";
    URL.revokeObjectURL = () => {};
    wrap(<ExportMenu kind="world" id="w1" />);
    await user.click(screen.getByRole("button", { name: t("io.export.menuLabel") }));
    const items = await screen.findAllByRole("menuitem");
    expect(items).toHaveLength(1);
    await user.click(items[0] as HTMLElement);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/worlds/w1/export?format=vietrp&as=json",
        expect.anything(),
      ),
    );
  });

  it("resolves lorebook options and honours a formats subset", () => {
    expect(resolveOptions("lorebook").map((o) => o.format)).toEqual(["vietrp", "st"]);
    expect(resolveOptions("character", ["ccv3-png", "lorebook-st"]).map((o) => o.id)).toEqual([
      "ccv3-png",
    ]);
  });
});
