import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorldEditor } from "@/features/library/world/WorldEditor";
import { t } from "@/i18n";
import { CardJudgePanel } from "./CardJudgePanel";
import { CreateStudio } from "./CreateStudio";
import type { CardJudgeResult, CreatorPoolsOut, CreatorSessionOut } from "./types";

interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
}

function jsonResponse(status: number, body?: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(events: Array<{ event: string; data: unknown }>): Response {
  const encoder = new TextEncoder();
  const payload = events
    .map((item) => `event: ${item.event}\ndata: ${JSON.stringify(item.data)}\n\n`)
    .join("");
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function mockFetch(handler: (call: RecordedCall) => Response | Promise<Response>): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = typeof input === "string" ? input : input.toString();
      const call: RecordedCall = {
        method: init?.method ?? "GET",
        path,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      };
      calls.push(call);
      return handler(call);
    }),
  );
  return calls;
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function renderCreateStudio() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/create"]}>
        <Routes>
          <Route path="/create" element={<CreateStudio />} />
          <Route path="/characters/:id" element={<p>character detail</p>} />
          <Route path="/worlds/:id" element={<p>world detail</p>} />
          <Route path="/settings" element={<p>settings page</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SAMPLE_POOLS: CreatorPoolsOut = {
  character: {
    carousels: {
      personality_archetype: ["Ngoài lạnh trong nóng", "Điềm tĩnh thực dụng"],
      backstory_premise: ["Nhân chứng mất tích", "Gia tộc sụp đổ"],
      goals: ["Tìm sự thật", "Trả món nợ cũ"],
      speech_style: ["Ngắn gọn cộc lốc", "Từ tốn sâu cay"],
      format_trope: ["Thám tử mất ngủ", "Chủ quán đêm bí ẩn"],
    },
    slots: {
      gender: ["Nữ", "Nam"],
      age_range: ["22–25 tuổi", "26–30 tuổi"],
      occupation: ["Pha chế quán cà phê", "Thám tử tư"],
      hair: ["Tóc đen dài", "Tóc ngắn layer"],
      eyes: ["Mắt nâu sẫm", "Mắt hổ phách"],
      build: ["Mảnh khảnh", "Cân đối"],
      zodiac: ["Bọ Cạp", "Ma Kết"],
      hobby: ["Sửa đồng hồ", "Chụp ảnh phim"],
      flaw: ["Thù dai", "Nghiện việc"],
      signature_item: ["Bật lửa đồng", "Sổ tay bìa da"],
    },
  },
  world: {
    carousels: {
      world_rules: ["Đời thường hiện đại", "Dị năng ẩn ngầm"],
      genre_trope: ["Slice of life", "Trinh thám noir"],
      tone: ["Trầm lắng", "U tối"],
      starting_situation: ["Mưa rào giữ chân", "Tin nhắn nửa đêm"],
    },
    slots: {
      era: ["Hiện đại 2020", "Thập niên 1990"],
      tech_level: ["Phổ thông", "Cyberpunk"],
      magic_level: ["Không phép thuật", "Dị năng hiếm"],
      climate: ["Mưa nhiệt đới", "Sương mù"],
      opening_place: ["Quán cà phê góc phố", "Nhà ga cũ"],
      root_level: ["country", "province"],
    },
  },
};

const SAMPLE_JUDGE: CardJudgeResult = {
  passed: true,
  score: 0.85,
  threshold: 0.65,
  criteria: [
    {
      id: "completeness",
      label: "Đầy đủ trường cốt lõi",
      probability: 0.92,
      passed: true,
      hint_vi: "",
    },
    {
      id: "atomic_concise",
      label: "Ngắn gọn & độc lập từng mục",
      probability: 0.86,
      passed: true,
      hint_vi: "",
    },
    {
      id: "no_command_tone",
      label: "Không dùng giọng mệnh lệnh",
      probability: 0.9,
      passed: true,
      hint_vi: "",
    },
    {
      id: "distinct_voice",
      label: "Giọng nói & phong cách riêng",
      probability: 0.82,
      passed: true,
      hint_vi: "",
    },
    {
      id: "actionable_goals",
      label: "Mục tiêu thúc đẩy hành động",
      probability: 0.6,
      passed: false,
      hint_vi: "Nên bổ sung động lực hành động cụ thể hơn trong cảnh mở đầu.",
    },
    {
      id: "safety_valid",
      label: "Tuổi, tính hư cấu & an toàn",
      probability: 0.98,
      passed: true,
      hint_vi: "",
    },
  ],
};

function makeSession(overrides: Partial<CreatorSessionOut> = {}): CreatorSessionOut {
  return {
    id: "sess_1",
    mode: "chat",
    target_type: "character",
    seed: { target_type: "character" },
    messages: [],
    raw: null,
    result: null,
    created_at: "2026-11-18T18:00:00Z",
    updated_at: "2026-11-18T18:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SlotMachineSection inside CreateStudio", () => {
  it("randomizes unlocked reels on Kéo cần while keeping locked reels unchanged", async () => {
    mockFetch((call) => {
      if (call.path === "/api/creator/pools") return jsonResponse(200, SAMPLE_POOLS);
      return jsonResponse(404, { error: { code: "not_found", message: "missing" } });
    });

    renderCreateStudio();

    expect(await screen.findByTestId("slot-value-occupation")).toHaveTextContent(
      "Pha chế quán cà phê",
    );
    expect(screen.getByTestId("slot-value-hair")).toHaveTextContent("Tóc đen dài");
    expect(screen.getByTestId("carousel-value-personality_archetype")).toHaveTextContent(
      "Ngoài lạnh trong nóng",
    );

    const occupationLabel = t("create.seed.characterFields.occupation");
    await userEvent.click(
      screen.getByRole("button", { name: t("create.seed.lockField", { label: occupationLabel }) }),
    );
    expect(screen.getByTestId("slot-reel-occupation")).toHaveAttribute("data-locked", "true");

    await userEvent.click(screen.getByRole("button", { name: t("create.seed.pullLever") }));

    expect(screen.getByTestId("slot-value-occupation")).toHaveTextContent("Pha chế quán cà phê");
    expect(screen.getByTestId("slot-value-hair")).toHaveTextContent("Tóc ngắn layer");
    expect(screen.getByTestId("carousel-value-personality_archetype")).toHaveTextContent(
      "Điềm tĩnh thực dụng",
    );

    // Switch to World target and verify world labels render cleanly.
    await userEvent.click(screen.getByRole("button", { name: t("create.targets.world") }));
    expect(await screen.findByTestId("slot-value-root_level")).toHaveTextContent(
      `${t("library.world.levels.country")} (country)`,
    );
  });
});

describe("ChatCreatorSection & 2-step SSE generation + save", () => {
  it("streams interview reply, runs 2-step generate, allows editing raw (skip_raw), fixes age, and saves to library", async () => {
    const generatedCard = {
      format: "vietrp-card",
      spec_version: "1.0",
      name: "Hạ Vy",
      age: null as number | null,
      is_fictional: true,
      tagline: "Chủ quán cà phê khuya.",
      personality: "Điềm tĩnh và tinh tế.",
      goals: "Giữ quán qua mùa đông.",
      speech: { style: "Ngắn gọn, nhẹ giọng." },
      greetings: ['"Khách muộn à?"'],
      tags: ["slice"],
    };

    const calls = mockFetch((call) => {
      if (call.path === "/api/creator/pools") return jsonResponse(200, SAMPLE_POOLS);
      if (call.method === "POST" && call.path === "/api/creator/sessions") {
        return jsonResponse(201, makeSession({ id: "sess_chat_1", mode: "chat" }));
      }
      if (call.method === "POST" && call.path === "/api/creator/sessions/sess_chat_1/message") {
        const msgSession = makeSession({
          id: "sess_chat_1",
          mode: "chat",
          messages: [
            { role: "user", content: "Tạo nhân vật Hạ Vy" },
            { role: "assistant", content: "Chào bạn! Hạ Vy bao nhiêu tuổi?" },
          ],
        });
        return sseResponse([
          { event: "delta", data: { type: "delta", delta: "Chào bạn! " } },
          { event: "delta", data: { type: "delta", delta: "Hạ Vy bao nhiêu tuổi?" } },
          {
            event: "message",
            data: {
              type: "message",
              message: { role: "assistant", content: "Chào bạn! Hạ Vy bao nhiêu tuổi?" },
            },
          },
          { event: "done", data: { type: "done", session: msgSession } },
        ]);
      }
      if (call.method === "POST" && call.path === "/api/creator/sessions/sess_chat_1/generate") {
        const body = call.body as { skip_raw?: boolean; raw?: string };
        if (body.skip_raw) {
          const updatedCard = { ...generatedCard, tagline: "Chủ quán cà phê đêm mưa." };
          const doneSession = makeSession({
            id: "sess_chat_1",
            mode: "chat",
            raw: body.raw ?? "",
            result: { data: updatedCard, warnings: [], judge_score: SAMPLE_JUDGE },
          });
          return sseResponse([
            { event: "formatted", data: { type: "formatted", data: updatedCard } },
            {
              event: "validated",
              data: { type: "validated", data: updatedCard, warnings: [] },
            },
            { event: "judged", data: { type: "judged", judge_score: SAMPLE_JUDGE } },
            { event: "done", data: { type: "done", session: doneSession } },
          ]);
        }

        const doneSession = makeSession({
          id: "sess_chat_1",
          mode: "chat",
          raw: "[TÊN]\nHạ Vy\n[TÍNH CÁCH]\nĐiềm tĩnh.",
          result: {
            data: generatedCard,
            warnings: [{ path: "age", code: "age_missing", message: "missing age" }],
            judge_score: SAMPLE_JUDGE,
          },
        });
        return sseResponse([
          { event: "raw", data: { type: "raw", raw: "[TÊN]\nHạ Vy\n[TÍNH CÁCH]\nĐiềm tĩnh." } },
          { event: "formatted", data: { type: "formatted", data: generatedCard } },
          {
            event: "validated",
            data: {
              type: "validated",
              data: generatedCard,
              warnings: [{ path: "age", code: "age_missing", message: "missing age" }],
            },
          },
          { event: "judged", data: { type: "judged", judge_score: SAMPLE_JUDGE } },
          { event: "done", data: { type: "done", session: doneSession } },
        ]);
      }
      if (call.method === "POST" && call.path === "/api/creator/sessions/sess_chat_1/save") {
        return jsonResponse(201, {
          target_type: "character",
          item_id: "char_42",
        });
      }
      return jsonResponse(404, { error: { code: "not_found", message: "missing" } });
    });

    renderCreateStudio();

    // Switch to Chat mode
    await userEvent.click(screen.getByRole("tab", { name: t("create.modes.chat") }));

    const input = await screen.findByLabelText(t("create.chat.inputLabel"));
    await userEvent.type(input, "Tạo nhân vật Hạ Vy");
    await userEvent.click(screen.getByRole("button", { name: t("create.chat.send") }));

    expect(await screen.findByText("Chào bạn! Hạ Vy bao nhiêu tuổi?")).toBeInTheDocument();

    // Click "Chốt & Tạo"
    await userEvent.click(screen.getByRole("button", { name: t("create.chat.finalize") }));

    const rawBox = await screen.findByLabelText(t("create.pipeline.rawLabel"));
    await waitFor(() => expect(rawBox).toHaveValue("[TÊN]\nHạ Vy\n[TÍNH CÁCH]\nĐiềm tĩnh."));
    expect(await screen.findByTestId("judge-score-badge")).toHaveTextContent("85%");
    expect(screen.getByTestId("judge-status-badge")).toHaveTextContent(t("library.judge.passed"));
    expect(
      screen.getByText("Nên bổ sung động lực hành động cụ thể hơn trong cảnh mở đầu."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("creator-needs-age")).toBeInTheDocument();

    // Edit raw draft and run Step 2 (skip_raw: true)
    await userEvent.clear(rawBox);
    await userEvent.type(rawBox, "Tên: Hạ Vy\nMô tả: Chủ quán cà phê đêm mưa.");
    await userEvent.click(
      screen.getByRole("button", { name: t("create.pipeline.generateFromRaw") }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("creator-result-preview")).toHaveTextContent(
        "Chủ quán cà phê đêm mưa.",
      ),
    );
    const skipRawCall = calls.find(
      (c) =>
        c.path === "/api/creator/sessions/sess_chat_1/generate" &&
        (c.body as { skip_raw?: boolean }).skip_raw === true,
    );
    expect(skipRawCall?.body).toMatchObject({
      skip_raw: true,
      raw: "Tên: Hạ Vy\nMô tả: Chủ quán cà phê đêm mưa.",
    });

    // Fill quick age before saving and save to library
    const quickAge = screen.getByLabelText(t("create.pipeline.preview.quickAge"));
    await userEvent.type(quickAge, "24");
    await userEvent.click(screen.getByRole("button", { name: t("create.pipeline.save.button") }));

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/characters/char_42"),
    );
    const saveCall = calls.find((c) => c.path === "/api/creator/sessions/sess_chat_1/save");
    expect(saveCall?.body).toMatchObject({
      visibility: "private",
      data: { name: "Hạ Vy", age: 24 },
    });
  });

  it("maps openrouter_key_missing in chat interview and restores input", async () => {
    mockFetch((call) => {
      if (call.path === "/api/creator/pools") return jsonResponse(200, SAMPLE_POOLS);
      if (call.method === "POST" && call.path === "/api/creator/sessions") {
        return jsonResponse(201, makeSession({ id: "sess_err", mode: "chat" }));
      }
      if (call.method === "POST" && call.path === "/api/creator/sessions/sess_err/message") {
        return jsonResponse(400, {
          error: { code: "openrouter_key_missing", message: "No OpenRouter API key" },
        });
      }
      return jsonResponse(404, { error: { code: "not_found", message: "missing" } });
    });

    renderCreateStudio();
    await userEvent.click(screen.getByRole("tab", { name: t("create.modes.chat") }));

    const input = await screen.findByLabelText(t("create.chat.inputLabel"));
    await userEvent.type(input, "Ý tưởng mới");
    await userEvent.click(screen.getByRole("button", { name: t("create.chat.send") }));

    const errorBox = await screen.findByTestId("creator-chat-error");
    expect(errorBox).toHaveTextContent(t("errors.openrouter_key_missing"));
    expect(
      within(errorBox).getByRole("link", { name: t("library.judge.openSettings") }),
    ).toHaveAttribute("href", "/settings");
    expect(input).toHaveValue("Ý tưởng mới");
  });
});

describe("CardJudgePanel", () => {
  it("renders all 6 criteria, probability percentages, pass/fail icons, and hint_vi", () => {
    const lowJudge: CardJudgeResult = {
      ...SAMPLE_JUDGE,
      passed: false,
      score: 0.62,
      criteria: SAMPLE_JUDGE.criteria.map((c) =>
        c.id === "no_command_tone"
          ? {
              ...c,
              probability: 0.45,
              passed: false,
              hint_vi: "Đổi câu lệnh sang mô tả ngôi thứ ba.",
            }
          : c,
      ),
    };

    render(
      <MemoryRouter>
        <CardJudgePanel result={lowJudge} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("judge-score-badge")).toHaveTextContent("62%");
    expect(screen.getByTestId("judge-status-badge")).toHaveTextContent(
      t("library.judge.needsWork"),
    );
    for (const c of lowJudge.criteria) {
      expect(screen.getByTestId(`judge-criterion-${c.id}`)).toBeInTheDocument();
    }
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("Đổi câu lệnh sang mô tả ngôi thứ ba.")).toBeInTheDocument();
  });

  it("supports Card Judge inside WorldEditor for an existing world", async () => {
    const calls = mockFetch((call) => {
      if (call.path.startsWith("/api/lorebooks")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      if (call.method === "POST" && call.path === "/api/worlds/w1/judge") {
        return jsonResponse(200, {
          world: {
            id: "w1",
            name: "Phố Cũ",
            tagline: "",
            tags: [],
            visibility: "private",
            cover_url: null,
            needs_age: false,
            updated_at: "2026-11-18T18:00:00Z",
            created_at: "2026-11-18T18:00:00Z",
            is_owner: true,
            author: "Mèo",
            warnings: [],
            judge_score: SAMPLE_JUDGE,
            data: {
              format: "vietrp-world",
              spec_version: "1.0",
              name: "Phố Cũ",
              rules: "Đời thường",
              locations: [{ id: "pho", level: "area", name: "Phố Cũ" }],
              openings: [],
            },
          },
        });
      }
      return jsonResponse(200, {
        world: {
          id: "w1",
          name: "Phố Cũ",
          tagline: "",
          tags: [],
          visibility: "private",
          cover_url: null,
          needs_age: false,
          updated_at: "2026-11-18T18:00:00Z",
          created_at: "2026-11-18T18:00:00Z",
          is_owner: true,
          author: "Mèo",
          warnings: [],
          judge_score: null,
          data: {
            format: "vietrp-world",
            spec_version: "1.0",
            name: "Phố Cũ",
            rules: "Đời thường",
            locations: [{ id: "pho", level: "area", name: "Phố Cũ" }],
            openings: [],
          },
        },
      });
    });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/worlds/w1"]}>
          <Routes>
            <Route path="/worlds/:id" element={<WorldEditor id="w1" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("button", { name: t("library.judge.run") }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/worlds/w1/judge")).toBe(
        true,
      ),
    );
    expect(await screen.findByTestId("judge-score-badge")).toHaveTextContent("85%");
  });
});
