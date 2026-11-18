import type { Lorebook } from "@/types/library";

// Defaults mirror backend/app/formats/lorebook.py (scan_depth, token_budget).
export const DEFAULT_SCAN_DEPTH = 50;
export const DEFAULT_TOKEN_BUDGET = 500;

export interface EntryDraft {
  id: string;
  title: string;
  keys: string[];
  secondary_keys: string[];
  selective: boolean;
  constant: boolean;
  priority: number;
  position: "before_char" | "after_char";
  select_mode: "keyword" | "ai" | "both";
  content: string;
  enabled: boolean;
}

export interface LorebookDraft {
  name: string;
  description: string;
  scan_depth: number | null;
  token_budget: number | null;
  entries: EntryDraft[];
}

export function emptyLorebookDraft(): LorebookDraft {
  return {
    name: "",
    description: "",
    scan_depth: DEFAULT_SCAN_DEPTH,
    token_budget: DEFAULT_TOKEN_BUDGET,
    entries: [],
  };
}

export function lorebookToDraft(book: Lorebook): LorebookDraft {
  return {
    name: book.name,
    description: book.description ?? "",
    scan_depth: book.scan_depth ?? DEFAULT_SCAN_DEPTH,
    token_budget: book.token_budget ?? DEFAULT_TOKEN_BUDGET,
    entries: (book.entries ?? []).map((e) => ({
      id: e.id,
      title: e.title ?? "",
      keys: [...(e.keys ?? [])],
      secondary_keys: [...(e.secondary_keys ?? [])],
      selective: e.selective ?? false,
      constant: e.constant ?? false,
      priority: e.priority ?? 0,
      position: e.position ?? "before_char",
      select_mode: e.select_mode ?? "keyword",
      content: e.content ?? "",
      enabled: e.enabled ?? true,
    })),
  };
}

export function draftToLorebook(draft: LorebookDraft): Lorebook {
  return {
    format: "vietrp-lorebook",
    spec_version: "1.0",
    name: draft.name,
    description: draft.description,
    scan_depth: draft.scan_depth ?? DEFAULT_SCAN_DEPTH,
    token_budget: draft.token_budget ?? DEFAULT_TOKEN_BUDGET,
    entries: draft.entries,
  };
}
