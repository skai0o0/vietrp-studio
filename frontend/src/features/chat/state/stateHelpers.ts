import { t } from "@/i18n";
import type { TurnState } from "../store";
import type {
  CastMemberSummary,
  CharacterSceneState,
  SceneState,
  StatePatch,
  WorldState,
} from "@/types/chat";

export const TENSION_LEVELS = [0, 1, 2, 3, 4] as const;
export const CLOSENESS_LEVELS = [0, 1, 2, 3, 4] as const;
export const BOND_FIELD_NAMES = [
  "addressing",
  "nickname",
  "relationship",
  "stance",
  "closeness",
  "history",
] as const;

export type BondFieldName = (typeof BOND_FIELD_NAMES)[number];

export interface BondFieldsValue {
  addressing: string;
  nickname: string;
  relationship: string;
  stance: string;
  closeness: number;
  history: string;
}

export interface BondChangeRecord {
  seq: number;
  field: string;
  old: string;
  new: string;
}

export interface NormalizedBondRecord {
  pair_id: string;
  label: string;
  fields: BondFieldsValue;
  pinned: string[];
  manual: string[];
  changes: BondChangeRecord[];
}

export interface StructuredDraft {
  location_id: string;
  time: string;
  tension: number;
  present_ids: string[];
  awaiting_reply: string[];
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function asRecord(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

function clampInt(v: unknown, min: number, max: number, fallback = 0): number {
  if (typeof v !== "number" || Number.isNaN(v)) return fallback;
  return Math.min(max, Math.max(min, Math.round(v)));
}

export function normalizeSceneState(raw: unknown): Required<SceneState> {
  const obj = asRecord(raw);
  const rawEnv = asRecord(obj.env);
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(rawEnv)) {
    if (typeof v === "string") env[k] = v;
  }
  const rawChars = asRecord(obj.chars);
  const chars: Record<string, CharacterSceneState> = {};
  for (const [id, entry] of Object.entries(rawChars)) {
    const c = asRecord(entry);
    chars[id] = {
      mood: asString(c.mood),
      outfit: asString(c.outfit),
      pose: asString(c.pose),
      holding: asString(c.holding),
      condition: asString(c.condition),
    };
  }
  return {
    env,
    chars,
    items: asStringArray(obj.items),
  };
}

export function normalizeWorldState(raw: Record<string, unknown>): WorldState {
  const rawSilence = asRecord(raw.silence);
  const silence: Record<string, number> = {};
  for (const [k, v] of Object.entries(rawSilence)) {
    if (typeof v === "number" && !Number.isNaN(v)) silence[k] = v;
  }
  return {
    location_id: asString(raw.location_id),
    time: asString(raw.time),
    tension: clampInt(raw.tension, 0, 4, 0),
    present_ids: asStringArray(raw.present_ids),
    awaiting_reply: asStringArray(raw.awaiting_reply),
    silence,
    scene: normalizeSceneState(raw.scene),
    bonds: asRecord(raw.bonds),
    npcs: Array.isArray(raw.npcs) ? (raw.npcs as WorldState["npcs"]) : [],
    summary: asString(raw.summary),
    summary_upto: typeof raw.summary_upto === "number" ? raw.summary_upto : 0,
    events: Array.isArray(raw.events) ? (raw.events as WorldState["events"]) : [],
    manual: asStringArray(raw.manual),
  };
}

/** Overlays in-flight SSE state/scene/bonds onto persisted `chat.state`. */
export function mergeLiveWorldState(
  baseState: Record<string, unknown>,
  turn?: TurnState,
): WorldState {
  const base = normalizeWorldState(baseState);
  const live = turn?.liveState
    ? normalizeWorldState(turn.liveState as Record<string, unknown>)
    : null;
  const merged: WorldState = live ? { ...base, ...live } : { ...base };
  if (turn?.liveScene) {
    merged.scene = normalizeSceneState(turn.liveScene);
  }
  if (turn?.liveBonds) {
    merged.bonds = turn.liveBonds;
  }
  return merged;
}

function resolveParticipantName(id: string, cast: readonly CastMemberSummary[]): string {
  if (id === "user") return t("chat.message.you");
  const found = cast.find((m) => m.id === id || m.character_id === id);
  return found?.name ?? id;
}

export function normalizeBondRecord(
  pairId: string,
  rawValue: unknown,
  cast: readonly CastMemberSummary[],
): NormalizedBondRecord {
  const raw = asRecord(rawValue);
  const rawFields = "fields" in raw ? asRecord(raw.fields) : raw;
  const [leftId, rightId] = pairId.split(":");
  const fallbackLabel =
    leftId && rightId
      ? `${resolveParticipantName(leftId, cast)} ↔ ${resolveParticipantName(rightId, cast)}`
      : pairId;

  const rawChanges = Array.isArray(raw.changes) ? raw.changes : [];
  const changes: BondChangeRecord[] = rawChanges
    .map((c) => asRecord(c))
    .filter((c) => typeof c.field === "string")
    .map((c) => ({
      seq: typeof c.seq === "number" ? c.seq : 0,
      field: asString(c.field),
      old: asString(c.old),
      new: asString(c.new),
    }));

  return {
    pair_id: asString(raw.pair_id, pairId),
    label: asString(raw.label) || fallbackLabel,
    fields: {
      addressing: asString(rawFields.addressing),
      nickname: asString(rawFields.nickname),
      relationship: asString(rawFields.relationship),
      stance: asString(rawFields.stance),
      closeness: clampInt(rawFields.closeness, 0, 4, 0),
      history: asString(rawFields.history),
    },
    pinned: asStringArray(raw.pinned),
    manual: asStringArray(raw.manual),
    changes,
  };
}

export function buildBondPayload(
  record: NormalizedBondRecord,
  edited: BondFieldsValue,
): NormalizedBondRecord {
  const pinnedSet = new Set(record.pinned);
  const manualSet = new Set(record.manual);
  const nextFields: BondFieldsValue = { ...record.fields };

  for (const field of BOND_FIELD_NAMES) {
    if (pinnedSet.has(field)) continue;
    if (field === "closeness") {
      if (edited.closeness !== record.fields.closeness) manualSet.add(field);
      nextFields.closeness = edited.closeness;
    } else {
      if (edited[field] !== record.fields[field]) manualSet.add(field);
      nextFields[field] = edited[field];
    }
  }

  return {
    pair_id: record.pair_id,
    label: record.label,
    fields: nextFields,
    pinned: record.pinned,
    manual: BOND_FIELD_NAMES.filter((f) => manualSet.has(f)),
    changes: record.changes,
  };
}

function sameStringArray(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((item, i) => item === b[i]);
}

/** Sends ONLY modified structured keys so untouched keys are not marked `manual` on the server. */
export function diffStructuredPatch(
  original: StructuredDraft,
  draft: StructuredDraft,
): StatePatch | null {
  const patch: StatePatch = {};
  let changed = false;
  if (draft.location_id !== original.location_id) {
    patch.location_id = draft.location_id;
    changed = true;
  }
  if (draft.time !== original.time) {
    patch.time = draft.time;
    changed = true;
  }
  if (draft.tension !== original.tension) {
    patch.tension = draft.tension;
    changed = true;
  }
  if (!sameStringArray(draft.present_ids, original.present_ids)) {
    patch.present_ids = [...draft.present_ids];
    changed = true;
  }
  if (!sameStringArray(draft.awaiting_reply, original.awaiting_reply)) {
    patch.awaiting_reply = [...draft.awaiting_reply];
    changed = true;
  }
  return changed ? patch : null;
}
