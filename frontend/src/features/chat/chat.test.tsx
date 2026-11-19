import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { t } from "@/i18n";
import type {
  ChatOut,
  MessageOut,
  SceneState,
  StatePatch,
  TurnStreamEvent,
  UndoResult,
  WorldState,
} from "@/types/chat";
import { chatApi } from "./api";
import {
  chatKeys,
  useChat,
  useDeleteMessage,
  useEditMessage,
  useForkChat,
  usePatchBonds,
  usePatchState,
  usePromptPreview,
  useSetActiveVariant,
  useSummarizeChat,
  useUndoChat,
  useUpdateChat,
} from "./hooks";
import { MemorySection } from "./state/MemorySection";
import { initialTurnState, reduceTurn, useChatStreamStore } from "./store";
import { useTurnStream } from "./useTurnStream";

const CHAT = "c1";

function sse(events: Array<Record<string, unknown>>): Response {
  const body = events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper, spy };
}

function worldChatFixture(state: Record<string, unknown> = {}): ChatOut {
  return {
    id: CHAT,
    mode: "world",
    title: "Thế giới thử nghiệm",
    persona_id: null,
    world_id: "w1",
    world_name: "Hà Nội",
    opening_id: "op1",
    cast: [],
    messages_count: 1,
    settings: {},
    state,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
  };
}

const speakerStart = { type: "speaker_start", message_id: "m1", speaker: "char", seq: 1 };
const verdict = { type: "director", passed: true, score: 0.9, criteria: [], attempt: 0 };

beforeEach(() => useChatStreamStore.setState({ turns: {} }));
afterEach(() => vi.unstubAllGlobals());

