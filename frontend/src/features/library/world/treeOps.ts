import type { Location } from "@/types/generated/vietrp-world";
import { uniqueSlug } from "../lib/arrays";

export type Level = Location["level"];
export type Loc = Location;

/** Highest level first; mirrors `LEVEL_ORDER` in backend/app/formats/world.py. */
export const LEVELS: readonly Level[] = [
  "galaxy",
  "star_system",
  "planet",
  "country",
  "province",
  "district",
  "area",
  "place",
];

export function levelRank(level: Level): number {
  return LEVELS.indexOf(level);
}

export function parentOf(locations: readonly Loc[], id: string): Loc | undefined {
  const node = locations.find((l) => l.id === id);
  return node?.parent_id ? locations.find((l) => l.id === node.parent_id) : undefined;
}

export function childrenOf(locations: readonly Loc[], parentId: string | null): Loc[] {
  return locations.filter((l) => (l.parent_id ?? null) === parentId);
}

/** IDs of `id` and everything below it. */
export function subtreeIds(locations: readonly Loc[], id: string): Set<string> {
  const ids = new Set<string>([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const loc of locations) {
      if (loc.parent_id && ids.has(loc.parent_id) && !ids.has(loc.id)) {
        ids.add(loc.id);
        grew = true;
      }
    }
  }
  return ids;
}

export interface TreeRow {
  loc: Loc;
  depth: number;
}

/** Depth-first rows, siblings in array order. Orphans (unknown parent) are shown as roots. */
export function flattenTree(locations: readonly Loc[]): TreeRow[] {
  const known = new Set(locations.map((l) => l.id));
  const rows: TreeRow[] = [];
  const visit = (loc: Loc, depth: number): void => {
    rows.push({ loc, depth });
    for (const child of childrenOf(locations, loc.id)) visit(child, depth + 1);
  };
  for (const loc of locations) {
    if (!loc.parent_id || !known.has(loc.parent_id)) visit(loc, 0);
  }
  return rows;
}

/** Levels deeper than the parent (all levels for a root). */
export function levelsBelow(parentLevel: Level | null): Level[] {
  return parentLevel === null ? [...LEVELS] : LEVELS.slice(levelRank(parentLevel) + 1);
}

/** Levels a node may take: deeper than its parent and shallower than all its children. */
export function allowedLevels(locations: readonly Loc[], id: string): Level[] {
  const parent = parentOf(locations, id);
  const kids = childrenOf(locations, id);
  const min = parent ? levelRank(parent.level) : -1;
  const max = kids.length ? Math.min(...kids.map((k) => levelRank(k.level))) : LEVELS.length;
  return LEVELS.filter((_, rank) => rank > min && rank < max);
}

export function addRoot(
  locations: readonly Loc[],
  level: Level,
  name: string,
): { locations: Loc[]; id: string } {
  const id = uniqueSlug(
    "loc",
    locations.map((l) => l.id),
  );
  return { locations: [...locations, { id, parent_id: null, level, name, description: "" }], id };
}

/** Adds a child one level below the parent; returns null if the parent is already the deepest level. */
export function addChild(
  locations: readonly Loc[],
  parentId: string,
  name: string,
): { locations: Loc[]; id: string } | null {
  const parent = locations.find((l) => l.id === parentId);
  const level = parent ? levelsBelow(parent.level)[0] : undefined;
  if (!parent || !level) return null;
  const id = uniqueSlug(
    "loc",
    locations.map((l) => l.id),
  );
  return {
    locations: [...locations, { id, parent_id: parentId, level, name, description: "" }],
    id,
  };
}

/** Adds a node under the same parent, inserted right after the sibling's subtree. */
export function addSibling(
  locations: readonly Loc[],
  siblingId: string,
  name: string,
): { locations: Loc[]; id: string } | null {
  const sibling = locations.find((l) => l.id === siblingId);
  if (!sibling) return null;
  const id = uniqueSlug(
    "loc",
    locations.map((l) => l.id),
  );
  const created: Loc = {
    id,
    parent_id: sibling.parent_id ?? null,
    level: sibling.level,
    name,
    description: "",
  };
  const ids = subtreeIds(locations, siblingId);
  let lastIndex = locations.findIndex((l) => l.id === siblingId);
  locations.forEach((l, i) => {
    if (ids.has(l.id)) lastIndex = Math.max(lastIndex, i);
  });
  const next = [...locations];
  next.splice(lastIndex + 1, 0, created);
  return { locations: next, id };
}

export function updateLocation(locations: readonly Loc[], id: string, patch: Partial<Loc>): Loc[] {
  return locations.map((l) => (l.id === id ? { ...l, ...patch } : l));
}

export function deleteSubtree(
  locations: readonly Loc[],
  id: string,
): { locations: Loc[]; removed: Set<string> } {
  const removed = subtreeIds(locations, id);
  return { locations: locations.filter((l) => !removed.has(l.id)), removed };
}

/** Swaps the node (with its subtree staying attached by parent id) with the previous/next sibling. */
export function moveSibling(locations: readonly Loc[], id: string, delta: -1 | 1): Loc[] {
  const node = locations.find((l) => l.id === id);
  if (!node) return [...locations];
  const siblings = childrenOf(locations, node.parent_id ?? null);
  const at = siblings.findIndex((l) => l.id === id);
  const other = siblings[at + delta];
  if (!other) return [...locations];
  const a = locations.findIndex((l) => l.id === id);
  const b = locations.findIndex((l) => l.id === other.id);
  const next = [...locations];
  [next[a], next[b]] = [next[b] as Loc, next[a] as Loc];
  return next;
}

export function canMoveSibling(locations: readonly Loc[], id: string, delta: -1 | 1): boolean {
  const node = locations.find((l) => l.id === id);
  if (!node) return false;
  const siblings = childrenOf(locations, node.parent_id ?? null);
  const at = siblings.findIndex((l) => l.id === id);
  return siblings[at + delta] !== undefined;
}

/** Valid new parents for `id`: not itself/descendants, and shallower than the node's level. `null` = root. */
export function parentChoices(locations: readonly Loc[], id: string): (Loc | null)[] {
  const node = locations.find((l) => l.id === id);
  if (!node) return [];
  const below = subtreeIds(locations, id);
  const rank = levelRank(node.level);
  const parents = locations.filter((l) => !below.has(l.id) && levelRank(l.level) < rank);
  return [null, ...parents];
}

export function canReparent(
  locations: readonly Loc[],
  id: string,
  newParentId: string | null,
): boolean {
  return parentChoices(locations, id).some((p) => (p?.id ?? null) === newParentId);
}

/** Moves the node (and its subtree) under a new parent, as the last child. No-op if not allowed. */
export function reparent(locations: readonly Loc[], id: string, newParentId: string | null): Loc[] {
  if (!canReparent(locations, id, newParentId)) return [...locations];
  const node = locations.find((l) => l.id === id) as Loc;
  const ids = subtreeIds(locations, id);
  const moved = locations
    .filter((l) => ids.has(l.id))
    .map((l) => (l.id === id ? { ...node, parent_id: newParentId } : l));
  const rest = locations.filter((l) => !ids.has(l.id));
  return [...rest, ...moved];
}

/** Path label such as `Trái Đất › Việt Nam › TP.HCM`. */
export function pathLabel(locations: readonly Loc[], id: string): string {
  const names: string[] = [];
  let current = locations.find((l) => l.id === id);
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    names.unshift(current.name || current.id);
    const parentId: string | null | undefined = current.parent_id;
    current = parentId ? locations.find((l) => l.id === parentId) : undefined;
  }
  return names.join(" › ");
}
