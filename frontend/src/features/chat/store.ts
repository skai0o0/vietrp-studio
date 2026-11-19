import { create } from "zustand";
import type {
  DirectorEvent,
  NoticeEvent,
  PlanEvent,
  SceneState,
  TurnStreamEvent,
  UsageEvent,
  WorldState,
} from "@/types/chat";

export type TurnStatus = "idle" | "streaming" | "done" | "error";

/** Per-speaker streaming buffer tracked across multi-speaker turns. */
export interface SpeakerTurnBuffer {
  messageId: string;
  speaker: string;
  seq: number;
  buffer: string;
  isDraft: boolean;
  director: DirectorEvent | null;
  directorPending: boolean;
  attempt: number;
  /** Writer reasoning ("thinking") of the current attempt. */
  reasoning: string;
  reasoningAttempt: number;
  stopped: boolean;
  done: boolean;
}

/** UI/stream state of one chat's running turn. Server data stays in TanStack Query. */
export interface TurnState {
  status: TurnStatus;
  plan: PlanEvent | null;
  messageId: string | null;
  speaker: string | null;
  /** Visible text of the current speaker (draft or approved content). */
  buffer: string;
  /** True while `buffer` is draft text the Director has not approved yet. */
  isDraft: boolean;
  director: DirectorEvent | null;
  /** True between a draft/rejudge and the Director verdict. */
  directorPending: boolean;
  attempt: number;
  notices: NoticeEvent[];
  usage: UsageEvent[];
  errorCode: string | null;
  /** Optimistic user message rendered while waiting for server persistence. */
  optimisticUserMessage: string | null;
  /** Monotonic per-chat error counter so repeated identical errors still re-surface. */
  errorNonce: number;
  /** Ordered `message_id`s seen during this turn. */
  speakerOrder: string[];
  speakerBuffers: Record<string, SpeakerTurnBuffer>;
  liveScene: SceneState | null;
  liveState: WorldState | null;
  liveBonds: Record<string, unknown> | null;
  liveSummary: string | null;
  archivistEventsAdded: number;
  stateChanged: string[];
  stateConfidence: Record<string, number>;
}

export const initialTurnState: TurnState = {
  status: "idle",
  plan: null,
  messageId: null,
  speaker: null,
  buffer: "",
  isDraft: false,
  director: null,
  directorPending: false,
  attempt: 0,
  notices: [],
  usage: [],
  errorCode: null,
  optimisticUserMessage: null,
  errorNonce: 0,
  speakerOrder: [],
  speakerBuffers: {},
  liveScene: null,
  liveState: null,
  liveBonds: null,
  liveSummary: null,
  archivistEventsAdded: 0,
  stateChanged: [],
  stateConfidence: {},
};

function updateActiveBuffer(
  state: TurnState,
  updater: (entry: SpeakerTurnBuffer) => SpeakerTurnBuffer,
): Record<string, SpeakerTurnBuffer> {
  if (state.messageId === null) return state.speakerBuffers;
  const entry = state.speakerBuffers[state.messageId];
  if (!entry) return state.speakerBuffers;
  return { ...state.speakerBuffers, [state.messageId]: updater(entry) };
}

/** Pure reducer: one SSE event in, next turn state out. */
export function reduceTurn(state: TurnState, event: TurnStreamEvent): TurnState {
  switch (event.type) {
    case "plan":
      return { ...state, plan: event };
    case "speaker_start": {
      const nextOrder = state.speakerOrder.includes(event.message_id)
        ? state.speakerOrder
        : [...state.speakerOrder, event.message_id];
      const nextEntry: SpeakerTurnBuffer = {
        messageId: event.message_id,
        speaker: event.speaker,
        seq: event.seq,
        buffer: "",
        isDraft: false,
        director: null,
        directorPending: false,
        attempt: 0,
        reasoning: "",
        reasoningAttempt: 0,
        stopped: false,
        done: false,
      };
      return {
        ...state,
        messageId: event.message_id,
        speaker: event.speaker,
        buffer: "",
        isDraft: false,
        director: null,
        directorPending: false,
        attempt: 0,
        speakerOrder: nextOrder,
        speakerBuffers: { ...state.speakerBuffers, [event.message_id]: nextEntry },
      };
    }
    case "draft":
      return {
        ...state,
        buffer: state.buffer + event.delta,
        isDraft: true,
        directorPending: true,
        speakerBuffers: updateActiveBuffer(state, (e) => ({
          ...e,
          buffer: e.buffer + event.delta,
          isDraft: true,
          directorPending: true,
        })),
      };
    case "reasoning":
      return {
        ...state,
        speakerBuffers: updateActiveBuffer(state, (e) => ({
          ...e,
          // A Director retry starts a new attempt: its reasoning replaces the old one.
          reasoning: e.reasoningAttempt === event.attempt ? e.reasoning + event.delta : event.delta,
          reasoningAttempt: event.attempt ?? 0,
        })),
      };
    case "content":
      return {
        ...state,
        buffer: state.buffer + event.delta,
        speakerBuffers: updateActiveBuffer(state, (e) => ({
          ...e,
          buffer: e.buffer + event.delta,
        })),
      };
    case "director":
      return {
        ...state,
        director: event,
        directorPending: false,
        isDraft: false,
        speakerBuffers: updateActiveBuffer(state, (e) => ({
          ...e,
          director: event,
          directorPending: false,
          isDraft: false,
        })),
      };
    case "reset_content": {
      const isActive = event.message_id === state.messageId || state.messageId === null;
      const target = state.speakerBuffers[event.message_id];
      return {
        ...state,
        ...(isActive ? { buffer: "", isDraft: false } : {}),
        ...(target
          ? {
              speakerBuffers: {
                ...state.speakerBuffers,
                [event.message_id]: { ...target, buffer: "", isDraft: false },
              },
            }
          : {}),
      };
    }
    case "rejudge":
      return {
        ...state,
        attempt: event.attempt,
        directorPending: true,
        speakerBuffers: updateActiveBuffer(state, (e) => ({
          ...e,
          attempt: event.attempt,
          directorPending: true,
        })),
      };
    case "speaker_end": {
      const target = state.speakerBuffers[event.message_id];
      if (!target) return state;
      return {
        ...state,
        speakerBuffers: {
          ...state.speakerBuffers,
          [event.message_id]: {
            ...target,
            done: true,
            stopped: event.stopped ?? false,
          },
        },
      };
    }
    case "scene":
      return {
        ...state,
        liveScene: (event.merged as SceneState | undefined) ?? state.liveScene,
      };
    case "state":
      return {
        ...state,
        liveState: event.state,
        stateChanged: event.changed ?? [],
        stateConfidence: event.confidence ?? {},
        liveScene: event.state.scene ?? state.liveScene,
      };
    case "bonds":
      return {
        ...state,
        liveBonds: event.bonds,
      };
    case "archivist":
      return {
        ...state,
        liveSummary: event.summary ?? state.liveSummary,
        archivistEventsAdded: event.events_added ?? 0,
      };
    case "notice":
      return { ...state, notices: [...state.notices, event] };
    case "usage":
      return { ...state, usage: [...state.usage, event] };
    case "error":
      return {
        ...state,
        status: "error",
        errorCode: event.code,
        directorPending: false,
        errorNonce: state.errorNonce + 1,
      };
    case "done":
      return {
        ...state,
        status: state.status === "error" ? "error" : "done",
        directorPending: false,
        optimisticUserMessage: null,
      };
    default:
      return state;
  }
}