describe("reduceTurn", () => {
  it("replaces the buffer on reset_content", () => {
    let s = reduceTurn(initialTurnState, speakerStart as never);
    s = reduceTurn(s, { type: "draft", delta: "Nháp " } as never);
    s = reduceTurn(s, { type: "draft", delta: "một" } as never);
    expect(s).toMatchObject({ buffer: "Nháp một", isDraft: true, directorPending: true });
    s = reduceTurn(s, { type: "reset_content", message_id: "m1" } as never);
    expect(s.buffer).toBe("");
    s = reduceTurn(s, { type: "content", delta: "Bản cuối" } as never);
    expect(s.buffer).toBe("Bản cuối");
  });

  it("keeps notices and records error codes", () => {
    let s = reduceTurn(initialTurnState, { type: "notice", code: "director_failed" } as never);
    s = reduceTurn(s, { type: "error", code: "llm_failed" } as never);
    expect(s.notices).toHaveLength(1);
    expect(s).toMatchObject({ status: "error", errorCode: "llm_failed" });
  });

  it("tracks multi-speaker buffers, dedupes speakerOrder, and isolates reset_content", () => {
    const plan: TurnStreamEvent = {
      type: "plan",
      turn_type: "dialogue",
      speakers: [
        { id: "vy", kind: "character", sentences: 2, order: 0, reason: "addressed" },
        { id: "han", kind: "character", sentences: 1, order: 1, reason: "reacts" },
      ],
    };
    let s = reduceTurn(initialTurnState, plan);
    s = reduceTurn(s, { type: "speaker_start", message_id: "m1", speaker: "vy", seq: 1 });
    s = reduceTurn(s, { type: "speaker_start", message_id: "m1", speaker: "vy", seq: 1 });
    expect(s.speakerOrder).toEqual(["m1"]);

    s = reduceTurn(s, { type: "draft", delta: "Nháp Vy" });
    s = reduceTurn(s, { type: "rejudge", attempt: 1 });
    expect(s.speakerBuffers.m1).toMatchObject({
      buffer: "Nháp Vy",
      isDraft: true,
      directorPending: true,
      attempt: 1,
    });

    s = reduceTurn(s, { type: "reset_content", message_id: "m1" });
    s = reduceTurn(s, { type: "content", delta: "Lời Vy" });
    const passVerdict: TurnStreamEvent = {
      type: "director",
      passed: true,
      score: 0.95,
      criteria: [],
      attempt: 1,
    };
    s = reduceTurn(s, passVerdict);
    s = reduceTurn(s, { type: "speaker_end", message_id: "m1", variant_idx: 0, stopped: false });

    // Second speaker starts; a late reset_content for m1 must not clear m2's active buffer.
    s = reduceTurn(s, { type: "speaker_start", message_id: "m2", speaker: "han", seq: 2 });
    s = reduceTurn(s, { type: "content", delta: "Lời Hân" });
    s = reduceTurn(s, { type: "reset_content", message_id: "m1" });
    expect(s.buffer).toBe("Lời Hân");
    expect(s.speakerBuffers.m1?.buffer).toBe("");
    expect(s.speakerBuffers.m2?.buffer).toBe("Lời Hân");

    s = reduceTurn(s, { type: "speaker_end", message_id: "m2", variant_idx: 0, stopped: true });
    expect(s.speakerOrder).toEqual(["m1", "m2"]);
    expect(s.speakerBuffers.m1).toMatchObject({
      speaker: "vy",
      seq: 1,
      done: true,
      stopped: false,
      director: passVerdict,
    });
    expect(s.speakerBuffers.m2).toMatchObject({
      speaker: "han",
      seq: 2,
      done: true,
      stopped: true,
      buffer: "Lời Hân",
    });
  });

  it("updates liveScene, liveState, liveBonds, stateChanged and stateConfidence", () => {
    const mergedScene: SceneState = {
      env: { weather: "mưa phùn" },
      chars: { vy: { mood: "vui", holding: "ô" } },
      items: ["ghế đá"],
    };
    let s = reduceTurn(initialTurnState, {
      type: "scene",
      delta: { env: { weather: "mưa phùn" } },
      merged: mergedScene as unknown as Record<string, unknown>,
    });
    expect(s.liveScene).toEqual(mergedScene);

    // Scene event without merged keeps existing liveScene.
    s = reduceTurn(s, { type: "scene", delta: {} });
    expect(s.liveScene).toEqual(mergedScene);

    const worldState: WorldState = {
      location_id: "pho_di_bo",
      time: "19:30",
      tension: 2,
      present_ids: ["vy", "han"],
      awaiting_reply: ["han"],
      silence: { han: 1 },
      scene: {
        env: { weather: "tạnh mưa" },
        chars: { vy: { mood: "ngạc nhiên" } },
        items: [],
      },
    };
    s = reduceTurn(s, {
      type: "state",
      state: worldState,
      changed: ["location_id", "time"],
      confidence: { location_id: 0.91, time: 0.88 },
    });
    expect(s.liveState).toEqual(worldState);
    expect(s.stateChanged).toEqual(["location_id", "time"]);
    expect(s.stateConfidence).toEqual({ location_id: 0.91, time: 0.88 });
    expect(s.liveScene).toEqual(worldState.scene);

    // State event without scene preserves previous liveScene.
    s = reduceTurn(s, {
      type: "state",
      state: { location_id: "quan_tra" },
    });
    expect(s.liveScene).toEqual(worldState.scene);
    expect(s.stateChanged).toEqual([]);
    expect(s.stateConfidence).toEqual({});

    const bonds = { "vy:han": { fields: { stance: "thân thiết" } } };
    s = reduceTurn(s, { type: "bonds", bonds });
    expect(s.liveBonds).toEqual(bonds);
  });

  it("handles archivist event by updating liveSummary and archivistEventsAdded", () => {
    expect(initialTurnState.liveSummary).toBeNull();
    expect(initialTurnState.archivistEventsAdded).toBe(0);

    let s = reduceTurn(initialTurnState, {
      type: "archivist",
      summary: "- Hai người hẹn nhau ở quán cà phê.",
      events_added: 2,
    });
    expect(s.liveSummary).toBe("- Hai người hẹn nhau ở quán cà phê.");
    expect(s.archivistEventsAdded).toBe(2);

    // Null summary preserves previous liveSummary.
    s = reduceTurn(s, { type: "archivist", summary: null, events_added: 0 });
    expect(s.liveSummary).toBe("- Hai người hẹn nhau ở quán cà phê.");
    expect(s.archivistEventsAdded).toBe(0);
  });
});

