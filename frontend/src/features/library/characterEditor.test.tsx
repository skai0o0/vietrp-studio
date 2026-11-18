import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import { CharacterEditor } from "./character/CharacterEditor";
import { parseValidationMessage } from "./lib/errors";
import { characterOut, json, mockApi, renderAt, type Call } from "./testHelpers";

vi.mock("@/features/io", () => ({
  ImportButton: () => <button type="button">import-button</button>,
  ExportMenu: () => <button type="button">export-menu</button>,
}));

afterEach(() => vi.unstubAllGlobals());

const noLorebooks = json(200, { items: [], next_cursor: null });

function isLorebooks(call: Call): boolean {
  return call.path.startsWith("/api/lorebooks");
}

function renderNew() {
  return renderAt(<CharacterEditor id="new" />, "/characters/:id", "/characters/new");
}

describe("character editor: create and save", () => {
  it("creates a card and moves to its detail route", async () => {
    const calls = mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST" && call.path === "/api/characters") {
        return json(201, { character: characterOut() });
      }
      if (call.path === "/api/characters/c1") return json(200, { character: characterOut() });
      return undefined;
    });
    renderNew();

    await userEvent.type(screen.getByLabelText(t("library.character.name")), "Mai");
    await userEvent.type(screen.getByLabelText(t("library.character.age")), "17");
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/characters/c1"));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({
      visibility: "private",
      data: { format: "vietrp-card", name: "Mai", age: 17, is_fictional: true },
    });
  });

  it("reorders and edits list items before saving", async () => {
    const calls = mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST") return json(201, { character: characterOut() });
      return json(200, { character: characterOut() });
    });
    renderNew();

    await userEvent.type(screen.getByLabelText(t("library.character.name")), "Mai");
    await userEvent.type(screen.getByLabelText(t("library.character.age")), "20");
    const add = screen.getByRole("button", { name: t("library.character.addGreeting") });
    await userEvent.click(add);
    await userEvent.click(add);
    await userEvent.type(screen.getByLabelText(t("library.character.greetingItem", { n: 1 })), "A");
    await userEvent.type(screen.getByLabelText(t("library.character.greetingItem", { n: 2 })), "B");
    await userEvent.click(
      screen.getByRole("button", {
        name: t("library.list.moveUp", { name: t("library.character.greetingItem", { n: 2 }) }),
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const body = calls.find((c) => c.method === "POST")?.body as { data: { greetings: string[] } };
    expect(body.data.greetings).toEqual(["B", "A"]);
  });
});

describe("character editor: server errors", () => {
  it("maps validation_error details to the matching fields", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST") {
        return json(422, {
          error: {
            code: "validation_error",
            message:
              "data is invalid: name: String should have at least 1 character; tagline: String should have at most 140 characters",
          },
        });
      }
      return undefined;
    });
    renderNew();
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    const name = screen.getByLabelText(t("library.character.name"));
    await waitFor(() => expect(name).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText(t("library.fieldErrors.minLength", { count: 1 }))).toBeInTheDocument();
    expect(
      screen.getByText(t("library.fieldErrors.maxLength", { count: 140 })),
    ).toBeInTheDocument();
    expect(screen.getByTestId("save-error")).toBeInTheDocument();
  });

  it("maps the missing-age message to the age field", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST") {
        return json(422, {
          error: { code: "validation_error", message: "data is invalid: age is required" },
        });
      }
      return undefined;
    });
    renderNew();
    await userEvent.type(screen.getByLabelText(t("library.character.name")), "Mai");
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    await waitFor(() =>
      expect(screen.getByLabelText(t("library.character.age"))).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
  });

  it("shows nsfw_minor_public beside the visibility toggle", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST") {
        return json(422, { error: { code: "nsfw_minor_public", message: "blocked" } });
      }
      return undefined;
    });
    renderNew();
    await userEvent.click(screen.getByRole("button", { name: t("library.actions.save") }));

    expect(await screen.findByTestId("visibility-error")).toHaveTextContent(
      t("errors.nsfw_minor_public"),
    );
  });

  it("parses slug and range messages", () => {
    const parsed = parseValidationMessage(
      "Request validation failed: body.data.secrets.0.id: String should match pattern '^[a-z0-9_]{1,40}$'; body.data.age: Input should be greater than or equal to 0",
    );
    expect(parsed.fields["secrets.0.id"]).toBe(t("library.fieldErrors.slug"));
    expect(parsed.fields["age"]).toBe(t("library.fieldErrors.min", { value: 0 }));
  });
});

