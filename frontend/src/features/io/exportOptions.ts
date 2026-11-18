import type { MessageKey } from "@/i18n";
import type { ExportAs, ExportFormat, LorebookExportFormat } from "@/types/library";

export type ExportKind = "character" | "world" | "lorebook";

export type ExportFormatId =
  | "vietrp-json"
  | "ccv2-json"
  | "ccv2-png"
  | "ccv3-json"
  | "ccv3-png"
  | "lorebook-vietrp"
  | "lorebook-st";

export interface ExportOption {
  id: ExportFormatId;
  labelKey: MessageKey;
  format: ExportFormat | LorebookExportFormat;
  as: ExportAs;
}

const OPTIONS: Record<ExportFormatId, ExportOption> = {
  "vietrp-json": {
    id: "vietrp-json",
    labelKey: "io.export.vietrpJson",
    format: "vietrp",
    as: "json",
  },
  "ccv2-json": { id: "ccv2-json", labelKey: "io.export.ccv2Json", format: "ccv2", as: "json" },
  "ccv2-png": { id: "ccv2-png", labelKey: "io.export.ccv2Png", format: "ccv2", as: "png" },
  "ccv3-json": { id: "ccv3-json", labelKey: "io.export.ccv3Json", format: "ccv3", as: "json" },
  "ccv3-png": { id: "ccv3-png", labelKey: "io.export.ccv3Png", format: "ccv3", as: "png" },
  "lorebook-vietrp": {
    id: "lorebook-vietrp",
    labelKey: "io.export.vietrpJson",
    format: "vietrp",
    as: "json",
  },
  "lorebook-st": { id: "lorebook-st", labelKey: "io.export.lorebookSt", format: "st", as: "json" },
};

/** Every format the backend supports for each kind (WP-I contract). */
export const DEFAULT_FORMATS: Record<ExportKind, readonly ExportFormatId[]> = {
  character: ["vietrp-json", "ccv2-json", "ccv2-png", "ccv3-json", "ccv3-png"],
  world: ["vietrp-json"],
  lorebook: ["lorebook-vietrp", "lorebook-st"],
};

export function resolveOptions(
  kind: ExportKind,
  formats?: readonly ExportFormatId[],
): ExportOption[] {
  const allowed = DEFAULT_FORMATS[kind];
  const wanted = formats ?? allowed;
  return wanted.filter((f) => allowed.includes(f)).map((f) => OPTIONS[f]);
}