describe("useTurnStream", () => {
  it("draft_then_replace: rejected draft is reset, then done refreshes messages", async () => {
    const { wrapper, spy } = setup();
    const body: Array<Record<string, unknown>> = [
      { type: "plan", turn_type: "reply", speakers: [], lore_ids: [], card_fields: [] },
      speakerStart,
      { type: "draft", delta: "bản nháp" },
      { type: "rejudge", attempt: 1 },
      { type: "reset_content", message_id: "m1" },
      { type: "content", delta: "Xin " },
      { type: "content", delta: "chào" },
      verdict,
      { type: "notice", code: "director_rejected", agent: "director" },
      { type: "speaker_end", message_id: "m1", variant_idx: 0, stopped: false },
      { type: "done", message_ids: ["m1"] },
    ];
    const fetchMock = vi.fn().mockResolvedValue(sse(body));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });

    await act(() => result.current.send({ text: "hi", prefill: "Ừ" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/turn",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: "hi", prefill: "Ừ" }),
      }),
    );
    expect(result.current.turn).toMatchObject({
      status: "done",
      buffer: "Xin chào",
      isDraft: false,
      directorPending: false,
      attempt: 1,
    });
    expect(result.current.turn.notices[0]?.code).toBe("director_rejected");
    expect(spy).toHaveBeenCalledWith({ queryKey: ["chats", "messages", CHAT] });
  });

  it("hold_until_approved: no draft text, pending is not set, content arrives after verdict", async () => {
    const { wrapper } = setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          sse([
            speakerStart,
            verdict,
            { type: "content", delta: "Đã duyệt" },
            { type: "done", message_ids: ["m1"] },
          ]),
        ),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(() => result.current.send({ text: "hi" }));
    expect(result.current.turn).toMatchObject({
      buffer: "Đã duyệt",
      isDraft: false,
      status: "done",
    });
    expect(result.current.turn.director?.passed).toBe(true);
  });

  it("error event ends the turn with its code and does not refresh as done", async () => {
    const { wrapper, spy } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(sse([speakerStart, { type: "error", code: "llm_failed" }])),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(() => result.current.send({ text: "hi" }));
    expect(result.current.turn).toMatchObject({ status: "error", errorCode: "llm_failed" });
    expect(spy).not.toHaveBeenCalled();
  });

  it("refreshes on mid-turn error when an earlier speaker already saved", async () => {
    const { wrapper, spy } = setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          sse([
            speakerStart,
            { type: "content", delta: "Vy xong rồi." },
            { type: "speaker_end", message_id: "m1", variant_idx: 0, stopped: false },
            { type: "speaker_start", message_id: "m2", speaker: "han", seq: 2 },
            { type: "error", code: "llm_failed" },
          ]),
        ),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(() => result.current.send({ text: "hi" }));
    expect(result.current.turn).toMatchObject({ status: "error", errorCode: "llm_failed" });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
  });

  it("resets single_call draft buffer on reset_content before any speaker_start", () => {
    let state = reduceTurn(
      { ...initialTurnState, status: "streaming" },
      { type: "draft", delta: "Nháp hỏng." },
    );
    expect(state.messageId).toBeNull();
    expect(state.buffer).toBe("Nháp hỏng.");
    state = reduceTurn(state, { type: "reset_content", message_id: "group" });
    expect(state.buffer).toBe("");
    expect(state.isDraft).toBe(false);
  });

  it("send resolves false when the request fails before the stream starts", async () => {
    const { wrapper } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "openrouter_key_missing", message: "x" } }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.send({ text: "hi" });
    });
    expect(ok).toBe(false);
    expect(result.current.turn.errorCode).toBe("openrouter_key_missing");
  });

  it("maps a 409 turn_running response to an error code", async () => {
    const { wrapper } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "turn_running", message: "busy" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(() => result.current.send({ text: "hi" }));
    expect(result.current.turn).toMatchObject({ status: "error", errorCode: "turn_running" });
  });

  it("stop() calls the stop route, aborts the stream and keeps partial text", async () => {
    const { wrapper } = setup();
    const encoder = new TextEncoder();
    let signal: AbortSignal | undefined;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/stop"))
        return new Response(JSON.stringify({ stopped: true }), { status: 200 });
      signal = init?.signal ?? undefined;
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          const chunk = (e: object) =>
            controller.enqueue(encoder.encode(`event: x\ndata: ${JSON.stringify(e)}\n\n`));
          chunk(speakerStart);
          chunk({ type: "content", delta: "dở dang" });
          signal?.addEventListener("abort", () =>
            controller.error(new DOMException("a", "AbortError")),
          );
        },
      });
      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });

    let pending: Promise<boolean> = Promise.resolve(true);
    act(() => {
      pending = result.current.send({ text: "hi" });
    });
    await waitFor(() => expect(result.current.turn.buffer).toBe("dở dang"));
    await act(async () => {
      await result.current.stop();
      await pending;
    });

    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/chats/c1/stop")).toBe(true);
    expect(signal?.aborted).toBe(true);
    expect(result.current.turn).toMatchObject({ status: "done", buffer: "dở dang" });
  });

  it("streams a multi-speaker world turn and keeps speakerOrder and speakerBuffers", async () => {
    const { wrapper } = setup();
    const events: Array<Record<string, unknown>> = [
      {
        type: "plan",
        turn_type: "dialogue",
        speakers: [
          { id: "vy", kind: "character", sentences: 2, order: 0, reason: "direct" },
          { id: "han", kind: "character", sentences: 2, order: 1, reason: "followup" },
        ],
      },
      { type: "speaker_start", message_id: "m_vy", speaker: "vy", seq: 1 },
      { type: "draft", delta: "Bản nháp Vy" },
      { type: "reset_content", message_id: "m_vy" },
      { type: "content", delta: "Vy mỉm cười." },
      { type: "director", passed: true, score: 0.92, criteria: [], attempt: 0 },
      {
        type: "scene",
        delta: { chars: { vy: { mood: "vui" } } },
        merged: { env: {}, chars: { vy: { mood: "vui" } }, items: [] },
      },
      { type: "speaker_end", message_id: "m_vy", variant_idx: 0, stopped: false },
      { type: "speaker_start", message_id: "m_han", speaker: "han", seq: 2 },
      { type: "draft", delta: "Hân gật đầu." },
      { type: "director", passed: true, score: 0.9, criteria: [], attempt: 0 },
      { type: "speaker_end", message_id: "m_han", variant_idx: 0, stopped: false },
      { type: "done", message_ids: ["m_vy", "m_han"] },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sse(events)));
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });

    await act(() => result.current.send({ text: "Chào hai bạn" }));

    expect(result.current.turn.status).toBe("done");
    expect(result.current.turn.plan?.speakers).toHaveLength(2);
    expect(result.current.turn.speakerOrder).toEqual(["m_vy", "m_han"]);
    expect(result.current.turn.speakerBuffers.m_vy).toMatchObject({
      speaker: "vy",
      buffer: "Vy mỉm cười.",
      isDraft: false,
      done: true,
      stopped: false,
    });
    expect(result.current.turn.speakerBuffers.m_han).toMatchObject({
      speaker: "han",
      buffer: "Hân gật đầu.",
      isDraft: false,
      done: true,
      stopped: false,
    });
    expect(result.current.turn.liveScene).toEqual({
      env: {},
      chars: { vy: { mood: "vui" } },
      items: [],
    });
  });

  it("syncs cached chat.state on state and bonds events without invalidating mid-turn", async () => {
    const { client, wrapper, spy } = setup();
    client.setQueryData(
      chatKeys.detail(CHAT),
      worldChatFixture({ location_id: "nha", time: "08:00", bonds: { old: true } }),
    );
    const nextWorldState: WorldState = {
      location_id: "cong_vien",
      time: "09:00",
      tension: 1,
      present_ids: ["vy"],
    };
    const nextBonds = { "vy:user": { fields: { addressing: "cậu - tớ" } } };

    const encoder = new TextEncoder();
    let finishStream!: () => void;
    const fetchMock = vi.fn(async () => {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          const push = (e: Record<string, unknown>) =>
            controller.enqueue(encoder.encode(`event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`));
          push({
            type: "state",
            state: nextWorldState,
            changed: ["location_id", "time"],
            confidence: { location_id: 0.94 },
          });
          push({ type: "bonds", bonds: nextBonds });
          finishStream = () => {
            push({ type: "done", message_ids: [] });
            controller.close();
          };
        },
      });
      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.send({ text: "Đi công viên" });
    });

    await waitFor(() => expect(result.current.turn.liveBonds).toEqual(nextBonds));
    expect(spy).not.toHaveBeenCalled();
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))?.state).toMatchObject({
      location_id: "cong_vien",
      time: "09:00",
      tension: 1,
      present_ids: ["vy"],
      bonds: nextBonds,
    });
    expect(result.current.turn).toMatchObject({
      liveState: nextWorldState,
      stateChanged: ["location_id", "time"],
      stateConfidence: { location_id: 0.94 },
      liveBonds: nextBonds,
    });

    await act(async () => {
      finishStream();
      await pending;
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
  });

  it("does not populate chat detail cache mid-turn when chat detail is not cached yet", async () => {
    const { client, wrapper } = setup();
    const setSpy = vi.spyOn(client, "setQueryData");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sse([
          { type: "state", state: { location_id: "pho" } },
          { type: "bonds", bonds: { "vy:user": {} } },
          { type: "done", message_ids: [] },
        ]),
      ),
    );
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(() => result.current.send({ text: "hi" }));

    expect(setSpy).not.toHaveBeenCalled();
    expect(client.getQueryData(chatKeys.detail(CHAT))).toBeUndefined();
  });

  it("syncs cached chat.state.summary on archivist event and invalidates chat detail on done", async () => {
    const { client, wrapper, spy } = setup();
    client.setQueryData(
      chatKeys.detail(CHAT),
      worldChatFixture({ summary: "Tóm tắt cũ", summary_upto: 0, events: [] }),
    );

    const encoder = new TextEncoder();
    let finishStream!: () => void;
    const fetchMock = vi.fn(async () => {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          const push = (e: Record<string, unknown>) =>
            controller.enqueue(encoder.encode(`event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`));
          push({
            type: "archivist",
            summary: "Tóm tắt mới từ Archivist",
            events_added: 2,
          });
          finishStream = () => {
            push({ type: "done", message_ids: [] });
            controller.close();
          };
        },
      });
      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.send({ text: "Tiếp tục" });
    });

    await waitFor(() => expect(result.current.turn.liveSummary).toBe("Tóm tắt mới từ Archivist"));
    expect(spy).not.toHaveBeenCalled();
    expect(result.current.turn.archivistEventsAdded).toBe(2);
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))?.state).toMatchObject({
      summary: "Tóm tắt mới từ Archivist",
    });

    await act(async () => {
      finishStream();
      await pending;
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
  });
});