describe("character editor: existing cards", () => {
  it("shows soft warnings next to their fields", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      return json(200, {
        character: characterOut({
          warnings: [{ path: "appearance", code: "field_long", message: "long" }],
        }),
      });
    });
    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");

    const warnings = await screen.findAllByTestId("field-warning");
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toHaveTextContent(t("library.warnings.fieldLong"));
    const field = screen.getByLabelText(t("library.character.appearance")).parentElement;
    expect(field && within(field).getByTestId("field-warning")).toBeTruthy();
  });

  it("flags a card without age", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      return json(200, {
        character: characterOut({
          needs_age: true,
          data: {
            format: "vietrp-card",
            spec_version: "1.0",
            name: "Mai",
            age: null,
            is_fictional: true,
          },
        }),
      });
    });
    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");
    expect(await screen.findByTestId("needs-age")).toBeInTheDocument();
  });

  it("is read-only for other owners and offers to add the card to the library", async () => {
    const calls = mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST" && call.path === "/api/characters/c1/duplicate") {
        return json(201, { character: characterOut({ id: "c9" }) });
      }
      if (call.path === "/api/characters/c9")
        return json(200, { character: characterOut({ id: "c9" }) });
      return json(200, {
        character: characterOut({ is_owner: false, visibility: "public", author: "Ai đó" }),
      });
    });
    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");

    const name = await screen.findByLabelText(t("library.character.name"));
    expect(name).toHaveAttribute("readonly");
    expect(
      screen.queryByRole("button", { name: t("library.actions.save") }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: t("library.character.addSecret") }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: t("library.actions.addToLibrary") }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/characters/c9"));
    expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/duplicate"))).toBe(true);
  });

  it("asks for confirmation before deleting", async () => {
    const calls = mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "DELETE") return json(204);
      return json(200, { character: characterOut() });
    });
    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");

    await userEvent.click(await screen.findByRole("button", { name: t("library.actions.delete") }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: t("library.actions.delete") }),
    );

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/library/characters"),
    );
  });
});

describe("character editor: Card Judge", () => {
  it("displays saved judge_score and updates it when clicking Chấm điểm Card Judge", async () => {
    const initialJudge = {
      passed: false,
      score: 0.68,
      threshold: 0.65,
      criteria: [
        {
          id: "completeness",
          label: "Đầy đủ trường cốt lõi",
          probability: 0.8,
          passed: true,
          hint_vi: "",
        },
        {
          id: "atomic_concise",
          label: "Ngắn gọn & độc lập từng mục",
          probability: 0.55,
          passed: false,
          hint_vi: "Nên rút gọn phần backstory dưới 300 ký tự.",
        },
      ],
    };

    const updatedJudge = {
      passed: true,
      score: 0.91,
      threshold: 0.65,
      criteria: [
        {
          id: "completeness",
          label: "Đầy đủ trường cốt lõi",
          probability: 0.94,
          passed: true,
          hint_vi: "",
        },
        {
          id: "atomic_concise",
          label: "Ngắn gọn & độc lập từng mục",
          probability: 0.88,
          passed: true,
          hint_vi: "",
        },
      ],
    };

    const calls = mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST" && call.path === "/api/characters/c1/judge") {
        return json(200, { character: characterOut({ judge_score: updatedJudge }) });
      }
      return json(200, { character: characterOut({ judge_score: initialJudge }) });
    });

    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");

    expect(await screen.findByTestId("judge-score-badge")).toHaveTextContent("68%");
    expect(screen.getByText("Nên rút gọn phần backstory dưới 300 ký tự.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: t("library.judge.run") }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/characters/c1/judge")).toBe(
        true,
      ),
    );
    expect(await screen.findByTestId("judge-score-badge")).toHaveTextContent("91%");
    expect(screen.getByTestId("judge-status-badge")).toHaveTextContent(t("library.judge.passed"));
  });

  it("maps openrouter_key_missing when judging fails", async () => {
    mockApi((call) => {
      if (isLorebooks(call)) return noLorebooks;
      if (call.method === "POST" && call.path === "/api/characters/c1/judge") {
        return json(400, {
          error: { code: "openrouter_key_missing", message: "missing key" },
        });
      }
      return json(200, { character: characterOut({ judge_score: null }) });
    });

    renderAt(<CharacterEditor id="c1" />, "/characters/:id", "/characters/c1");
    await userEvent.click(await screen.findByRole("button", { name: t("library.judge.run") }));

    expect(await screen.findByTestId("judge-error")).toHaveTextContent(
      t("errors.openrouter_key_missing"),
    );
  });
});
