import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { t, type MessageKey } from "@/i18n";
import type { FormatWarning, ImportResult } from "@/types/library";

const WARNING_KEYS: Record<string, MessageKey> = {
  avatar_ignored: "io.import.warningCodes.avatar_ignored",
  lorebook_not_found: "io.import.warningCodes.lorebook_not_found",
  age_missing: "io.import.warningCodes.age_missing",
  field_long: "io.import.warningCodes.field_long",
  imperative_text: "io.import.warningCodes.imperative_text",
};

export function warningLabel(warning: FormatWarning): string {
  return t(WARNING_KEYS[warning.code] ?? "io.import.warningCodes.unknown");
}

/** Where "Mở" leads for an imported item (also the editor link for `needs_age`). */
export function openTarget(result: ImportResult): { to: string; name: string } {
  if (result.kind === "character" && result.character) {
    return { to: `/characters/${result.character.id}`, name: result.character.name };
  }
  if (result.kind === "world" && result.world) {
    return { to: `/worlds/${result.world.id}`, name: result.world.name };
  }
  return {
    to: result.lorebook ? `/library/lorebooks/${result.lorebook.id}` : "/library/lorebooks",
    name: result.lorebook?.name ?? "",
  };
}

interface ImportResultPanelProps {
  result: ImportResult;
  onAnother: () => void;
  onNavigate: () => void;
}

export function ImportResultPanel({ result, onAnother, onNavigate }: ImportResultPanelProps) {
  const target = openTarget(result);
  const showAgeCallout = result.needs_age && result.kind === "character";
  return (
    <div className="flex flex-col gap-4">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <CheckCircle2 className="size-4 text-accent" aria-hidden />
        <span className="font-medium">{t("io.import.resultTitle")}</span>
        <span className="rounded-sm border border-border px-2 py-0.5 text-xs text-muted">
          {t(`io.import.kind.${result.kind}`)}
        </span>
        <span className="truncate">{target.name}</span>
      </p>

      {showAgeCallout ? (
        <div role="alert" className="rounded-md border border-danger p-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-danger">
            <AlertTriangle className="size-4" aria-hidden />
            {t("io.import.needsAgeTitle")}
          </p>
          <p className="mt-1 text-muted">{t("io.import.needsAgeBody")}</p>
          <Button asChild size="sm" className="mt-3">
            <Link to={target.to} onClick={onNavigate}>
              {t("io.import.needsAgeLink")}
            </Link>
          </Button>
        </div>
      ) : null}

      {result.warnings.length > 0 ? (
        <div className="text-sm">
          <p className="mb-1 font-medium">{t("io.import.warnings")}</p>
          <ul className="list-disc space-y-1 pl-5 text-muted">
            {result.warnings.map((warning, index) => (
              <li key={`${warning.code}-${warning.path}-${index}`}>{warningLabel(warning)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={onAnother}>
          {t("io.import.another")}
        </Button>
        <Button asChild>
          <Link to={target.to} onClick={onNavigate}>
            {t("io.import.openItem")}
          </Link>
        </Button>
      </div>
    </div>
  );
}
