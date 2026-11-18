import type { VietrpWorld } from "@/types/library";
import type { Loc } from "./treeOps";

export interface OpeningDraft {
  id: string;
  title: string;
  message: string;
  time: string;
  location_id: string;
  present_ids: string[];
  tension: number;
  player_role: string;
}

export interface WorldDraft {
  name: string;
  rules: string;
  tags: string[];
  lorebook_ids: string[];
  locations: Loc[];
  openings: OpeningDraft[];
}

export function emptyWorldDraft(): WorldDraft {
  return { name: "", rules: "", tags: [], lorebook_ids: [], locations: [], openings: [] };
}

export function worldToDraft(world: VietrpWorld): WorldDraft {
  return {
    name: world.name,
    rules: world.rules ?? "",
    tags: [...(world.tags ?? [])],
    lorebook_ids: [...(world.lorebook_ids ?? [])],
    locations: (world.locations ?? []).map((l) => ({
      id: l.id,
      parent_id: l.parent_id ?? null,
      level: l.level,
      name: l.name,
      description: l.description ?? "",
    })),
    openings: (world.openings ?? []).map((o) => ({
      id: o.id,
      title: o.title ?? "",
      message: o.message ?? "",
      time: o.time ?? "",
      location_id: o.location_id,
      present_ids: [...(o.present_ids ?? [])],
      tension: o.tension ?? 0,
      player_role: o.player_role ?? "",
    })),
  };
}

export function draftToWorld(draft: WorldDraft): VietrpWorld {
  return {
    format: "vietrp-world",
    spec_version: "1.0",
    ...draft,
    // The generated type caps tags with a long tuple union; the server enforces the limit.
    tags: draft.tags as VietrpWorld["tags"],
  };
}
