import type { ActiveVariantRequest } from "./generated/chat-active-variant-request";
import type { ContinueRequest } from "./generated/chat-continue-request";
import type { ChatCreate } from "./generated/chat-create";
import type { ForkRequest } from "./generated/chat-fork-request";
import type { MessageUpdate } from "./generated/chat-message-update";
import type { MessageOut, MessageVariantOut, DirectorVerdict } from "./generated/chat-message";
import type { CastMemberSummary, ChatOut } from "./generated/chat-out";
import type { PromptLayer, PromptPreview } from "./generated/chat-prompt-preview";
import type { RegenerateRequest } from "./generated/chat-regenerate-request";
import type { ChatSettings } from "./generated/chat-settings";
import type { ChatSummary } from "./generated/chat-summary";
import type { TurnRequest } from "./generated/chat-turn-request";
import type { UndoResult } from "./generated/chat-undo-result";
import type { ChatUpdate } from "./generated/chat-update";
import type { PresetIn } from "./generated/presets-in";
import type { PresetOut } from "./generated/presets-out";
import type { StatePatch } from "./generated/state-patch";
import type { CharacterSceneState, SceneState, WorldState } from "./generated/world-state";
import type {
  ArchivistEvent,
  BondsEvent,
  ContentEvent,
  DirectorEvent,
  DoneEvent,
  DraftEvent,
  ErrorEvent,
  NoticeEvent,
  PingEvent,
  PlanEvent,
  PlanSpeaker,
  RejudgeEvent,
  ResetContentEvent,
  SceneEvent,
  SpeakerEndEvent,
  SpeakerStartEvent,
  StateEvent,
  UsageEvent,
} from "./generated/events";

export type {
  ActiveVariantRequest,
  ArchivistEvent,
  BondsEvent,
  CastMemberSummary,
  CharacterSceneState,
  ChatCreate,
  ChatOut,
  ChatSettings,
  ChatSummary,
  ChatUpdate,
  ContinueRequest,
  DirectorEvent,
  DirectorVerdict,
  ForkRequest,
  MessageOut,
  MessageUpdate,
  MessageVariantOut,
  NoticeEvent,
  PlanEvent,
  PlanSpeaker,
  PresetIn,
  PresetOut,
  PromptLayer,
  PromptPreview,
  RegenerateRequest,
  SceneEvent,
  SceneState,
  SpeakerEndEvent,
  SpeakerStartEvent,
  StateEvent,
  StatePatch,
  TurnRequest,
  UndoResult,
  UsageEvent,
  WorldState,
};

/** Union of the individual generated event interfaces (the schema root is a wrapper doc). */
export type TurnStreamEvent =
  | PlanEvent
  | SpeakerStartEvent
  | DraftEvent
  | DirectorEvent
  | ContentEvent
  | ResetContentEvent
  | RejudgeEvent
  | SceneEvent
  | SpeakerEndEvent
  | StateEvent
  | ArchivistEvent
  | BondsEvent
  | NoticeEvent
  | UsageEvent
  | PingEvent
  | DoneEvent
  | ErrorEvent;

export type AgentId = PresetIn["agent"];

export interface ChatListParams {
  limit?: number;
  offset?: number;
}

export interface MessagesParams {
  before?: number;
  limit?: number;
  include?: "drafts";
}

/** `GET /api/models` row (WP-O utility route; shape hand-written until it is exported). */
export interface ModelInfo {
  id: string;
  name: string;
  context_length: number | null;
}

export interface TokenCount {
  tokens: number;
}

export interface UsageRow {
  agent: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  cost: number;
  created_at: string;
}

export interface StopResult {
  stopped: boolean;
}