export type LiveStreamField = "liveState" | "liveScene" | "liveBonds" | "liveSummary";

interface ChatStreamStore {
  turns: Record<string, TurnState>;
  begin: (chatId: string, optimisticUserText?: string | null) => void;
  apply: (chatId: string, event: TurnStreamEvent) => void;
  fail: (chatId: string, code: string) => void;
  finish: (chatId: string) => void;
  clearLiveFields: (chatId: string, fields: LiveStreamField[]) => void;
  clearMemory: (chatId: string) => void;
  clear: (chatId: string) => void;
}

export const useChatStreamStore = create<ChatStreamStore>((set) => ({
  turns: {},
  begin: (chatId, optimisticUserText = null) =>
    set((s) => ({
      turns: {
        ...s.turns,
        [chatId]: {
          ...initialTurnState,
          status: "streaming",
          errorNonce: s.turns[chatId]?.errorNonce ?? 0,
          optimisticUserMessage: optimisticUserText ?? null,
        },
      },
    })),
  apply: (chatId, event) =>
    set((s) => ({
      turns: { ...s.turns, [chatId]: reduceTurn(s.turns[chatId] ?? initialTurnState, event) },
    })),
  fail: (chatId, code) =>
    set((s) => {
      const prev = s.turns[chatId] ?? initialTurnState;
      return {
        turns: {
          ...s.turns,
          [chatId]: {
            ...prev,
            status: "error",
            errorCode: code,
            directorPending: false,
            optimisticUserMessage: null,
            errorNonce: prev.errorNonce + 1,
          },
        },
      };
    }),
  // Stream closed without `done`/`error` (abort): keep the buffer, stop streaming.
  finish: (chatId) =>
    set((s) => {
      const current = s.turns[chatId];
      if (!current || current.status !== "streaming") return s;
      return {
        turns: {
          ...s.turns,
          [chatId]: { ...current, status: "done", optimisticUserMessage: null },
        },
      };
    }),
  clearLiveFields: (chatId, fields) =>
    set((s) => {
      const current = s.turns[chatId];
      if (!current || fields.length === 0) return s;
      const next = { ...current };
      let changed = false;
      for (const field of fields) {
        if (field === "liveState" && (next.liveState !== null || next.stateChanged.length > 0)) {
          next.liveState = null;
          next.stateChanged = [];
          next.stateConfidence = {};
          changed = true;
        } else if (field === "liveScene" && next.liveScene !== null) {
          next.liveScene = null;
          changed = true;
        } else if (field === "liveBonds" && next.liveBonds !== null) {
          next.liveBonds = null;
          changed = true;
        } else if (
          field === "liveSummary" &&
          (next.liveSummary !== null || next.archivistEventsAdded !== 0)
        ) {
          next.liveSummary = null;
          next.archivistEventsAdded = 0;
          changed = true;
        }
      }
      return changed ? { turns: { ...s.turns, [chatId]: next } } : s;
    }),
  clearMemory: (chatId) =>
    set((s) => {
      const current = s.turns[chatId];
      if (!current || (current.liveSummary === null && current.archivistEventsAdded === 0)) {
        return s;
      }
      return {
        turns: {
          ...s.turns,
          [chatId]: { ...current, liveSummary: null, archivistEventsAdded: 0 },
        },
      };
    }),
  clear: (chatId) =>
    set((s) => {
      const rest = { ...s.turns };
      delete rest[chatId];
      return { turns: rest };
    }),
}));
