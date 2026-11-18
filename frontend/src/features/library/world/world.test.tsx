import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { t } from "@/i18n";
import { json, mockApi, renderAt, worldOut } from "../testHelpers";
import { LocationTree } from "./LocationTree";
import {
  addChild,
  allowedLevels,
  canReparent,
  deleteSubtree,
  flattenTree,
  moveSibling,
  reparent,
  type Loc,
} from "./treeOps";
import { WorldEditor } from "./WorldEditor";

vi.mock("@/features/io", () => ({
  ImportButton: () => <button type="button">import-button</button>,
  ExportMenu: () => <button type="button">export-menu</button>,
}));

afterEach(() => vi.unstubAllGlobals());

const loc = (
  id: string,
  name: string,
  level: Loc["level"],
  parent_id: string | null = null,
): Loc => ({
  id,
  name,
  level,
  parent_id,
  description: "",
});

const SAMPLE: Loc[] = [
  loc("vn", "Việt Nam", "country"),
  loc("hcm", "TP.HCM", "province", "vn"),
  loc("q1", "Quận 1", "district", "hcm"),
  loc("jp", "Nhật Bản", "country"),
];

describe("tree operations", () => {
  it("adds a child one level below and refuses below the deepest level", () => {
    const added = addChild(SAMPLE, "hcm", "Mới");
    expect(added?.locations.at(-1)).toMatchObject({ parent_id: "hcm", level: "district" });
    const withPlace = [...SAMPLE, loc("p", "Phố", "place", "q1")];
    expect(addChild(withPlace, "p", "Mới")).toBeNull();
  });

  it("limits levels to deeper-than-parent and shallower-than-children", () => {
    expect(allowedLevels(SAMPLE, "hcm")).toEqual(["province"]);
    expect(allowedLevels(SAMPLE, "q1")).toEqual(["district", "area", "place"]);
    expect(allowedLevels(SAMPLE, "vn")).toEqual(["galaxy", "star_system", "planet", "country"]);
  });

  it("deletes a node together with its subtree", () => {
    const { locations, removed } = deleteSubtree(SAMPLE, "vn");
    expect([...removed].sort()).toEqual(["hcm", "q1", "vn"]);
    expect(locations.map((l) => l.id)).toEqual(["jp"]);
  });

  it("only reparents to a shallower node outside its own subtree", () => {
    expect(canReparent(SAMPLE, "hcm", "jp")).toBe(true);
    expect(canReparent(SAMPLE, "hcm", "q1")).toBe(false);
    expect(canReparent(SAMPLE, "vn", "hcm")).toBe(false);
    const moved = reparent(SAMPLE, "hcm", "jp");
    expect(flattenTree(moved).map((r) => `${r.depth}:${r.loc.id}`)).toEqual([
      "0:vn",
      "0:jp",
      "1:hcm",
      "2:q1",
    ]);
  });

  it("swaps with the neighbouring sibling", () => {
    expect(moveSibling(SAMPLE, "jp", -1).map((l) => l.id)).toEqual(["jp", "hcm", "q1", "vn"]);
    expect(moveSibling(SAMPLE, "vn", -1).map((l) => l.id)).toEqual(SAMPLE.map((l) => l.id));
  });
});

function Harness({
  initial,
  onRemoved,
}: {
  initial: Loc[];
  onRemoved?: (ids: ReadonlySet<string>) => void;
}) {
  const [locations, setLocations] = useState(initial);
  return (
    <LocationTree
      locations={locations}
      openingCountFor={() => 2}
      onChange={(next, removed) => {
        setLocations(next);
        if (removed) onRemoved?.(removed);
      }}
    />
  );
}

function rowNames(): string[] {
  const list = screen.getByRole("list", { name: t("library.world.treeLabel") });
  return within(list)
    .getAllByRole("listitem")
    .map((li) => li.textContent ?? "");
}