describe("chat queries", () => {
  it("useChat fetches the detail route", async () => {
    const { wrapper } = setup();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: CHAT, title: "T" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useChat(CHAT), { wrapper });
    await waitFor(() => expect(result.current.data).toMatchObject({ id: CHAT }));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/chats/c1");
  });

  it("builds query strings for messages and prompt preview with optional speaker", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await chatApi.messages(CHAT, { before: 5, limit: 20 });
    await chatApi.promptPreview(CHAT, "xin chào");
    await chatApi.promptPreview(CHAT, "xin chào", "vy");
    await chatApi.promptPreview(CHAT, "xin chào", "");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/chats/c1/messages?before=5&limit=20");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/chats/c1/prompt-preview?text=xin+ch%C3%A0o");
    expect(fetchMock.mock.calls[2]?.[0]).toBe(
      "/api/chats/c1/prompt-preview?text=xin+ch%C3%A0o&speaker=vy",
    );
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/chats/c1/prompt-preview?text=xin+ch%C3%A0o");
  });

  it("usePromptPreview passes speaker and differentiates queryKey", async () => {
    const { wrapper } = setup();
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ layers: [], total_tokens: 10, budget: 100 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result, rerender } = renderHook(
      ({ speaker }: { speaker?: string }) => usePromptPreview(CHAT, "chào", true, speaker),
      { wrapper, initialProps: { speaker: undefined as string | undefined } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/chats/c1/prompt-preview?text=ch%C3%A0o");

    rerender({ speaker: "narrator" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "/api/chats/c1/prompt-preview?text=ch%C3%A0o&speaker=narrator",
    );
  });

  it("patchState + usePatchState send full StatePatch and update cached chat detail", async () => {
    const { client, wrapper } = setup();
    const patch: StatePatch = {
      location_id: "thu_vien",
      time: "14:00",
      tension: 3,
      present_ids: ["vy"],
      awaiting_reply: ["vy"],
      silence: { han: 2 },
      scene: {
        env: { quiet: "yên tĩnh" },
        chars: { vy: { mood: "tập trung", outfit: "áo sơ mi" } },
        items: ["sách cũ"],
      },
    };
    const updatedChat = worldChatFixture({ ...patch, manual: ["location_id", "time"] });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updatedChat), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => usePatchState(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(patch);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/state",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    );
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))).toEqual(updatedChat);
  });

  it("patchBonds delegates to patchState and usePatchBonds keeps updating chat detail", async () => {
    const { client, wrapper } = setup();
    const bonds = { "vy:user": { fields: { nickname: "Tiểu Vy" } } };
    const updatedChat = worldChatFixture({ bonds });
    const patchStateSpy = vi.spyOn(chatApi, "patchState");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updatedChat), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => usePatchBonds(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(bonds);
    });

    expect(patchStateSpy).toHaveBeenCalledWith(CHAT, { bonds });
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))).toEqual(updatedChat);
    patchStateSpy.mockRestore();
  });

  it("summarize + useSummarizeChat call POST /summarize and update detail + messages caches", async () => {
    const { client, wrapper, spy } = setup();
    const updatedChat = worldChatFixture({
      summary: "- Đã nén ký ức",
      summary_upto: 6,
      events: [{ id: "sk_gap_nhau", title: "Gặp nhau", content: "Vy gặp Nam ở quán." }],
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updatedChat), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useSummarizeChat(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/summarize",
      expect.objectContaining({ method: "POST" }),
    );
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))).toEqual(updatedChat);
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
  });

  it("MemorySection triggers POST /summarize and surfaces backend error codes in Vietnamese", async () => {
    const { client } = setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "nothing_to_summarize", message: "none" } }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify(
            worldChatFixture({
              summary: "Tóm tắt mới",
              summary_upto: 4,
              events: [],
            }),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <QueryClientProvider client={client}>
        <MemorySection
          chatId={CHAT}
          summary="Tóm tắt ban đầu"
          summaryUpto={2}
          events={[]}
          onSaveSummary={vi.fn()}
          onSaveEvents={vi.fn()}
        />
      </QueryClientProvider>,
    );

    const btn = screen.getByRole("button", { name: t("stateEditor.memory.summarizeNow") });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(t("chat.errors.nothing_to_summarize")),
    );

    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        t("stateEditor.memory.summarizeSuccess"),
      ),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/summarize",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("continueTurn streams /continue and refreshes messages, detail, and list on done", async () => {
    const { wrapper, spy } = setup();
    const fetchMock = vi.fn().mockResolvedValue(
      sse([
        { type: "speaker_start", message_id: "m2", speaker: "linh", seq: 2 },
        { type: "content", delta: "Linh bước tới." },
        { type: "speaker_end", message_id: "m2", variant_idx: 0, stopped: false },
        { type: "done", message_ids: ["m2"] },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });

    await act(() => result.current.continueTurn("Linh"));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/continue",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ prefill: "Linh" }),
      }),
    );
    expect(result.current.turn).toMatchObject({ status: "done", buffer: "Linh bước tới." });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...chatKeys.all, "list"] });
  });

  it("regenerate streams /messages/{id}/regenerate and refreshes on error after rewind", async () => {
    const { wrapper, spy } = setup();
    const fetchMock = vi.fn().mockResolvedValue(
      sse([
        { type: "speaker_start", message_id: "m1", speaker: "linh", seq: 1 },
        { type: "error", code: "llm_failed" },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });

    await act(() => result.current.regenerate("m1"));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/messages/m1/regenerate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({}),
      }),
    );
    expect(result.current.turn).toMatchObject({ status: "error", errorCode: "llm_failed" });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
  });

  it("useSetActiveVariant updates cached messages and invalidates chat queries", async () => {
    const { client, wrapper, spy } = setup();
    const initial: MessageOut = {
      id: "m1",
      seq: 1,
      speaker: "linh",
      active_variant: 0,
      meta: {},
      created_at: "t",
      variants: [
        { idx: 0, content: "A", created_at: "t" },
        { idx: 1, content: "B", created_at: "t" },
      ],
    };
    const updated: MessageOut = { ...initial, active_variant: 1 };
    client.setQueryData([...chatKeys.messages(CHAT), {}], [initial]);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updated), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useSetActiveVariant(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ messageId: "m1", variantIdx: 1 });
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/messages/m1/active-variant",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ variant_idx: 1 }),
      }),
    );
    expect(client.getQueryData<MessageOut[]>([...chatKeys.messages(CHAT), {}])?.[0]).toEqual(
      updated,
    );
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...chatKeys.all, "list"] });
  });

  it("useEditMessage patches message content and updates cache", async () => {
    const { client, wrapper, spy } = setup();
    const initial: MessageOut = {
      id: "m1",
      seq: 1,
      speaker: "user",
      active_variant: 0,
      meta: {},
      created_at: "t",
      variants: [{ idx: 0, content: "Cũ", created_at: "t" }],
    };
    const updated: MessageOut = {
      ...initial,
      variants: [{ idx: 0, content: "Mới", created_at: "t" }],
    };
    client.setQueryData([...chatKeys.messages(CHAT), {}], [initial]);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updated), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useEditMessage(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ messageId: "m1", content: "Mới" });
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/messages/m1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ content: "Mới" }),
      }),
    );
    expect(
      client.getQueryData<MessageOut[]>([...chatKeys.messages(CHAT), {}])?.[0]?.variants[0]
        ?.content,
    ).toBe("Mới");
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...chatKeys.all, "list"] });
  });

  it("useDeleteMessage and useUndoChat update detail cache and invalidate messages & list", async () => {
    const { client, wrapper, spy } = setup();
    const undoPayload: UndoResult = {
      removed_count: 2,
      chat: worldChatFixture({ time: "18:00" }),
    };
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(undoPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result: delHook } = renderHook(() => useDeleteMessage(CHAT), { wrapper });
    await act(async () => {
      await delHook.current.mutateAsync("m2");
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/chats/c1/messages/m2",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))).toEqual(undoPayload.chat);

    const { result: undoHook } = renderHook(() => useUndoChat(CHAT), { wrapper });
    await act(async () => {
      await undoHook.current.mutateAsync();
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/chats/c1/undo",
      expect.objectContaining({ method: "POST" }),
    );
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.messages(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.detail(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...chatKeys.all, "list"] });
  });

  it("useForkChat posts ForkRequest, caches forked chat, and invalidates chat list", async () => {
    const { client, wrapper, spy } = setup();
    const forked: ChatOut = {
      ...worldChatFixture(),
      id: "c_fork",
      parent_chat_id: CHAT,
      forked_at_seq: 3,
      title: "Nhánh mới",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(forked), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useForkChat(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ message_id: "m3", upto_seq: 3 });
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chats/c1/fork",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ message_id: "m3", upto_seq: 3 }),
      }),
    );
    expect(client.getQueryData<ChatOut>(chatKeys.detail("c_fork"))).toEqual(forked);
    expect(spy).toHaveBeenCalledWith({ queryKey: [...chatKeys.all, "list"] });
  });

  it("useUpdateChat applies optimistic cache update, rolls back on error, and invalidates prompt-preview", async () => {
    const { client, wrapper, spy } = setup();
    const initial = worldChatFixture();
    client.setQueryData(chatKeys.detail(CHAT), initial);

    let rejectRequest!: (reason?: unknown) => void;
    const pendingPromise = new Promise<Response>((_res, rej) => {
      rejectRequest = rej;
    });
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(pendingPromise)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...initial, persona_id: "p2" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUpdateChat(CHAT), { wrapper });
    let failPromise!: Promise<ChatOut>;
    act(() => {
      failPromise = result.current.mutateAsync({ persona_id: "p1" });
    });

    await waitFor(() =>
      expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))?.persona_id).toBe("p1"),
    );
    rejectRequest(new Error("boom"));
    await expect(failPromise).rejects.toThrow("Network request failed");
    expect(client.getQueryData<ChatOut>(chatKeys.detail(CHAT))?.persona_id).toBeNull();

    await act(async () => {
      await result.current.mutateAsync({ persona_id: "p2" });
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.promptPreview(CHAT) });
  });

  it("useUndoChat clears SSE stream store overlay and invalidates derived caches", async () => {
    const { wrapper, spy } = setup();
    useChatStreamStore.setState({
      turns: {
        [CHAT]: {
          ...initialTurnState,
          status: "done",
          buffer: "Bản cũ",
          liveSummary: "Tóm tắt cũ",
        },
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ removed_count: 2, chat: worldChatFixture() }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUndoChat(CHAT), { wrapper });
    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(useChatStreamStore.getState().turns[CHAT]).toBeUndefined();
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.promptPreview(CHAT) });
    expect(spy).toHaveBeenCalledWith({ queryKey: chatKeys.usage(CHAT) });
  });

  it("tracks monotonic errorNonce, clears optimisticUserMessage on finish, and supports partial clearLiveFields", () => {
    useChatStreamStore.getState().begin(CHAT, "Xin chào Linh");
    expect(useChatStreamStore.getState().turns[CHAT]?.optimisticUserMessage).toBe("Xin chào Linh");

    useChatStreamStore.getState().fail(CHAT, "llm_failed");
    expect(useChatStreamStore.getState().turns[CHAT]).toMatchObject({
      status: "error",
      errorCode: "llm_failed",
      optimisticUserMessage: null,
      errorNonce: 1,
    });

    useChatStreamStore.getState().begin(CHAT, "Thử lại");
    useChatStreamStore.getState().apply(CHAT, { type: "error", code: "llm_failed" } as never);
    expect(useChatStreamStore.getState().turns[CHAT]?.errorNonce).toBe(2);

    useChatStreamStore.setState({
      turns: {
        [CHAT]: {
          ...initialTurnState,
          liveState: { time: "22:00" },
          liveBonds: { "a:b": {} },
          liveSummary: "Tóm tắt live",
          archivistEventsAdded: 2,
        },
      },
    });
    useChatStreamStore.getState().clearLiveFields(CHAT, ["liveSummary"]);
    const after = useChatStreamStore.getState().turns[CHAT];
    expect(after?.liveSummary).toBeNull();
    expect(after?.archivistEventsAdded).toBe(0);
    expect(after?.liveState).toEqual({ time: "22:00" });
    expect(after?.liveBonds).toEqual({ "a:b": {} });
  });

  it("merges SSE scene event into cached chat state", async () => {
    const { client, wrapper } = setup();
    client.setQueryData(chatKeys.detail(CHAT), worldChatFixture());
    const mergedScene: SceneState = {
      env: { weather: "gió lạnh" },
      chars: { vy: { mood: "bình tĩnh" } },
      items: ["ô"],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        sse([
          { type: "scene", merged: mergedScene },
          { type: "done", message_ids: [] },
        ]),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTurnStream(CHAT), { wrapper });
    await act(async () => {
      await result.current.send({ text: "Nhìn quanh" });
    });

    const cached = client.getQueryData<ChatOut>(chatKeys.detail(CHAT));
    expect((cached?.state as WorldState | undefined)?.scene).toEqual(mergedScene);
  });
});
