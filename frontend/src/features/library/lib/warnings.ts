import { t } from "@/i18n";
import type { FormatWarning } from "@/types/library";

function warningText(warning: FormatWarning): string {
  switch (warning.code) {
    case "field_long":
      return t("library.warnings.fieldLong");
    case "imperative_text":
      return t("library.warnings.imperativeText");
    case "age_missing":
      return t("library.warnings.ageMissing");
    default:
      return t("library.warnings.generic");
  }
}

/** Groups server soft warnings by their field path. */
export function groupWarnings(warnings: readonly FormatWarning[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {};
  for (const warning of warnings) {
    const list = grouped[warning.path] ?? [];
    const text = warningText(warning);
    if (!list.includes(text)) list.push(text);
    grouped[warning.path] = list;
  }
  return grouped;
}