describe("location tree editor", () => {
  it("adds a child under the selected node", async () => {
    render(<Harness initial={SAMPLE} />);
    await userEvent.click(screen.getByRole("button", { name: /Việt Nam/ }));
    await userEvent.click(screen.getByRole("button", { name: t("library.world.addChild") }));

    expect(rowNames()).toContain(
      `${t("library.world.newLocation")}${t("library.world.levels.province")}`,
    );
    // the new node is selected and its panel is shown
    expect(screen.getByLabelText(t("library.world.locationName"))).toHaveValue(
      t("library.world.newLocation"),
    );
  });

  it("offers only valid levels for a node", async () => {
    render(<Harness initial={SAMPLE} />);
    await userEvent.click(screen.getByRole("button", { name: /Quận 1/ }));

    const levels = screen.getByLabelText(t("library.world.locationLevel"));
    expect(
      within(levels).queryByRole("option", { name: t("library.world.levels.country") }),
    ).toBeNull();
    expect(
      within(levels).queryByRole("option", { name: t("library.world.levels.province") }),
    ).toBeNull();
    expect(
      within(levels).getByRole("option", { name: t("library.world.levels.district") }),
    ).toBeInTheDocument();
    expect(
      within(levels).getByRole("option", { name: t("library.world.levels.place") }),
    ).toBeInTheDocument();
  });

  it("disables adding a child at the deepest level", async () => {
    render(<Harness initial={[loc("p", "Phố", "place")]} />);
    await userEvent.click(screen.getByRole("button", { name: /Phố/ }));
    expect(screen.getByRole("button", { name: t("library.world.addChild") })).toBeDisabled();
  });

  it("deletes a subtree only after confirmation", async () => {
    const removedIds: string[] = [];
    render(<Harness initial={SAMPLE} onRemoved={(ids) => removedIds.push(...ids)} />);
    expect(rowNames()).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: /Việt Nam/ }));
    await userEvent.click(screen.getByRole("button", { name: t("library.world.deleteLocation") }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(
      t("library.world.deleteDescription", { count: 3, openings: 2 }),
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: t("library.world.deleteConfirm") }),
    );

    await waitFor(() => expect(rowNames()).toHaveLength(1));
    expect(rowNames()[0]).toContain("Nhật Bản");
    expect(removedIds.sort()).toEqual(["hcm", "q1", "vn"]);
  });

  it("moves a node up and down among its siblings", async () => {
    render(<Harness initial={SAMPLE} />);
    await userEvent.click(screen.getByRole("button", { name: /Nhật Bản/ }));
    expect(screen.getByRole("button", { name: t("library.world.moveDown") })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: t("library.world.moveUp") }));
    expect(rowNames()[0]).toContain("Nhật Bản");
    await userEvent.click(screen.getByRole("button", { name: t("library.world.moveDown") }));
    expect(rowNames()[0]).toContain("Việt Nam");
  });

  it("changes the parent from the select without drag and drop", async () => {
    render(<Harness initial={SAMPLE} />);
    await userEvent.click(screen.getByRole("button", { name: /TP\.HCM/ }));
    await userEvent.selectOptions(screen.getByLabelText(t("library.world.locationParent")), "jp");

    const rows = rowNames();
    expect(rows.findIndex((r) => r.includes("TP.HCM"))).toBeGreaterThan(
      rows.findIndex((r) => r.includes("Nhật Bản")),
    );
  });
});

describe("world editor", () => {
  it("saves a new world with a root location and an opening", async () => {
    const calls = mockApi((call) => {
      if (call.path.startsWith("/api/lorebooks"))
        return json(200, { items: [], next_cursor: null });
      if (call.method === "POST") return json(201, { world: worldOut() });
      return json(200, { world: worldOut() });
    });
    renderAt(<WorldEditor id="new" />, "/worlds/:id", "/worlds/new");

    await userEvent.type(screen.getByLabelText(t("library.world.name")), "Sài Gòn 2077");
    await userEvent.click(screen.getByRole("button", { name: t("library.world.addRoot") }));
    await userEvent.click(screen.getByRole("button", { name: t("library.world.addOpening") }));
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const body = calls.find((c) => c.method === "POST")?.body as {
      data: { locations: Loc[]; openings: { location_id: string }[] };
    };
    expect(body.data.locations).toHaveLength(1);
    expect(body.data.locations[0]).toMatchObject({ level: "country", parent_id: null });
    expect(body.data.openings[0]?.location_id).toBe(body.data.locations[0]?.id);
  });
});
