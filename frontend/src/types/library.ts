import type { CardJudgeCriterion, CardJudgeResult } from "./generated/card-judge-result";
import type { Lorebook } from "./generated/lorebook";
import type { Persona } from "./generated/persona";
import type { VietrpCard } from "./generated/vietrp-card";
import type { VietrpWorld } from "./generated/vietrp-world";

export type { CardJudgeCriterion, CardJudgeResult, Lorebook, Persona, VietrpCard, VietrpWorld };

export type Visibility = "private" | "public";
export type TargetType = "character" | "world";

export interface FormatWarning {
  path: string;
  code: string;
  message: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface CharacterSummary {
  id: string;
  name: string;
  tagline: string;
  tags: string[];
  visibility: Visibility;
  avatar_url: string | null;
  needs_age: boolean;
  updated_at: string;
}

export interface CharacterOut extends CharacterSummary {
  data: VietrpCard;
  is_owner: boolean;
  author: string;
  created_at: string;
  warnings: FormatWarning[];
  judge_score?: CardJudgeResult | null;
}

export interface WorldSummary {
  id: string;
  name: string;
  tagline: string;
  tags: string[];
  visibility: Visibility;
  cover_url: string | null;
  needs_age: boolean;
  updated_at: string;
}

export interface WorldOut extends WorldSummary {
  data: VietrpWorld;
  is_owner: boolean;
  author: string;
  created_at: string;
  warnings: FormatWarning[];
  judge_score?: CardJudgeResult | null;
}

export interface PersonaOut {
  id: string;
  data: Persona;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface LorebookSummary {
  id: string;
  name: string;
  entry_count: number;
  visibility: Visibility;
  updated_at: string;
}

export interface LorebookOut extends LorebookSummary {
  data: Lorebook;
  is_owner: boolean;
  author: string;
}

export interface GalleryItem {
  type: TargetType;
  id: string;
  name: string;
  tagline: string;
  tags: string[];
  image_url: string | null;
  author: string;
  is_owner: boolean;
  is_favorite: boolean;
  favorite_count: number;
  updated_at: string;
}

export interface ListParams {
  q?: string;
  tag?: string;
  limit?: number;
}

export interface GalleryParams extends ListParams {
  type?: TargetType;
  sort?: "recent" | "favorites";
}

export type ExportFormat = "vietrp" | "ccv2" | "ccv3";
export type ExportAs = "json" | "png";
export type LorebookExportFormat = "vietrp" | "st";

export type ImportKind = "character" | "world" | "lorebook";

export interface ImportResult {
  kind: ImportKind;
  character?: CharacterOut;
  world?: WorldOut;
  lorebook?: LorebookOut;
  warnings: FormatWarning[];
  needs_age: boolean;
}
